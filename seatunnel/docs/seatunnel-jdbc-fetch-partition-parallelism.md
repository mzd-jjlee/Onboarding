# Config 설명: fetch_size, JDBC 파티셔닝, parallelism

2026-09-18. PostgreSQL JDBC → Parquet 배치 실습의 발표 보조 자료.

## 먼저 구분할 세 가지

| 설정 | 답하는 질문 | 의미 |
|---|---|---|
| `fetch_size` | 한 번에 결과를 얼마나 가져오는가? | 각 JDBC 조회 결과를 가져오는 단위 |
| JDBC 파티셔닝 | 조회 범위를 어떻게 나누는가? | 지정한 컬럼의 범위를 여러 작업 조각으로 분할 |
| `parallelism` | 처리 작업을 얼마나 병렬로 구성하는가? | 실행 병렬도. 실제 동시 실행은 작업 계획과 가용 자원에 좌우됨 |

`LIMIT`은 위 세 설정과 별도로 **쿼리가 반환할 전체 행 수**를 제한한다. `parallelism`은 CPU 코어 수나 RAM 할당량을 지정하는 옵션이 아니다.

## Airflow/Python에서 직접 구현했던 작업과 비교

아래는 마지막 PK를 저장하고 반복 조회하던 작업을 가정한 비교다. 실제 기존 Python 코드의 구현을 검증한 것은 아니다.

| 기존 Airflow/Python의 역할 | SeaTunnel에서 대응하는 개념 |
|---|---|
| `LIMIT 3000` 등으로 이번 쿼리의 행 수 제한 | Source 쿼리의 조회 범위·조건 |
| DB에서 결과를 조금씩 가져오기 | JDBC `fetch_size` |
| PK 범위를 여러 작업으로 나누기 | JDBC 파티셔닝 |
| 여러 작업을 동시에 실행하기 | `parallelism` |
| 마지막 처리 PK를 저장하고 다음 실행에서 재사용 | 현재 실습 config에는 없는 진행 위치 관리 기능 |

### LIMIT 3000과 fetch_size=3000은 다르다

기존 Python 작업이 다음 쿼리를 사용했다면 결과 자체가 최대 3,000행이다.

```sql
SELECT * FROM orders
WHERE id > :last_pk
ORDER BY id
LIMIT 3000;
```

적재 성공 후 마지막 PK를 저장하고, 다음 쿼리에서 그 이후를 읽도록 애플리케이션이 관리한다. PK 기반 방식은 새 PK의 행을 이어 읽는 데 적합하지만, 이미 처리한 PK의 UPDATE나 DELETE를 자동 감지하는 CDC와 같지는 않다.

반면 다음 조회에 `fetch_size=3000`을 적용하면 대상은 여전히 테이블 전체다.

```sql
SELECT * FROM orders;
```

```text
전체를 대상으로 쿼리 실행
  → 최대 3,000행 가져오기 → 처리
  → 다음 최대 3,000행 가져오기 → 처리
  → 결과 끝까지 반복
```

이는 PostgreSQL JDBC가 커서 방식으로 읽는 경우의 개념도다. 전체 행을 먼저 SeaTunnel 메모리에 올린 뒤 나누는 것이 아니며, 매번 LIMIT/OFFSET 쿼리를 새로 실행하는 것도 아니다. 다만 DB 서버 내부의 스캔·정렬 방식까지 fetch size가 정하지는 않는다.

PostgreSQL JDBC에서는 양수 fetch size, autocommit 비활성화, forward-only ResultSet 등의 커서 사용 조건이 필요하다. 다른 DB·드라이버에도 동일한 동작을 무조건 가정하지 않는다. 자세한 조건은 [pgJDBC 공식 문서](https://jdbc.postgresql.org/documentation/query/)를 참고한다.

`batch_size`는 도구와 단계에 따라 의미가 다르다. Python 코드에서는 조회·적재 작업 단위에 붙인 이름일 수 있다. SeaTunnel JDBC Sink에서는 DB에 일괄 쓰기할 행의 단위이며, JDBC Source의 `fetch_size`와 별개다. 현재 Parquet Sink에 JDBC Sink의 `batch_size`를 그대로 적용하지 않는다.

## 파티셔닝과 fetch size는 함께 적용된다

설명용으로 PK가 1부터 2억까지 분포하고 조회 범위를 네 조각으로 나눈다고 가정하면 다음과 같다. 실제 경계 SQL과 분할 결과는 커넥터 구현 및 데이터 분포에 따른다.

```text
조회 범위 전체
 ├─ 범위 A → fetch_size 단위로 가져오기 → 처리
 ├─ 범위 B → fetch_size 단위로 가져오기 → 처리
 ├─ 범위 C → fetch_size 단위로 가져오기 → 처리
 └─ 범위 D → fetch_size 단위로 가져오기 → 처리
```

각 범위가 수천만 행이더라도 그 범위를 한 번에 메모리에 올리는 것은 아니다. PK 범위를 나누어도 빈 구간이나 값의 편중이 있으면 조각별 행 수는 같지 않을 수 있다. 파티션 컬럼은 지원되는 적절한 컬럼을 선택하며, 반드시 PK여야 하는 것은 아니다.

다음은 설명용 설정 조각이며 실행용 완성 config는 아니다.

```hocon
env {
  parallelism = 4
  job.mode = "BATCH"
}

# source.Jdbc 안에 지정
partition_column = "order_id"
partition_lower_bound = 1
partition_upper_bound = 200000000
partition_num = 4
fetch_size = 3000
```

- `partition_num=4`: 조회 범위를 네 작업 조각으로 만든다.
- `parallelism=4`: 여러 조각을 병렬 처리할 수 있도록 실행 병렬도를 설정한다.
- `fetch_size=3000`: 각 조회에서 결과를 가져오는 단위다.

`partition_num=4`, `parallelism=1`이면 조각이 여러 개여도 동시 읽기 향상을 기대하기 어렵다. 반대로 파티셔닝 없는 단일 조회에서 `parallelism`만 높인다고 쿼리 범위가 자동으로 여러 개가 된다고 생각하면 안 된다.

## parallelism은 CPU·RAM을 고정 분할하는 옵션이 아니다

Local에서는 하나의 JVM 안에서 여러 작업이 CPU와 힙을 공유한다. `parallelism=4`가 작업별 CPU 1코어나 힙 750MiB를 예약한다는 뜻은 아니다. 스레드 실행은 OS 스케줄링과 엔진 실행 구조에 영향을 받으며, 객체와 버퍼는 공통 힙을 사용한다.

```text
Local JVM / 최대 힙 3GiB
 ├─ 처리 작업 A ─┐
 ├─ 처리 작업 B ─┤
 ├─ 처리 작업 C ─┼─ 하나의 힙을 공유
 └─ 처리 작업 D ─┘
```

Cluster는 여러 JVM에 작업을 배치할 수 있다. 각 JVM은 자신의 힙을 갖지만, 모든 노드에 균등 배치되거나 병렬도만큼 노드가 생기는 것을 보장하지 않는다.

Local/Cluster는 **실행 배치 방식**, Batch/Streaming·CDC는 **작업의 처리 방식**을 구분한다. JDBC 파티셔닝은 Local Batch에도 사용할 수 있다. CDC의 초기 스냅샷 분할과 변경 이벤트 읽기는 커넥터별로 다르므로 JDBC Batch 옵션을 그대로 적용하지 않는다.

## 성능과 메모리에 미치는 영향

| 변경 | 기대할 수 있는 효과 | 고려할 점 |
|---|---|---|
| fetch size 감소 | 읽기 측 버퍼 메모리 감소 가능 | DB 왕복 통신 증가 가능 |
| fetch size 증가 | DB 왕복 통신 감소 가능 | 읽기 측 메모리 증가 가능 |
| 파티셔닝과 병렬도 증가 | 자원에 여유가 있으면 처리 시간 단축 가능 | 동시 조회·큐·Writer·버퍼가 늘어 메모리와 DB 부하 증가 가능 |

파티셔닝은 OOM 해결을 보장하지 않는다. 여러 조회가 동시에 실행되면 각 조회의 버퍼를 함께 고려해야 한다. 또한 fetch size는 전체 파이프라인의 메모리 상한, 파일당 행 수, 커밋 단위, 재시작 지점이 아니다. Parquet Writer가 오래 보유하는 버퍼는 별도로 분석해야 한다. 기존 사례는 [Local 힙·OOM 검증](local-heap-oom-study.md)을 참고한다.

## 현재 1억·2억 행 Local 실습에 적용

작성 시점의 `02_postgres_to_parquet_100m.conf`와 `02_postgres_to_parquet_200m_local.conf`는 모두 병렬도 1, fetch size 5,000이며 JDBC 파티셔닝은 없다. `run-job.sh`가 Local 모드와 초기 힙 1GiB / 최대 힙 3GiB를 적용한다.

현재 config는 마지막 PK를 저장해 다음 독립 실행에 재사용하지 않는다. 다시 실행하면 전체 조회를 다시 시작한다. 엔진의 체크포인트 기반 복구와, 마지막 PK를 다음 잡에 넘기는 증분 적재 설계는 구분해야 한다.

## 발표 슬라이드에 넣을 요약

**제목: 얼마나 가져오고, 어떻게 나누고, 몇 개를 동시에 처리할까?**

- `fetch_size`: 각 DB 조회에서 결과를 가져오는 단위
- JDBC 파티셔닝: 조회할 데이터 범위를 여러 조각으로 분할
- `parallelism`: 처리 작업의 병렬도. Local에서는 같은 JVM의 자원을 공유
- `LIMIT`: 쿼리 결과의 총 행 수 제한. fetch size와 다름

발표 멘트:

> “이전에 Python에서는 마지막 PK 이후를 LIMIT 3000으로 조회하고, 적재 후 PK를 저장하는 로직을 직접 작성했습니다. SeaTunnel의 fetch size는 그 LIMIT과 달리 전체 조회 결과를 조금씩 가져오는 단위입니다. 파티셔닝은 조회 범위를 나누고, parallelism은 작업을 병렬로 실행하도록 설정합니다. Local에서도 병렬 처리가 가능하지만 같은 JVM의 힙을 공유하므로, 병렬도를 높이는 것이 메모리 부족 해결을 뜻하지는 않습니다.”

공식 참고 자료: [SeaTunnel 2.3.13 JDBC Source](https://seatunnel.apache.org/docs/2.3.13/connectors/source/Jdbc/), [JDBC Sink](https://seatunnel.apache.org/docs/2.3.13/connectors/sink/Jdbc/), [PostgreSQL JDBC 커서와 fetch size](https://jdbc.postgresql.org/documentation/query/).
