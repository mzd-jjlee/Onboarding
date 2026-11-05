# iceberg — 로컬 데이터 레이크하우스 구축

`~/projects/Onboarding/iceberg/` 에서 작업할 때 적용되는 규칙.
상위 규칙(`~/projects/.claude/CLAUDE.md`, `Onboarding/CLAUDE.md`)도 함께 적용된다.

## 설명 방식 (가장 중요)

**작업자는 레이크하우스 구축이 처음이다.** 따라서 결과물만 내놓지 말고 아래를 지킨다.

1. **용어를 풀어서 쓴다.** "카탈로그", "매니페스트", "스냅샷", "커밋" 같은 말을 처음 쓸 때는 그게
   이 구조에서 뭘 가리키는지 한 줄로 설명한다. 이미 설명한 용어를 매번 다시 설명할 필요는 없다.
2. **왜 필요한지를 먼저 쓴다.** "Trino를 추가한다"가 아니라 "Superset은 SQL을 실행해 줄 엔진에
   붙는 BI 도구이고 Iceberg는 SQL 서버가 없으므로, 중간에 Trino가 필요하다" 식으로 쓴다.
3. **명령어는 복사해서 바로 실행 가능한 형태로 준다.** 어느 디렉터리에서 실행하는지, 호스트인지
   컨테이너 안인지 명시한다.
4. **검증 방법을 같이 준다.** 각 단계마다 "성공했으면 이게 보인다"를 적는다. 기대값(행 수, 합계,
   출력 형태)을 쓴다.
5. **확인한 것과 추측을 구분한다.** 실제로 실행해서 확인한 결과와, 공식 문서만 보고 설계한 것을
   문장에서 구분한다. 검증하지 않은 설정을 "이렇게 하면 된다"로 쓰지 않는다.
6. **막히는 지점을 미리 알려준다.** 처음 하는 사람이 밟을 함정(포트 충돌, 컨테이너 안에서의
   `localhost`, 드라이버 설치 위치 등)은 해당 단계에서 바로 언급한다.

## 구축 목표 (4단계)

1. **적재**: SeaTunnel로 원본 데이터를 로컬 환경에 옮긴다. sink는 `Iceberg`를 쓴다
   (`LocalFile` sink로 Parquet만 쓰는 방식이 아니다 — Iceberg sink가 파일 작성과 테이블 커밋을 함께 한다).
2. **테이블 포맷**: Apache Iceberg로 오픈 테이블 포맷을 구성한다.
3. **메타데이터**: Hive Metastore(HMS)로 카탈로그(namespace·테이블·현재 metadata 위치)를 관리한다.
4. **조회**: **Apache Superset** 웹 UI에서 Iceberg 테이블을 조회한다.
   Superset은 Iceberg에 직접 붙지 못하므로 **Trino**를 쿼리 엔진으로 둔다.

```
원본 PG ──SeaTunnel──▶ Iceberg 파일(./lake) + HMS 커밋
브라우저 ──▶ Superset ──SQL──▶ Trino ──▶ HMS(위치 확인) + ./lake(파일 읽기)
```

## 현재 상태

| 구성요소 | 상태 |
|---|---|
| SeaTunnel 2.3.13 → Iceberg sink | 동작 확인됨 (배치 2회, 5건 / 합계 170000) |
| Iceberg 1.6.1, format v2, `retail.orders` | 생성됨 |
| Hive Metastore 4.0.1 (`thrift://hms:9083`) | 동작 확인됨 |
| Trino 483 | HMS + 기존 file:/lake 경로 조회 검증 완료, localhost:8081 |
| Superset 6.0.0 | Trino 연결·주문 Dataset·차트·대시보드 등록, localhost:8088 |
| production_orders_100m | 2026-10-08 SeaTunnel 적재 성공: 100,000,000행, Parquet 4개 / 330,496,199 bytes. Trino 실파일 스캔 집계가 원본 PostgreSQL과 일치. 사용자가 Superset SQL Lab 조회 확인. 상세: `docs/production-orders-100m.md`. |

- 설계 문서: `docs/local-lakehouse-superset.md` (전체 구축 순서),
  `docs/local-lakehouse-build-options.md` (저장소 선택지),
  `docs/md/local-lakehouse-flow.md` (그림 3장으로 보는 환경 배치 · 적재 · 조회 흐름)
- 실행 증거: `evidence/` — 원본 데이터, SeaTunnel 적재 로그와 HMS 기록을 유지한다. Trino 조회 결과는 `evidence/trino/`에 있다. Superset 조회 기록은 `evidence/superset/`에 있다. 1억 행 검증 및 실패 시도 기록은 `evidence/production-100m/`에 있다.

## 아키텍처 경계

- 기존 보조 조회·검증 코드와 그 산출물은 사용자 요청으로 삭제했다.
  `catalog-tools`는 HMS namespace 초기화만 수행한다. 새 조회·검증은 Trino로 구현했다 (`scripts/trino.sh`, `scripts/verify_trino.py`).
- **기존 `retail.orders` 테이블과 `./lake` 파일은 보존한다.** 저장소를 S3 호환으로 바꾸는 경우에도
  기존 namespace를 수정하지 말고 새 namespace(`retail_s3` 등)에 새로 적재한다.
- **Iceberg metadata JSON / manifest 안의 절대 URI를 문자열 치환으로 고치지 않는다.**
  `warehouse` 설정만 바꿔도 기존 테이블은 이동하지 않는다.
- **원시 SeaTunnel job을 반복 실행하지 않는다.** `data_save_mode = "APPEND_DATA"`는 행 중복을 막지 않는다.
  기존 배치 래퍼와 중복 검사 도구는 삭제했다. 재적재 전에 Trino 기반 선행 상태 검사를 구현한다.
- 서비스 간 통신은 `iceberg-learning-net` 네트워크의 **서비스 이름**으로 한다
  (Superset 컨테이너에서 `localhost:8080`은 Trino가 아니다).

## 호스트 포트

현재 `catalog-db`는 DBeaver 확인용으로 `127.0.0.1:15432:5432`를 공개한다. Trino는 `127.0.0.1:8081:8080`을 공개한다. 새로 공개할 때는 아래 충돌을 피한다.

| 포트 | 이미 쓰는 곳 |
|---|---|
| 5432 | `Onboarding/openmetadata` 소스 Postgres |
| 8080 | `Onboarding/openmetadata` Airflow UI |
| 8585 | `Onboarding/openmetadata` OpenMetadata UI |

→ **Trino는 컨테이너 8080을 호스트 8081로 매핑했다.** Superset은 8088을 쓴다.
컨테이너 내부 포트는 그대로 둬도 된다 (충돌은 호스트 포트에서만 난다).

## 작업 규칙

- `compose.yaml`은 이 프로젝트가 직접 작성한 파일이라 수정해도 된다
  (openmetadata의 `docker-compose.yml`과 다르다 — 그쪽은 공식 배포본이라 수정 금지).
- Trino/Superset은 기존 서비스를 건드리지 않도록 **별도 파일**(`compose.analytics.yaml` 등)로 추가하고
  `iceberg-learning-net`에 붙이는 방식을 우선 검토한다.
- 자격증명은 문서·job 파일에 하드코딩하지 않고 환경변수나 자리표시자로 둔다.
- 새 단계를 구현하면 `evidence/`에 버전·설정·출력을 남긴다.

## 다른 에이전트와 함께 작업할 때

이 폴더는 Claude와 Codex를 번갈아 쓴다. 기초 구축은 Codex, 세부 질의는 Claude 쪽으로 나뉜다.

- **두 에이전트가 각자의 대화 기록만 보고 서로를 모른다.** 작업 시작 시 `git status`와
  `git log -1 --stat`으로 현재 상태를 먼저 확인한다. 기억에 있는 파일 목록을 믿지 않는다.
- 같은 파일을 동시에 수정하지 않는다. 턴이 바뀌는 지점에서 커밋해 두면 상대가 변경 내역을 읽을 수 있다.
- Docker 스택을 올리고 내리는 작업은 한쪽에서만 한다.

## Trino 실행과 검증

- 기동: `bash scripts/up-trino.sh` (기존 DB/HMS와 Trino만 기동, 재적재 없음).
- 조회: `bash scripts/trino.sh --execute "SELECT * FROM iceberg.retail.orders"`.
- 검증: `python3 scripts/verify_trino.py` (기존 5건 데이터 기준).
- 반드시 두 Compose 파일을 함께 사용한다: `-f compose.yaml -f compose.analytics.yaml`.
- `fs.local.enabled=true`, `local.location=/`: 기존 file:/lake 절대 URI를 유지한다. 설정 상세는 `docs/trino-local-query.md` 참고.
- 공유 lake는 읽기 전용, Iceberg catalog는 READ_ONLY. Superset도 연결 완료했다.

## Superset 실행

- `bash scripts/up-superset.sh`: 이미지 빌드, DB 초기화, 기동, REST API 등록.
- `python3 scripts/show-superset-login.py`: 로컬 관리자 로그인 정보 확인.
- 대시보드: http://localhost:8088/superset/dashboard/local-iceberg/
- `.env.superset` 및 `superset-db` 볼륨 보존. 자세한 설명은 `docs/superset-local-ui.md`.

- 파일별 사용 시점과 스크립트 호출 관계: `docs/md/project-files-guide.md` (그림 + 전체 파일 표). 문서 작업 중 적재 재실행 없음.
- HMS 입문용 대화형 안내: `docs/web/hms-guide.html`. 로컬 HTML이며 버튼은 설명만 변경하고 서비스를 호출하지 않는다.
- `analysis/read_parquet.ipynb`: 실제 catalog-db SELECT에서 시작하는 JSON → snapshot → Avro manifest list → manifest → Parquet 읽기 학습. live/evidence 모드, 원본 노트북 별도 보존. 전체 셀 실행 완료 (현재 5행/170000, 과거 3행/69000, lake 파일 9개 불변). 기록: `evidence/notebook/read-parquet-execution.json`. fastavro 및 노트북 실행용 dev 의존성을 pyproject/uv.lock에 추가했다.
- JSON → Avro → Parquet 그림 및 외부 설명 검토: `docs/md/iceberg-json-to-parquet.md`, 이미지 `docs/assets/lakehouse-flow/07-json-to-parquet.png`. 실제 manifest 2개/Parquet 2개 참조 확인.
- 2026-10-12: 사용자 승인으로 `.DS_Store`, `docs/.DS_Store`, `docs/assets/.DS_Store`만 삭제. evidence·노트북 백업·서비스·데이터 보존. `docs/md/project-files-guide.md`에 코드 검토 순서, 환경 준비·1억 행 실행·HMS 등록·조회 상세 및 누락된 대용량 작업 파일을 보완했다. 내장 imagegen 그림 `docs/assets/lakehouse-flow/08-scripts-to-lakehouse.png` 추가. 이번 작업은 문서 정리이며 서비스 기동·적재·검증 쿼리는 재실행하지 않았다.

- `docs/web/iceberg-write-guide.html`: append 적재의 Parquet → manifest → manifest list → JSON → HMS 커밋 및 Trino 조회를 설명하는 독립 HTML. 소량 orders의 실제 파일 탐색과 1억 행/컬럼 선택 설명을 포함하며, 가상 예시와 검증 기록을 구분한다.

- 2026-10-14: Trino·Superset 연결 설정과 SQL 조회 흐름 그림 `docs/assets/lakehouse-flow/10-trino-superset-iceberg-connection.png` 추가. 설명·생성 프롬프트는 `docs/md/trino-superset-connection-image.md`. 기존 설정 확인 및 이미지 생성만 수행했고 서비스/데이터 재실행 없음.

- 2026-10-15: `analysis/read_parquet.ipynb`를 production_orders_100m 기준으로 전환. 기존 사용자 셀을 포함한 5행 버전은 `analysis/read_parquet.orders-5rows.ipynb`에 보존. live 전체 셀(nbclient)·evidence 모드 실행 성공, 17개 대상 파일 SHA-256 불변. 4개 Parquet footer 합계 1억 행, 파일당 5행 샘플. JSON 5개=빈 테이블+4커밋, manifest list 4개와 재사용 manifest 4개 확인. 기록 `evidence/notebook/production-100m/`. 전체 행 스캔·재적재 없음, 추가 필수 작업 없음.

- 2026-10-15: 재구성된 presentation 자료를 읽고 전체 목표 아키텍처 이미지 `docs/assets/lakehouse-flow/11-local-lakehouse-overview.png` 생성. 설명·프롬프트는 `docs/md/local-lakehouse-overview-image.md`. 발표 HTML/기획 MD는 변경하지 않음. 적재·조회 흐름과 두 DB 구분, 브라우저는 호스트임을 표시. 서비스 실행 없음.

- 2026-10-15: 사용자 제공 로고를 참고해 전체 아키텍처의 Trino·Hive 마스코트를 수정한 `11-local-lakehouse-overview-v2.png` 추가. 기존 이미지·발표 HTML 보존.

- 2026-10-15: 전체 아키텍처 최신 이미지 `11-local-lakehouse-overview-v3.png`: Docker 제목·고래 아이콘, 호스트 브라우저 경계 분리, 전체 제목 제거. 사용자가 지정한 나머지 설명 유지. 발표 HTML 미수정.

- 2026-10-29: 사용자 요청으로 presentation/local-lakehouse.html 21쪽 네 번째 카드에 월별 파티션 규칙, order_date SQL, 9월 후보 파일 선택 및 14일 필터 예시 추가. 월별→일별 명세 변경과 기존 파일 유지, 이번 실습 미적용 명시. 기존 편집 내용과 speaker-notes.md 보존. 브라우저 렌더 검증은 미수행.

- 2026-11-05: 공개 API 적재 실습 추가. `scripts/public_api_weather.py`가 Open-Meteo ERA5 서울 2025-10-01~07의 168행을 수집하고 SeaTunnel LocalFile → Iceberg로 `public_api.weather_hourly`에 적재한다. `weather_time`은 ISO 8601 +09:00 string이며 Trino에서 `from_iso8601_timestamp()`로 해석한다. API 원본·CSV·로그·검증 보고서는 `evidence/public-api/`. 전체 값 대사, replay skip(동일 snapshot), 기존 28파일 SHA-256 및 orders 5건/170000 보존 확인. 초기 timestamp 시도는 신규 테이블만 복구했고 미참조 파일은 보존. 상세 `docs/public-api-to-iceberg.md`, `tasks/001-public-api-to-iceberg.md`. 원시 job 직접 실행 금지; 부분 중복/정정값은 래퍼가 중단한다. 리니지·mart·스케줄링은 후속 범위.

- 공개 API CSV bind mount는 `compose.yaml`의 `seatunnel.volumes`에서 관리한다. 별도 API Compose 파일 없이 기존 `compose.yaml` + `compose.analytics.yaml` 두 파일로 실행한다.

- `evidence/`의 새 실행 산출물은 `.gitignore`로 제외한다. 원본·로그는 로컬에 보존하고 결과 요약은 tasks/docs에 기록한다. 기존 추적 중인 증거 파일 57개는 노트북 evidence 모드와 문서에서 사용하므로 추적 상태를 유지한다.
