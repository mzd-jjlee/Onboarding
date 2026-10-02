# OpenMetadata 로컬 연동 시연 설계

## 목적
"OpenMetadata가 뭔지, 왜 쓰는지, 실제로 어떻게 쓰는지"를 로컬 Docker 환경에서 보여주는 온보딩 시연.
기존 ETL 프로젝트(`etl.py`)와는 독립적이지만, 같은 저장소의 `data/sales_raw.csv`, `data/customers_raw.csv`를
"실제로 카탈로그화할 데이터"로 재사용해서 이야기를 연결한다: *"우리 ETL이 다루는 이 데이터를,
OpenMetadata가 어떻게 검색 가능하게 만들어주는가"*.

## OpenMetadata가 무엇이고 왜 필요한가 (시연 스크립트용 한 줄 요약)
OpenMetadata는 오픈소스 **데이터 카탈로그**다. 여러 DB/웨어하우스/BI 도구에 흩어진 테이블·컬럼 메타데이터를
자동으로 수집(ingestion)해서 한 곳에서 검색·문서화·리니지 추적을 할 수 있게 해준다. 데모에서 보여줄 핵심 가치:
1. **자동 수집** — DB 커넥션 정보만 넣으면 스키마/테이블/컬럼을 자동으로 긁어옴 (수작업 문서화 불필요)
2. **검색/디스커버리** — "sales라는 테이블이 어디 있더라"를 UI에서 검색
3. **스케줄링 가능한 파이프라인** — Airflow 기반으로 주기적 재수집을 UI에서 클릭만으로 설정
4. **리니지/오너십/설명** — 테이블에 설명, 태그, 오너를 달아 협업 문서화

## 아키텍처

```
                 ┌───────────────────────────────────────────┐
                 │   OpenMetadata 공식 스택 (docker-compose.yml)  │
                 │   - mysql (메타데이터 저장소)                    │
                 │   - elasticsearch (검색 인덱스)                 │
                 │   - openmetadata-server  → UI :8585         │
                 │   - ingestion (Airflow)  → UI :8080          │
                 └───────────────────┬───────────────────────┘
                                     │ host.docker.internal:5432 로 접속
                                     │ (별도 compose 프로젝트라 다른 docker network)
                 ┌───────────────────▼───────────────────────┐
                 │  소스 Postgres (docker-compose.sourcedb.yml)  │
                 │  DB: retaildb  (호스트 포트 5432 공개)          │
                 │  - customers 테이블                           │
                 │  - sales 테이블 (FK → customers)              │
                 └───────────────────────────────────────────┘
```

두 스택을 별도 `docker compose` 프로젝트로 분리했다: OpenMetadata 쪽은 공식 배포 파일을 그대로 두고,
소스 DB는 우리가 임의로 추가한 "카탈로그 대상"이라는 역할 구분을 명확히 하기 위해서다. 서로 다른
compose 프로젝트는 기본적으로 다른 docker network에 있으므로, OpenMetadata 컨테이너에서 소스 Postgres에
접속할 때는 컨테이너 이름이 아니라 **호스트를 경유**(`host.docker.internal:5432`, Docker Desktop 전용 기능)한다.

## 결정 사항과 근거

| 결정 | 선택 | 이유 |
|---|---|---|
| OpenMetadata 배포 방식 | **공식 Quickstart** (GitHub Release의 `docker-compose.yml` 그대로 사용) | 온보딩 목적상 "UI에서 ingestion pipeline을 만들고 스케줄링하는" 실제 사용 경험을 보여줘야 함. 경량 CLI-only 구성은 이 핵심 경험을 생략하게 됨. 리소스(수GB, 기동 수 분)는 1회성 데모 비용으로 감수 |
| 버전 고정 | `1.13.3-release` (조회 시점 최신 stable) | 재현 가능성 확보. RC(2.0.0-rc*)는 제외 |
| 소스 DB 종류 | Postgres | OpenMetadata 커넥터 데모로 흔히 쓰이고, 프로젝트 CLAUDE.md의 "표준 라이브러리만" 제약은 `etl.py`에 한정되므로 이 데모 영역에서는 해당 없음 |
| 시드 데이터 | 기존 `data/sales_raw.csv` + `data/customers_raw.csv` 재사용, `etl.py`와 동일한 정제 규칙 적용 | ETL 프로젝트와 스토리 연결 ("이 프로젝트가 다루는 데이터를 카탈로그화") |
| 커스텀 DAG 등록 방식 | `docker-compose.dags.yml` 오버레이로 `openmetadata/dags/`를 `/opt/airflow/dags/custom`에 bind-mount | `docker cp`로 실행 중 컨테이너에 직접 넣는 방법도 가능하지만 git에 남지 않고 컨테이너 재생성 시 사라짐. 오버레이는 파일이 저장소에 커밋되어 재현 가능하고, 공식 `docker-compose.yml`은 여전히 손대지 않는다는 원칙을 지킨다 |

## 저장소 구성

```
openmetadata/
  docker-compose.yml            # 공식 배포본 그대로 (수정 금지, 버전 올릴 때만 재다운로드)
  docker-compose.dags.yml       # ingestion(Airflow) 컨테이너에 커스텀 DAG 폴더를 얹는 오버레이 (공식 파일 비수정 원칙 유지)
  docker-compose.sourcedb.yml   # 소스 Postgres (커스텀)
  dags/
    customer_sales_summary_join.py  # customers+sales 조인 → customer_sales_summary 파생 테이블 생성 데모 DAG
  sourcedb-init/
    generate_seed_sql.py        # data/*.csv → 01_init.sql 재생성 (etl.py와 동일 정제 규칙, stdlib only)
    01_init.sql                 # 생성물. Postgres 컨테이너 최초 기동 시 자동 실행됨
  scripts/
    up.sh                       # seed 재생성 + 소스 DB + OpenMetadata(+dags 오버레이) 순서로 기동
    down.sh                     # 종료 (--volumes 옵션으로 데이터까지 삭제)
```

## 실행 절차

### 0) 사전 준비 (이 머신에는 아직 없음 — 최초 1회 필요)
이 저장소를 만든 머신에는 **Docker가 설치되어 있지 않았다** (`docker: command not found`). 진행 전에:
- [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/) 설치
- Docker Desktop 설정에서 **메모리 6GiB 이상, vCPU 4개 이상** 할당 (공식 최소 요구사항)

### 1) 기동
```bash
cd openmetadata
./scripts/up.sh
```
내부적으로: (a) CSV에서 seed SQL 재생성 → (b) 소스 Postgres 기동 → (c) OpenMetadata 공식 스택 기동.
서버가 완전히 준비되기까지 1~2분 걸릴 수 있다.

`up.sh`를 안 쓰고 `docker compose`를 직접 치는 경우, OpenMetadata 쪽은 **반드시 두 파일을 같이** 넘겨야
커스텀 DAG(`openmetadata/dags/`)가 Airflow에 마운트된다. 하나만 넘기면(`-f docker-compose.yml`만) 컨테이너가
재생성될 때 DAG가 안 보인다 — 파일 자체가 지워지는 건 아니고, 다음에 두 파일을 같이 넘겨서 다시 올리면 복구된다.
```bash
docker compose -f docker-compose.yml -f docker-compose.dags.yml up -d
```
소스 Postgres는 원래대로 별도 파일이라 그대로 명시한다: `docker compose -f docker-compose.sourcedb.yml up -d`

### 2) OpenMetadata UI 접속
- http://localhost:8585 , 로그인: `admin@open-metadata.org` / `admin`

### 3) Postgres 커넥터 등록 (UI에서 클릭만으로 진행 — YAML/CLI 불필요)
Settings → Services → Databases → **Add New Service** → Postgres 선택 후:
- Host and Port: `host.docker.internal:5432`
- Username / Password: `demo` / `demo`
- Database: `retaildb`

저장 후 **Add Ingestion**으로 Metadata Ingestion 파이프라인을 만들고 실행(또는 스케줄)하면
`customers`, `sales` 두 테이블이 몇 초 안에 카탈로그에 나타난다. 여기가 시연의 핵심 장면이다.

### 4) (확장) 조인 DAG로 파생 테이블을 만들어 재-ingestion 확인
DAG 하나가 이미 준비되어 있다: `openmetadata/dags/customer_sales_summary_join.py`.
`customers`+`sales`를 조인해 `customer_sales_summary`(고객별 주문 수/합계) 테이블을 retaildb에 만든다.
"ETL/파이프라인이 만든 새 테이블도 OpenMetadata가 알아서 카탈로그에 잡아낸다"를 보여주는 것이 목적이다.

- Airflow UI(http://localhost:8080, `admin`/`admin`)에서 `customer_sales_summary_join` DAG를 찾아
  Unpause 후 Trigger. `psycopg2`로 `host.docker.internal:5432`(retaildb)에 접속해
  `DROP TABLE IF EXISTS` → `CREATE TABLE AS SELECT ... JOIN ...`을 실행하므로 재실행해도 안전하다(멱등적).
- DAG가 성공하면 OpenMetadata UI에서 등록해둔 Postgres 서비스의 **Ingestion Pipeline을 다시 실행**한다
  (Settings → Services → Databases → 해당 서비스 → 기존 pipeline → Run, 또는 새로 Add Ingestion).
  몇 초 후 `customer_sales_summary`가 `customers`, `sales`와 함께 카탈로그에 나타난다.

이 DAG는 `/opt/airflow/dags`(named volume, OpenMetadata가 자체 ingestion pipeline DAG를 자동 생성해 넣는 공간)를
직접 건드리지 않고, `docker-compose.dags.yml`로 `/opt/airflow/dags/custom` 서브디렉터리에 호스트의 `openmetadata/dags/`를
bind-mount해서 추가했다. Airflow는 DAGS_FOLDER 하위를 재귀적으로 스캔하므로 별도 설정 없이 인식된다.
`scripts/up.sh`/`down.sh`가 이미 `-f docker-compose.yml -f docker-compose.dags.yml`로 두 파일을 함께 사용한다.

### 5) 종료
```bash
./scripts/down.sh            # 컨테이너만 종료 (데이터 보존)
./scripts/down.sh --volumes  # 데이터까지 완전 삭제
```

## 참고한 공식 문서
설계 전 아래 공식 문서를 직접 확인해서 URL/버전/기본 계정 정보를 검증했다 (추측 없이 실제 문서 기준):
- [Try OpenMetadata in Docker (Quick Start)](https://docs.open-metadata.org/quick-start/local-docker-deployment) — 설치 절차, 사전 요구사항(Docker ≥20.10, Compose ≥2.1.1, 메모리 6GiB), 기본 로그인 정보 출처
- [PostgreSQL Connector](https://docs.open-metadata.org/connectors/database/postgres) — 커넥션 필드, 필요 권한, UI 기반 ingestion 가능 여부 확인
- [GitHub Releases — open-metadata/OpenMetadata](https://github.com/open-metadata/OpenMetadata/releases) — `docker-compose.yml` 배포 자산과 최신 stable 태그(`1.13.3-release`) 확인

향후 이런 종류의 작업(관리형 오픈소스 스택을 로컬에 붙이는 시연)을 할 때는:
1. 회사/OSS 프로젝트의 **공식 docs 사이트의 "Quick Start"/"Getting Started" 페이지**를 최우선으로 본다 — 블로그/서드파티 튜토리얼은 버전이 낡았을 가능성이 높다.
2. docker-compose 같은 배포 산출물은 **직접 손으로 재현하지 말고 공식 GitHub Release 자산을 그대로 다운로드**해서 커밋한다 (오타/누락 위험 제거, 버전 추적 용이).
3. 커넥터/통합 문서는 "필요 권한(privileges)"과 "UI vs CLI/YAML 필요 여부"를 반드시 확인 — 데모 난이도에 직접 영향을 준다.

## 알려진 제약
- `host.docker.internal`은 Docker Desktop(Mac/Windows) 전용 동작이다. 리눅스 네이티브 Docker 엔진에서는
  `--add-host=host.docker.internal:host-gateway`를 compose에 추가하거나, 두 compose를 같은 네트워크에
  묶어야 한다. 이 저장소는 Mac 환경 기준으로 설계했다.
- `openmetadata/docker-compose.yml`은 공식 배포 파일 그대로이므로, 버전을 올리고 싶으면 새 release 태그로
  다시 다운로드해서 덮어쓴다 (수동 편집하지 않는다).
