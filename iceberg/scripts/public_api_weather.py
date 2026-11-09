#!/usr/bin/env python3
"""Open-Meteo archive -> validated CSV -> SeaTunnel Iceberg -> Trino comparison.

Standard library only. The steps live in src/public_api/weather.py and are shared
with the Airflow DAG (dags/public_weather_to_iceberg.py).
"""
import argparse
from datetime import date
import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent / 'src'))

from public_api import weather  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=date.fromisoformat, default=date(2025, 10, 1))
    parser.add_argument('--end', type=date.fromisoformat, default=date(2025, 10, 7))
    parser.add_argument('--replay', type=Path, help='Replay saved API JSON without HTTP')
    args = parser.parse_args()
    if not 0 <= (args.end - args.start).days < weather.MAX_DAYS:
        parser.error(f'Choose an inclusive range of 1 to {weather.MAX_DAYS} days')
    out = weather.new_run(args.start, args.end, replay=args.replay)
    rows = weather.collect(out)
    action = weather.precheck(out)
    weather.load(out)
    weather.verify(out)
    print(json.dumps({'status': 'PASS', 'action': action,
                      'rows': rows, 'table': weather.TABLE}, indent=2))


if __name__ == '__main__':
    main()
