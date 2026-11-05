# 공개 API에서 Iceberg까지: 서울 날씨

## 무엇을 만들었나

Open-Meteo 공개 API의 서울 시간별 ERA5 기상 재분석 데이터를 실제로 받아 Iceberg 테이블로 저장한다. ERA5는 모델과 관측을 결합한 재분석 자료이며 특정 관측소의 실측 기록이 아니다.

```text
Open-Meteo Historical Weather API
  → Python: HTTP 수집, 원본 JSON 보존, 데이터 검증, CSV 변환
  → SeaTunnel 2.3.13: LocalFile source → Iceberg sink
  → /lake/warehouse/public_api.db/weather_hourly (Parquet + Iceberg 메타데이터)
  → Hive Metastore에 테이블 등록
  → Trino: 원본과 전체 컬럼 비교 및 일별 집계
```

Iceberg는 SQL 서버가 아니라 테이블 포맷이다. SeaTunnel이 파일과 스냅샷(커밋된 테이블 상태)을 만들고, HMS는 현재 메타데이터 위치를 관리하며, Trino가 파일을 읽어 SQL을 실행한다. Python이 Parquet만 저장하고 끝나는 방식이 아니다.

## 실행

저장소의 `iceberg/` 폴더에서 실행한다. Python 3 표준 라이브러리만 필요하다. Docker와 기존 HMS·Trino가 준비되어 있어야 한다.

```bash
cd /Users/mz01-jaejunlee/projects/Onboarding/iceberg
bash scripts/up-trino.sh
python3 scripts/public_api_weather.py
```

기본 요청은 서울 좌표 37.5665, 126.9780, 2025-10-01~2025-10-07, 모델 `era5`, 시간대 `Asia/Seoul`이다. 7일 × 24시간 = 168행을 기대한다. 무료 API는 인증키가 필요 없는 비상업 학습용이며 상업 사용 시 공급자 이용 조건을 별도로 확인한다.

다른 날짜는 한 번에 최대 31일까지 요청한다.

```bash
python3 scripts/public_api_weather.py --start 2025-10-08 --end 2025-10-14
```

적재 완료된 같은 범위를 재실행하면 모든 값이 동일한 경우 `SKIP_IDENTICAL`이 출력된다. 일부 날짜가 기존 데이터와 겹치거나 API 정정으로 값이 다르면 실패하고 데이터를 추가하지 않는다. 겹치지 않는 구간으로 요청하거나 별도의 정정 절차를 설계한다.

원본 JSON으로 네트워크 없이 재검증할 수도 있다. 날짜는 원본 응답과 일치해야 한다. `evidence/`의 새 파일은 Git에서 제외하므로 새로 clone한 환경에서는 먼저 API 수집을 실행하고, 아래 경로를 해당 실행에서 생성된 `response.json` 경로로 바꾼다.

```bash
python3 scripts/public_api_weather.py \
  --replay evidence/public-api/20261105T072050Z-cfd8ac25/response.json
```

`jobs/04_public_weather_to_iceberg.conf`를 직접 실행하지 않는다. APPEND job에는 고유 키 제약이나 중복 방지 기능이 없으며 Python 래퍼가 선행 검사를 수행한다.

## 테이블과 시간대

대상은 `iceberg.public_api.weather_hourly`다. 기존 `retail` 테이블과 분리되어 있다.

| 컬럼 | Iceberg 타입 | 의미 |
| --- | --- | --- |
| city | string | 현재 `seoul` 고정 |
| weather_time | string | `2025-10-01T00:00:00+09:00` 형태의 한국 시간 |
| temperature_2m | double | 지상 2m 기온, °C |
| relative_humidity_2m | int | 지상 2m 상대습도, % |
| precipitation | double | 시간별 강수량, mm |

시간은 원본 계층에서 시간대가 명시된 ISO 8601 문자열로 저장한다. SeaTunnel의 timestamp 매핑에서 현지 시각이 UTC로 해석되는 것을 피하기 위한 선택이다. Trino의 `from_iso8601_timestamp()`로 실제 시간 타입을 얻는다. 다음 집계는 한국 날짜를 사용한다.

```sql
SELECT
    CAST(from_iso8601_timestamp(weather_time) AT TIME ZONE 'Asia/Seoul' AS date) AS day,
    count(*) AS hours,
    round(avg(temperature_2m), 2) AS avg_temperature_c,
    round(sum(precipitation), 2) AS precipitation_mm
FROM iceberg.public_api.weather_hourly
GROUP BY 1
ORDER BY 1;
```

터미널이나 기존 Superset SQL Lab의 Trino 연결에서 조회한다.

```bash
bash scripts/trino.sh --execute \
  'SELECT * FROM iceberg.public_api.weather_hourly ORDER BY weather_time LIMIT 10'
```

현재 Trino는 읽기 전용으로 유지했다. 위 집계는 조회이며 별도 mart 테이블이나 리니지를 생성하지 않는다.

## 검증과 실패 처리

- HTTP timeout 30초, 네트워크 오류·429·5xx에 한해 최대 3회 요청한다. 적재 job은 자동 재시도하지 않는다.
- 시간대 오프셋, 단위, 배열 길이, 시간 순서, 결측·비유한 값, 습도·강수 범위를 확인한다.
- 키 `(city, weather_time)`에 해당하는 구간을 모든 컬럼으로 비교한다. 완전히 동일하면 skip, 부분 적재/변경값/중복은 실패한다.
- 적재 후 Trino로 전체 168행을 원본과 비교한다. 현재 파일과 스냅샷, 일별 집계도 보고서에 남긴다.
- `data/public-api/.lock`은 같은 호스트의 래퍼 동시 실행을 막는다. 다른 머신·수동 writer까지 통제하는 분산 잠금은 아니다.
- 작업 중 실패하면 해당 실행의 `report.json`, `seatunnel.log`를 확인한다. 재실행 시에도 실제 대상 테이블을 먼저 비교하므로 커밋 이후 응답을 잃은 경우 동일 데이터는 skip된다.

```bash
python3 -m unittest discover -s tests -p 'test_public_api_weather.py' -v
```

## 파일 안내

| 경로 | 용도 |
| --- | --- |
| `scripts/public_api_weather.py` | API 수집, 검증, 선행 검사, 적재 실행, 대사 |
| `scripts/prepare-public-api-catalog.py` | HMS에 새 namespace만 준비 |
| `jobs/04_public_weather_to_iceberg.conf` | CSV → Iceberg job |
| `compose.yaml`의 `seatunnel.volumes` | CSV를 SeaTunnel 컨테이너에 읽기 전용 마운트 |
| `data/public-api/` | 실행용 임시 CSV와 잠금 파일, Git 제외 |
| `evidence/public-api/<실행ID>/` | JSON, SHA-256, CSV, 로그, 성공/실패 보고서 |
| `tasks/001-public-api-to-iceberg.md` | 목표, 완료 조건과 실제 검증 기록 |

## 출처

Weather data by [Open-Meteo.com](https://open-meteo.com/), CC BY 4.0. API의 재분석 모델 선택과 이용 조건은 [Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) 및 [가격·이용 범위](https://open-meteo.com/en/pricing)를 참고한다.

커넥터 설정 근거: SeaTunnel 2.3.13 [LocalFile source](https://seatunnel.apache.org/docs/2.3.13/connectors/source/LocalFile/), [Iceberg sink](https://seatunnel.apache.org/docs/2.3.13/connectors/sink/Iceberg/).
