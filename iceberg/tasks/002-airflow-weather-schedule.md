# Airflow 스케줄링: 공개 API 날씨 증분 적재

## 목표와 계약

- `public_api.weather_hourly`를 Airflow DAG `public_weather_to_iceberg`로 매일 09:00(KST) 이어 받는다.
- 범위: 테이블의 마지막 날짜 다음 날부터 `batch_days`(기본 7) 일, 단 `오늘 - lag_days`(기본 6)까지. 없으면 skip.
- 001의 검증·선행 검사·적재·대사 규칙을 그대로 사용한다. 로직은 `src/public_api/weather.py`로 옮겨 CLI와 DAG가 공유한다.
- Airflow는 `compose.airflow.yaml`(Airflow 3.3.1 standalone + 전용 Postgres), 호스트 포트 8082. 기존 Compose 파일은 변경하지 않는다.

## 완료 조건

| 조건 | 검증 | 결과 |
| --- | --- | --- |
| 원천 API 데이터 범위 확인 | 다른 범위 직접 요청 | 통과: 1940-01-01부터 제공, 2025-10 744행, 2024년 8784행. 최근 약 5일은 null |
| 리팩터링 회귀 없음 | CLI replay, 단위 테스트 | 통과: SKIP_IDENTICAL 168행, 테스트 8개 |
| 스케줄 실행 적재 | scheduled run | 통과: 2025-10-08~14, 168행, 누적 336 |
| 파라미터 실행 | `batch_days=3` | 통과: 2025-10-15~17, 72행, 누적 408 |
| 새 데이터 없음 처리 | `lag_days=400` | 통과: plan 이후 skipped, 행 변화 없음 |
| 중복 없음 | Trino count vs distinct | 통과: 408 = 408 |
| 기존 데이터 보존 | SHA-256, orders 조회 | 통과: 28파일 동일, orders 5행·170000 |

## 범위 밖

운영용 실행 방식(소켓 마운트 대체), 분산 잠금, 값 정정/upsert, 알림, 리니지.

## 실행 기록 (2026-11-09)

상세: `docs/airflow-weather-dag.md`. DAG는 일시정지 해제 상태로 두었다. 매일 09:00에 7일씩 따라잡는다.
