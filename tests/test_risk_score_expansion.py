import unittest

from src.risk_score_expansion import expanded_risk_summary


class RiskScoreExpansionTests(unittest.TestCase):
    def test_expanded_risk_summary_uses_available_market_and_stock_data(self):
        market = {
            "概況": [
                {"指標": "加權指數 (TWII)", "當日數值": "43000", "單日變動": "-1.80%"},
                {"指標": "櫃買指數 (OTC)", "當日數值": "250", "單日變動": "-2.10%"},
                {"指標": "費半指數 (SOX)", "當日數值": "5000", "單日變動": "-3.20%"},
                {"指標": "恐慌指數 (VIX)", "當日數值": "28.5", "單日變動": "+12.00%"},
            ],
            "自選股": [
                {
                    "代號": "2330",
                    "名稱": "台積電",
                    "漲跌幅(%)": -2.0,
                    "外資當日(張)": -9000,
                    "投信當日(張)": -1000,
                    "融資增減(張)": 1200,
                    "MA20乖離(%)": -4.0,
                },
                {
                    "代號": "0050",
                    "名稱": "0050",
                    "漲跌幅(%)": -1.5,
                    "外資當日(張)": -3000,
                    "投信當日(張)": -500,
                    "融資增減(張)": 500,
                    "MA20乖離(%)": -3.0,
                },
            ],
        }
        derivatives = {"summary": {"risk_score": 65}}

        summary = expanded_risk_summary(market, derivatives)

        self.assertEqual(summary["base_score"], 65)
        self.assertGreater(summary["expanded_score"], 65)
        self.assertEqual(summary["bias"], "risk_off")
        factor_names = [factor["name"] for factor in summary["factors"]]
        self.assertIn("現貨趨勢", factor_names)
        self.assertIn("波動風險", factor_names)
        self.assertIn("國際風險", factor_names)
        self.assertIn("法人籌碼", factor_names)
        self.assertIn("權值股強弱", factor_names)
        self.assertIn("融資壓力", factor_names)

    def test_positive_external_and_weighted_stock_data_can_reduce_risk(self):
        market = {
            "概況": [
                {"指標": "加權指數 (TWII)", "當日數值": "46000", "單日變動": "+1.80%"},
                {"指標": "費半指數 (SOX)", "當日數值": "6000", "單日變動": "+3.00%"},
                {"指標": "恐慌指數 (VIX)", "當日數值": "16.0", "單日變動": "-8.00%"},
            ],
            "自選股": [
                {
                    "代號": "2330",
                    "漲跌幅(%)": 2.0,
                    "外資當日(張)": 9000,
                    "投信當日(張)": 1500,
                    "融資增減(張)": -1000,
                    "MA20乖離(%)": 4.0,
                },
                {
                    "代號": "0050",
                    "漲跌幅(%)": 1.5,
                    "外資當日(張)": 3000,
                    "投信當日(張)": 500,
                    "融資增減(張)": -500,
                    "MA20乖離(%)": 3.0,
                },
            ],
        }
        derivatives = {"summary": {"risk_score": 65}}

        summary = expanded_risk_summary(market, derivatives)

        self.assertLess(summary["expanded_score"], 65)
        self.assertEqual(summary["bias"], "neutral")

    def test_market_trend_and_breadth_data_adjust_score_when_available(self):
        market = {"總覽": [], "自選股": []}
        derivatives = {"summary": {"risk_score": 60}}
        trend = {
            "indices": {
                "TWII": {
                    "latest": 100,
                    "ma5": 98,
                    "gap_ma5_pct": 2.04,
                    "ma20": 94,
                    "gap_ma20_pct": 6.38,
                }
            }
        }
        breadth = {"breadth": {"total": 1000, "advances": 720, "declines": 200, "advance_ratio": 0.72, "decline_ratio": 0.2}}

        summary = expanded_risk_summary(market, derivatives, trend, breadth)

        self.assertLess(summary["expanded_score"], 60)
        names = [factor["name"] for factor in summary["factors"]]
        self.assertIn("大盤 MA20", names)
        self.assertIn("市場廣度", names)

    def test_monthly_global_and_sector_data_adjust_score_when_available(self):
        market = {"overview": [], "stocks": []}
        derivatives = {"summary": {"risk_score": 50}}
        global_market = {
            "market_data": {
                "Americas": [
                    {"ticker": "^IXIC", "change": -2.5},
                    {"ticker": "^GSPC", "change": -1.8},
                ],
                "Rates_Forex": [
                    {"ticker": "USDTWD=X", "change": 0.6},
                    {"ticker": "DX-Y.NYB", "change": 0.7},
                    {"ticker": "^TNX", "change": 12},
                ],
            }
        }
        sector_flow = {
            "periods": {
                "6M": {
                    "sectors": [
                        {"ticker": "XLK", "alpha_pct": -6.5},
                        {"ticker": "SMH", "alpha_pct": -8.0},
                    ]
                }
            }
        }

        summary = expanded_risk_summary(
            market,
            derivatives,
            global_market_data=global_market,
            us_sector_flow_data=sector_flow,
        )

        self.assertGreater(summary["expanded_score"], 50)
        names = [factor["name"] for factor in summary["factors"]]
        self.assertIn("Nasdaq", names)
        self.assertIn("USD/TWD", names)
        self.assertIn("US tech sector", names)
        self.assertIn("US semiconductor ETF", names)

    def test_derivative_expansion_and_lending_data_adjust_score(self):
        market = {"overview": [], "stocks": []}
        derivatives = {
            "summary": {"risk_score": 50},
            "night_session": {"txf_change_pct": -1.4},
            "options": {"skew_pressure": 0.55, "iv_skew": 0.12},
        }
        lending = {
            "market": {"total_lending_balance": 100000, "total_daily_change": 8000, "daily_change_ratio": 0.08},
            "watchlist_items": [
                {"code": "2330", "name": "TSMC", "daily_change": 1500},
                {"code": "2308", "name": "Delta", "daily_change": 1300},
                {"code": "2454", "name": "MTK", "daily_change": 1200},
            ],
        }

        summary = expanded_risk_summary(market, derivatives, securities_lending_data=lending)

        self.assertGreater(summary["expanded_score"], 50)
        names = [factor["name"] for factor in summary["factors"]]
        self.assertIn("TXF night session", names)
        self.assertIn("TXO option skew", names)
        self.assertIn("TXO IV skew", names)
        self.assertIn("Securities lending", names)
        self.assertIn("Watchlist lending pressure", names)


if __name__ == "__main__":
    unittest.main()
