# iceberg — 로컬 데이터 레이크하우스

원본(PostgreSQL·공개 API) → **SeaTunnel** → **Iceberg** 테이블(HMS 카탈로그, 파일은 `./lake` 또는 **MinIO**) → **Trino** → **Superset**. 날씨 적재는 **Airflow**가 매일 실행한다.
상위 규칙(`~/projects/.claude/CLAUDE.md`, `Onboarding/CLAUDE.md`)도 함께 적용된다. Codex는 `AGENTS.md`를 통해 이 파일을 읽는다.

## 설명 방식 (가장 중요)

**작업자는 레이크하우스 구축이 처음이다.** 결과물만 내놓지 말고 아래를 지킨다.

1. **용어를 풀어서 쓴다.** "카탈로그", "매니페스트", "스냅샷", "커밋" 같은 말을 처음 쓸 때 이 구조에서 뭘 가리키는지 한 줄로 설명한다. 이미 설명한 용어는 반복하지 않는다.
2. **왜 필요한지를 먼저 쓴다.** "Trino를 추가한다"가 아니라 "Superset은 SQL 엔진에 붙는 BI 도구이고 Iceberg는 SQL 서버가 없으므로 Trino가 필요하다" 식으로 쓴다.
3. **명령어는 복사해서 바로 실행 가능한 형태로 준다.** 실행 디렉터리와 호스트/컨테이너 여부를 명시한다.
4. **검증 방법을 같이 준다.** 단계마다 "성공하면 이게 보인다"와 기대값(행 수, 합계, 출력 형태)을 쓴다.
5. **확인한 것과 추측을 구분한다.** 실행해서 확인한 결과와 문서만 보고 설계한 것을 문장에서 구분한다.
6. **막히는 지점을 미리 알려준다.** 포트 충돌, 컨테이너 안의 `localhost` 같은 함정은 해당 단계에서 언급한다.

## 절대 하지 말 것

- **`docker compose down -v` 금지.** MinIO 데이터, HMS 등록 정보(`catalog-db`), Superset 설정이 볼륨째 삭제된다.
- **원시 SeaTunnel job(`jobs/*.conf`)을 직접 반복 실행하지 않는다.** `APPEND_DATA`는 중복을 막지 않는다. 항상 아래 "적재 래퍼"로 실행한다.
- **기존 `./lake` 파일과 기존 namespace는 수정하지 않는다.** 저장소를 바꿀 때도 새 namespace(`retail_s3` 등)에 새로 적재한다.
- **Iceberg metadata JSON·manifest 안의 경로를 문자열 치환하지 않고, HMS 내부 DB(`catalog-db`)를 직접 수정하지 않는다.** 조회만 한다.
- **Trino catalog의 `READ_ONLY`를 풀지 않는다.** 쓰기는 SeaTunnel(과 테이블 생성용 Java 코드)만 한다.
- **Airflow가 떠 있을 때 날씨 CLI 적재(`scripts/public_api_weather.py`)를 실행하지 않는다.** 호스트-컨테이너 잠금 공유가 확인되지 않았다.
- **매일 09:00(KST, Airflow 날씨 DAG) 근처에 HMS·Trino를 재시작하지 않는다.**
- **자격증명을 문서·job 파일에 적지 않는다.** 환경변수나 자리표시자로 둔다.
- `Onboarding/openmetadata/docker-compose.yml`(공식 배포본)은 수정하지 않는다. 이 폴더의 `compose*.yaml`은 직접 작성한 것이라 수정해도 된다.

## Compose 구성과 기동·종료

호스트, `Onboarding/iceberg/`에서 실행한다. Compose 프로젝트 이름(`iceberg-learning`)이 `compose.yaml`에 있으므로 **`compose.yaml`은 항상 포함**한다 (빠지면 빈 볼륨이 새로 생긴다).

| 파일 | 서비스 |
|---|---|
| `compose.yaml` | `catalog-db`, `hms`, `source-db`(orders 5행), 작업용 `seatunnel`·`catalog-tools`(profile `tools`) |
| `compose.analytics.yaml` | `trino`, `superset`, `superset-db`, `superset-init` |
| `compose.minio.yaml` | `minio`, `minio-init`(bucket 생성) |
| `compose.airflow.yaml` | `airflow`, `airflow-db` |
| `compose.bulk.yaml` | 대용량 JDBC 적재용 SeaTunnel 메모리(Xmx 3GiB)·원본 계정 환경변수 오버레이 |

```bash
# 조회 환경 (HMS + Trino + MinIO + Superset)
docker compose -f compose.yaml -f compose.analytics.yaml -f compose.minio.yaml up -d --wait catalog-db hms trino minio superset

# 스크립트로 단계별 기동
bash scripts/up-trino.sh      # catalog-db, HMS, Trino
bash scripts/up-minio.sh      # .env.minio 생성(최초 1회), MinIO, bucket, HMS·Trino 재생성
bash scripts/up-superset.sh   # 이미지 빌드·초기화·기동·기본 등록
bash scripts/up-airflow.sh    # Airflow (Trino가 떠 있어야 함)

# 종료 (-v 금지). Airflow를 띄웠다면 -f compose.airflow.yaml도 추가
docker compose -f compose.yaml -f compose.analytics.yaml -f compose.minio.yaml down
```

조회: `bash scripts/trino.sh --execute "SELECT count(*) FROM iceberg_s3.retail_s3.production_orders"`

## 포트와 자격증명 위치

| 호스트 포트 | 서비스 | 접속 정보 위치 |
|---|---|---|
| 15432 | `catalog-db` (HMS 내부 DB, DBeaver 조회용) | `compose.yaml` (`hive` / DB `metastore`) |
| 8081 | Trino | 사용자 `analyst`, 비밀번호 없음 |
| 8088 | Superset | `.env.superset` (`python3 scripts/show-superset-login.py`) |
| 8082 | Airflow | 로그인 없음 (127.0.0.1 전용) |
| 9000 / 9001 | MinIO API / 웹 콘솔 | `.env.minio` (`scripts/prepare_minio_env.py`가 생성, git 제외) |
| 5440 | 원본 PostgreSQL `srcdb` (**`Onboarding/seatunnel` 프로젝트**) | `seatunnel/docker-compose.sourcedb.yml`. 적재 시 `SOURCE_USER`/`SOURCE_PASSWORD` 환경변수로 전달 |

다른 프로젝트가 쓰는 포트: 5432(openmetadata 원본 PG), 8080(openmetadata Airflow), 8585(OpenMetadata UI), 3306(seatunnel MySQL). 새 포트는 이와 겹치지 않게 `127.0.0.1`에만 공개한다.

## 테이블과 적재 방법 (현재 상태)

| 테이블 (Trino) | 파일 위치 | 내용 | 적재 래퍼 | 상세 |
|---|---|---|---|---|
| `iceberg.retail.orders` | `./lake` | 5행, amount 합계 170000. 보존 기준값 | (초기 실습, 재적재 없음) | `docs/local-lakehouse-superset.md` |
| `iceberg.retail.production_orders_100m` | `./lake` | 1억 행, Parquet 4개 | `scripts/load-production-100m.py` → `verify-production-100m.py` | `docs/production-orders-100m.md` |
| `iceberg.public_api.weather_hourly` | `./lake` | 서울 시간별 날씨. Airflow DAG `public_weather_to_iceberg`가 매일 09:00 증분 (2026-11-11 576행) | `scripts/public_api_weather.py`, `dags/public_weather_to_iceberg.py` | `tasks/001-public-api-to-iceberg.md`, `tasks/002-airflow-weather-schedule.md`, `docs/airflow-weather-dag.md` |
| `iceberg_s3.public_api_s3.weather_hourly` | MinIO | 위 테이블의 2026-11-11 snapshot 복사본 576행. **일회성**: 원본이 늘어난 뒤 재실행하면 "원본과 다름"으로 중단 | `scripts/load-weather-to-minio.py` | `docs/minio-s3-lakehouse.md` |
| `iceberg_s3.retail_s3.production_orders` | MinIO | `srcdb.production_orders` 200만 행, `month(order_date)` 13파티션 | `scripts/load-production-orders-to-minio.py` | `tasks/003-production-orders-to-minio.md` |

- Trino catalog: `iceberg`(로컬 `./lake`), `iceberg_s3`(MinIO). 같은 HMS를 보지만 **파일 위치가 맞는 catalog로만 읽힌다** (`iceberg_s3.retail.orders`는 목록에만 보이고 조회는 실패).
- Superset 연결: `Local Iceberg / Trino`(기본 catalog `iceberg`), `MinIO Iceberg / Trino`(기본 catalog `iceberg_s3`). SQL Lab 표시 한도 5만 행, 조회·CSV 20만 행(`config/superset/superset_config.py`).
  2026-11-12 확인 시 `production_orders_100m` Dataset은 Superset에 없다 (SQL Lab 쿼리는 가능).

## 작업 방식

- 새 작업은 `tasks/NNN-*.md`(목표·결정·완료 조건·범위 밖·실행 기록)로 시작하고, 사용자 검토 후 구현한다.
- 새 실행 결과는 `evidence/<작업>/<run_id>/`에 남긴다. 새 산출물은 `.gitignore` 대상이고, 결과 요약은 tasks/docs에 쓴다. 기존 추적 중인 evidence 파일 57개는 노트북·문서가 쓰므로 추적을 유지한다.
- 새 서비스는 기존 서비스를 건드리지 않게 별도 compose 파일로 추가하고 `iceberg-learning-net`에 붙인다.
- 변경 후 실행 방법은 docs, 현재 상태는 이 파일의 "테이블과 적재 방법" 표에 반영한다. 날짜별 작업 기록은 이 파일이 아니라 tasks/git에 남긴다.

## 처음 밟기 쉬운 함정

- 컨테이너끼리는 **서비스 이름**으로 통신한다(`hms:9083`, `trino:8080`, `minio:9000`). 컨테이너 안의 `localhost`는 자기 자신이다.
- 다른 compose 프로젝트(원본 PG 5440)는 컨테이너에서 `host.docker.internal:5440`으로 접속한다.
- Iceberg 테이블 위치는 sink의 `warehouse`가 아니라 **HMS namespace의 location**을 따른다. MinIO용 namespace는 `s3a://` location을 지정해 먼저 만든다.
- PyIceberg 0.10은 HMS 4와 테이블 조회가 호환되지 않는다(`Invalid method name: get_table`). 테이블 생성·검사는 SeaTunnel 이미지의 Java Iceberg 클라이언트(`scripts/Prepare*Catalog.java`)로 한다. 그 이미지의 Java는 8이다.
- 원본 PK가 있는 JDBC 적재는 Iceberg identifier로 복사되어 Delta writer가 메모리를 크게 쓴다. append 적재는 PK 메타데이터를 떼고 식별자 없는 테이블을 미리 만든다 (`docs/production-orders-100m.md`).
- Docker 런타임은 Rancher Desktop이다 (회사 Mac에서 Docker Desktop은 Zscaler와 충돌).

## Codex와 함께 작업할 때

이 폴더는 Claude와 Codex를 번갈아 쓴다. 두 에이전트는 서로의 대화 기록을 모른다.

- 작업 시작 시 `git status`와 `git log -1 --stat`으로 현재 상태를 먼저 확인한다. 기억에 있는 파일 목록을 믿지 않는다.
- 같은 파일을 동시에 수정하지 않는다. 턴이 바뀌는 지점에서 커밋해 상대가 변경 내역을 읽게 한다.
- Docker 스택을 올리고 내리는 작업은 한쪽에서만 한다.

## 더 볼 문서

| 문서 | 내용 |
|---|---|
| `docs/local-lakehouse-superset.md` | 전체 구축 순서 |
| `docs/md/project-files-guide.md` | 파일별 사용 시점과 스크립트 호출 관계 |
| `docs/md/local-lakehouse-flow.md`, `docs/md/lakehouse-concept.md` | 그림으로 보는 배치·적재·조회 흐름, 개념 |
| `docs/trino-local-query.md` | Trino의 `file:/lake` 조회 설정 |
| `docs/minio-s3-lakehouse.md` | MinIO 구성, 컴포넌트별 S3 설정 |
| `docs/superset-local-ui.md` | Superset 구성 |
| `docs/web/*.html` | HMS·Iceberg 쓰기·날씨 DAG 대화형 안내 (서비스 호출 없음) |
| `analysis/read_parquet.ipynb` | JSON → snapshot → manifest → Parquet 읽기 실습 노트북 |
| `docs/changelog.md` | 2026-11-16 이전 날짜별 작업 기록 |
