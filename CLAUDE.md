# Onboarding — 메가존 온보딩 기술 실습 모음

팀 기술 소개 발표를 위해 공부하고 **로컬 Docker로 직접 구축해 본** 프로젝트 모음이다.
각 폴더는 독립된 프로젝트(별도 compose 프로젝트·별도 Docker 네트워크)이며, 세부 규칙은 각 폴더의 CLAUDE.md를 따른다.

## 프로젝트

| 폴더 | 주제 | 구성 | 발표 자료 | 세부 규칙 |
|---|---|---|---|---|
| `openmetadata/` | 데이터 카탈로그 로컬 시연 | OpenMetadata 공식 배포(서버·MySQL·Elasticsearch·수집용 Airflow) + 카탈로그 대상 원본 Postgres 2개 | `docs/openmetadata-onboarding-slides.pptx`, 대본 `docs/openmetadata-presentation-script.md` | `openmetadata/CLAUDE.md` |
| `seatunnel/` | ETL/ELT 도구 Apache SeaTunnel 실습 | 원본 Postgres·MySQL + SeaTunnel(배치 JDBC, 힙/OOM, 병렬 분할, CDC, 클러스터). NiFi 비교 | `docs/slides/seatunnel-practice-share.pptx` | CLAUDE.md 없음. 문서 안내 `seatunnel/docs/README.md` |
| `iceberg/` | 로컬 데이터 레이크하우스 구축 | PostgreSQL → SeaTunnel → Iceberg(Hive Metastore 카탈로그) → Trino → Superset, Airflow 스케줄링. 저장소는 처음 `./lake` 로컬 폴더, **새 데이터는 MinIO(S3 호환)** | `presentation/local-lakehouse.html`, `presentation/speaker-notes.md`, `presentation/local-lakehouse-deck-plan.md` | `iceberg/CLAUDE.md` |

루트의 나머지는 초기 학습 자료다.
- `etl.py` + `data/*.csv`: 표준 라이브러리만 쓰는 ETL 토이(CSV → SQLite `data/sales.db`). `data/*.csv`는 openmetadata 원본 DB 시드로 재사용된다. "표준 라이브러리만" 제약은 `etl.py`에만 해당한다.
- `docker-basics-guide.yaml`: Docker/Compose 읽기 안내서. 실행용 compose 파일이 아니다.
- `docs/`: `etl.py` 관련 문서.

## 프로젝트 사이의 연결

- **seatunnel 원본 Postgres(`localhost:5440`, DB `srcdb`)는 iceberg의 대용량 원본으로도 쓴다** (`production_orders_100m`, `production_orders` 200만 행). seatunnel 폴더에서 `docker compose -f docker-compose.sourcedb.yml up -d postgres`로 띄운다.
- 다른 compose 프로젝트의 서비스는 서비스 이름으로 찾을 수 없다. 컨테이너에서 **`host.docker.internal:<호스트 포트>`**로 접속한다 (Rancher Desktop에서 동작 확인).

## 호스트 포트 지도

| 포트 | 프로젝트 | 서비스 |
|---|---|---|
| 5432 / 5433 | openmetadata | 원본 Postgres `retaildb` / `manufacturingdb` |
| 3306 | openmetadata **와** seatunnel | OpenMetadata MySQL / seatunnel 원본 MySQL — **같은 포트라 동시에 띄울 수 없다** |
| 8080 | openmetadata | 수집용 Airflow UI |
| 8585 / 8586 | openmetadata | OpenMetadata UI / 관리 포트 |
| 9200 / 9300 | openmetadata | Elasticsearch |
| 5440 | seatunnel | 원본 Postgres `srcdb` |
| 15432 | iceberg | `catalog-db` (HMS 내부 DB) |
| 8081 / 8082 / 8088 | iceberg | Trino / Airflow / Superset |
| 9000 / 9001 | iceberg | MinIO API / 콘솔 |

새 포트를 공개할 때는 이 표와 겹치지 않게 하고, 추가하면 이 표도 갱신한다.

## 공통 운영 주의

- **`openmetadata/docker-compose.yml`은 `restart: always`**라 `stop`으로 멈춰도 Docker(Rancher Desktop)가 다시 켜지면 같이 뜬다. 안 쓸 때는 `down`으로 내린다.
- `docker compose down -v`(볼륨 삭제)는 사용자가 명시적으로 요청할 때만 한다. 각 프로젝트의 DB·카탈로그·적재 데이터가 볼륨에 있다.
- 발표 파일(`.pptx`)은 사용자가 PowerPoint에서 편집 중일 수 있다. 열려 있는지 확인 없이 덮어쓰지 않는다.
