import unittest
from pathlib import Path

from src.daily_briefing import DEFAULT_BRIEFING_DIR, build_briefing_markdown, build_coverage_index


class DailyBriefingTests(unittest.TestCase):
    def test_default_briefing_dir_is_separate_from_intraday_notes(self):
        self.assertEqual(DEFAULT_BRIEFING_DIR, Path("docs/notes/每日看盤筆記").resolve())
        self.assertNotEqual(DEFAULT_BRIEFING_DIR, Path("docs/notes/看盤筆記").resolve())

    def test_build_coverage_index_uses_four_digit_codes(self):
        coverage = {
            "items": [
                {"code": "2330", "found": True, "themes": ["AI", "CoWoS"]},
                {"code": "0050", "found": False, "themes": ["ETF"]},
            ]
        }

        index = build_coverage_index(coverage)

        self.assertIn("2330", index)
        self.assertNotIn("0050", index)

    def test_build_briefing_markdown_includes_core_sections(self):
        market = {
            "總覽": [{"類別": "市場", "指標": "加權指數", "當日數值": 39521.73, "單日變動": "-0.8%"}],
            "個股籌碼": [
                {
                    "股票代號": 2330,
                    "股票名稱": "台積電",
                    "收盤價": 2135,
                    "漲跌幅(%)": -2.06,
                    "外資當日(張)": -1200,
                    "投信當日(張)": 300,
                    "融資增減(張)": 100,
                    "MA20乖離(%)": -1.2,
                }
            ],
            "權證監控": [
                {"權證代碼": 55145, "權證名稱": "台積電元大58購01", "漲跌幅%": -12.29, "買賣價差比%": 11.98, "實質槓桿": 30.55}
            ],
        }
        derivatives = {
            "summary": {"risk_score": 75, "bias": "risk_off"},
            "futures": {"basis": -31.73, "basis_pct": -0.08},
            "positioning": {"foreign_tx_net_open_interest": -47074},
            "options": {"pc_ratio": 171.12, "pc_ratio_5d_avg": 143.08},
        }
        coverage = {
            "items": [
                {"code": "2330", "found": True, "themes": ["AI 伺服器", "CoWoS"], "customers_suppliers": ["NVIDIA"]}
            ]
        }

        markdown = build_briefing_markdown("20260429", market, derivatives, coverage)

        self.assertIn("# 每日看盤筆記 20260429", markdown)
        self.assertIn("## 期貨 / 選擇權風險", markdown)
        self.assertIn("風險偏空", markdown)
        self.assertIn("台積電", markdown)
        self.assertIn("AI 伺服器, CoWoS", markdown)
        self.assertIn("## 權證監控", markdown)


if __name__ == "__main__":
    unittest.main()
