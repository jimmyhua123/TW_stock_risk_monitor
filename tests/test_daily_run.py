import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from daily_run import build_steps


class DailyRunTests(unittest.TestCase):
    def test_daily_run_excludes_non_daily_steps_by_default(self):
        with TemporaryDirectory() as temp_dir:
            descriptions = [
                description for _, description, _ in build_steps("20260611", project_root=Path(temp_dir))
            ]

        self.assertIn("台灣風險監控報告", descriptions)
        self.assertIn("期貨與選擇權風險", descriptions)
        self.assertIn("Watchlist 族群分析", descriptions)
        self.assertIn("每日看盤筆記", descriptions)
        self.assertNotIn("全球市場與總經數據", descriptions)
        self.assertNotIn("股期換月轉倉逆價差監控", descriptions)
        self.assertIn("個股產業與題材補充", descriptions)

    def test_daily_run_can_refresh_coverage_when_requested(self):
        with TemporaryDirectory() as temp_dir:
            descriptions = [
                description
                for _, description, _ in build_steps(
                    "20260611",
                    refresh_coverage=True,
                    project_root=Path(temp_dir),
                )
            ]

        self.assertIn("個股產業與題材補充", descriptions)

    def test_daily_run_skips_network_fetch_steps_when_outputs_exist(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "outputs" / "json").mkdir(parents=True)
            (root / "outputs" / "derivatives_json").mkdir(parents=True)
            (root / "outputs" / "coverage_json").mkdir(parents=True)
            (root / "outputs" / "json" / "20260611.json").write_text("{}", encoding="utf-8")
            (root / "outputs" / "derivatives_json" / "derivatives_20260611.json").write_text("{}", encoding="utf-8")
            (root / "outputs" / "coverage_json" / "coverage_20260611.json").write_text("{}", encoding="utf-8")

            descriptions = [
                description for _, description, _ in build_steps("20260611", project_root=root)
            ]

        self.assertNotIn("台灣風險監控報告", descriptions)
        self.assertNotIn("Excel 轉 JSON / TXT", descriptions)
        self.assertNotIn("期貨與選擇權風險", descriptions)
        self.assertNotIn("個股產業與題材補充", descriptions)
        self.assertIn("Watchlist 族群分析", descriptions)
        self.assertIn("每日看盤筆記", descriptions)

    def test_daily_run_uses_risk_report_json_when_date_is_omitted(self):
        with TemporaryDirectory() as temp_dir:
            steps = build_steps(None, project_root=Path(temp_dir))
        group_cmd = next(cmd for _, description, cmd in steps if description == "Watchlist 族群分析")

        self.assertIn("--report", group_cmd)
        self.assertIn("outputs\\json\\risk_report.json", group_cmd)


if __name__ == "__main__":
    unittest.main()
