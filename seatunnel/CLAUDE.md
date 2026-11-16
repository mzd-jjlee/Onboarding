# seatunnel/ — Apache SeaTunnel ETL/ELT 실습

팀 기술 소개를 위해 SeaTunnel을 로컬 Docker로 실습했다: PostgreSQL/MySQL JDBC 배치 → Parquet, JVM 힙과 OOM, JDBC 분할·병렬도, Zeta 클러스터, PostgreSQL CDC. Apache NiFi와도 비교했다.
상위 규칙(`~/projects/.claude/CLAUDE.md`, `Onboarding/CLAUDE.md`)도 함께 적용된다. 포트 전체 지도는 `../CLAUDE.md`.

## 먼저 읽을 것

- 문서 안내와 발표 기준 문서: `docs/README.md` (PPT 수정은 이 문서들을 기준으로 한다)
- 시연 잡 4개와 실행 방법: `jobs/README.md`
- 발표 자료: `docs/slides/seatunnel-practice-share.pptx` (사용자가 PowerPoint에서 편집 중일 수 있다. 열려 있는지 확인 없이 덮어쓰지 않는다)
- `docs/archive/`는 이전 가이드·실험 기록이다. 과거 결과 대조가 필요할 때만 본다.

## 원본 DB와 실행

- 원본 DB: `docker compose -f docker-compose.sourcedb.yml up -d postgres` (MySQL이 필요하면 `mysql`도). DB `srcdb`, 계정은 compose 파일 참조.
  - Postgres `localhost:5440`, MySQL `localhost:3306`. **MySQL 3306은 OpenMetadata MySQL과 겹쳐 동시에 띄울 수 없다.**
  - `restart: unless-stopped`: `stop`으로 멈추면 다시 켜지지 않는다.
- 잡 실행: `scripts/run-job.sh`(배치, 힙 3GiB), `run-cdc-job.sh`(CDC, 장시간 실행), `start-cluster.sh` / `run-cluster-job.sh` / `stop-cluster.sh`(Zeta 클러스터).
  - 모두 `apache/seatunnel:2.3.13`을 `seatunnel_default` 네트워크에서 실행한다. 잡 설정의 DB 주소는 컨테이너 이름(`postgres:5432`)이다.
  - 실행 컨테이너는 실행마다 새 이름으로 남는다(로그 보존). 확인 후 `docker rm`으로 정리한다.
- 결과: `output/`(Parquet, git 제외). 재실행 전 기존 결과와 섞이지 않게 출력 경로를 바꾸거나 기존 결과를 보관한다.

## 다른 프로젝트와 공유하는 것

- **이 Postgres는 `Onboarding/iceberg`의 대용량 원본이기도 하다** (`production_orders_100m` 1억 행, `production_orders` 200만 행). 테이블을 바꾸거나 지우기 전에 iceberg 쪽 영향을 확인한다. iceberg 컨테이너에서는 `host.docker.internal:5440`으로 접속한다.
- `production_orders`(200만 행)는 초기화 SQL(`sourcedb-init/postgres/01_init.sql`)이 만든 테이블이고, `_10m/_100m/_200m`, `cdc_demo_orders`는 이후 실습에서 추가됐다. 볼륨 `seatunnel_postgres-data`를 지우면 모두 사라진다.

## CDC 주의

- Replication slot은 CDC 잡의 읽은 위치를 Postgres에 남기는 기록이다. 비활성 slot도 WAL을 붙잡아 디스크를 차지한다.
- 현재 slot: `seatunnel_cdc_10m_iu_test`(잡 15). 잡 09는 `seatunnel_cdc_dbsink_demo`를 쓰며 실행 시 생성된다.
  2026-11-12 어떤 잡도 참조하지 않던 `seatunnel_cdc_insert_update`(WAL 1.3GB 점유)를 사용자 허용 후 삭제했다.
- 잡 09(`startup.mode = "initial"`)는 원본 1,000만 행 전체 스냅샷부터 읽는다. 메모리와 대상 테이블을 확인한 뒤 실행한다.
- 검증용 변경 SQL: `tests/manual/cdc_10m_events.sql`.
