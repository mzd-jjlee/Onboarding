import os
import sys
from pathlib import Path

# import error 방지를 위해 src 폴더를 python path에 추가
sys.path.append(os.path.abspath(os.path.join(Path(__file__).parent.parent, "src")))

import pendulum
from airflow.sdk import dag, task, Param


@dag(
    dag_id="public_weather_to_iceberg",
    schedule="0 9 * * *",  # 매일 09:00 (Asia/Seoul)
    start_date=pendulum.datetime(2026, 11, 1, tz="Asia/Seoul"),
    catchup=False,
    max_active_runs=1,
    description="Open-Meteo 서울 시간별 날씨를 며칠치씩 이어 받아 Iceberg public_api.weather_hourly에 적재",
    render_template_as_native_obj=True,
    tags=["iceberg", "public-api", "seatunnel"],
    params={
        "batch_days": Param(
            7,
            type="integer",
            minimum=1,
            maximum=31,
            title="Batch Days",
            description="한 번 실행에 가져올 최대 일수 (API 1회 요청 최대 31일)",
        ),
        "lag_days": Param(
            6,
            type="integer",
            minimum=5,
            title="ERA5 Lag Days",
            description="ERA5 값은 약 5일 늦게 채워진다. 오늘 - lag_days 이후 날짜는 다음 실행으로 미룬다.",
        ),
        "first_date": Param(
            "2025-10-01",
            type="string",
            format="date",
            title="First Date",
            description="테이블이 비어 있을 때 시작할 날짜. 데이터가 있으면 마지막 적재일 다음 날부터 이어 받는다.",
        ),
    },
)
def public_weather_to_iceberg():
    """서울 날씨 증분 배치.

    1. plan: Trino로 테이블의 마지막 적재일을 읽고, 그 다음 날부터 batch_days만큼(ERA5 지연 제외) 범위 결정.
       새로 받을 날짜가 없으면 이후 task를 skip.
    2. collect: Open-Meteo API 수집 + 검증 → evidence/public-api/<run_id>/weather.csv
    3. precheck: 대상 범위의 기존 행과 비교 (없으면 LOAD, 동일하면 SKIP_IDENTICAL, 다르면 실패)
    4. load: LOAD일 때만 SeaTunnel(LocalFile → Iceberg sink) 실행, HMS 커밋
    5. verify: Trino로 전 행 대사 및 report.json 마무리
    """

    @task.short_circuit
    def plan(**kwargs):
        from datetime import date
        from public_api.weather import latest_loaded_date, plan_window

        params = kwargs["params"]
        today = pendulum.now("Asia/Seoul").date()
        window = plan_window(
            latest_loaded_date(), today, params["batch_days"], params["lag_days"],
            date.fromisoformat(params["first_date"]),
        )
        print(f"today={today} window={window}")
        return {"start": str(window[0]), "end": str(window[1])} if window else False

    @task
    def collect(window, **kwargs):
        from datetime import date
        from public_api.weather import collect, new_run

        out = new_run(date.fromisoformat(window["start"]), date.fromisoformat(window["end"]),
                      trigger=f"airflow:{kwargs['run_id']}")
        collect(out)
        return str(out)

    @task
    def precheck(run_dir):
        from public_api.weather import precheck

        return precheck(Path(run_dir))

    @task
    def load(run_dir):
        from public_api.weather import load

        return load(Path(run_dir))

    @task
    def verify(run_dir):
        from public_api.weather import verify

        return verify(Path(run_dir))

    # ── Flow 정의 ──
    window = plan()
    run_dir = collect(window)
    checked = precheck(run_dir)
    loaded = load(run_dir)
    verified = verify(run_dir)
    window >> run_dir >> checked >> loaded >> verified


public_weather_to_iceberg()
