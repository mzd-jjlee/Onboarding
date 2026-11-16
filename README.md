# Onboarding
메가존 온보딩 중에 수행한 과제 내역. 팀 기술 소개 발표를 위해 공부하고 로컬 Docker로 직접 구축했다.

| 폴더 | 주제 | 발표 자료 |
|---|---|---|
| [openmetadata/](openmetadata/) | 데이터 카탈로그(OpenMetadata) 로컬 시연 | `openmetadata/docs/openmetadata-onboarding-slides.pptx` |
| [seatunnel/](seatunnel/) | ETL/ELT 도구 Apache SeaTunnel 실습 (배치, OOM, 병렬, CDC, 클러스터) | `seatunnel/docs/slides/seatunnel-practice-share.pptx` |
| [iceberg/](iceberg/) | 로컬 데이터 레이크하우스 (SeaTunnel → Iceberg·HMS → Trino → Superset, MinIO, Airflow) | `iceberg/presentation/local-lakehouse.html` |

루트의 `etl.py`·`data/`는 초기 ETL 토이 예제이고, `docker-basics-guide.yaml`은 Docker/Compose 학습 문서다.
각 프로젝트의 실행 방법은 폴더 안 README·CLAUDE.md·docs를 본다. 프로젝트 간 포트 지도는 [CLAUDE.md](CLAUDE.md).
