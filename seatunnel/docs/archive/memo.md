## 세션 요약: 2026-09-15 SeaTunnel 실습

### 추가 검증: Local 힙과 OOM (2026-09-15 오후)

- 사용자의 승인으로 현재 P8 2억 행 설정을 Local 512MiB와 Local 3GiB에서 순차 실행했다. 두 실험 모두 G1GC로 맞췄으며 기존 Local의 기본 GC까지 그대로 재현한 것은 아니다.
- Local 512MiB: 약 4,300만 행에서 `OutOfMemoryError: Java heap space` 재현. Parquet 쓰기 경로의 객체 할당 실패를 확인했다. OOM 덤프에 Writer 46개와 Writer에서 참조 가능한 byte[] 약 369.7MiB를 확인했다. 파일 전환 뒤에도 Writer를 보관하고 커밋 시 닫는 2.3.13 구현을 대조했다.
- 엔진의 실패/재시도를 관측한 뒤 512MiB 실험 컨테이너를 수동 종료했다. 이 컨테이너의 exit=137은 수동 종료 결과이며 `OOMKilled=false`다.
- Local 3GiB: **FINISHED, 227초, 읽기/쓰기 200,000,000, 실패 0**. Parquet 200개, 메타데이터 2억 행, 1,558,402,577바이트. Job ID `1152134530241396737`.
- 따라서 “2억 행은 Local로 불가능해서 Cluster가 필요하다” 또는 “Cluster로 바꾸면 OOM이 해결된다”는 발표 주장은 사용하지 않는다. Cluster에서 실행·작업 배치를 검증한 사실은 유효하다.
- 실험 보고서/로그 읽기: `docs/local-heap-oom-study.md`. 원본 로그, GC 로그, JVM 옵션, 힙 덤프, 별도 Parquet 결과: `output/oom-study/20260915/`. 기존 잡 설정과 기존 결과는 유지했다.
- 두 HTML 학습 폴더(`cdc-flow-site`, `cluster-learning`)는 내용만 확인했고 삭제 승인은 아직 받지 않았으므로 보존 중이다.

### 이전 정리

- **끝낸 것**:
  - SeaTunnel 2.3.13 기반 PostgreSQL → Parquet 배치 실습을 정리함.
  - Zeta Engine 클러스터 모드로 2개 노드(`seatunnel-node1`, `seatunnel-node2`)를 구성하고, 약 2억 행의 PostgreSQL 데이터를 Parquet으로 처리함.
  - 최신 실행 로그에서 `parallelism=8`, `partition_num=8`, `fetch_size=5000`, `Total Read=200,000,000`, `Total Write=200,000,000`, `Total Failed=0`, `FINISHED`, 총 431초를 확인함.
  - `partition_num`은 JDBC 읽기 파티션 수, `parallelism`은 동시 작업 병렬도, `fetch_size`는 JDBC fetch 단위라는 차이를 정리함.
  - 2노드 클러스터에 작업이 제출되었다는 사실은 확인했지만, 노드별 처리량이 항상 균등하거나 두 노드가 반드시 모두 데이터 처리를 맡는 것은 아님을 확인함. 실제 배치는 Zeta 스케줄러와 slot 상태가 결정함.
  - `run-cluster-job.sh`는 임시 작업 제출 컨테이너를 실행하고, `hazelcast-client.yaml`을 통해 기존 Zeta 클러스터에 Job을 제출하는 구조로 주석을 보완함.
  - `docs/seatunnel-introduction-and-cluster-batch.md`에 SeaTunnel 정의, Source–Transform–Sink, Zeta/Flink/Spark 비교, Docker 구성, JVM/커넥터 동작, 일반 배치와 2억 행 클러스터 배치 흐름을 정리함.
  - `jobs/01_postgres_to_parquet.conf`에 SQL Transform 예시를 추가해 `product_name`을 대문자로 변환하고, `WHERE quantity >= 5` 같은 필터를 Source query 또는 Transform에서 적용할 수 있음을 확인함.

- **다음에 할 것**:
  - `docs/seatunnel-introduction-and-cluster-batch.md`를 바탕으로 그림 중심의 발표 자료(PPT) 초안 작성.
  - 발표 시연 순서 확정: 기본 batch DB → Parquet, 2억 행 cluster batch, CDC 변경 이력 → Parquet, CDC DB → DB.
  - 필요하면 각 Zeta 노드 로그를 수집해 실제 Source Task와 Sink/Commit Task가 어느 노드에 배치됐는지 확인.
  - Spark는 현재 Zeta 실습과 별개로, 기존 Spark 인프라가 있을 때 SeaTunnel 파이프라인을 Spark 엔진으로 실행하는 선택지라는 수준부터 학습. Spark 엔진을 새로 구축하기 전에는 배치/CDC 발표 범위를 Zeta 중심으로 유지.

- **막힌 부분/주의할 점**:
  - `partition_num=8` 또는 노드 2개만으로 작업이 노드에 균등 분산된다고 설명하지 않는다. 노드별 처리량은 각 노드 로그나 모니터링 지표 없이는 확정할 수 없다.
  - `-m cluster`는 Spark cluster mode가 아니라 SeaTunnel Zeta cluster mode다.
  - LocalFile Parquet은 일반적으로 변경 이벤트를 append하는 파일 sink이므로, JDBC Sink처럼 기존 행을 UPDATE/DELETE해 최신 상태를 유지하는 저장소로 설명하지 않는다.
  - 대용량 LocalFile Sink에서는 `tmp_path`와 최종 `path`가 모든 노드에서 접근 가능한 공유 경로인지 확인한다. 노드별 로컬 디스크를 사용하면 임시 파일 이동·커밋 결과가 분리될 수 있다.
  - 새 배치 결과를 검증할 때는 기존 Parquet 파일과 섞이지 않도록 출력 폴더를 비우거나 실행별 별도 경로를 사용한다.
  - Spark는 SeaTunnel 2.3.13 기준 CDC 실습 엔진으로 사용하지 않고, Spark 런타임·클러스터·드라이버 배포가 별도로 필요하다는 점을 구분한다.

- **참고 파일**:
  - `docs/seatunnel-introduction-and-cluster-batch.md`
  - `docs/200m-batch-execution-study.md`
  - `docs/200m-p8-verification.md`
  - `jobs/01_postgres_to_parquet.conf`
  - `jobs/12_postgres_200m_to_parquet_cluster.conf`
  - `scripts/run-cluster-job.sh`
