import unittest

from src.securities_lending_monitor import normalize_twt93u_row, summarize_lending_rows


class SecuritiesLendingMonitorTests(unittest.TestCase):
    def test_summarize_lending_rows_totals_market_and_watchlist_items(self):
        rows = [
            {"證券代號": "2330", "證券名稱": "TSMC", "借券賣出餘額": "10,000", "借券賣出當日增減": "1,500"},
            {"證券代號": "2308", "證券名稱": "Delta", "借券賣出餘額": "5,000", "借券賣出當日增減": "-500"},
            {"證券代號": "9999", "證券名稱": "Other", "借券賣出餘額": "2,000", "借券賣出當日增減": "100"},
        ]

        summary = summarize_lending_rows(rows, {"2330", "2308"})

        self.assertEqual(summary["market"]["total_lending_balance"], 17000)
        self.assertEqual(summary["market"]["total_daily_change"], 1100)
        self.assertEqual(summary["market"]["daily_change_ratio"], 0.0647)
        self.assertEqual([item["code"] for item in summary["watchlist_items"]], ["2330", "2308"])

    def test_normalize_twt93u_row_preserves_duplicate_balance_fields(self):
        raw = ["2330", "TSMC", "1", "2", "3", "4", "5", "6", "10,000", "300", "100", "0", "10,200", "7", ""]

        row = normalize_twt93u_row(raw)
        summary = summarize_lending_rows([row], {"2330"})

        self.assertEqual(row["lending_previous_balance"], "10,000")
        self.assertEqual(row["lending_balance"], "10,200")
        self.assertEqual(summary["market"]["total_daily_change"], 200)


if __name__ == "__main__":
    unittest.main()
