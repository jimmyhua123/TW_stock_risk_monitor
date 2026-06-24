import unittest
from pathlib import Path

from src.daily_briefing import (
    DEFAULT_BRIEFING_DIR,
    build_briefing_markdown,
    build_coverage_index,
    format_signal,
    render_risk_trend_summary,
    summarize_risk_history,
)


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

    def test_format_signal_uses_clear_risk_direction_labels(self):
        self.assertEqual(format_signal("risk_on"), "風險偏低 / 偏多環境")
        self.assertEqual(format_signal("risk_off"), "風險偏高 / 偏空環境")

    def test_summarize_risk_history_uses_rolling_averages(self):
        history = [
            {"date": "20260612", "score": 70, "bias": "risk_off"},
            {"date": "20260615", "score": 68, "bias": "neutral"},
            {"date": "20260616", "score": 60, "bias": "neutral"},
            {"date": "20260617", "score": 72, "bias": "risk_off"},
            {"date": "20260618", "score": 35, "bias": "risk_on"},
        ]

        trend = summarize_risk_history(history)
        lines = render_risk_trend_summary(history)
        markdown = "\n".join(lines)

        self.assertEqual(trend["current"], 35)
        self.assertEqual(trend["delta"], -37)
        self.assertEqual(trend["ma3"], 55.7)
        self.assertEqual(trend["ma5"], 61.0)
        self.assertIn("5日風險均值", markdown)
        self.assertIn("不宜直接解讀成穩定偏多", markdown)

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
            "summary": {"risk_score": 90, "bias": "risk_off"},
            "futures": {"basis": -120.0, "basis_pct": -0.30},
            "positioning": {"foreign_tx_net_open_interest": -47074},
            "options": {"pc_ratio": 171.12, "pc_ratio_5d_avg": 143.08},
        }
        coverage = {
            "items": [
                {"code": "2330", "found": True, "themes": ["AI 伺服器", "CoWoS"], "customers_suppliers": ["NVIDIA"]}
            ]
        }

        markdown = build_briefing_markdown("20260429", market, derivatives, coverage)

        self.assertIn("20260429", markdown)
        self.assertIn("Put/Call Ratio", markdown)
        self.assertIn("bearish", markdown)
        self.assertIn("+15", markdown)
        self.assertIn("90", markdown)
        self.assertIn("MA5/MA10/MA20", markdown)
        self.assertIn("SOX", markdown)
        self.assertIn("Nasdaq", markdown)
        self.assertIn("2330", markdown)
        self.assertIn("CoWoS", markdown)
        self.assertIn("055145", markdown)

    def test_build_briefing_markdown_uses_monthly_global_inputs(self):
        market = {"蝮質汗": [], "?蝐Ⅳ": []}
        derivatives = {"summary": {"risk_score": 50}}
        global_market = {
            "market_data": {
                "Americas": [{"ticker": "^IXIC", "change": -2.2}],
                "Rates_Forex": [{"ticker": "USDTWD=X", "change": 0.5}],
            }
        }
        sector_flow = {
            "periods": {
                "6M": {"sectors": [{"ticker": "XLK", "alpha_pct": -7.0}]}
            }
        }

        markdown = build_briefing_markdown(
            "20260429",
            market,
            derivatives,
            global_market_data=global_market,
            us_sector_flow_data=sector_flow,
        )

        self.assertIn("Nasdaq", markdown)
        self.assertIn("USD/TWD", markdown)
        self.assertIn("US tech sector", markdown)

    def test_build_briefing_markdown_includes_defensive_rotation_factor(self):
        markdown = build_briefing_markdown(
            "20260624",
            {"overview": [], "stocks": []},
            {"summary": {"risk_score": 50}},
            defensive_rotation_data={
                "taiwan": {"signal": "downtrend_risk"},
                "us": {"signal": "neutral"},
                "summary": {"signal": "elevated_downtrend_risk"},
            },
        )

        self.assertIn("Taiwan defensive rotation", markdown)

    def test_build_briefing_marks_non_risk_rotation_as_zero_points(self):
        markdown = build_briefing_markdown(
            "20260624",
            {"overview": [], "stocks": []},
            {"summary": {"risk_score": 50}},
            defensive_rotation_data={
                "taiwan": {"signal": "healthy_rotation"},
                "us": {"signal": "usd_defense"},
                "summary": {"signal": "neutral"},
            },
        )

        self.assertIn("Taiwan defensive rotation: 0", markdown)
        self.assertIn("Swiss defensive rotation: 0", markdown)

    def test_build_briefing_shows_zero_point_rotation_status_without_data(self):
        markdown = build_briefing_markdown(
            "20260624",
            {"overview": [], "stocks": []},
            {"summary": {"risk_score": 50}},
        )

        self.assertIn("Taiwan defensive rotation: 0", markdown)
        self.assertIn("Swiss defensive rotation: 0", markdown)


if __name__ == "__main__":
    unittest.main()
