# Airflow로 공개 API 날씨 적재 스케줄링

## 왜 Airflow인가

[공개 API → Iceberg](public-api-to-iceberg.md)에서는 사람이 `--start/--end`를 정해서 래퍼를 직접 실행했다.
Airflow는 **정해진 시간에 작업을 실행하고, 각 단계의 성공/실패/건너뜀 이력을 웹 UI에 남기는 스케줄러**다.
이번 단계에서는 "어느 날짜를 받을지"도 Airflow 실행이 스스로 정하게 해서, 매일 며칠치씩 이어 받는 배치를 만든다.

- **DAG**: Airflow가 실행하는 작업 묶음. 이 프로젝트에서는 `dags/public_weather_to_iceberg.py` 하나.
- **task**: DAG 안의 한 단계. 각 task는 따로 실행되고 따로 재시도할 수 있다.
- **DAG run**: DAG를 한 번 실행한 기록. 스케줄 실행(`scheduled__…`)과 수동 실행(`manual__…`)이 있다.

## 구성

```
Airflow (localhost:8082, 매일 09:00 KST)
  └ public_weather_to_iceberg
      plan ─▶ collect ─▶ precheck ─▶ load ─▶ verify
       │         │           │          │        └ Trino로 전 행 대사, report.json PASS
       │         │           │          └ LOAD일 때만 SeaTunnel(LocalFile → Iceberg sink) + HMS 커밋
       │         │           └ 대상 범위 기존 행 비교: 없음=LOAD / 동일=SKIP_IDENTICAL / 다름=실패
       │         └ Open-Meteo 수집·검증 → evidence/public-api/<run_id>/weather.csv
       └ Trino로 마지막 적재일 조회 → 다음 날부터 batch_days만큼 범위 결정 (없으면 이후 task skip)
```

- 로직은 `src/public_api/weather.py`에 있고, DAG task와 CLI(`scripts/public_api_weather.py`)가 같은 함수를 호출한다.
- Airflow는 `compose.airflow.yaml`로 따로 추가했다. 기존 `compose.yaml`, `compose.analytics.yaml` 서비스는 바꾸지 않았다.
  `airflow-db`(Airflow 실행 이력 저장용 Postgres)는 HMS의 `catalog-db`와 별개다.

### 날짜 범위를 정하는 방법 (증분 배치)

Airflow 실행 날짜로 범위를 계산하지 않고, **테이블에 실제로 들어 있는 마지막 날짜**를 기준으로 삼는다.

```
start = 테이블의 max(weather_time) 날짜 + 1일   (테이블이 비었으면 first_date)
end   = min(start + batch_days - 1,  오늘 - lag_days)
start > end 이면 받을 데이터가 없으므로 skip
```

- 실행끼리 범위가 겹치지 않는다. 실패한 날짜는 다음 실행이 다시 시도한다(빈 구간이 생기지 않는다).
- **ERA5 지연:** 2026-11-09 확인 시 API 값은 2026-11-04 08:00까지만 있고 그 뒤는 null이었다(약 5일 지연).
  그래서 기본 `lag_days=6`이다. null이 섞이면 collect 단계 검증에서 적재 전에 실패한다.
- 밀린 구간이 있으면 하루 1회 실행마다 `batch_days`(기본 7일)씩 따라잡고, 다 따라잡으면 하루에 하루치씩 받는다.

### DAG 파라미터 (UI의 Trigger 화면에서 변경 가능)

| 이름 | 기본값 | 의미 |
|---|---|---|
| `batch_days` | 7 | 한 실행에 받을 최대 일수 (1~31) |
| `lag_days` | 6 | 오늘 - lag_days 이후 날짜는 다음 실행으로 미룸 (최소 5) |
| `first_date` | 2025-10-01 | 테이블이 비어 있을 때의 시작일 |

## 실행

호스트, `iceberg/` 폴더에서 실행한다. Trino가 떠 있어야 한다(plan/precheck/verify가 Trino를 조회한다).

```bash
cd /Users/mz01-jaejunlee/projects/Onboarding/iceberg
bash scripts/up-trino.sh
bash scripts/up-airflow.sh        # 첫 실행은 이미지 빌드 포함
```

성공하면 `Airflow UI: http://localhost:8082`가 출력되고 `docker ps`에 `iceberg-learning-airflow-1 (healthy)`가 보인다.
로그인 화면 없이 관리자 권한으로 열린다(127.0.0.1에만 공개한 로컬 실습 설정).

- 일시정지/해제: UI의 토글, 또는 `docker exec iceberg-learning-airflow-1 airflow dags pause public_weather_to_iceberg`
- 수동 실행: UI의 ▶ Trigger, 또는
  `docker exec iceberg-learning-airflow-1 airflow dags trigger public_weather_to_iceberg --conf '{"batch_days": 3}'`
- 결과 확인:

```bash
bash scripts/trino.sh --execute \
  "SELECT count(*), min(weather_time), max(weather_time) FROM iceberg.public_api.weather_hourly"
```

Airflow를 내릴 때는 Airflow만 멈춘다(다른 서비스와 볼륨은 유지):

```bash
LAB_ROOT=$PWD docker compose -f compose.yaml -f compose.analytics.yaml -f compose.airflow.yaml stop airflow airflow-db
```

## 처음 하는 사람이 밟을 함정

- **컨테이너 안에서 `docker compose`를 부르는 구조.** task가 기존 래퍼처럼 `docker compose run seatunnel`을 호출하므로
  Airflow 컨테이너에 Docker 소켓(`/var/run/docker.sock`)을 마운트했다. 로컬 실습에서는 가장 단순하지만,
  소켓을 가진 컨테이너는 호스트 Docker 전체를 제어할 수 있으므로 운영 환경에서는 쓰지 않는 방식이다
  (운영이라면 KubernetesPodOperator나 SeaTunnel 클러스터 REST 제출 등을 검토).
- **프로젝트를 호스트와 같은 절대 경로로 마운트한다.** `compose.yaml`의 `./lake` 같은 상대 경로는 Docker 데몬 쪽에서
  호스트 경로로 해석된다. 컨테이너 안 경로가 `/opt/lab`처럼 다르면 SeaTunnel 컨테이너에 엉뚱한 빈 폴더가 붙는다.
  그래서 `up-airflow.sh`가 `LAB_ROOT=$(pwd)`를 넘겨 같은 경로로 마운트한다. `compose.airflow.yaml`을 직접 쓸 때도 `LAB_ROOT`가 필요하다.
- **소켓 권한.** Airflow는 uid 50000으로 실행된다. Rancher Desktop VM의 소켓 그룹(이 Mac에서는 gid 102)을
  `up-airflow.sh`가 조회해 `group_add`로 넣는다.
- **포트.** 8080(openmetadata Airflow), 8081(Trino)과 겹치지 않게 **8082**를 쓴다.
- **동시 실행.** `max_active_runs=1`로 Airflow 실행끼리는 순서대로 돈다. 하지만 호스트에서 CLI를 동시에 돌리는 것까지는 막지 못한다
  (`data/public-api/.lock`은 호스트와 컨테이너 사이에서 공유된다고 확인하지 않았다). Airflow가 켜져 있으면 CLI 적재는 하지 않는다.

## 실행 기록 (2026-11-09, 실제 실행으로 확인)

| DAG run | 결과 | 범위 | 적재 | 누적 행 |
|---|---|---|---|---|
| (기존 11/5 CLI) | — | 2025-10-01~07 | 168 | 168 |
| `scheduled__2026-11-09T00:00:00+00:00` (일시정지 해제 직후 자동 실행) | success | 2025-10-08~14 | 168 | 336 |
| `manual__…00:41:55` (`batch_days=3`) | success | 2025-10-15~17 | 72 | 408 |
| `manual__…00:42:40` (`lag_days=400`, 받을 날짜 없음) | success, plan 이후 4개 task skipped | — | 0 | 408 |

- Trino 확인: 408행 = 408개 고유 시각, `2025-10-01T00:00:00+09:00` ~ `2025-10-17T23:00:00+09:00`, snapshot 3개.
- 기존 데이터 보존: `retail.orders` 5행 / 합계 170000, `existing-lake-before.json`의 28개 파일 SHA-256 모두 동일.
- 리팩터링 회귀 확인: CLI로 11/5 응답을 replay → `SKIP_IDENTICAL`, 168행.
- 단위 테스트 8개 통과 (`plan_window` 5개 추가).
- 실행별 산출물: `evidence/public-api/<run_id>/` (Git 제외). `report.json`의 `trigger`에 Airflow run_id가 기록된다.

검증하지 않은 것: 다음 날 09:00 스케줄이 실제로 도는지(일시정지 해제 직후 실행만 확인), API 실패(429/5xx) 시 Airflow 재시도 동작,
ERA5 과거 값 정정 발생 여부. 값 정정이 생기면 precheck가 실패하고 적재하지 않는다.
