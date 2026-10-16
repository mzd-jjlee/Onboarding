# 데이터 레이크하우스란 무엇이고, 왜 Iceberg인가

작성일 2026-10-13 (2026-10-16 4절 추가). 발표 자료 [presentation/local-lakehouse.html](../../presentation/local-lakehouse.html)
3~4쪽의 근거 문서다.

이 저장소의 다른 문서들은 **어떻게 구축했는지**를 다룬다
([구축 안내서](../local-lakehouse-superset.md), [파일 가이드](project-files-guide.md)).
이 문서는 그 앞 단계 — **애초에 왜 이 구조인가**를 정리한다.

> **출처 구분** — 이 문서의 개념 설명과 업계 동향은 **공개 자료를 조사한 것**이고,
> 이번 실습에서 검증한 내용이 아니다. 우리가 직접 실행해 확인한 것은
> [1억 행 검증 기록](../production-orders-100m.md)과 `evidence/` 쪽에 있다.
> 문장에서 둘을 섞지 않는다.

---

## 1. 한 줄 정의

> **레이크의 값싼 오픈 저장소 위에, 웨어하우스의 관리 기능(트랜잭션 · 스키마 · 이력)을 얹은 구조.**

좀 더 풀면 — 데이터를 **열린 파일 형식**(Parquet 등)으로 **값싼 객체 저장소**(S3·GCS·로컬 FS)에
두고, 그 위에 **테이블 계층**을 올려 트랜잭션·스키마 강제·빠른 조회를 얻는 설계다.

“웨어하우스와 레이크의 장점만 뽑았다”는 요약은 대체로 맞다. 다만 **공짜로 합쳐지는 것은 아니다** —
그 관리 기능을 얻으려면 테이블 포맷·카탈로그·쿼리 엔진을 **직접 골라 조립**해야 한다.
그게 레이크하우스의 비용이고, 이번 실습이 겪은 것도 그 비용이다.

## 2. 세 가지 방식의 기술적 차이

“값싼 저장소 + 관리 기능”이라는 요약 아래에, 구현상 아래 차이가 있다.
**각 행은 엔지니어가 실제로 부딪히는 질문**으로 적었다.

| 기술적 질문 | 데이터 웨어하우스 | 데이터 레이크 | **레이크하우스** |
|---|---|---|---|
| **바이트가 어떤 형식으로 놓이나** | 그 시스템 **전용 내부 포맷** (Snowflake micro-partition, BigQuery Capacitor, Redshift 컬럼 블록) | 객체 저장소에 **열린 포맷** (Parquet·ORC·Avro) | **열린 포맷** — 레이크와 동일 |
| **“이 테이블 = 어떤 파일들”을 아는 주체** | **엔진 내부 카탈로그.** 그 엔진만 안다 | **디렉터리 관례.** 경로를 LIST해서 추측 | **메타데이터 파일.** 공개 스펙이 정의 |
| **읽을 수 있는 주체** | 그 시스템의 SQL 인터페이스뿐 | 파일을 읽는 아무 엔진 | 스펙을 구현한 아무 엔진 |
| **쓰기가 보이는 시점** | 내부 트랜잭션 커밋 후 | **파일이 생기는 즉시** — 쓰는 도중도 보인다 | **포인터 원자 교체 후** |
| **밖으로 꺼내려면** | UNLOAD · EXPORT → **사본이 생긴다** | 파일 그대로 | 파일 그대로 |

### 차이를 가르는 축은 두 번째 행이다

흔히 “값싼 저장소를 쓰느냐”로 설명하지만, 기술적으로 셋을 가르는 것은
**“테이블의 정의를 누가 들고 있는가”** 다.

| | 테이블 정의의 소유자 | 결과 |
|---|---|---|
| 웨어하우스 | **엔진이 들고 있다** | 저장 포맷과 엔진을 분리할 수 없다. 다른 엔진을 붙이려면 데이터를 **복사**해야 한다 |
| 레이크 | **아무도 안 들고 있다** | 경로 관례에 의존하므로 합의가 깨지기 쉽다 |
| 레이크하우스 | **공개된 스펙이 들고 있다** | 서로 모르는 여러 엔진이 **같은 테이블에 합의**할 수 있다 |

이번 실습의 쓰기(SeaTunnel)와 읽기(Trino)가 서로를 모른 채 동작하는 것도
세 번째 줄 덕분이다. 둘은 **같은 스펙**과 **같은 카탈로그 주소**만 공유한다.

### 데이터 레이크가 “늪”이 된 기술적 이유

파일을 싸게 많이 쌓을 수는 있었지만, 테이블로 쓰기엔 세 가지가 빠져 있었다.

| 빠진 것 | 실제로 생기는 문제 |
|---|---|
| **원자적 커밋** | 쓰는 중에 읽으면 **일부 파일만** 보인다. 반쯤 적재된 결과가 조회된다 |
| **테이블 경계의 정의** | 경로 관례에 의존 → 객체 저장소의 **느린 LIST**를 매번 해야 하고, 스키마가 언제 어떻게 바뀌었는지 기록이 없다 |
| **파일 단위 통계** | 어떤 파일을 건너뛸 수 있는지 판단할 근거가 없어 **전부 읽어야** 한다 |

레이크하우스는 이 셋을 **메타데이터 계층**으로 메운 것이다. 세 번째(통계로 파일 거르기)가
실제로 어떻게 동작하는지는 발표 자료 20쪽에서 **우리 테이블의 실제 통계값**으로 확인할 수 있다.

### 무엇으로 가능해지나 — 테이블 포맷

**파일 더미를 테이블처럼 보이게 하는 약속**이다. 파일 옆에 메타데이터를 같이 두고
“지금 이 테이블은 이 Parquet들로 구성된다”를 적어둔다. 그래서 파일 위에서도
트랜잭션과 이력이 생긴다.

구조의 실제 모습은 [JSON에서 Parquet까지](iceberg-json-to-parquet.md)와
발표 자료 17~23쪽에서 **우리 저장소의 실제 파일**로 확인할 수 있다.

## 3. 왜 데이터 팀들이 이 구조로 옮겨가나

| | 이유 |
|---|---|
| **① 비용** | 객체 저장소가 웨어하우스 저장소보다 훨씬 싸다. 대용량 로그·ML 학습 데이터를 웨어하우스에 넣기엔 비용이 감당되지 않았다 |
| **② 엔진 독립** | 저장과 계산이 분리된다. Trino·Spark·Flink를 골라 쓰고 나중에 갈아탈 수 있다. 데이터가 특정 제품에 묶이지 않는다 |
| **③ 사본이 하나** | BI와 ML이 같은 데이터를 본다. 웨어하우스로 복사하고 다시 동기화하는 파이프라인이 줄어든다 |
| **④ 운영 신뢰성** | ACID와 스냅샷으로 쓰는 중에 읽어도 깨지지 않는다. 과거 시점 조회와 되돌리기가 된다 |

②가 이번 실습의 설계와 직접 연결된다. 쓰기(SeaTunnel)와 읽기(Trino)가 서로를 모른 채
**카탈로그와 파일 저장소 두 지점에서만 만나는** 구조가 그 결과다 (발표 자료 27쪽).

## 4. 왜 Iceberg를 테이블 포맷으로 쓰는가 — 기술적 이유

3절이 “왜 레이크하우스인가”였다면, 여기는 **“그 테이블 포맷으로 왜 Iceberg인가”** 다.
비교 대상은 두 갈래다 — **이전 세대인 Hive 테이블**, 그리고 **동세대인 Delta Lake · Hudi**.

> **먼저 공정하게** — 아래 기능 중 상당수는 Delta Lake와 Hudi도 제공한다.
> Iceberg만의 독점 기능으로 읽으면 안 된다. 차이는 **설계가 얼마나 일찍·깊게 들어갔는지**와
> **특정 엔진에 묶이지 않는지**에 있다. 그 점은 4.6에서 따로 다룬다.

### 4.1 디렉터리 목록(LIST)에서 벗어났다 — Hive 대비 가장 큰 차이

**Hive 테이블의 조회 과정:**

```
① 메타스토어에서 파티션 위치를 얻는다
② 각 파티션 디렉터리를 파일시스템에 LIST 한다      ← 병목
③ 파일마다 메타데이터를 읽는다
```

②가 문제다. **객체 저장소(S3·GCS)는 수백만 개 파일을 나열하는 데 최적화돼 있지 않다.**
파일이 늘수록 조회 계획 수립이 선형으로 느려지고, 목록 일관성 보장도 약하다.

**Iceberg는 파일 경로를 메타데이터에 기록해 둔다.** 디렉터리를 훑지 않고,
**읽어야 한다고 판명된 파일만** 저장소에 접근한다. 게다가 계층이 둘이라
(manifest list → manifest) manifest list의 요약 정보만 보고 **manifest 자체를 통째로
건너뛸 수** 있다. 파일 수가 늘어도 메타데이터 연산이 선형으로 늘지 않는 이유다.

> **우리 파일에서 확인한 것** — 1억 행 테이블에서 **manifest list 레코드 4개**만 읽어도
> 전체 행 수 100,000,000이 나온다. Parquet을 하나도 열지 않는다.
> (발표 자료 16쪽, `evidence/notebook/production-100m/`)

### 4.2 컬럼을 이름이나 위치가 아니라 **ID**로 추적한다

Iceberg는 모든 컬럼에 **불변의 정수 ID(field ID)** 를 부여한다. 우리 테이블의 실제 값:

```json
{"id": 1, "name": "order_id",     "type": "long"}
{"id": 2, "name": "factory_id",   "type": "string"}
{"id": 3, "name": "product_name", "type": "string"}
{"id": 4, "name": "quantity",     "type": "int"}
{"id": 5, "name": "order_date",   "type": "date"}
{"id": 6, "name": "status",       "type": "string"}
```

이게 왜 중요한가 — 다른 방식에는 각각 함정이 있다.

| 추적 방식 | 생기는 문제 |
|---|---|
| **이름 기반** | 삭제한 컬럼과 같은 이름을 나중에 다시 쓰면, **지웠던 컬럼의 옛 데이터가 되살아날** 수 있다 |
| **위치 기반** | 가운데 컬럼을 삭제하면 뒤 컬럼들이 앞으로 밀려 **이름과 데이터가 어긋난다** |
| **ID 기반 (Iceberg)** | 이름을 바꾸든 순서를 바꾸든 ID가 그대로라 안전하다 |

그래서 **컬럼 추가·삭제·이름 변경·순서 변경·타입 확장**을 **데이터 파일을 다시 쓰지 않고**
할 수 있다. 스키마가 바뀐 뒤에도 과거 데이터를 그대로 조회할 수 있다.

**관계형 DB와 비교하면** — 현대 RDB(PostgreSQL 11+, MySQL 8 등)도 단순한 컬럼 추가는
메타데이터만 바꿔 빠르게 끝난다. 다만 **컬럼 순서 변경이나 타입 변경**은 여전히
테이블 전체 재작성과 잠금(lock)을 부를 수 있다. Iceberg는 이 경우에도
**데이터 파일을 건드리지 않는다** — 새 metadata JSON을 쓰는 것으로 끝난다.

> **우리 파일에서 확인한 것** — metadata JSON의 `last-column-id: 6`.
> 컬럼을 지웠다 다시 만들어도 이 값은 되감기지 않고 새 ID가 발급된다.
> 단, **이번 실습에서 스키마를 실제로 바꿔보지는 않았다.**

### 4.3 숨은 파티셔닝(hidden partitioning) — 쓰지 않아도 되는 지식

Hive에서는 **사용자가 파티션 컬럼을 알고 `WHERE`에 직접 써야** 했다.

```sql
-- Hive: dt 파티션을 모르면 전체 스캔이 된다
SELECT * FROM orders WHERE dt = '2026-01-01' AND order_ts > '...'
```

빠뜨려도 **에러가 나지 않고 조용히 전체 스캔**이 된다. 느려질 뿐이라 알아채기 어렵다.

Iceberg는 파티션 값을 **원본 컬럼에서 변환(transform)으로 유도**한다
(`day(order_ts)`, `bucket(16, id)` 등). 사용자는 **파티션 컬럼의 존재를 몰라도**
평소처럼 쿼리하면 되고, 엔진이 알아서 파티션을 걸러낸다.
**사용자 실수로 생기는 조용한 전체 스캔을 구조적으로 막는 것**이 핵심이다.

> ⚠ **이번 실습에서는 쓰지 않았다.** 우리 테이블은 파티션이 없다 —
> metadata JSON의 `partition-specs`가 `[{"spec-id": 0, "fields": []}]`로 비어 있다.
> 1억 행을 `order_id` 범위로 4분할해 적재했지만 그건 **읽기 병렬 분할**이지
> Iceberg 파티션이 아니다. 19쪽에서 본 파일별 `order_id` 범위 통계는
> 파티션이 아니라 **manifest의 min/max 통계**로 걸러낸 것이다.

### 4.4 파티션 진화(partition evolution) — 과거 데이터를 다시 쓰지 않는다

운영하다 보면 파티션 기준을 바꿔야 할 때가 온다(일 단위 → 시간 단위 등).
Hive에서는 보통 **테이블을 다시 만들고 전체 데이터를 재작성**해야 했다.

Iceberg는 **파티션 명세를 바꿔도 기존 데이터를 그대로 둔다.** 옛 데이터는 옛 명세로,
새 데이터는 새 명세로 기록되고, 조회는 **두 명세를 모두 고려해** 계획을 세운다.

> ⚠ **이번 실습에서는 쓰지 않았다** (4.3과 같은 이유 — 파티션이 없다).
> 다만 `last-partition-id: 999`가 명세 ID를 추적하는 자리로 이미 존재한다.

### 4.5 스냅샷과 원자적 커밋

쓰기가 공개되는 시점이 **포인터 교체 한 번**이다. 파일을 다 쓴 뒤 마지막에
“현재 스냅샷”을 가리키는 값만 바꾼다. 그래서

- **쓰는 도중 읽어도** 읽는 쪽에는 이전 상태가 보인다 (반쯤 적재된 결과가 안 보인다)
- **과거 시점 조회**와 **되돌리기**가 된다
- 동시에 커밋하려는 쪽이 둘이면 한쪽이 실패하고 재시도한다

이 성질들을 묶어 부르는 말이 **ACID**다 — 원자성(Atomicity) · 일관성(Consistency) ·
고립성(Isolation) · 지속성(Durability). 레이크하우스 설명에서 “ACID를 지원한다”고 할 때
가장 체감되는 것은 **I(고립성)** 이다. 쓰는 도중 읽어도 이전 상태가 보이는 것.

> ⚠ **흔한 오해 둘 — 바로잡아 둔다.**
>
> **① “커밋에 실패하면 쓰던 파일이 롤백되어 사라진다”** — 아니다.
> Iceberg의 원자성은 **“새 상태가 공개되지 않는다”**는 뜻이지, 이미 쓴 파일이
> 지워진다는 뜻이 아니다. 파일은 **아무도 참조하지 않는 채 디스크에 남는다.**
> 그래서 운영에서 **orphan file deletion**이라는 정리 작업을 따로 돌린다.
>
> **우리가 실제로 겪은 사례** — 1억 행 적재 1·2차 시도가 커밋 없이 중단됐을 때,
> 스냅샷이 없는 빈 테이블이 남아 `..._attempt1`로 이름을 바꿔 보존했다
> (`docs/production-orders-100m.md`).
>
> **② “C(일관성)가 제약 조건까지 보장한다”** — 아니다.
> Iceberg는 **스키마(타입과 필수 여부)** 까지만 강제하고, RDB 같은
> **외래 키(FK)나 CHECK 제약은 제공하지 않는다.**
> 우리 테이블도 `order_id`만 `required: true`이고 나머지는 아니다.

> **우리 파일에서 확인한 것** — 1억 행 테이블에 스냅샷 4개가 남아 있고,
> `total-records`가 25M → 50M → 75M → 100M으로 누적돼 있다 (발표 자료 15쪽).
> 다만 **`FOR VERSION AS OF` 같은 시점 조회 쿼리는 실행해 보지 않았다.**

### 4.6 엔진에 묶이지 않는다 — 이것이 실질적 선택 이유인 경우가 많다

앞의 4.1~4.5는 Delta Lake·Hudi도 상당 부분 제공한다. **실무에서 Iceberg를 고르는
이유로 가장 자주 꼽히는 것은 거버넌스와 중립성**이다.

| | 내용 |
|---|---|
| **스펙이 공개돼 있다** | [Iceberg 스펙](https://iceberg.apache.org/spec/)만 보고 독립 구현을 만들 수 있다. 실제로 Trino·Spark·Flink·PyIceberg·DuckDB 등이 각자 구현했다 |
| **특정 엔진의 부속이 아니다** | Delta Lake는 초기에 Databricks·Spark 중심으로 발전했다(현재는 UniForm으로 Iceberg 호환을 제공한다). Iceberg는 처음부터 여러 엔진을 전제로 설계됐다 |
| **카탈로그도 표준화 중** | REST Catalog 스펙이 생겨, 카탈로그 구현(HMS·Glue·Polaris 등)까지 갈아끼울 수 있는 방향으로 간다 |
| **재단 거버넌스** | Apache 재단 프로젝트라 특정 회사의 제품 전략에 종속되지 않는다 |

> **우리 실습에서 확인한 것** — 같은 `./lake` 파일을 **SeaTunnel(쓰기)**,
> **Trino(조회)**, **PyIceberg 노트북(학습)** 세 도구로 다뤘다. 셋은 서로를 모르고
> 공유하는 것은 카탈로그 주소와 파일 경로뿐이다.

### 정리 — 이번 실습에서 확인한 것과 안 써본 것

| 기술적 이유 | 이번 실습 |
|---|---|
| 4.1 LIST 회피 · 메타데이터 계층 | **확인** — manifest list 4개로 1억 행 집계 |
| 4.2 컬럼 ID 기반 스키마 | **파일에서 확인** — field ID 1~6. 다만 스키마 변경은 안 해봤다 |
| 4.3 숨은 파티셔닝 | **미사용** — 파티션 없는 테이블 |
| 4.4 파티션 진화 | **미사용** |
| 4.5 스냅샷 · 원자적 커밋 | **확인** — 스냅샷 4개 누적. 시점 조회 쿼리는 미실행 |
| 4.6 엔진 중립 | **확인** — 같은 파일을 세 도구로 읽음 |

**발표에서 말할 때는 이 구분을 지킨다.** 안 써본 기능을 “해봤다”로 말하지 않는다.
4.3·4.4는 “Iceberg가 제공하는 기능이지만 이번 구성에서는 쓰지 않았다”로 소개한다.

## 5. Apache Iceberg가 표준이 되어가는 흐름

테이블 포맷은 Iceberg · Delta Lake · Apache Hudi 셋이 경쟁해 왔다.
**2024년을 지나며 Iceberg 쪽으로 수렴하는 중**이다.

| 시점 | 사건 |
|---|---|
| 2024.06 | **Databricks가 Tabular 인수** — Iceberg 창시자들이 세운 회사. 보도된 금액 10~20억 달러 |
| 2024 | **Snowflake가 Polaris 카탈로그**를 오픈소스로 공개하고 Apache 재단에 기증 |
| 2024.12 | **AWS S3 Tables** 발표 — S3에 Iceberg를 관리형으로 제공 |
| 진행 중 | **Google BigQuery**의 Iceberg 테이블, **Azure**의 Iceberg 연동 |
| 진행 중 | 경쟁 포맷 **Delta Lake도 UniForm**으로 Iceberg 호환을 제공 |

**“경쟁 포맷을 만든 쪽조차 Iceberg 호환으로 움직였다”**는 점이 이 흐름의 성격을 잘 보여준다.

### 정직하게 — “이미 1위”는 아니다

조사에 따라 **현재 도입 점유율은 Delta Lake가 다소 앞선다**(39% vs 31%).
다만 향후 3년 도입 **계획**에서는 Iceberg가 앞선다(29% vs 23%).

→ **“이미 표준”이 아니라 “표준으로 수렴 중”**이 정확한 표현이다. 발표에서도 그렇게 말한다.

### 그래서 이번 실습도 Iceberg

- 특정 벤더 제품 없이 **오픈소스만으로 로컬에 세울 수 있다**
- 나중에 클라우드로 옮겨도 **같은 포맷**이 쓰인다 — 배워두면 환경이 바뀌어도 남는다
- 같은 파일을 Trino·PyIceberg 등 **여러 도구로 읽는 것을 실제로 확인**했다
  (이건 우리가 검증한 것이다 — `evidence/trino/`, `analysis/read_parquet.ipynb`)

구성요소 선택의 상세한 근거는 발표 자료 12쪽과
[저장소 선택지 문서](../local-lakehouse-build-options.md)에 있다.

## 6. 이 프로젝트와의 대응

| 레이크하우스의 역할 | 이번 실습에서 고른 것 |
|---|---|
| 적재 | SeaTunnel 2.3.13 (Iceberg sink) |
| 테이블 포맷 | **Apache Iceberg 1.6.1** (format v2) |
| 카탈로그 | Hive Metastore 4.0.1 |
| 파일 저장소 | 로컬 `./lake` (운영이라면 S3 호환 객체 저장소) |
| 조회 엔진 | Trino 483 |
| 화면 | Apache Superset 6.0.0 |

**카탈로그가 Iceberg의 필수 요소는 아니다.** HMS 대신 JDBC·REST 카탈로그도 쓸 수 있고,
이번에는 SeaTunnel과 Trino 양쪽이 바로 지원한다는 이유로 HMS를 골랐다.

## 7. 참고한 자료

업계 동향 부분은 아래 공개 자료를 조사해 정리했다. **이번 실습에서 검증한 내용이 아니다.**

- [Introduction to the Iceberg Data Lakehouse — Dremio](https://www.dremio.com/blog/iceberg-data-lakehouse/)
- [Apache Iceberg Crash Course: What is a Data Lakehouse and a Table Format? — Dremio](https://www.dremio.com/blog/apache-iceberg-crash-course-what-is-a-data-lakehouse-and-a-table-format/)
- [Snowflake, Databricks and the Fight for Apache Iceberg Tables — The New Stack](https://thenewstack.io/snowflake-databricks-and-the-fight-for-apache-iceberg-tables/)
- [AWS Unveils Hosted Apache Iceberg Service on S3 — BigDATAwire](https://www.hpcwire.com/bigdatawire/2024/12/03/aws-unveils-hosted-apache-iceberg-service-on-s3-new-metadata-management-layer/)
- [Lakehouse Convergence: Delta Lake & Iceberg — Capital One](https://www.capitalone.com/tech/cloud/lakehouse-format-convergence-delta-lake-iceberg/)
- [Why Apache Iceberg is essential for modern data lakehouses — TechTarget](https://www.techtarget.com/searchdatamanagement/opinion/Why-Apache-Iceberg-is-essential-for-modern-data-lakehouses)
- [Apache Iceberg And Trino: Powering Data Lakehouse Architecture — Open Source For You](https://www.opensourceforu.com/2026/01/apache-iceberg-and-trino-powering-data-lakehouse-architecture/)

**4절(기술적 이유) 조사 자료 — 2026-10-16 추가:**

- [Schema evolution — Apache Iceberg 공식 문서](https://iceberg.apache.org/docs/latest/evolution/) — 컬럼 ID 기반 추적, 파티션 진화
- [Partitioning — Apache Iceberg 문서](https://apache-iceberg.mintlify.app/concepts/partitioning) — 숨은 파티셔닝의 변환(transform)
- [Iceberg Spec](https://iceberg.apache.org/spec/) — manifest list의 요약 정보로 manifest를 건너뛰는 조회 계획
- [Apache Iceberg vs Delta Lake (II): Schema and partition evolution — Flexera](https://www.flexera.com/blog/finops/iceberg-vs-delta-lake-schema-partition/)
- [Iceberg Partitioning vs. Hive Partitioning — OLake](https://olake.io/iceberg/hive-partitioning-vs-iceberg-partitioning/) — Hive의 디렉터리 LIST 병목
- [Apache Iceberg Metadata Explained: Snapshots & Manifests — OLake](https://olake.io/blog/apache-iceberg-metadata-explained/)
- [Hive-Style Date Partitions or Iceberg Hidden Partitioning?](https://oneuptime.com/blog/post/2026-08-13-hive-date-partitions-vs-iceberg-hidden-partitioning/view)

**외부 설명 검토 (2026-10-16)** — 사용자가 Gemini와 나눈 Iceberg 대화를 함께 검토했다.
큰 흐름(메타데이터 계층 순서, 컬럼 ID 기반 스키마 진화, RDB와의 대비)은 맞지만
두 군데가 부정확해 4.5에 교정을 적어두었다 — **커밋 실패 시 “롤백”으로 파일이
사라진다는 설명**과 **C(일관성)가 제약 조건까지 보장한다는 설명**이다.
`docs/md/iceberg-json-to-parquet.md`의 외부 설명 검토 표와 같은 방식이다.

**4절에서 “우리 파일에서 확인한 것”으로 표시한 값**은 공개 자료가 아니라
이 저장소의 실제 파일을 읽어 확인한 것이다 (metadata JSON 파싱 · fastavro · pyarrow).
`evidence/notebook/production-100m/`과 `evidence/production-100m/`에 기록이 있다.

Iceberg 자체의 구조는 [공식 스펙](https://iceberg.apache.org/spec/)과
[Configuration 문서](https://iceberg.apache.org/docs/latest/configuration/)를 따른다.
외부 설명 중 사실과 다른 부분을 우리 파일로 대조한 기록은
[iceberg-json-to-parquet.md](iceberg-json-to-parquet.md)와
[발표 기획서 7절](../../presentation/local-lakehouse-deck-plan.md)에 있다.
