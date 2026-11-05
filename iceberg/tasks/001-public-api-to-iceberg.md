# 공개 API → Iceberg: 서울 시간별 과거 날씨

## 목표와 계약

- Open-Meteo Historical Weather API의 ERA5 재분석 데이터를 수집한다. 실측 관측 자료가 아니다.
- 기본 범위: 서울(37.5665, 126.9780), 2025-10-01~2025-10-07, Asia/Seoul, 시간별 168행.
- 테이블: `iceberg.public_api.weather_hourly`. 키: `(city, weather_time)`.
- 컬럼: city(string), weather_time(string, ISO 8601 +09:00), temperature_2m(double, °C), relative_humidity_2m(int, %), precipitation(double, mm).
- API → 원본 JSON → 검증된 CSV → SeaTunnel LocalFile/Iceberg sink → HMS 등록 및 파일 커밋 → Trino 조회.
- 기존 retail 테이블·파일과 Trino 읽기 전용 설정 보존. 신규 namespace만 생성.
- 무료 API는 비상업 학습용. 출처: [Open-Meteo](https://open-meteo.com/), 데이터 CC BY 4.0.

## 실행 규칙

- Python 표준 라이브러리 사용. HTTP timeout 30초, 네트워크/429/5xx만 최대 3회 시도.
- 최대 31일, 응답 배열 길이·시간 순서·단위·결측치 검증. 이상 시 적재 전 실패.
- 요청 URL, 원본 JSON, SHA-256, CSV, job 로그, 대사 결과를 실행별 evidence에 보존.
- 기존 범위를 모든 컬럼으로 비교해 동일하면 SKIP. 일부만 있거나 값이 다르면 적재 중단.
- APPEND job을 직접 재실행하지 않는다. job 실패 후 무조건 재시도하지 않고 실제 테이블 상태를 확인한다.
- 로컬 파일 잠금으로 이 래퍼의 동시 실행 방지. 외부 writer와의 분산 동시성/자동 정정은 범위 밖.
- API 페이지네이션 없음. 수집 범위의 시작·종료 날짜로 요청한다.

## 완료 조건

| 조건 | 검증 | 결과 |
| --- | --- | --- |
| 실제 공개 API 수집 | 원본 JSON과 URL 보존 | 통과 |
| Iceberg 적재 및 Trino 조회 | 원본과 168행 전체 컬럼 비교 | 통과: 168행, Parquet 1개 |
| 재실행 중복 방지 | 저장 JSON replay 후 행 수·snapshot 유지 | 통과: SKIP_IDENTICAL, 168행·snapshot 동일 |
| 기존 데이터 보존 | 기존 파일 지문과 주문 조회 비교 | 통과: 28파일 SHA-256 동일, orders 5행·170000 |
| 오류 방지 | 결측·날짜 누락·부분 적재·변경값 테스트 | 통과: 단위 테스트 3개 및 하위 오류 사례 |

## 범위 밖

스케줄링, 자동 upsert/정정, 다중 writer, 리니지 등록, Superset 차트 자동 생성.

## 실행 기록 (2026-11-05)

- 상태: 완료. 요약: `evidence/public-api/verification.json`.
- 첫 요청은 실행 샌드박스 DNS 제한으로 실패. 네트워크 허용 후 실제 응답 확보.
- 첫 적재(`20261105T072050Z-cfd8ac25`)는 168행을 썼으나 SeaTunnel timestamp → Iceberg timestamptz 매핑으로 검증 실패. 한국 현지 시각을 UTC로 오해할 수 있어 ISO 8601 +09:00 string으로 변경.
- 초기 실습 테이블만 타입·위치·168행 조건을 검사한 Java Iceberg 클라이언트로 등록 해제(dropTable, purge=false) 후 재생성했다. 기존 retail 테이블은 변경하지 않았다. 초기 시도의 미참조 파일은 삭제하지 않고 보존했다.
- PyIceberg 0.10의 테이블 조회는 HMS 4에서 `Invalid method name: get_table`로 실패했다. namespace 생성은 성공하며, 복구에는 기존 SeaTunnel의 Java 클라이언트를 사용했다. 일회성 복구 코드는 evidence에 보관한다.
- 수정 후 적재: `20261105T072318Z-3887c148/report.json`, PASS/LOAD, 모든 컬럼 비교 통과.
- 재실행: `20261105T072458Z-0c6ba511/report.json`, PASS/SKIP_IDENTICAL, snapshot `679372500462352873` 유지.
- 기존 파일 검증: `existing-lake-before.json`, `existing-lake-verification.json`. 기존 orders 조회 결과는 5행, 합계 170000.
- 단위 테스트: `python3 -m unittest discover -s tests -p 'test_public_api_weather.py' -v`, 3개 통과.
- 남은 제한: 다른 날짜 범위의 실제 수집, HTTP 429 실서버 장애, 외부 writer 동시 실행은 검증하지 않았다. 정정·부분 중복 구간은 자동 처리하지 않고 중단한다.
