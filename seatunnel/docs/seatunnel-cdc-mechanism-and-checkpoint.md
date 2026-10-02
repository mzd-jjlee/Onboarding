# SeaTunnel의 PostgreSQL CDC 처리 메커니즘과 체크포인트

작성일: 2026-09-30. 이번 실습(`jobs/15_postgres_10m_cdc_insert_update.conf`)을 기준으로, SeaTunnel을 실무에서
쓰려는 엔지니어가 알아두면 좋은 내부 동작을 정리한다. 공식 문서와 이번 실습 중 직접 확인한 로그를 근거로 했고,
직접 검증하지 않은 부분은 별도로 표시한다.

## 1. 왜 이 문서가 필요한가

CDC(Change Data Capture)는 "DB 변경을 실시간으로 받아온다"는 개념만 알아서는 실무에서 막힌다. 실제로는
"이 잡이 중간에 죽으면 어떻게 되는가", "커밋이라는 게 정확히 뭘 하는 건가", "왜 읽은 행 수랑 저장된 행 수가
다른가" 같은 질문에 답할 수 있어야 운영이 가능하다. 이 문서는 그 질문들에 답한다.

## 2. 전체 흐름: WAL부터 Parquet까지

```text
PostgreSQL 데이터 변경 → WAL 기록
              ↓
PostgreSQL 논리 디코딩 (pgoutput 플러그인)
              ↓  (복제 슬롯이 진행 위치·필요한 WAL 보존 관리)
복제 연결을 통한 스트림 전달
              ↓
SeaTunnel Postgres-CDC Source가 스트림 수신
              ↓
RowKindExtractor: 변경 종류를 cdc_op 컬럼으로 추출
              ↓
SQL Transform: 필요한 종류만 필터링
              ↓
LocalFile Sink: Parquet 기록 → 체크포인트마다 파일 커밋
```

### 2.1 WAL 기록

PostgreSQL은 INSERT/UPDATE/DELETE가 일어나면 이를 WAL(Write-Ahead Log)에 기록한다. WAL은 원래 DB 자체의
장애 복구용 내부 기록이라, "어느 행이 이렇게 바뀌었다"를 사람이 바로 읽을 수 있는 형태가 아니다.

### 2.2 논리 디코딩(Logical Decoding)과 pgoutput

논리 디코딩은 PostgreSQL이 WAL을 해석해서 "어느 테이블의 어느 행이 INSERT/UPDATE/DELETE로 바뀌었다"는,
읽을 수 있는 변경 메시지로 바꿔주는 과정이다. 이 해석을 실제로 수행하는 것이 `pgoutput` 같은 플러그인이고,
**이 작업은 SeaTunnel이 아니라 PostgreSQL 서버 안에서 일어난다.** SeaTunnel 쪽 커넥터 코드는 그 플러그인이
출력하는 형식을 이해해서 읽어올 뿐이다.

- `decoding.plugin.name = "pgoutput"`: PostgreSQL이 변경 메시지를 만들 때 쓸 플러그인 이름을 지정하는 설정.
  PostgreSQL 10부터 내장된 플러그인이라 별도 설치가 필요 없다.

### 2.3 복제 슬롯(Replication Slot)

슬롯은 이벤트를 담아두는 저장소가 아니다. PostgreSQL 서버 안에 있는, **"이 소비자(이번 CDC 잡)에게 어디까지
전달했는지 기억하는 북마크 + 그 지점까지 필요한 WAL을 지우지 않고 보존해주는 보증"**이다. 같은 PostgreSQL을
읽는 CDC 잡이 여러 개면, 서로 다른 슬롯 이름을 써서 각자 자기 진행 위치를 따로 관리한다.

- `slot.name = "seatunnel_cdc_10m_iu_test"`: 이번 잡이 사용할 슬롯의 이름. 슬롯 자체와 그 진행 위치는
  PostgreSQL이 관리하며, SeaTunnel은 이 이름을 지정해서 참조할 뿐이다.

`decoding.plugin.name`과 `slot.name` 둘 다 **PostgreSQL 쪽이 관리하는 값**이라는 점이 중요하다. SeaTunnel이
직접 소유하거나 계산하는 값이 아니다.

### 2.4 스트림(Stream)

이렇게 만들어진 변경 메시지가 복제 연결(replication connection)을 통해 끊기지 않고 계속 흘러들어오는 것
자체를 스트림이라고 한다. 한 번에 다 뽑아오는 배치성 조회가 아니라, DB에 변경이 생길 때마다 그때그때 이어서
전달되는 흐름이다. 이번 잡의 `job.mode`가 `STREAMING`인 이유가 이것이다.

### 2.5 RowKindExtractor와 SQL Transform

- **RowKindExtractor**: 커넥터가 이미 감지한 변경 종류(`INSERT`, `UPDATE_BEFORE`, `UPDATE_AFTER`, `DELETE`)를
  `cdc_op`라는 새 컬럼으로 뽑아낸다. `transform_type = "FULL"`이면 `INSERT`처럼 풀네임으로, `SHORT`면
  `+I` 같은 기호로 표기된다. ([공식 문서](https://seatunnel.apache.org/docs/2.3.13/transforms/rowkind-extractor/))
- **SQL Transform**: `cdc_op IN ('INSERT', 'UPDATE_AFTER')`처럼, 추출된 컬럼을 기준으로 필요한 행만
  통과시킨다. 이번 실습에서는 신규 행과 수정 후 행만 남기고, 수정 전 행(`UPDATE_BEFORE`)과 삭제(`DELETE`)는
  걸러냈다 — 이는 SeaTunnel이 DELETE를 지원하지 못해서가 아니라, **이 SQL 필터를 그렇게 설정했기 때문**이다.

### 2.6 LocalFile Sink

필터를 통과한 행을 Parquet으로 인코딩해서 기록한다. 처음부터 최종 경로에 쓰는 것이 아니라, `tmp_path`로
지정한 임시 경로(예: `/output/.seatunnel-staging`)에 먼저 쓴다.

## 3. 체크포인트: "커밋"이 실제로 하는 일

`checkpoint.interval = 3000`은 "3초마다 이벤트를 받는다"는 뜻이 아니다. **이벤트 수신·처리(WAL 스트림 읽기
→ RowKindExtractor → SQL 필터 → Parquet 인코딩)는 이벤트가 도착하는 대로 계속 일어난다.** 체크포인트는 그렇게
계속 처리되고 있는 내용을 약 3초 주기로 한 번씩 "확정(commit)"하는 절차다.

체크포인트가 완료될 때 동시에 일어나는 일:

1. **Source 쪽 — 위치 확정**: 여기까지는 확실히 처리했다는 WAL 위치(LSN)를 SeaTunnel(Zeta 엔진)이 자신의
   체크포인트 상태로 기록하고, 동시에 PostgreSQL에도 알려서 **복제 슬롯의 확인된 위치를 그만큼 전진**시킨다.
2. **Sink 쪽 — 파일 확정**: 그동안 임시 경로에 쓰고 있던 Parquet 파일을 `path`로 지정한 **최종 경로로
   rename**한다. 이 rename은 데이터를 합치거나 다시 쓰는 과정이 아니라, 이미 다 쓴 파일을 최종 위치로
   원자적으로 옮기는 것뿐이다. bind mount로 호스트 폴더를 연결해뒀다면, 이 최종 경로가 곧 그 호스트 폴더다.

즉 "이벤트 처리"와 "커밋"은 서로 다른 레이어다. 처리는 강물처럼 계속 흐르고, 체크포인트는 3초마다 "여기까지
온 것은 확실히 도착했다"고 도장을 찍는 것에 가깝다.

## 4. 잡이 중간에 죽으면 어떻게 되는가

같은 `slot.name`으로 SeaTunnel을 다시 실행하면, PostgreSQL의 복제 슬롯이 "이 소비자는 여기까지 받아갔다"는
위치를 그대로 들고 있으므로, 처음부터 다시 훑지 않고 **마지막으로 확인된 지점부터 스트림을 이어받는다.** 그
지점까지의 데이터는 이미 체크포인트를 통해 최종 경로에 Parquet 파일로 남아 있다. 큰 틀에서는 재시작 지점을
수동으로 관리할 필요가 없도록 설계돼 있다.

다만 두 가지는 정확히 알아둬야 한다.

- **완전한 exactly-once 보장은 아니다.** 체크포인트가 완료되기 "직전"에 죽으면, 이미 Sink에는 쓰였지만
  아직 슬롯에는 확인되지 않은 구간이 있을 수 있다. 재시작하면 그 구간이 다시 흘러들어올 수 있고, 결과적으로
  Parquet에 같은 행이 중복으로 남을 가능성이 이론적으로 있다 (at-least-once에 가까운 동작).
- **이번 실습에서 크래시 후 재시작 시나리오를 직접 테스트하지는 않았다.** 슬롯·체크포인트 메커니즘 자체는
  PostgreSQL과 SeaTunnel(Debezium 기반 커넥터)의 공식 동작이지만, "실제로 잡을 중간에 죽이고 재시작해서
  중복 여부를 확인"하는 실험은 이 프로젝트에서 수행하지 않았다. 운영에 적용하기 전에는 이 시나리오를 직접
  검증하는 것을 권장한다.

## 5. Read Count와 Write Count가 다른 이유 (참고)

이번 실습(INSERT 200 · UPDATE 100 · DELETE 50)을 기준으로, CDC Source가 읽은 레코드 수와 Sink에 실제로
쓰기 시도한 레코드 수가 다르게 찍힌다.

| DB 작업 | 행 수 | CDC 레코드(Read Count) | Parquet 저장(Write Count) |
|---|---:|---:|---:|
| INSERT | 200 | 200 (INSERT) | 200 |
| UPDATE | 100 | 200 (UPDATE_BEFORE + UPDATE_AFTER) | 100 (AFTER만) |
| DELETE | 50 | 50 (DELETE) | 0 (저장 안 함) |
| 합계 | 350 | 450 | 300 |

UPDATE 한 번은 DB 입장에서 "행 1개 변경"이지만, CDC는 이를 변경 전/후 두 개의 레코드로 표현하기 때문에
Read Count가 늘어난다. 그중 SQL Transform을 통과한 것(INSERT + UPDATE_AFTER)만 Write Count로 잡힌다.
자세한 근거는 [cdc_seatunnel.md](cdc_seatunnel.md) 참고.

## 6. 엔지니어를 위한 요약

- `decoding.plugin.name`, `slot.name`은 PostgreSQL이 관리하는 값이다 — SeaTunnel은 이름을 지정해 참조할 뿐이다.
- 이벤트 처리는 계속 일어나고, 체크포인트(`checkpoint.interval`)는 그 결과를 주기적으로 확정(WAL 위치 기록 +
  파일 rename)하는 절차다.
- 같은 슬롯 이름으로 재시작하면 마지막 확인 지점부터 이어받는다. 다만 완전 무중복(exactly-once)은 보장되지
  않으므로, 다운스트림에서 중복 제거가 필요한지는 별도로 검토해야 한다.
- DB 변경 수 · CDC 레코드 수 · 최종 저장 행 수는 서로 다른 숫자다. UPDATE는 CDC 레코드 2건(BEFORE/AFTER)을
  만들고, SQL Transform 설정에 따라 그중 일부만 최종 저장된다.
- DELETE가 저장되지 않는 것은 SeaTunnel의 한계가 아니라 이번 SQL 필터(`cdc_op IN ('INSERT','UPDATE_AFTER')`)의
  설정 때문이다.

## 참고 자료

- [Apache SeaTunnel PostgreSQL CDC 커넥터 (2.3.13)](https://seatunnel.apache.org/docs/2.3.13/connectors/source/PostgreSQL-CDC/)
- [Apache SeaTunnel RowKindExtractor (2.3.13)](https://seatunnel.apache.org/docs/2.3.13/transforms/rowkind-extractor/)
- [PostgreSQL 공식 문서 — 논리 디코딩](https://www.postgresql.org/docs/16/logicaldecoding-explanation.html)
- 이 프로젝트 실행 로그: `jobs/15_postgres_10m_cdc_insert_update.conf`, [cdc_seatunnel.md](cdc_seatunnel.md)
