# DB 200만 행 → MinIO(S3) Iceberg: 월별 파티션 적재

> 상태: **완료 (2026-11-12).** 사용자 검토로 결정 확정 후 구현·적재·검증. 결과는 맨 아래 "실행 기록".

## 왜 하는가

- 지금 MinIO에 있는 Iceberg 테이블은 공개 API에서 받은 576행 하나뿐이다(`iceberg_s3.public_api_s3.weather_hourly`, `docs/minio-s3-lakehouse.md`).
  CSV 파일을 읽어 Parquet 1개로 쓰는 작은 실습이라 "많은 데이터를 객체 저장소에 쓰는" 감각은 얻지 못했다.
- 이번에는 **DB에서 직접 읽어서**(JDBC) **200만 행**을 MinIO에 적재하고, 처음으로 **파티션**을 적용한다.
  - **JDBC source**: SeaTunnel이 PostgreSQL에 SQL로 접속해 행을 읽는 방식. CSV를 중간에 만들지 않는다.
  - **파티션**: 테이블 파일을 특정 컬럼 값(여기서는 주문 월)별로 나눠 저장하는 것. 조회할 때 조건에 맞는 파일만 읽어 스캔량이 줄어든다.
  - **숨은 파티셔닝(hidden partitioning)**: Iceberg는 `month(order_date)`처럼 컬럼에 변환을 걸어 파티션을 만든다.
    사용자는 `WHERE order_date >= ...`만 쓰면 되고, `order_month` 같은 별도 컬럼을 만들 필요가 없다.

## 원본 조사 결과 (2026-11-12, 실제 조회로 확인)

원본: `Onboarding/seatunnel/docker-compose.sourcedb.yml`의 Postgres. 호스트 `localhost:5440`, DB `srcdb`, 컨테이너 `seatunnel_practice_postgres`.
컨테이너에서는 `host.docker.internal:5440`으로 접속한다 (iceberg 스택과 다른 compose 프로젝트 = 다른 Docker 네트워크).

> 주의: compose 파일 주석에는 "customers(5만 행) + sales(200만 행)"라고 쓰여 있지만 **실제 테이블은 `factories` + `production_orders`**다.
> 초기화 SQL(`seatunnel/sourcedb-init/postgres/01_init.sql`)과 실제 DB가 일치하고, 주석만 예전 내용이다.

`srcdb.public`에 있는 테이블:

| 테이블 | 행 수(추정) | 크기 | 비고 |
|---|---|---|---|
| `production_orders_200m` | 2억 | 18 GB | |
| `production_orders_100m` | 1억 | 9.5 GB | 2026-10-08 로컬 lake 적재 원본 |
| `production_orders_10m` / `_replica` | 1,000만 | 각 951 MB | CDC 실습용 |
| `cdc_demo_orders` | 1,000만 | 712 MB | CDC 실습용 |
| **`production_orders`** | **200만** | **204 MB** | **이번 대상** |
| `factories` | 30 | 32 kB | 공장 차원 테이블 |

**`public.production_orders` 상세** (전체 집계로 확인):

| 항목 | 값 |
|---|---|
| 컬럼 | `order_id bigint PK`, `factory_id text`, `product_name text`, `quantity int`, `order_date date`, `status text` |
| 행 수 | 2,000,000 |
| `order_id` 범위 | 1 ~ 2,000,000 (빈 번호 없음) |
| `quantity` 합계 | 509,812,561 |
| `order_date` 범위 | 2025-09-07 ~ 2026-09-07 (13개 월) |
| 고유 `factory_id` / `product_name` | 30 / 10 |
| NULL이 있는 행 | 0 |
| `status`별 | CANCELLED·COMPLETED·CREATED·IN_PROGRESS 각 500,000 |

월별 행 수 (파티션 하나에 들어갈 양):

| 월 | 행 수 | 월 | 행 수 |
|---|---|---|---|
| 2025-09 | 128,712 | 2026-03 | 169,817 |
| 2025-10 | 170,132 | 2026-04 | 164,482 |
| 2025-11 | 164,111 | 2026-05 | 169,941 |
| 2025-12 | 169,386 | 2026-06 | 163,871 |
| 2026-01 | 170,494 | 2026-07 | 169,681 |
| 2026-02 | 153,827 | 2026-08 | 169,900 |
| | | 2026-09 | 35,646 |

- 원본 PK(`order_id`)가 있다. 2026-10-08 1억 행 적재에서 **원본 PK가 Iceberg writer로 넘어가 Delta writer가 선택되고 메모리가 폭증**한 문제가 있었다
  (`docs/production-orders-100m.md`). 이번에도 같은 대책(PK 메타데이터 제거 projection + 식별자 없는 테이블 사전 생성)을 쓴다.
- CDC 실습용 비활성 replication slot 정리 (2026-11-12, 사용자 허용 후 수행):
  - **replication slot**: CDC 소비자가 "어디까지 읽었는지"를 Postgres에 남겨 두는 기록. slot이 남아 있으면 Postgres는 그 이후의 변경 로그(WAL)를 지우지 못한다.
  - `seatunnel_cdc_insert_update`: 비활성, WAL 1,325 MB를 붙잡고 있었고 `seatunnel/` 안의 어떤 job·문서도 이 이름을 쓰지 않아 **삭제**했다. 삭제 + CHECKPOINT 후 `pg_wal` 1,344 MB(84파일) → 80 MB(5파일).
  - `seatunnel_cdc_10m_iu_test`: `seatunnel/jobs/15_postgres_10m_cdc_insert_update.conf`가 사용하는 slot이라 **유지**했다. 붙잡은 WAL은 63 kB.

## 목표와 계약

- 원본 `srcdb.public.production_orders` 200만 행을 MinIO 위 새 Iceberg 테이블 `retail_s3.production_orders`에 **한 번** 적재한다.
- 흐름: PostgreSQL ─JDBC─▶ SeaTunnel(PK 제거 projection) ─Iceberg sink─▶ MinIO `s3a://lakehouse/warehouse/retail_s3.db/` + HMS 커밋 ─▶ Trino `iceberg_s3`로 조회.
- 파티션: `month(order_date)` 숨은 파티셔닝 → 13개 파티션.
- `order_id`는 NOT NULL 컬럼으로 값 그대로 적재하고, Iceberg identifier field(PK 표시)는 붙이지 않는다 (결정 6).
- 기존 것은 바꾸지 않는다: `./lake`의 모든 테이블, `public_api_s3.weather_hourly`, 원본 DB(읽기 전용 접속), Trino catalog의 `READ_ONLY` 설정.

## 설계

### 추가한 파일 (기존 파일은 `compose.bulk.yaml` 주석만 수정)

| 파일 | 역할 | 참고한 기존 파일 |
|---|---|---|
| `scripts/PrepareRetailS3Catalog.java` + `prepare-retail-s3-catalog.sh` | namespace `retail_s3`와 **파티션된 빈 append 테이블**을 Java Iceberg API로 미리 생성 | `PrepareProductionCatalog.java` |
| `jobs/06_production_orders_to_minio_iceberg.conf` | JDBC source → PK 제거 Sql transform 2단 → Iceberg sink(s3a) | `03_production_orders_100m.conf`, `05_weather_to_minio_iceberg.conf` |
| `scripts/load-production-orders-to-minio.py` | 선행 검사 → 테이블 준비 → 적재 → 원본 대사 → 파티션·pruning 확인 → 기존 데이터 보존 확인 → evidence 기록. **원시 job 직접 실행 금지** | `load-production-100m.py`, `load-weather-to-minio.py` |
| `scripts/register-retail-s3-superset.py` | Superset에 MinIO용 연결·Dataset·월별 차트 등록 후 Superset 경유 조회로 확인 | `register-production-superset.py` |

- 테이블을 SeaTunnel 자동 생성(`CREATE_SCHEMA_WHEN_NOT_EXIST`)에 맡기지 않고 Java로 먼저 만드는 이유:
  ① 원본 PK가 Iceberg identifier로 복사되는 것을 막고, ② `month(order_date)` 같은 **변환 파티션은 SeaTunnel 옵션으로 지정할 수 없을 가능성이 높아서**다.
  (②의 SeaTunnel 옵션 지원 여부는 확인하지 않았다. 미리 만든 파티션 테이블에 SeaTunnel이 파티션대로 쓰는 것은 실행으로 확인했다.)
- PyIceberg는 HMS 4와 테이블 조회가 호환되지 않아(`Invalid method name: get_table`, task 001 기록) 테이블 생성·검사에 쓰지 않는다.
- 원본 접속 계정은 job 파일에 적지 않고 환경변수 `SOURCE_USER` / `SOURCE_PASSWORD`로 넘긴다. 메모리 설정과 함께 기존 `compose.bulk.yaml`을 그대로 쓴다.

### 선행 검사 (래퍼가 적재 전에 확인)

| 상태 | 동작 |
|---|---|
| 대상 테이블 없음 | 테이블 생성 후 적재 |
| 테이블 있음, snapshot 없음(빈 테이블), 파티션·식별자 설정이 기대와 같음 | 적재 |
| 테이블 있음, 데이터 있음, 원본 집계와 전부 일치 | `SKIP_IDENTICAL` (재적재 안 함) |
| 그 외 (일부만 있음, 값 다름, 파티션 설정 다름) | **중단.** 사람이 확인한다 |

## 결정 사항 (2026-11-12 사용자 검토)

| # | 항목 | 결정 |
|---|---|---|
| 1 | 대상 테이블 이름 | `retail_s3.production_orders` |
| 2 | 파티션 | `month(order_date)`. 월 단위 기간 조회를 편하게 하기 위해 |
| 3 | SeaTunnel 병렬도 | `parallelism = 2`, `partition_num = 2` |
| 4 | JVM 메모리 | 기본 힙은 작으므로 처음부터 `compose.bulk.yaml` 방식 적용: **Xmx 3GiB**, 컨테이너 제한 4GiB (`config/jvm_100m_options` 재사용) |
| 5 | Superset | **Dataset 등록까지 포함** (아래 참고) |
| 6 | 원본 PK | `order_id` **컬럼과 값은 유지**, Iceberg identifier field(PK 표시)는 붙이지 않음. Iceberg identifier는 중복을 막지 않고 upsert/CDC 기준으로만 쓰이며, 붙이면 SeaTunnel이 Delta writer를 써서 메모리를 더 쓴다. 중복 없음은 적재 후 `count(DISTINCT order_id)`로 검증 |

### Superset 등록이 따로 필요한 이유

- **SQL Lab에서 SQL로 조회하는 것은 등록 없이 된다.** Superset은 Trino에 SQL을 보내기만 하고, Trino가 HMS를 통해 새 테이블을 바로 찾는다.
  `SELECT ... FROM iceberg_s3.retail_s3.production_orders`처럼 catalog까지 쓰면 된다.
- **차트·대시보드를 만들려면 Dataset 등록이 필요하다.** Dataset은 "이 테이블을 차트 재료로 쓰겠다"고 Superset 메타DB에 남기는 기록이다.
  2026-10-08 1억 행 때도 `scripts/register-production-superset.py`로 Dataset과 저장 SQL을 등록했다.
- 현재 Superset의 Trino 연결은 `trino://superset@trino:8080/iceberg`라 기본 catalog가 `iceberg`(로컬 lake)다.
  `iceberg_s3` 테이블을 Dataset으로 등록하려면 **MinIO용 연결을 하나 더 추가**(`.../iceberg_s3`)하거나 기존 연결에서 다른 catalog를 고를 수 있어야 한다.
  → **MinIO용 연결 `MinIO Iceberg / Trino`(`trino://superset@trino:8080/iceberg_s3`)를 새로 추가**했다. 기존 연결의 catalog 설정을 바꾸지 않기 위해서다.
  기존 연결 하나로 여러 catalog를 고르는 방식(multi-catalog)은 시도하지 않았다.

## 완료 조건

| 조건 | 검증 | 결과 |
| --- | --- | --- |
| 원본과 집계 일치 | 원본 PG와 Trino에서 같은 집계 비교: 행 수, `order_id` 합계·최소·최대, `quantity` 합계, NULL 수, `status`별·월별 행 수 | 통과: 12개 요약 항목 + 월별 13행 + status별 4행 모두 문자열까지 일치 |
| 행 중복 없음 | Trino `count(*)` = `count(DISTINCT order_id)` = 2,000,000 | 통과: 2,000,000 = 2,000,000 |
| 파일이 MinIO에 있음 | `"production_orders$files"`의 모든 `file_path`가 `s3a://lakehouse/warehouse/retail_s3.db/`로 시작 | 통과: Parquet 26개 전부 `.../production_orders/data/order_date_month=YYYY-MM/` 아래 |
| 파티션 적용 | `"production_orders$partitions"`가 13행이고 각 행 수가 위 월별 표와 같음. bucket에 월별 폴더가 생김 | 통과: 13개, 월별 행 수 일치 |
| Superset 조회 | 등록한 Dataset으로 SQL Lab·차트에서 2,000,000행 집계 확인 | 통과: 차트 쿼리 13개월·합계 2,000,000, SQL Lab 2,000,000행·quantity 509,812,561 |
| 파티션 효과 확인 | 한 달 조건 쿼리를 `EXPLAIN ANALYZE`로 실행했을 때 읽은 파일·행 수가 전체보다 적음 | 통과: 2026-01 조건 → 스캔 입력 170,494행(= 1월 행 수), split 2개. 전체 200만 행·26파일 중 해당 월만 읽음 |
| 재실행 시 중복 방지 | 래퍼 재실행 → `SKIP_IDENTICAL`, snapshot 수 변화 없음 | 통과: `SKIP_IDENTICAL`, snapshot 2개 유지 |
| 기존 데이터 보존 | `./lake` 파일 SHA-256 실행 전후 동일, `weather_hourly`(MinIO) 576행 유지, orders 5건/170000 | 통과: `./lake` 72파일 동일, weather 576행, orders 5건/170000 |

## 실행 규칙

- 실행 위치는 호스트의 `Onboarding/iceberg/`. 원본 DB는 `Onboarding/seatunnel/`에서 `postgres` 서비스만 띄운다.
- 원본은 적재 중 바뀌지 않는다고 가정한다(정적 배치). PostgreSQL은 Iceberg처럼 snapshot을 고정해 읽을 수 없다.
  확인 근거: 2026-11-12 조사 시 `production_orders`의 insert/update/delete 통계 0, CDC slot 비활성.
- 원시 SeaTunnel job(`06_...conf`)을 직접 반복 실행하지 않는다. `APPEND_DATA`는 중복을 막지 않는다.
- 실패하면 바로 재시도하지 않고, HMS·MinIO의 실제 테이블 상태를 먼저 확인한다. 실패 기록은 지우지 않는다.
- Airflow 날씨 DAG(매일 09:00)가 HMS·Trino 재시작과 겹치지 않게 한다.
- 실행 결과는 `evidence/minio-production-orders/<run_id>/`에 남기고(`.gitignore` 대상), 요약은 이 파일 "실행 기록"과 `docs/minio-s3-lakehouse.md`에 쓴다.

## 범위 밖

- 1억·2억 행 테이블 적재 (이번 결과를 보고 후속 task로 판단)
- 증분 적재·CDC·upsert, 원본 변경 반영
- compaction(작은 파일 합치기), snapshot 만료, 파티션 변경(partition evolution)
- `factories`와의 조인 테이블, mart 생성
- Superset 대시보드 구성 (Dataset 등록과 확인용 차트 1개까지만 범위)
- `seatunnel/docker-compose.sourcedb.yml`의 틀린 주석 수정 (다른 프로젝트 영역)

## 위험과 미확인 사항 (실행 후 정리)

- ~~SeaTunnel writer가 미리 만든 테이블의 파티션 설정을 따르는지~~ → **따른다.** `order_date_month=YYYY-MM/` 폴더별로 파일이 생겼다.
- 작은 파일: 예상(파일당 1~2MB)보다 더 작게 **파일당 평균 약 326KB**(26개, 합계 8.1MiB)였다. zstd 압축과 컬럼 값 반복이 많아서다.
  200만 행 조회에는 문제없지만, 매일 append하는 테이블이라면 compaction이 필요해지는 구조다 (범위 밖).
- 한 번 실행에 **snapshot이 2개** 생긴다. 병렬도 2 → writer 2개가 각자 100만 행·13파일을 쓰고, 마지막에 하나씩 따로 커밋한다(0.24초 간격).
  2026-10-08 1억 행(병렬도 4)의 "빈 테이블 + 4커밋"과 같은 동작이다. 두 커밋 사이에 중단되면 절반만 커밋된 상태가 될 수 있고,
  그 경우 래퍼는 "원본과 다름"으로 **중단**한다(자동 재적재하지 않음).
- 원본 DB 컨테이너가 iceberg 스택과 같은 시간에 떠 있어야 한다. 실행 시 Docker VM 메모리 9.9GiB에서 문제없었다.

## 실행 기록 (2026-11-12)

실행 환경: Rancher Desktop, iceberg 스택(catalog-db·HMS·Trino·MinIO·Superset) + seatunnel 원본 Postgres. Airflow는 기동하지 않음.

```bash
# 호스트, Onboarding/seatunnel: 원본 Postgres만 기동
docker compose -f docker-compose.sourcedb.yml up -d --wait postgres
# 호스트, Onboarding/iceberg
bash scripts/up-trino.sh && bash scripts/up-minio.sh
# 원본 계정은 seatunnel/docker-compose.sourcedb.yml의 POSTGRES_USER / POSTGRES_PASSWORD
export SOURCE_USER='<원본 DB 사용자>'
export SOURCE_PASSWORD='<원본 DB 비밀번호>'
python3 scripts/load-production-orders-to-minio.py
docker compose -f compose.yaml -f compose.analytics.yaml up -d --wait superset
docker compose -f compose.yaml -f compose.analytics.yaml exec -T superset python /lab/scripts/register-retail-s3-superset.py
```

| 실행 | 결과 |
|---|---|
| 1회차 `20261112T014913Z-30f5521b` | `PASS` / `LOAD`. SeaTunnel Read 2,000,000 / Write 2,000,000 / Failed 0, job 8초(래퍼 기준 11.4초), OOM 없음 |
| 2회차 `20261112T015015Z-6b2af368` | `PASS` / `SKIP_IDENTICAL`, snapshot 2개 유지. 1회차의 pruning 추출 정규식 오류(집계 단계 숫자를 잡음)를 고친 뒤 실행해 pruning 자동 검증까지 통과 |
| Superset 등록 | 연결 id 2 `MinIO Iceberg / Trino`, Dataset id 2, 차트 id 3 (http://localhost:8088/explore/?slice_id=3). 기존 연결 1·Dataset 1·차트 1·2 변경 없음 |

- 테이블 결과: 2,000,000행, 파티션 13개, Parquet 26개(파티션당 writer별 1개) / 8,483,141 bytes, snapshot 2개(각 append 100만 행).
- 개발 중 수정: SeaTunnel 이미지의 Java가 8이라 `Map.of` 컴파일 실패 → `Collections.singletonMap`으로 변경 (테이블 생성 전 `check` 단계에서 발견).
- 기록: `evidence/minio-production-orders/<run_id>/` (report.json, 실행 계획 `explain-analyze-2026-01.txt`, SeaTunnel·Java 로그, `superset.json`).
- 참고: Superset 메타DB에는 2026-10-08에 등록했다고 기록된 `production_orders_100m` Dataset이 현재 없다. 이번 작업 전부터 없던 것으로, 원인은 확인하지 않았고 건드리지 않았다.

### VS Code에서 Java 코드 보기 (2026-11-12)

`scripts/PrepareRetailS3Catalog.java`는 SeaTunnel 컨테이너 안의 JAR로 컴파일되므로, 호스트 VS Code는 `org.apache.*` import를 찾지 못해 빨간 줄을 표시한다(실행에는 영향 없음).
`.vscode/settings.json`의 `java.project.referencedLibraries`가 아래 로컬 복사본을 참조한다. `vendor/`는 git 제외라 새 PC에서는 다시 만든다.

```bash
# 호스트, Onboarding/iceberg
mkdir -p vendor/java-classpath
CID=$(docker create apache/seatunnel:2.3.13)
docker cp $CID:/opt/seatunnel/connectors/connector-iceberg-2.3.13.jar vendor/java-classpath/
docker cp $CID:/opt/seatunnel/lib/seatunnel-hadoop3-3.1.4-uber.jar vendor/java-classpath/
docker rm $CID
```

성공하면 `vendor/java-classpath/`에 JAR 2개(약 55MB, 43MB)가 생긴다. Iceberg 클래스(`HiveCatalog`, `Namespace`, `Types`)는 앞의 것, Hadoop `Configuration`은 뒤의 것에 들어 있다.
