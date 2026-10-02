# SeaTunnel 문서 안내

현재 발표와 실습 정리에서 바로 사용하는 문서는 `docs/` 아래에 둔다.

## 발표용 최신 문서

| 문서 | 용도 |
|---|---|
| [seatunnel-overview.md](seatunnel-overview.md) | SeaTunnel의 목적, Source–Transform–Sink, Zeta 개념 소개 |
| [local-heap-oom-study.md](local-heap-oom-study.md) | Local 512MiB OOM과 3GiB 성공 실험, 클러스터 해석 |
| [java-jvm-heap-and-seatunnel-oom.md](java-jvm-heap-and-seatunnel-oom.md) | Java·JAR 실행 구조, JVM 힙과 Docker 제한 구분, OOM 발표 멘트 |
| [seatunnel-jdbc-fetch-partition-parallelism.md](seatunnel-jdbc-fetch-partition-parallelism.md) | LIMIT·fetch size 차이, JDBC 파티셔닝·병렬도, Airflow/Python 비교와 config 발표 멘트 |
| [seatunnel-spark-engine-and-cdc-limits.md](seatunnel-spark-engine-and-cdc-limits.md) | Zeta·Flink·Spark 비교와 CDC 엔진 제약 |
| [cdc_seatunnel.md](cdc_seatunnel.md) | PostgreSQL CDC 실습 흐름, 로그, 캡처 화면, PPT 반영 지침 |
| [seatunnel-vs-nifi-comparison.md](seatunnel-vs-nifi-comparison.md) | Apache NiFi와의 아키텍처/생산성/사용사례 비교, 우리 팀 상황에 대한 시사점 |
| [nifi-architecture-and-slide-guide.md](nifi-architecture-and-slide-guide.md) | NiFi 핵심 구조·대기열·오류 처리 설명과 발표 수정 가이드. 기존 NiFi 비교 문서와 충돌하는 내용은 이 문서의 정정 사항을 우선 적용 |

PPT 원본은 [slides/seatunnel-practice-share.pptx](slides/seatunnel-practice-share.pptx)이며, PPT 수정은 Claude가 담당한다. 위 문서들을 PPT 수정의 기준으로 사용한다.

## 보관 문서

[archive/](archive/)에는 삭제하지 않고 이동한 이전 가이드와 실험 기록이 있다. 내용 확인이나 과거 실행 결과 대조가 필요할 때만 참고한다.

- `200m-batch-execution-study.md`, `200m-p8-verification.md`: 과거 2억 행 클러스터 실행 증거
- `cdc-10m-insert-update-verification.md`: 이전 CDC 이벤트 검증 결과
- `seatunnel-introduction-and-cluster-batch.md`: 기존 소개·클러스터 설명 초안
- `seatunnel-batch-cdc-guide.md`, `seatunnel-db-to-parquet-guide.md`, `seatunnel-tutorial.md`: 상세 실습 가이드의 이전 버전
- `airflow-cluster-batch.md`: Airflow 확장 예제
- `memo.md`: 세션 작업 기록

보관은 삭제가 아니며, 필요하면 원래 위치로 되돌릴 수 있다. 새 발표 내용은 먼저 최신 문서에 반영하고, 보관 문서는 과거 사실을 확인하는 용도로 유지한다.
