import unittest

import pandas as pd

from src.defensive_rotation_monitor import summarize_defensive_rotation


class DefensiveRotationMonitorTests(unittest.TestCase):
    def test_identifies_taiwan_financial_outperformance_with_market_breakdown(self):
        dates = pd.date_range("2026-01-01", periods=25, freq="B")
        closes = pd.DataFrame(
            {
                "^TWII": [100] * 20 + [99, 98, 97, 96, 95],
                "0055.TW": [100] * 20 + [101, 102, 103, 104, 105],
                "SPY": [100] * 25,
                "EWL": [100] * 25,
                "DX-Y.NYB": [100] * 25,
            },
            index=dates,
        )

        summary = summarize_defensive_rotation(closes)

        self.assertEqual(summary["taiwan"]["signal"], "downtrend_risk")
        self.assertEqual(summary["taiwan"]["relative_strength"]["return_pct"], 10.53)
        self.assertEqual(summary["summary"]["signal"], "elevated_downtrend_risk")

    def test_treats_swiss_outperformance_during_strong_dollar_as_rate_defense(self):
        dates = pd.date_range("2026-01-01", periods=25, freq="B")
        closes = pd.DataFrame(
            {
                "^TWII": [100] * 25,
                "0055.TW": [100] * 25,
                "SPY": [100] * 20 + [99, 98, 97, 96, 95],
                "EWL": [100] * 20 + [101, 102, 103, 104, 105],
                "DX-Y.NYB": [100] * 20 + [101, 102, 103, 104, 105],
            },
            index=dates,
        )

        summary = summarize_defensive_rotation(closes)

        self.assertEqual(summary["us"]["signal"], "usd_defense")
        self.assertEqual(summary["summary"]["signal"], "neutral")

    def test_does_not_label_usd_defense_without_swiss_outperformance(self):
        dates = pd.date_range("2026-01-01", periods=25, freq="B")
        closes = pd.DataFrame(
            {
                "^TWII": [100] * 25,
                "0055.TW": [100] * 25,
                "SPY": [100] * 25,
                "EWL": [100] * 25,
                "DX-Y.NYB": [100] * 20 + [101, 102, 103, 104, 105],
            },
            index=dates,
        )

        summary = summarize_defensive_rotation(closes)

        self.assertEqual(summary["us"]["signal"], "neutral")


if __name__ == "__main__":
    unittest.main()
