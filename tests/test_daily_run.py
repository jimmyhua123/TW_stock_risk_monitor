import unittest

from daily_run import build_steps


class DailyRunTests(unittest.TestCase):
    def test_daily_run_excludes_non_daily_steps_by_default(self):
        descriptions = [description for _, description, _ in build_steps("20260611")]

        self.assertIn("台灣風險監控報告", descriptions)
        self.assertIn("期貨與選擇權風險", descriptions)
        self.assertIn("Watchlist 族群分析", descriptions)
        self.assertIn("每日看盤筆記", descriptions)
        self.assertNotIn("全球市場與總經數據", descriptions)
        self.assertNotIn("股期換月轉倉逆價差監控", descriptions)
        self.assertNotIn("個股產業與題材補充", descriptions)

    def test_daily_run_can_refresh_coverage_when_requested(self):
        descriptions = [description for _, description, _ in build_steps("20260611", refresh_coverage=True)]

        self.assertIn("個股產業與題材補充", descriptions)

    def test_daily_run_uses_risk_report_json_when_date_is_omitted(self):
        steps = build_steps(None)
        group_cmd = next(cmd for _, description, cmd in steps if description == "Watchlist 族群分析")

        self.assertIn("--report", group_cmd)
        self.assertIn("outputs\\json\\risk_report.json", group_cmd)


if __name__ == "__main__":
    unittest.main()
