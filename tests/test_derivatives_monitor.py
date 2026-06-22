import unittest

import pandas as pd

from src.derivatives_monitor import (
    DerivativesMonitor,
    assess_basis,
    assess_foreign_futures,
    assess_night_session,
    assess_option_skew,
    assess_pc_ratio,
    black_scholes_price,
    calculate_option_skew,
    calculate_summary,
    implied_volatility,
    parse_number,
)


class DerivativesMonitorTests(unittest.TestCase):
    def test_parse_number_handles_commas_percent_and_symbols(self):
        self.assertEqual(parse_number("23,456"), 23456)
        self.assertEqual(parse_number("+1.25%"), 1.25)
        self.assertEqual(parse_number("--"), None)
        self.assertEqual(parse_number(""), None)

    def test_assess_basis_classifies_futures_discount(self):
        self.assertEqual(assess_basis(-120), "bearish")
        self.assertEqual(assess_basis(80), "bullish")
        self.assertEqual(assess_basis(10), "neutral")
        self.assertEqual(assess_basis(None), "unknown")

    def test_assess_pc_ratio_classifies_option_pressure(self):
        self.assertEqual(assess_pc_ratio(135), "hedging_pressure")
        self.assertEqual(assess_pc_ratio(72), "call_speculation")
        self.assertEqual(assess_pc_ratio(100), "neutral")
        self.assertEqual(assess_pc_ratio(None), "unknown")

    def test_assess_foreign_futures_classifies_positioning(self):
        self.assertEqual(assess_foreign_futures(-16000), "bearish")
        self.assertEqual(assess_foreign_futures(18000), "bullish")
        self.assertEqual(assess_foreign_futures(500), "neutral")
        self.assertEqual(assess_foreign_futures(None), "unknown")

    def test_assess_night_session_classifies_after_hours_move(self):
        self.assertEqual(assess_night_session(-2.1), "strong_bearish")
        self.assertEqual(assess_night_session(-1.2), "bearish")
        self.assertEqual(assess_night_session(1.3), "bullish")
        self.assertEqual(assess_night_session(0.2), "neutral")
        self.assertEqual(assess_night_session(None), "unknown")

    def test_calculate_option_skew_uses_nearby_otm_prices(self):
        rows = [
            {"side": "call", "strike": 100, "settlement": 80},
            {"side": "call", "strike": 101, "settlement": 30},
            {"side": "put", "strike": 100, "settlement": 70},
            {"side": "put", "strike": 99, "settlement": 60},
        ]

        skew = calculate_option_skew(rows, 100.2)

        self.assertEqual(skew["atm_strike"], 100)
        self.assertEqual(skew["put_ratio"], 0.8571)
        self.assertEqual(skew["call_ratio"], 0.375)
        self.assertEqual(skew["skew_signal"], "put_skew")
        self.assertEqual(assess_option_skew(skew["skew_pressure"]), "put_skew")
        self.assertIn("atm_call_iv", skew)
        self.assertIn("iv_skew", skew)

    def test_implied_volatility_inverts_black_scholes_price(self):
        price = black_scholes_price("call", 100, 100, 30 / 365, 0.015, 0.25)

        iv = implied_volatility("call", 100, 100, 30 / 365, 0.015, price)

        self.assertAlmostEqual(iv, 0.25, places=3)

    def test_calculate_summary_combines_available_signals(self):
        payload = {
            "futures": {"basis_signal": "bearish"},
            "positioning": {"foreign_tx_net_signal": "bearish"},
            "options": {"pc_ratio_signal": "hedging_pressure"},
        }

        summary = calculate_summary(payload)

        self.assertEqual(summary["risk_score"], 90)
        self.assertEqual(summary["bias"], "risk_off")
        self.assertEqual(len(summary["signals"]), 3)

    def test_extract_foreign_tx_position_uses_open_interest_net_lots(self):
        columns = pd.MultiIndex.from_tuples([
            ("meta", "meta", "商品 名稱"),
            ("meta", "meta", "身份別"),
            ("未平倉餘額", "多空淨額", "口數"),
            ("未平倉餘額", "多空淨額", "契約 金額"),
        ])
        table = pd.DataFrame(
            [["臺股期貨", "外資", -47074, -371735161]],
            columns=columns,
        )

        value = DerivativesMonitor("20260429")._extract_foreign_tx_position_from_table(table)

        self.assertEqual(value, -47074)


if __name__ == "__main__":
    unittest.main()
