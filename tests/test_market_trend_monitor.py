import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.market_trend_monitor import build_market_trend


class MarketTrendMonitorTests(unittest.TestCase):
    def test_build_market_trend_uses_existing_daily_json_files(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for idx in range(1, 21):
                date = f"202606{idx:02d}"
                payload = {
                    "總覽": [
                        {"指標": "加權指數 (TWII)", "當日數值": 100 + idx, "單日變動": "+0.1%"},
                        {"指標": "櫃買指數 (OTC)", "當日數值": 200 + idx, "單日變動": "+0.1%"},
                    ]
                }
                (root / f"{date}.json").write_text(json.dumps(payload), encoding="utf-8")

            result = build_market_trend("20260620", root)

        self.assertEqual(result["indices"]["TWII"]["latest"], 120)
        self.assertEqual(result["indices"]["TWII"]["ma5"], 118)
        self.assertEqual(result["indices"]["TWII"]["ma10"], 115.5)
        self.assertEqual(result["indices"]["TWII"]["ma20"], 110.5)
        self.assertEqual(result["indices"]["OTC"]["latest"], 220)


if __name__ == "__main__":
    unittest.main()
