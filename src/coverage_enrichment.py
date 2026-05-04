#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Enrich watchlist stocks with My-TW-Coverage business and theme data."""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from risk_monitor import get_trading_date
except ImportError:
    from src.risk_monitor import get_trading_date


DEFAULT_COVERAGE_ROOT = Path("data/external/My-TW-Coverage")
DEFAULT_WATCHLIST = Path("data/config/watchlist.json")


def extract_wikilinks(text: str) -> List[str]:
    seen = set()
    links = []
    for link in re.findall(r"\[\[([^\]]+)\]\]", text):
        link = link.strip()
        if link and link not in seen:
            seen.add(link)
            links.append(link)
    return links


def find_report(code: str, coverage_root: Path = DEFAULT_COVERAGE_ROOT) -> Optional[Path]:
    reports_dir = coverage_root / "Pilot_Reports"
    if not reports_dir.is_dir():
        return None

    matches = sorted(reports_dir.glob(f"*/*{code}_*.md"))
    return matches[0] if matches else None


def parse_report(content: str, path: Path) -> Dict[str, Any]:
    title_match = re.search(r"^#\s+(\d{4})\s+-\s+\[\[([^\]]+)\]\]", content, re.MULTILINE)
    if title_match:
        code = title_match.group(1)
        company = title_match.group(2).strip()
    else:
        file_match = re.match(r"^(\d{4})_(.+)\.md$", path.name)
        code = file_match.group(1) if file_match else ""
        company = file_match.group(2) if file_match else path.stem

    metadata = _parse_metadata(content)
    business = _section(content, "業務簡介")
    supply_chain = _section(content, "供應鏈位置")
    customers = _section(content, "主要客戶及供應商")
    non_financial = content.split("## 財務概況")[0]

    own_names = {company, code}
    links = [link for link in extract_wikilinks(non_financial) if link not in own_names]

    return {
        "code": code,
        "company": company,
        "sector": metadata.get("板塊"),
        "industry": metadata.get("產業"),
        "market_cap_m_twd": metadata.get("市值"),
        "enterprise_value_m_twd": metadata.get("企業價值"),
        "business_summary": _clean_text(business, max_chars=420),
        "supply_chain": _clean_text(supply_chain, max_chars=700),
        "customers_suppliers": extract_wikilinks(customers),
        "themes": links[:30],
        "source_path": str(path),
    }


def build_enrichment(watchlist: Iterable[Dict[str, Any]], coverage_root: Path = DEFAULT_COVERAGE_ROOT) -> List[Dict[str, Any]]:
    results = []
    for item in watchlist:
        code = str(item.get("code", "")).strip()
        if not _is_stock_code(code):
            continue

        path = find_report(code, coverage_root)
        if path is None:
            results.append({
                "code": code,
                "name": item.get("name", ""),
                "found": False,
                "reason": "coverage report not found",
            })
            continue

        content = path.read_text(encoding="utf-8")
        parsed = parse_report(content, path)
        parsed["name"] = item.get("name") or parsed["company"]
        parsed["found"] = True
        results.append(parsed)

    return results


def load_watchlist(path: Path = DEFAULT_WATCHLIST) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    return data.get("watchlist", [])


def export_payload(payload: Dict[str, Any], date_str: str) -> Dict[str, str]:
    json_dir = Path("outputs/coverage_json")
    txt_dir = Path("outputs/coverage_txt")
    json_dir.mkdir(parents=True, exist_ok=True)
    txt_dir.mkdir(parents=True, exist_ok=True)

    json_path = json_dir / f"coverage_{date_str}.json"
    txt_path = txt_dir / f"coverage_{date_str}.txt"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(format_text(payload), encoding="utf-8")

    return {"json": str(json_path), "txt": str(txt_path)}


def format_text(payload: Dict[str, Any]) -> str:
    lines = [
        f"# Watchlist 產業與題材補充 ({payload.get('date', '-')})",
        "",
        f"來源: {payload.get('source', '-')}",
        "授權: My-TW-Coverage MIT License",
        "",
    ]

    for item in payload.get("items", []):
        if not item.get("found"):
            lines.extend([
                f"## {item.get('code')} {item.get('name', '')}",
                f"- 狀態: {item.get('reason')}",
                "",
            ])
            continue

        lines.extend([
            f"## {item['code']} {item['company']}",
            f"- 板塊/產業: {item.get('sector') or '-'} / {item.get('industry') or '-'}",
            f"- 題材: {', '.join(item.get('themes', [])[:12]) or '-'}",
            f"- 客戶/供應商: {', '.join(item.get('customers_suppliers', [])[:12]) or '-'}",
            f"- 業務摘要: {item.get('business_summary') or '-'}",
            "",
        ])

    return "\n".join(lines)


def _parse_metadata(content: str) -> Dict[str, str]:
    metadata = {}
    for key in ("板塊", "產業", "市值", "企業價值"):
        match = re.search(rf"^\*\*{re.escape(key)}:\*\*\s*(.+)$", content, re.MULTILINE)
        if match:
            metadata[key] = match.group(1).strip()
    return metadata


def _section(content: str, heading: str) -> str:
    pattern = rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    return match.group(1).strip() if match else ""


def _clean_text(text: str, max_chars: int) -> str:
    text = re.sub(r"^\*\*(板塊|產業|市值|企業價值):\*\*.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _is_stock_code(code: str) -> bool:
    return bool(re.fullmatch(r"\d{4}", code))


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich watchlist with My-TW-Coverage reports")
    parser.add_argument("--date", type=str, help="報告日期 YYYYMMDD，預設取最近交易日")
    parser.add_argument("--coverage-root", default=str(DEFAULT_COVERAGE_ROOT), help="My-TW-Coverage repo path")
    parser.add_argument("--watchlist", default=str(DEFAULT_WATCHLIST), help="watchlist JSON path")
    args = parser.parse_args()

    date_str = get_trading_date(args.date)
    coverage_root = Path(args.coverage_root)
    watchlist_path = Path(args.watchlist)

    if not coverage_root.is_dir():
        print(f"[ERROR] 找不到 coverage repo: {coverage_root}")
        print("[HINT] 先執行: git clone --depth 1 https://github.com/Timeverse/My-TW-Coverage.git data/external/My-TW-Coverage")
        return 1

    items = build_enrichment(load_watchlist(watchlist_path), coverage_root)
    payload = {
        "date": date_str,
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "Timeverse/My-TW-Coverage",
        "source_license": "MIT",
        "coverage_root": str(coverage_root),
        "items": items,
    }
    paths = export_payload(payload, date_str)

    found_count = sum(1 for item in items if item.get("found"))
    print(f"[SUCCESS] coverage JSON: {paths['json']}")
    print(f"[SUCCESS] coverage TXT: {paths['txt']}")
    print(f"[INFO] matched {found_count}/{len(items)} watchlist stocks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
