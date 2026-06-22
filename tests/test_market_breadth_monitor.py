import unittest

from src.market_breadth_monitor import calculate_breadth


class MarketBreadthMonitorTests(unittest.TestCase):
    def test_calculate_breadth_counts_advances_declines_and_limits(self):
        prices = {
            "2330": {"pct_change": 1.2},
            "0050": {"pct_change": -0.5},
            "2454": {"pct_change": 0},
            "2308": {"pct_change": 10.0},
            "99991": {"pct_change": -3.0},
            "ABCD": {"pct_change": 5.0},
            "2317": {"pct_change": -9.9},
        }

        breadth = calculate_breadth(prices)

        self.assertEqual(breadth["total"], 5)
        self.assertEqual(breadth["advances"], 2)
        self.assertEqual(breadth["declines"], 2)
        self.assertEqual(breadth["unchanged"], 1)
        self.assertEqual(breadth["limit_up"], 1)
        self.assertEqual(breadth["limit_down"], 1)
        self.assertEqual(breadth["advance_decline_ratio"], 1.0)


if __name__ == "__main__":
    unittest.main()
