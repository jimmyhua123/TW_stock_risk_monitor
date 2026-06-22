import unittest

from monthly_run import build_steps


class MonthlyRunTests(unittest.TestCase):
    def test_monthly_run_includes_low_frequency_jobs(self):
        descriptions = [description for _, description, _ in build_steps("20260612")]

        self.assertIn("全球市場與總經資料", descriptions)
        self.assertIn("個股產業與題材補充", descriptions)
        self.assertIn("股期換月轉倉逆價差監控", descriptions)
        self.assertNotIn("美股產業資金流報告", descriptions)

    def test_monthly_run_can_include_heavy_sector_flow(self):
        descriptions = [description for _, description, _ in build_steps("20260612", include_sector_flow=True)]

        self.assertIn("美股產業資金流報告", descriptions)

    def test_monthly_sector_flow_runs_structured_json_monitor(self):
        steps = build_steps("20260612", include_sector_flow=True)
        sector_cmd = next(cmd for _, description, cmd in steps if description == "美股產業資金流報告")

        self.assertEqual(["-m", "src.us_sector_flow_monitor"], sector_cmd[1:3])
        self.assertIn("--date", sector_cmd)
        self.assertIn("20260612", sector_cmd)

    def test_monthly_run_passes_date_to_date_aware_jobs(self):
        steps = build_steps("20260612")

        for _, description, cmd in steps:
            self.assertIn("--date", cmd, description)
            self.assertIn("20260612", cmd, description)


if __name__ == "__main__":
    unittest.main()
