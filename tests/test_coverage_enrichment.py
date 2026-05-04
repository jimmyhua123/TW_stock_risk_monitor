import tempfile
import unittest
from pathlib import Path

from src.coverage_enrichment import (
    build_enrichment,
    extract_wikilinks,
    find_report,
    parse_report,
)


SAMPLE_REPORT = """# 2330 - [[台積電]]

## 業務簡介
**板塊:** Technology
**產業:** Semiconductors
**市值:** 47,845,508 百萬台幣
**企業價值:** 45,886,629 百萬台幣

[[台積電]] 是全球最大晶圓代工廠，受惠於 [[AI 伺服器]]、[[CoWoS]] 與 [[NVIDIA]] 需求。

## 供應鏈位置
**上游:** [[ASML]], [[矽晶圓]]
**中游:** **台積電** 晶圓代工
**下游:** [[Apple]], [[NVIDIA]], [[AMD]]

## 主要客戶及供應商
### 主要客戶
- [[Apple]]
- [[NVIDIA]]

### 主要供應商
- [[ASML]]

## 財務概況
| P/E | P/B |
| --- | --- |
| 20 | 5 |
"""


class CoverageEnrichmentTests(unittest.TestCase):
    def test_extract_wikilinks_deduplicates_in_order(self):
        links = extract_wikilinks("[[CoWoS]] [[NVIDIA]] [[CoWoS]]")

        self.assertEqual(links, ["CoWoS", "NVIDIA"])

    def test_parse_report_extracts_metadata_sections_and_themes(self):
        parsed = parse_report(SAMPLE_REPORT, Path("2330_台積電.md"))

        self.assertEqual(parsed["code"], "2330")
        self.assertEqual(parsed["company"], "台積電")
        self.assertEqual(parsed["sector"], "Technology")
        self.assertEqual(parsed["industry"], "Semiconductors")
        self.assertIn("AI 伺服器", parsed["themes"])
        self.assertIn("Apple", parsed["customers_suppliers"])
        self.assertNotIn("台積電", parsed["themes"])
        self.assertNotIn("板塊", parsed["business_summary"])
        self.assertNotIn("財務概況", parsed["business_summary"])

    def test_find_report_locates_ticker_under_sector_dirs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_dir = root / "Pilot_Reports" / "Semiconductors"
            report_dir.mkdir(parents=True)
            path = report_dir / "2330_台積電.md"
            path.write_text(SAMPLE_REPORT, encoding="utf-8")

            found = find_report("2330", root)

        self.assertEqual(found, path)

    def test_build_enrichment_marks_missing_reports(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_dir = root / "Pilot_Reports" / "Semiconductors"
            report_dir.mkdir(parents=True)
            (report_dir / "2330_台積電.md").write_text(SAMPLE_REPORT, encoding="utf-8")

            result = build_enrichment(
                [{"code": "2330", "name": "台積電"}, {"code": "0050", "name": "0050"}],
                root,
            )

        self.assertEqual(len(result), 2)
        self.assertTrue(result[0]["found"])
        self.assertFalse(result[1]["found"])


if __name__ == "__main__":
    unittest.main()
