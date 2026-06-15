import tempfile
import unittest
from pathlib import Path

from src.group_monitor import (
    build_group_analysis,
    infer_groups,
    load_watchlist,
    normalize_code,
    render_text_report,
    run,
)


MARKET_REPORT = {
    "個股籌碼": [
        {
            "股票代號": 50,
            "股票名稱": "0050",
            "收盤價": 99.85,
            "漲跌幅(%)": -0.4,
            "成交量(張)": 299040,
            "外資當日(張)": -91840,
            "外資5日累計": 27927,
            "投信當日(張)": 2846,
            "投信5日累計": 7880,
            "自營商當日(張)": 112662,
            "融資增減(張)": 12383,
            "融資5日累計": 45120,
            "借券增減(張)": -5094824,
            "MA20乖離(%)": 0.53,
        },
        {
            "股票代號": 2330,
            "股票名稱": "台積電",
            "收盤價": 1200,
            "漲跌幅(%)": 2.5,
            "成交量(張)": 50000,
            "外資當日(張)": 12000,
            "外資5日累計": 30000,
            "投信當日(張)": 1500,
            "投信5日累計": 3500,
            "自營商當日(張)": 800,
            "融資增減(張)": -300,
            "融資5日累計": -1200,
            "借券增減(張)": 100,
            "MA20乖離(%)": 4.2,
        },
    ]
}


class GroupMonitorTests(unittest.TestCase):
    def test_normalize_code_pads_numeric_stock_codes(self):
        self.assertEqual(normalize_code(50), "0050")
        self.assertEqual(normalize_code("2330"), "2330")
        self.assertEqual(normalize_code("00631L"), "00631L")

    def test_load_watchlist_supports_groups_and_legacy_items(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "watchlist.json"
            path.write_text(
                """
                {
                  "watchlist": [
                    {"code": "2330", "name": "台積電", "groups": ["半導體", "AI"], "thesis": "先進製程"},
                    {"code": "0050", "name": "0050"}
                  ]
                }
                """,
                encoding="utf-8",
            )

            watchlist = load_watchlist(path)

        self.assertEqual(watchlist[0]["groups"], ["半導體", "AI"])
        self.assertEqual(watchlist[1]["groups"], [])

    def test_infer_groups_uses_coverage_when_watchlist_has_only_code_and_name(self):
        watch_item = {"code": "2330", "name": "台積電", "groups": []}
        coverage_item = {
            "found": True,
            "sector": "Technology",
            "industry": "Semiconductors",
            "themes": ["AI", "CoWoS", "NVIDIA", "Advanced Packaging"],
        }

        groups = infer_groups(watch_item, coverage_item)

        self.assertEqual(groups, ["Technology", "Semiconductors", "AI", "CoWoS", "NVIDIA"])

    def test_infer_groups_keeps_watchlist_groups_first(self):
        watch_item = {"code": "2330", "name": "台積電", "groups": ["半導體"]}
        coverage_item = {"found": True, "sector": "Technology", "themes": ["AI"]}

        groups = infer_groups(watch_item, coverage_item)

        self.assertEqual(groups, ["半導體"])

    def test_build_group_analysis_ranks_groups_and_marks_missing_stocks(self):
        watchlist = [
            {"code": "2330", "name": "台積電", "groups": ["半導體"], "thesis": "AI 需求", "peers": [], "risk_notes": ["匯率"], "priority": "core"},
            {"code": "0050", "name": "0050", "groups": ["ETF"], "thesis": "", "peers": [], "risk_notes": [], "priority": ""},
            {"code": "2454", "name": "聯發科", "groups": ["半導體"], "thesis": "", "peers": [], "risk_notes": [], "priority": ""},
        ]

        analysis = build_group_analysis(
            watchlist,
            MARKET_REPORT,
            {},
            date="20260611",
            source_report="outputs/json/20260611.json",
            source_watchlist="data/config/watchlist.json",
        )

        semiconductor = next(group for group in analysis["groups"] if group["group"] == "半導體")
        self.assertEqual(semiconductor["stock_count"], 2)
        self.assertEqual(semiconductor["covered_count"], 1)
        self.assertEqual(semiconductor["missing"][0]["code"], "2454")
        self.assertIn("AI 需求", semiconductor["theses"])
        self.assertIn("匯率", semiconductor["risk_notes"])

    def test_render_text_report_contains_group_summary(self):
        watchlist = [{"code": "2330", "name": "台積電", "groups": ["半導體"], "thesis": "", "peers": [], "risk_notes": [], "priority": ""}]
        analysis = build_group_analysis(
            watchlist,
            MARKET_REPORT,
            {},
            date="20260611",
            source_report="report.json",
            source_watchlist="watchlist.json",
        )

        report = render_text_report(analysis)

        self.assertIn("Watchlist 族群分析 20260611", report)
        self.assertIn("半導體", report)
        self.assertIn("台積電", report)

    def test_run_writes_json_and_text_outputs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            watchlist_path = root / "watchlist.json"
            report_path = root / "20260611.json"
            json_dir = root / "group_json"
            txt_dir = root / "group_txt"
            watchlist_path.write_text('{"watchlist": [{"code": "2330", "name": "台積電", "groups": ["半導體"]}]}', encoding="utf-8")
            report_path.write_text(__import__("json").dumps(MARKET_REPORT, ensure_ascii=False), encoding="utf-8")

            analysis, json_path, txt_path = run(
                date="20260611",
                watchlist_path=watchlist_path,
                report_path=report_path,
                json_dir=json_dir,
                txt_dir=txt_dir,
            )

        self.assertEqual(len(analysis["groups"]), 1)
        self.assertTrue(json_path.name.endswith("20260611.json"))
        self.assertTrue(txt_path.name.endswith("20260611.txt"))


if __name__ == "__main__":
    unittest.main()
