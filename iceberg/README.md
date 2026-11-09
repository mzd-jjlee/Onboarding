# 로컬 데이터 레이크하우스

목표 구조는 **SeaTunnel Iceberg sink → Iceberg + Hive Metastore → Trino → Apache Superset 웹 조회**다.

**먼저 [로컬 데이터 레이크하우스 구축 안내서](docs/local-lakehouse-superset.md)를 읽는다.** 구성요소 역할, 쓰기·조회 흐름, 로컬 저장소 호환성, Superset 연결, 검증 SQL과 구축 완료 기준을 정리했다.

그림으로 먼저 보고 싶다면 [환경 배치·적재·웹 조회 그림 안내서](docs/md/local-lakehouse-flow.md)를 읽는다.

**구축한 코드와 실행 흐름을 검토하려면 [스크립트에서 1억 행 적재·조회까지](docs/md/project-files-guide.md)를 먼저 읽는다.** 환경 준비 → SeaTunnel 실행 → Iceberg 파일 작성·HMS 등록 → Trino/Superset 조회 그림과 파일별 읽는 순서가 있다.

## 문서

| 문서 | 용도 |
|---|---|
| [새 구축 안내서](docs/local-lakehouse-superset.md) | 현재 목표의 전체 구조와 구현 순서 |
| [구축 선택지](docs/local-lakehouse-build-options.md) | 기존 공유 디스크 재사용과 로컬 S3 대안의 설정 |

## Trino 조회

```sh
bash scripts/up-trino.sh
bash scripts/trino.sh --execute 'SELECT * FROM iceberg.retail.orders ORDER BY order_id'
```

DBeaver: Trino 연결, `localhost:8081`, catalog `iceberg`, schema `retail`, 사용자 `analyst`, 비밀번호 없음.
[Trino 연결·검증 안내서](docs/trino-local-query.md)에 설정과 결과를 정리했다.

## 구현 상태

SeaTunnel 2.3.13 Iceberg sink, Hive Metastore 4.0.1, PostgreSQL 16, 공유 `/lake` 및 HMS 초기화 도구가 구현되어 있다. 2026-10-02 기록에서 첫 배치 3건, 추가 적재 후 5건·합계 170,000, 과거 스냅샷 및 카탈로그 재시작 보존을 확인했다.

**Trino 483 및 Superset 6.0.0 연결 완료.** 기존 `retail.orders` 조회 외에, 2026-10-08 원본 PostgreSQL `production_orders_100m` 1억 행을 SeaTunnel으로 Iceberg에 적재했다. Trino가 Parquet 4개(약 330.5 MB)를 스캔해 원본 집계와 대조했고 결과가 일치했다. 사용자가 Superset SQL Lab에서도 이 테이블 조회를 확인했다. 설정·검증·SQL은 [1억 행 적재 안내서](docs/production-orders-100m.md), 실행 산출물은 `evidence/production-100m/`에 있다.

기존 보조 조회·배치 검증 도구와 관련 산출물은 제거했다. Iceberg 실제 데이터와 원본·SeaTunnel·HMS 기록은 유지한다. 초기 구축 절차와 중복 적재 주의사항은 [구축 안내서](docs/local-lakehouse-superset.md#6-구현-순서)를 참고한다.

에이전트 작업 규칙은 [AGENTS.md](AGENTS.md)와 [CLAUDE.md](CLAUDE.md)를 참조한다.

## Superset 웹 조회

[주문 대시보드 열기](http://localhost:8088/superset/dashboard/local-iceberg/) · [접속 및 구성 안내](docs/superset-local-ui.md)

```sh
# 로그인 정보 확인
python3 scripts/show-superset-login.py
# 전체 분석 계층 기동 및 초기 설정
bash scripts/up-superset.sh
```

파일들의 사용 시점이 궁금하면 [config · jobs · scripts 그림 안내](docs/md/project-files-guide.md)를 참고한다.

HMS의 역할은 [브라우저용 단계별 안내서](docs/web/hms-guide.html)에서 적재·조회·커밋 흐름을 눌러보며 확인할 수 있다. HTML 파일을 브라우저로 열면 동작한다.

## JSON → Avro → Parquet 직접 열어보기

[analysis/read_parquet.ipynb](analysis/read_parquet.ipynb)를 VS Code에서 열고 `.venv/bin/python` 커널을 선택한다. `uv sync` 후 위에서부터 실행하면 된다. 실제 catalog-db의 `metadata_location` → snapshot → manifest list → manifest → Parquet 순서로 읽으며, 현재 5행·합계 170000과 과거 3행·합계 69000의 실행 결과도 저장되어 있다.

Docker 없이 학습하려면 노트북의 `SOURCE_MODE`를 `evidence`로 바꾼다 (현재 DB 대신 과거 HMS 출력 기록 사용). 기존 노트북은 `analysis/read_parquet.before-walkthrough.ipynb`에 보존했다. 삭제 파일·스키마 진화를 처리하는 범용 엔진이 아닌 현재 append 예제 전용이다.

[JSON 하나에서 여러 Parquet를 찾는 그림과 설명 검토](docs/md/iceberg-json-to-parquet.md)에서 실제 Avro 참조 관계와 커밋·캐시·파일 선택의 의미를 확인할 수 있다.

Iceberg sink의 파일 생성 과정은 [Parquet·Avro·JSON 생성 단계별 웹 안내](docs/web/iceberg-write-guide.html)에서 확인한다. HTML을 브라우저로 열고 단계 버튼을 누르면 된다.

### 1억 행 테이블의 JSON·Avro·Parquet 직접 확인

[analysis/read_parquet.ipynb](analysis/read_parquet.ipynb)를 프로젝트 `.venv/bin/python` 커널로 위에서부터 실행한다 (`uv sync --dev`). 기본 live 모드는 실행 중인 catalog-db를 SELECT하며, Docker 없이 보려면 `SOURCE_MODE = "evidence"`로 바꾼다. 파일당 5행 샘플과 footer만 확인하므로 1억 행 전체를 메모리에 올리지 않는다. JSON 5개·manifest list 4개·manifest 4개·Parquet 4개의 실제 참조 관계와 네 커밋의 누적 행 수를 표시한다. 이전 5행 노트북은 `analysis/read_parquet.orders-5rows.ipynb`에 보존했다. 실행 검증: `evidence/notebook/production-100m/execution.json`.

## 공개 API → Iceberg 적재

서울의 시간별 과거 날씨(ERA5 재분석)를 Open-Meteo에서 수집해 `iceberg.public_api.weather_hourly`에 적재한다. Python 수집 → JSON/CSV 보존 → SeaTunnel Iceberg sink → Trino 전체 행 대사 흐름이다.

```bash
python3 scripts/public_api_weather.py
bash scripts/trino.sh --execute 'SELECT * FROM iceberg.public_api.weather_hourly ORDER BY weather_time LIMIT 10'
```

2026-11-05 실제 API 데이터 168행 적재·대사 완료. 같은 원본 재실행은 `SKIP_IDENTICAL`이며 행 수와 스냅샷이 유지됐다. 시간은 시간대를 명시한 ISO 8601 문자열로 저장한다. 기존 retail 데이터와 Trino 읽기 전용 설정은 유지했다.

[실행 안내와 집계 SQL](docs/public-api-to-iceberg.md) · [작업 문서](tasks/001-public-api-to-iceberg.md)

상세 검증 결과는 로컬 `evidence/public-api/verification.json`에 저장한다. 새 실행 산출물은 Git에서 제외하며, 검증 요약은 작업 문서에 남긴다.

### Airflow 스케줄링

Airflow DAG `public_weather_to_iceberg`가 매일 09:00(KST)에 테이블의 마지막 날짜 다음 날부터 최대 7일치를 이어 받는다. ERA5는 약 5일 늦게 채워지므로 `오늘 - 6일`까지만 받는다.

```bash
bash scripts/up-trino.sh
bash scripts/up-airflow.sh   # http://localhost:8082
```

2026-11-09 스케줄 실행 1회와 수동 실행 2회를 확인했다(168 → 336 → 408행, 받을 날짜가 없으면 skip). [Airflow 안내](docs/airflow-weather-dag.md) · [작업 문서](tasks/002-airflow-weather-schedule.md)
