# openmetadata/ — 프로젝트 배경

## 미션

팀장님 지시사항 (온보딩 첫 과제):

> Apache OpenMetadata (https://open-metadata.org/) 에 대해서
> 어떤 도구인지 / 왜 필요한지 / 실제로 어떻게 사용하는지 정도를
> 간단한 시연과 함께 소개해주시면 될 것 같아요!

발표 대상: 팀 내부 온보딩 공유. 발표일: 2026-09-03.

## 세션 시작 시 확인할 것

**작업을 시작하기 전에 `docs/memo.md`가 있으면 먼저 읽고, 직전 세션에서 어디까지 했는지 파악할 것.**
이 파일은 매 세션 종료 시 그 시점 기준으로 덮어써지는 인계 노트이며, "현재 진행 상태"의 유일한 출처다.
이 CLAUDE.md에는 진행 상태를 적지 않는다 (memo.md와 이중관리 방지).

## 핵심 산출물 위치

- `docs/openmetadata-overview.md` — OpenMetadata 개념 설명 문서 (무엇/왜/어떻게)
- `docs/openmetadata-demo-design.md` — 로컬 데모 환경 설계 근거
- `docs/openmetadata-onboarding-slides.pptx` — 발표용 슬라이드 (PowerPoint에서 사용자가 직접 편집 중일 수 있음 — 먼저 열려있는지 확인 없이 덮어쓰지 말 것)
- `docs/openmetadata-presentation-script.md` — 발표 대본(큐카드)
- `docs/memo.md` — 세션 간 작업 인계 노트 (최신 상태만 유지, 로그 아님)

## 실행과 구성

자세한 설계·근거는 `docs/openmetadata-demo-design.md`. 포트 전체 지도는 상위 `../CLAUDE.md`.

- 기동: `./scripts/up.sh` (seed SQL 재생성 → 원본 Postgres → 공식 스택) / 종료: `./scripts/down.sh` (`--volumes`는 데이터 삭제이므로 사용자가 요청할 때만)
- `docker-compose.yml` — OpenMetadata 공식 배포본 **그대로** (직접 수정 금지, 버전 올릴 땐 새 GitHub Release로 재다운로드). `restart: always`라 안 쓸 때는 `down`으로 내린다.
- `docker-compose.dags.yml` — 커스텀 DAG(`dags/`)를 수집용 Airflow 컨테이너에 얹는 오버레이. **반드시 `docker-compose.yml`과 같이 `-f` 두 개로** 올린다 (하나만 올리면 재생성 시 DAG가 안 보인다. 파일이 지워지는 건 아니고 두 파일로 다시 올리면 복구된다).
- `docker-compose.sourcedb.yml` — 카탈로그 대상 원본 Postgres 2개: `retaildb`(5432), `manufacturingdb`(5433, `sourcedb-init2/`)
- `dags/customer_sales_summary_join.py` — customers+sales 조인 데모 DAG. DAG를 만들거나 고칠 때는 `~/projects/.claude/rules/dag-style.md`를 따른다.
- `sourcedb-init/generate_seed_sql.py` — 루트 `data/*.csv` → seed SQL 재생성 (`etl.py`와 같은 정제 규칙)
- 접속: OpenMetadata UI `localhost:8585` (`admin@open-metadata.org` / `admin`), Airflow UI `localhost:8080` (`admin` / `admin`), 원본 Postgres `localhost:5432` (`retaildb` / `demo` / `demo`)
- OpenMetadata 컨테이너에서 원본 Postgres에 접속할 때는 컨테이너명이 아니라 `host.docker.internal`을 쓴다 (다른 compose 프로젝트 = 다른 Docker 네트워크). Rancher Desktop에서도 동작한다. 리눅스 네이티브 환경은 별도 네트워크 설정이 필요하다.
