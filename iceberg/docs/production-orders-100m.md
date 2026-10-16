# PostgreSQL 1억 행 → Iceberg → Trino → Superset

## 대상과 구성

- 원본: Mac `localhost:5440`, DB `srcdb`, `public.production_orders_100m`.
- 컨테이너에서 원본 연결: `host.docker.internal:5440`.
- 목적지: `iceberg.retail.production_orders_100m`.
- 파일 위치: `lake/warehouse/retail.db/production_orders_100m_append/`.
- 기존 `retail.orders` 5건 테이블과 파일은 보존한다.
- SeaTunnel 2.3.13, 4개 JDBC 범위 분할, fetch_size 5000, JVM Xmx 3GiB, 컨테이너 제한 4GiB.
- Parquet zstd, 목표 파일 크기 128MiB, row group 16MiB. 이 값은 정확한 최종 파일 크기를 보장하지 않는다.

## 이번 메모리 문제와 기존 실습의 차이

`seatunnel/docs/slides/seatunnel-practice-share.pptx` 16~17쪽과 `seatunnel/output/oom-study/20260915`를 확인했다. 기존 LocalFile 실습은 512MB 힙에서 Parquet writer 버퍼가 누적됐고 Xmx 3GiB로 처리했다. `seatunnel/scripts/run-job.sh`는 `cluster/jvm_client_options`를 마운트한다.

이번 실행도 처음부터 `config/jvm_100m_options`를 마운트해 **Xmx 3GiB가 실제 Java 명령줄에 적용**됐다. 하지만 원본 PostgreSQL 기본키가 Iceberg writer 설정으로 전달되어 Delta writer가 키별 행 위치를 누적했다. 첫 힙 histogram에서 `StructLikeWrapper`, `BaseTaskWriter$PathOffset`가 약 650만 개 확인됐다. 단순히 기본 512MB를 늘리는 문제가 아니었다.

SeaTunnel 2.3.13에서 주의할 점:

1. `IcebergSink`는 sink primary keys가 비어 있으면 source CatalogTable의 PK를 복사한다.
2. `IcebergWriterFactory`는 식별자가 있으면 upsert=false여도 Delta writer를 선택한다.
3. 따라서 대상 테이블만 식별자 없이 만드는 것으로는 충분하지 않다.

최종 설정은 SQL projection으로 `order_id → ingest_order_id → order_id` 이름을 바꿨다가 복원한다. 값·최종 타입·컬럼명은 유지하면서 중간 스키마의 PK 메타데이터를 제거한다. 식별자 없는 목적지 테이블을 미리 생성하고 upsert=false로 append writer를 선택한다. 이는 **이번 정적 전체 배치 적재용**이며 CDC/upsert 작업에 그대로 적용하지 않는다.

첫 실패 테이블은 HMS API로 `retail.production_orders_100m_attempt1`에 보존했다. 커밋된 snapshot이 없는 빈 테이블이다. 두 차례의 실패 로그는 `evidence/production-100m/attempt1`, `attempt2`에 있다. 종료 코드 137은 수동 stop 후 종료된 결과이며 자동 OOM kill로 단정하지 않는다.

## 파일과 실행 순서

| 파일 | 역할 |
|---|---|
| `jobs/03_production_orders_100m.conf` | JDBC → PK 메타데이터 제거 projection → Iceberg sink |
| `compose.bulk.yaml` | 이번 SeaTunnel 작업의 메모리와 소스 접속 환경변수 |
| `config/jvm_100m_options` | 실제 local 실행 JVM의 힙 설정 |
| `scripts/PrepareProductionCatalog.java` | SeaTunnel에 포함된 Java Iceberg API로 빈 append 테이블 생성 |
| `scripts/prepare-production-catalog.sh` | 위 Java 코드를 컨테이너 안에서 컴파일·실행 |
| `scripts/load-production-100m.py` | 테이블·경로·실행 기록을 검사해 중복 적재 차단 후 실행 |
| `scripts/verify-production-100m.py` | 원본 집계와 Trino 결과 대조 |
| `scripts/register-production-superset.py` | Superset Dataset·저장 SQL 등록 및 SQL Lab 조회 |

실행은 프로젝트 루트에서 한다. 소스 계정은 환경변수로 제공한다. 이미 적재를 시작했거나 테이블이 있으면 기본 실행은 거부한다.

```sh
export SOURCE_USER='<원본 DB 사용자>'
export SOURCE_PASSWORD='<원본 DB 비밀번호>'
python3 scripts/load-production-100m.py
```

`--reuse-empty`는 수동 진단 후에만 사용하는 복구 옵션이다. 성공 스냅샷이나 data 파일이 있으면 거부한다. 기존 실행 기록도 임의로 지우지 않는다. 원본 APPEND job을 직접 반복하면 중복 데이터가 생길 수 있다.

준비 코드에서 PyIceberg 0.10의 HMS `get_table` 호출이 현재 Hive 4 서버와 호환되지 않아, 실제 SeaTunnel에 포함된 Java Iceberg/HMS 클라이언트를 사용했다. 기존 namespace 준비 기능은 바꾸지 않았다.

## Superset에서 사용할 SQL

상단 SQL → SQL Lab, Database `Local Iceberg / Trino`, Catalog `iceberg`, Schema `retail`을 선택한다.

```sql
SELECT COUNT(*) AS row_count,
       SUM(CAST(quantity AS BIGINT)) AS total_quantity
FROM iceberg.retail.production_orders_100m;

SELECT status, COUNT(*) AS row_count,
       SUM(CAST(quantity AS BIGINT)) AS total_quantity
FROM iceberg.retail.production_orders_100m
GROUP BY status ORDER BY status;

SELECT * FROM iceberg.retail.production_orders_100m
WHERE order_id BETWEEN 1 AND 100
ORDER BY order_id LIMIT 100;
```

1억 행을 브라우저에 전부 전송하지 않고 집계와 제한된 샘플로 조회한다. PostgreSQL의 원본 PK/index가 Iceberg에 복사되는 것은 아니다.

## 검증 범위

원본의 전체 및 상태별 건수, order_id 합계·범위, quantity 합계·NULL 수, 날짜 범위, 문자열 길이 합계를 Trino의 컬럼 스캔 결과와 비교한다. 단순 metadata COUNT 확인만으로 끝내지 않는다. 이는 전체 행을 바이트 단위로 대조하는 검증은 아니다. 원본이 실행 중 변경되지 않는 정적 배치 실습을 전제로 한다.

원본 기준값: 100,000,000행, quantity 합계 25,500,992,494, order_id 1~100,000,000. 상태별 25,000,000행씩 4개다.

## 실행 결과 (2026-10-08)

- SeaTunnel 실행 종료 코드 0, 상태 `SUCCEEDED`.
- Trino가 실제 컬럼을 스캔해 원본과 비교: 총 건수·상태별 건수, ID 합계·범위, quantity 합계·NULL 수, 날짜 범위, 문자열 길이가 모두 일치했다.
- Iceberg `$files` 메타테이블에 등록된 Parquet 4개, 합계 330,496,199 bytes (약 315 MiB). Trino 검증 쿼리 실행 시간은 CLI 포함 약 5.9초였다.
- 기존 `iceberg.retail.orders`도 5건·amount 합계 170000으로 유지됨을 확인했다.
- 사용자가 Superset SQL Lab에서 `production_orders_100m` 조회 성공을 확인했다. 본 실행에서 Superset chart/dashboard를 새로 만들지는 않았다.
- 실행 로그, 원본 집계, Trino SQL/CSV 결과와 검증 요약은 `evidence/production-100m/`에 있다. 검증 스크립트는 `python3 scripts/verify-production-100m.py`이다.

집계 대조는 모든 컬럼의 데이터 행을 1:1 비교하는 체크섬 검증은 아니며, 위에 적은 집계·범위 검증이다. 원본 결과표도 함께 보관해 추후 재현할 수 있다.

디스크 확인 시 `seatunnel/output/production_orders_200m_local`은 약 1.5GB, OOM 기록은 약 2.4GB였고 Mac에 약 251GB 여유가 있었다. 이번 힙 문제 해결을 위해 기존 output을 삭제할 필요는 없었다.

## 공식 코드 근거

- [SeaTunnel 2.3.13 IcebergSink](https://github.com/apache/seatunnel/blob/2.3.13/seatunnel-connectors-v2/connector-iceberg/src/main/java/org/apache/seatunnel/connectors/seatunnel/iceberg/sink/IcebergSink.java)
- [IcebergWriterFactory](https://github.com/apache/seatunnel/blob/2.3.13/seatunnel-connectors-v2/connector-iceberg/src/main/java/org/apache/seatunnel/connectors/seatunnel/iceberg/sink/writer/IcebergWriterFactory.java)
- [SQLTransform](https://github.com/apache/seatunnel/blob/2.3.13/seatunnel-transforms-v2/src/main/java/org/apache/seatunnel/transform/sql/SQLTransform.java)

## JSON·Avro·Parquet 파일 탐색 노트북 (2026-10-15)

`analysis/read_parquet.ipynb`에서 현재 HMS 포인터부터 파일들을 따라간다. 실행 방법은 README의 노트북 안내 참고. live/evidence 모드 모두 실행 확인했다.

실제 metadata 버전은 초기 빈 테이블 JSON 1개와 2,500만 행씩 추가한 네 커밋 JSON 4개다. 스냅샷별 manifest list는 1/2/3/4개의 manifest를 참조하며 기존 manifest를 재사용한다. 현재 상태는 JSON 1개 → manifest list 1개 → manifest 4개 → Parquet 4개다. Parquet footer 합계는 100,000,000행, 실제 샘플은 각 파일 5행이다. 이 검증은 전체 데이터 재스캔이 아니며 기존 집계 검증과 구분한다. 대상 17개 파일은 SHA-256 대조로 내용 보존을 확인했다. 증거: `evidence/notebook/production-100m/execution.json`.
