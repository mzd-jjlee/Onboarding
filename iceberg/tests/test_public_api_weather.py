import copy
from datetime import date
from pathlib import Path
import sys
import unittest

sys.path.append(str(Path(__file__).resolve().parents[1] / 'src'))

from public_api import weather as w  # noqa: E402


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.day = date(2025, 10, 1)
        self.payload = {
            'utc_offset_seconds': 32400,
            'hourly_units': {'temperature_2m': '°C', 'relative_humidity_2m': '%', 'precipitation': 'mm'},
            'hourly': {'time': [f'2025-10-01T{h:02d}:00' for h in range(24)],
                       'temperature_2m': [20.5]*24, 'relative_humidity_2m': [60]*24, 'precipitation': [0.0]*24}}

    def test_valid_and_replay(self):
        rows = w.normalize(self.payload, self.day, self.day)
        self.assertEqual(len(rows), 24)
        self.assertEqual(rows[0][1], '2025-10-01T00:00:00+09:00')
        self.assertEqual(w.decision(rows, []), 'LOAD')
        self.assertEqual(w.decision(rows, rows), 'SKIP_IDENTICAL')

    def test_missing_null_units_and_duplicates(self):
        for mutation in ('length', 'null', 'units', 'duplicate', 'timezone', 'nan', 'humidity'):
            p = copy.deepcopy(self.payload)
            if mutation == 'length': p['hourly']['precipitation'].pop()
            if mutation == 'null': p['hourly']['temperature_2m'][0] = None
            if mutation == 'units': p['hourly_units']['temperature_2m'] = '°F'
            if mutation == 'duplicate': p['hourly']['time'][1] = p['hourly']['time'][0]
            if mutation == 'timezone': p['utc_offset_seconds'] = 0
            if mutation == 'nan': p['hourly']['temperature_2m'][0] = float('nan')
            if mutation == 'humidity': p['hourly']['relative_humidity_2m'][0] = 101
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                w.normalize(p, self.day, self.day)

    def test_partial_changed_or_duplicate_target_blocks_append(self):
        rows = w.normalize(self.payload, self.day, self.day)
        changed = copy.deepcopy(rows)
        changed[0][2] = 99.0
        for existing in (rows[:1], changed, rows + rows[:1]):
            with self.subTest(existing=len(existing)), self.assertRaises(ValueError):
                w.decision(rows, existing)


class PlanWindowTests(unittest.TestCase):
    today = date(2026, 11, 9)

    def test_continues_after_latest_loaded_day(self):
        self.assertEqual(w.plan_window(date(2025, 10, 7), self.today, 7, 6, date(2025, 10, 1)),
                         (date(2025, 10, 8), date(2025, 10, 14)))

    def test_empty_table_starts_at_first_date(self):
        self.assertEqual(w.plan_window(None, self.today, 3, 6, date(2025, 10, 1)),
                         (date(2025, 10, 1), date(2025, 10, 3)))

    def test_window_stops_at_era5_lag(self):
        self.assertEqual(w.plan_window(date(2026, 10, 30), self.today, 7, 6, date(2025, 10, 1)),
                         (date(2026, 10, 31), date(2026, 11, 3)))

    def test_nothing_new_returns_none(self):
        self.assertIsNone(w.plan_window(date(2026, 11, 3), self.today, 7, 6, date(2025, 10, 1)))

    def test_batch_days_limit(self):
        for days in (0, 32):
            with self.subTest(days=days), self.assertRaises(ValueError):
                w.plan_window(None, self.today, days, 6, date(2025, 10, 1))


if __name__ == '__main__':
    unittest.main()
