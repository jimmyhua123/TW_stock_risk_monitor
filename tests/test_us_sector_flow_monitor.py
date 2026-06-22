import unittest

import pandas as pd

from src.us_sector_flow_monitor import has_usable_sector_data, summarize_sector_flow


class UsSectorFlowMonitorTests(unittest.TestCase):
    def test_summarize_sector_flow_calculates_alpha_against_spy(self):
        dates = pd.date_range("2026-01-01", periods=130, freq="B")
        closes = pd.DataFrame(
            {
                "SPY": [100 + i for i in range(130)],
                "XLK": [100 + i * 1.5 for i in range(130)],
                "XLV": [100 + i * 0.5 for i in range(130)],
                "SMH": [100 + i * 2 for i in range(130)],
            },
            index=dates,
        )

        summary = summarize_sector_flow(closes, windows={"6M": 126})

        sectors = summary["periods"]["6M"]["sectors"]
        tickers = [item["ticker"] for item in sectors]
        self.assertEqual(tickers[:2], ["SMH", "XLK"])
        smh = sectors[0]
        self.assertEqual(smh["benchmark_return_pct"], 122.33)
        self.assertEqual(smh["return_pct"], 237.74)
        self.assertEqual(smh["alpha_pct"], 115.41)

    def test_has_usable_sector_data_rejects_empty_payloads(self):
        self.assertFalse(has_usable_sector_data({"periods": {}}))
        self.assertFalse(has_usable_sector_data({"periods": {"6M": {"sectors": []}}}))
        self.assertTrue(has_usable_sector_data({"periods": {"6M": {"sectors": [{"ticker": "XLK"}]}}}))


if __name__ == "__main__":
    unittest.main()
