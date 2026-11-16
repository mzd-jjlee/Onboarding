# iceberg 작업 기록 (CLAUDE.md에서 이동)

2026-11-16 `CLAUDE.md`를 규칙·명령·상태 위주로 정리하면서, 그 안에 쌓여 있던 작업 기록을 원문 그대로 옮겼다.
이후 작업 기록은 `tasks/NNN-*.md`의 "실행 기록"과 git 커밋에 남긴다. 아래 내용 중 일부(래퍼 삭제, Compose 파일 2개 등)는 당시 기준이며 현재와 다를 수 있다.

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

- 2026-11-09: Airflow 스케줄링 추가. `compose.airflow.yaml`(Airflow 3.3.1 standalone + airflow-db, 127.0.0.1:8082), 기동 `bash scripts/up-airflow.sh`. DAG `dags/public_weather_to_iceberg.py`는 매일 09:00 KST, 테이블 마지막 날짜+1일부터 `batch_days`(7)일, `오늘-lag_days`(6)까지 받는다(ERA5 약 5일 지연). 로직은 `src/public_api/weather.py`로 이동, CLI와 공유. Airflow는 docker.sock을 마운트해 `docker compose run seatunnel`을 호출하므로 프로젝트를 호스트와 같은 절대 경로(`LAB_ROOT`)로 마운트한다. 확인: scheduled 1회(10-08~14), manual 2회(10-15~17, 새 데이터 없음 skip) → 408행, 중복 없음, 기존 28파일 SHA-256·orders 5건/170000 보존. DAG 일시정지 해제 상태. Airflow 기동 중에는 CLI 적재 금지(호스트-컨테이너 잠금 공유 미확인). 상세 `docs/airflow-weather-dag.md`, `tasks/002-airflow-weather-schedule.md`.
