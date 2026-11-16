# SeaTunnel 팀 시연 — 네 가지 구성

| 순서 | 설정 | 내용 | 보존된 결과 |
|---|---|---|---|
| 1 | `01_postgres_to_parquet.conf` | PostgreSQL JDBC → 로컬 Parquet, 기본 배치 | `output/production_orders` |
| 2 | `12_postgres_200m_to_parquet_cluster.conf` | 2억 행, 4개 JDBC 파티션, Zeta 클러스터 배치 | `output/production_orders_200m` |
| 3 | `15_postgres_10m_cdc_insert_update.conf` | 1천만 행 테이블에서 시작 이후 INSERT·UPDATE_AFTER만 누적 | `output/cdc_10m_insert_update` |
| 4 | `09_postgres_cdc_to_jdbc_sink.conf` | CDC INSERT·UPDATE·DELETE를 대상 PostgreSQL 테이블에 반영 | `srcdb.public.cdc_demo_orders_replica` (DB에서 조회) |

## 실행

프로젝트 루트에서 실행한다. 원본 DB와 Docker 네트워크가 준비되어 있어야 한다.

```bash
./scripts/run-job.sh jobs/01_postgres_to_parquet.conf
# 클러스터가 없을 때만 시작. start-cluster.sh는 기존 두 노드 컨테이너를 제거하고 재생성한다.
./scripts/start-cluster.sh
./scripts/run-cluster-job.sh jobs/12_postgres_200m_to_parquet_cluster.conf
./scripts/run-cdc-job.sh jobs/15_postgres_10m_cdc_insert_update.conf
./scripts/run-cdc-job.sh jobs/09_postgres_cdc_to_jdbc_sink.conf
```

네 명령을 한꺼번에 실행하는 목록이 아니다. 시연할 잡을 골라 실행한다.
재실행 전 기존 Parquet 결과와 섞이지 않도록 새 출력 경로를 설정하거나 기존 결과를 별도 보관한다.

## 설명할 핵심

- 01: 배치 조회 결과를 Parquet으로 저장한다.
- 12: 클러스터 노드 수와 작업 분배는 별개다. 마지막 271초 실행에서는 읽기·쓰기 4개가 Node 2에, 커밋이 Node 1에 배치됐다. 공유 `tmp_path`로 전체 200개 파일이 정상 커밋됐다.
- 15: 최신 테이블 상태가 아니라 변경 후 값의 이력이다. `cdc_op`를 보존하며 DELETE와 UPDATE_BEFORE를 제외한다. `latest` 시작이므로 초기 1천만 행은 출력되지 않는다. 기존 검증 결과는 INSERT 150 + UPDATE_AFTER 150 = 300행이었다. 현재 `tests/manual/cdc_10m_events.sql`은 새 시연용 50000000번대에서 INSERT 200 + UPDATE 100 + DELETE 50을 발생시키며, 15번 결과는 INSERT 200 + UPDATE_AFTER 100 = 300행이 예상된다.
- 09: 원본 `cdc_demo_orders` → 대상 `cdc_demo_orders_replica`. 원본은 현재 10,000,002행이므로 `initial` 실행 시 전체 초기 스냅샷을 읽는다. 이전 소규모 실습 때보다 무거워졌으며, 대상 테이블 준비 및 JVM 메모리 확인 후 실행한다. 이번 정리에서는 DB 상태를 재검증하지 않았다.

현재 배치 로컬 래퍼 `run-job.sh`는 `cluster/jvm_client_options`를 마운트하여 초기 힙 1GiB / 최대 힙 3GiB로 실행한다. 백그라운드로 실행하며, 종료된 컨테이너도 보존한다. 실행 시 출력되는 `docker logs -f <컨테이너 이름>`으로 진행 및 종료 후 로그를 확인한다. 실행마다 고유한 이름을 사용하므로 이전 컨테이너를 자동 삭제하지 않는다. 확인이 끝난 컨테이너는 `docker rm <컨테이너 이름>`으로 정리한다. 배치는 완료 후 Exited 상태가 되며, 로그를 보려면 계속 실행 중일 필요는 없다.

`02_postgres_to_parquet_100m.conf`도 이 래퍼로 실행할 수 있다. 1억 행 테이블 `production_orders_100m` 전체 조회, 병렬도 1, JDBC 파티셔닝 없음이며 실제 행 수는 DB에 따라 결정된다. 출력은 `output/production_orders_100m`다. 별도 Transform 없이 JDBC Source를 Parquet Sink에 직접 연결한다.

`run-cdc-job.sh`는 이번 변경 대상이 아니며 이미지 기본 JVM 옵션을 사용한다. 클러스터 서버는 별도 `cluster/jvm_options`를 사용한다. 3GiB 설정도 모든 규모의 작업에서 OOM 방지를 보장하지 않으며 컨테이너·VM에 힙 외 메모리 여유가 필요하다.
CDC 재시작과 체크포인트 복구는 별개다. 운영용 복구 설정은 추가 검증이 필요하다.

## PPT 8번 Flow Chart 참고

8번 슬라이드의 `conf → Parquet` 흐름은 큰 틀에서 맞다. 정확한 실행 관계는 **`seatunnel.sh`(셸 스크립트) → `java` 명령으로 JVM 시작 → JVM이 `seatunnel-starter.jar`의 SeaTunnelClient 실행 → conf 파싱·Zeta 계획·connector JAR 로드 → Source/Transform/Sink Task**이다. JAR가 JVM을 부르는 것이 아니며 JAR마다 JVM이 생기는 것도 아니다.

Zeta Engine과 JVM은 같은 계층이 아니다. Zeta는 JVM 위에서 실행되는 SeaTunnel 엔진 코드이고, JDBC·Parquet 커넥터도 같은 Java 프로세스에 로드된다. 처리 중인 `SeaTunnelRow`, 큐, Parquet Writer 버퍼는 JVM 힙을 사용한다. `-Xmx512m` 또는 `-Xmx3g`는 해당 JVM의 최대 힙이지 컴퓨터 RAM 전체가 아니다.

`tmp_path → rename → output`은 파일 병합이 아니라 커밋 시 완성된 파일을 최종 경로로 확정하는 단계다. 마지막의 “starter JAR만 바꾸면 Spark/Flink로 엔진 교체” 문장은 사용하지 않는다. 엔진별 실행 스크립트·runtime·배포 환경을 별도로 구성해야 한다. 상세 수정 지침은 `docs/local-heap-oom-study.md`의 **PPT 8번 Flow Chart 검토** 절을 따른다.

## 참고 자료

- `docs/archive/cdc-10m-insert-update-verification.md`: 이전 CDC 검증 기록
- `tests/manual/cdc_10m_events.sql`: 검증용 INSERT/UPDATE/DELETE SQL
- `jobs/sink-examples/`: 실행 검증하지 않은 외부 저장소 템플릿
- `docs/archive/demo-cleanup-manifest.json`: 삭제·이동 목록

기존 docs와 analysis/read_parquet.ipynb는 실험 이력이다. 삭제된 옛 경로를 참조하는 셀/설명이 있을 수 있으므로 현재 시연 기준은 이 문서를 사용한다.
