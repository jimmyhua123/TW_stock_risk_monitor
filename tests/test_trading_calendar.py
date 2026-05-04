import unittest

from src.trading_calendar import TradingCalendar


class TradingCalendarTests(unittest.TestCase):
    def test_previous_trading_days_honors_buffer_days(self):
        calendar = TradingCalendar()
        calendar.trading_days = [
            "20260420",
            "20260421",
            "20260422",
            "20260423",
            "20260424",
            "20260427",
            "20260428",
            "20260429",
        ]

        days = calendar.get_previous_trading_days("20260429", 3, buffer_days=2)

        self.assertEqual(
            days,
            ["20260423", "20260424", "20260427", "20260428", "20260429"],
        )

    def test_previous_trading_days_without_buffer_keeps_existing_length(self):
        calendar = TradingCalendar()
        calendar.trading_days = [
            "20260420",
            "20260421",
            "20260422",
            "20260423",
            "20260424",
            "20260427",
            "20260428",
            "20260429",
        ]

        days = calendar.get_previous_trading_days("20260429", 3)

        self.assertEqual(days, ["20260427", "20260428", "20260429"])


if __name__ == "__main__":
    unittest.main()
