# cluade-test

이 저장소는 두 개의 별개 프로젝트를 담고 있다.

## 현재 주력: openmetadata/ — OpenMetadata 로컬 연동 시연

Docker로 OpenMetadata 공식 스택 + 소스 Postgres를 띄워서 데이터 카탈로그 자동 수집(ingestion)을 시연하는 프로젝트.
**현재 대부분의 작업이 여기서 이루어진다** (docker-compose 설정, Airflow DAG, 문서 정비).

자세한 설계/근거는 [openmetadata/docs/openmetadata-demo-design.md](openmetadata/docs/openmetadata-demo-design.md) 참고.

- 기동: `cd openmetadata && ./scripts/up.sh` / 종료: `./scripts/down.sh [--volumes]`
- 구성:
  - `docker-compose.yml` — OpenMetadata 공식 배포본 **그대로** (직접 수정 금지, 버전 올릴 땐 새 GitHub Release로 재다운로드)
  - `docker-compose.dags.yml` — 커스텀 DAG(`dags/`)를 ingestion(Airflow) 컨테이너에 얹는 오버레이. **반드시 `docker-compose.yml`과 같이 `-f` 두 개로** 올려야 커스텀 DAG가 보인다 (하나만 올리면 재생성 시 DAG가 안 보임 — 파일이 지워지는 건 아니고, 두 파일을 같이 다시 올리면 복구됨)
  - `docker-compose.sourcedb.yml` — 카탈로그 대상 소스 Postgres (`retaildb`, 호스트 포트 5432)
  - `dags/customer_sales_summary_join.py` — customers+sales 조인 데모 DAG. **Airflow DAG를 새로 만들거나 수정할 때는 `~/projects/.claude/rules/dag-style.md`의 공통 규칙(TaskFlow API, task는 얇게/로직은 모듈로, flow는 맨 마지막에 `>>`)도 함께 적용된다.**
  - `sourcedb-init/generate_seed_sql.py` — `data/*.csv` → seed SQL 재생성 (`etl.py`와 동일한 정제 규칙 적용)
- 접속 정보:
  - OpenMetadata UI: `localhost:8585` (`admin@open-metadata.org` / `admin`)
  - Airflow UI: `localhost:8080` (`admin` / `admin`)
  - 소스 Postgres: `localhost:5432` (`retaildb` / `demo` / `demo`)
- OpenMetadata 컨테이너에서 소스 Postgres에 접속할 때는 컨테이너명이 아니라 `host.docker.internal` 사용 (서로 다른 compose 프로젝트 = 다른 docker network라서 호스트를 경유해야 함). 이 구성은 Docker Desktop(Mac) 전용이며 리눅스 네이티브 환경에서는 별도 네트워크 설정이 필요함.

## 과거 예제: etl.py — 표준 라이브러리 기반 ETL 토이 프로젝트

`data/sales_raw.csv`를 읽어 정제한 뒤 `data/sales.db`(SQLite)에 적재. 외부 의존성 없이 `csv`/`sqlite3`/`pathlib`만 사용.
지금은 주력 작업이 아니지만 코드/데이터는 저장소에 남아 있고, `openmetadata/` 데모의 시드 데이터로 재사용된다.

- 실행: `python etl.py` (매번 `sales` 테이블을 DROP 후 재생성 — 멱등적 재실행 가능)
- 주의: `transform()`은 `order_id` 중복 행과 `customer`/`quantity`가 빈 값인 행을 **에러 없이 조용히 걸러낸다**. `quantity`/`unit_price`는 각각 `int()`/`float()`로 강제 변환하므로 숫자가 아닌 값이 있으면 예외가 발생한다.
- "표준 라이브러리만 사용" 제약은 **이 `etl.py`에만 해당**하며, `openmetadata/` 쪽 스크립트(Docker, psycopg2 등 외부 의존성 사용)에는 적용되지 않는다.
