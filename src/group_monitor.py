#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Watchlist group analysis for personal stock research."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WATCHLIST = PROJECT_ROOT / "data" / "config" / "watchlist.json"
DEFAULT_REPORT_DIR = PROJECT_ROOT / "outputs" / "json"
DEFAULT_COVERAGE_DIR = PROJECT_ROOT / "outputs" / "coverage_json"
DEFAULT_GROUP_JSON_DIR = PROJECT_ROOT / "outputs" / "group_json"
DEFAULT_GROUP_TXT_DIR = PROJECT_ROOT / "outputs" / "group_txt"

STOCK_SECTION = "個股籌碼"
UNCATEGORIZED_GROUP = "未分類"


def normalize_code(value: Any) -> str:
    """Normalize stock codes so JSON number 50 matches watchlist code 0050."""
    text = str(value).strip().upper()
    if text.endswith(".0"):
        text = text[:-2]
    if re.fullmatch(r"\d+", text):
        return text.zfill(4)
    return text


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text in {"-", "--", "nan", "NaN", "None"}:
        return None
    text = text.replace(",", "").replace("%", "")
    text = re.sub(r"[^0-9.+-]", "", text)
    if text in {"", "+", "-", ".", "+.", "-."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def normalize_watch_item(item: dict[str, Any]) -> dict[str, Any]:
    groups = as_list(item.get("groups"))
    if not groups:
        groups = as_list(item.get("group"))
    if not groups:
        groups = as_list(item.get("sector"))
    return {
        "code": normalize_code(item.get("code", "")),
        "name": str(item.get("name", "")).strip(),
        "groups": groups,
        "thesis": str(item.get("thesis", "")).strip(),
        "peers": [normalize_code(code) for code in as_list(item.get("peers"))],
        "risk_notes": as_list(item.get("risk_notes")),
        "priority": str(item.get("priority", "")).strip(),
    }


def load_watchlist(path: Path = DEFAULT_WATCHLIST) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    raw_items = data.get("watchlist", [])
    return [normalize_watch_item(item) for item in raw_items if item.get("code")]


def load_market_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def find_coverage_path(date: str | None = None, coverage_dir: Path = DEFAULT_COVERAGE_DIR) -> Path | None:
    if date:
        path = coverage_dir / f"coverage_{date}.json"
        if path.is_file():
            return path

    reports = sorted(coverage_dir.glob("coverage_*.json"), reverse=True)
    return reports[0] if reports else None


def load_coverage_index(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None or not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    index: dict[str, dict[str, Any]] = {}
    for item in data.get("items", []):
        code = normalize_code(item.get("code", ""))
        if code:
            index[code] = item
    return index


def find_report_path(date: str | None = None, report_dir: Path = DEFAULT_REPORT_DIR) -> Path:
    if date:
        path = report_dir / f"{date}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Market report not found: {path}")
        return path

    reports = sorted(report_dir.glob("*.json"), reverse=True)
    reports = [path for path in reports if path.stem.isdigit()]
    if not reports:
        raise FileNotFoundError(f"No dated market reports found in {report_dir}")
    return reports[0]


def index_stock_rows(market_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = market_report.get(STOCK_SECTION, [])
    return {normalize_code(row.get("股票代號")): row for row in rows if row.get("股票代號") is not None}


def infer_groups(watch_item: dict[str, Any], coverage_item: dict[str, Any] | None) -> list[str]:
    explicit_groups = as_list(watch_item.get("groups"))
    if explicit_groups:
        return explicit_groups

    inferred: list[str] = []
    if coverage_item and coverage_item.get("found", True):
        for key in ("sector", "industry"):
            value = str(coverage_item.get(key, "")).strip()
            if value and value not in inferred:
                inferred.append(value)
        for theme in as_list(coverage_item.get("themes"))[:3]:
            if theme not in inferred:
                inferred.append(theme)

    return inferred or [UNCATEGORIZED_GROUP]


def stock_score(metrics: dict[str, float | None]) -> float:
    score = 50.0
    price_change = metrics.get("price_change_pct")
    ma20_gap = metrics.get("ma20_gap_pct")
    foreign = metrics.get("foreign_net")
    trust = metrics.get("trust_net")
    dealer = metrics.get("dealer_net")
    margin = metrics.get("margin_change")

    if price_change is not None:
        score += clamp(price_change, -10, 10) * 3.0
    if ma20_gap is not None:
        score += clamp(ma20_gap, -12, 12) * 1.2
    for value, weight in ((foreign, 5.0), (trust, 4.0), (dealer, 3.0)):
        if value is not None and value != 0:
            score += weight if value > 0 else -weight
    if margin is not None and price_change is not None and margin > 0 and price_change < 0:
        score -= 4.0

    return round(clamp(score, 0, 100), 1)


def stock_status(score: float) -> str:
    if score >= 70:
        return "強勢"
    if score >= 55:
        return "偏強"
    if score >= 45:
        return "中性"
    if score >= 30:
        return "偏弱"
    return "風險"


def build_stock_analysis(
    watch_item: dict[str, Any],
    row: dict[str, Any] | None,
    coverage_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    groups = infer_groups(watch_item, coverage_item)

    if row is None:
        return {
            **watch_item,
            "groups": groups,
            "groups_source": "watchlist" if watch_item.get("groups") else ("coverage" if coverage_item else "fallback"),
            "covered": False,
            "status": "缺資料",
            "score": None,
            "metrics": {},
            "signals": [],
            "risk_flags": ["本日報表未找到此股票"],
        }

    metrics = {
        "price": parse_float(row.get("收盤價")),
        "price_change_pct": parse_float(row.get("漲跌幅(%)")),
        "volume_lots": parse_float(row.get("成交量(張)")),
        "foreign_net": parse_float(row.get("外資當日(張)")),
        "foreign_5d": parse_float(row.get("外資5日累計")),
        "trust_net": parse_float(row.get("投信當日(張)")),
        "trust_5d": parse_float(row.get("投信5日累計")),
        "dealer_net": parse_float(row.get("自營商當日(張)")),
        "margin_change": parse_float(row.get("融資增減(張)")),
        "margin_5d": parse_float(row.get("融資5日累計")),
        "stock_lending_change": parse_float(row.get("借券增減(張)")),
        "ma20_gap_pct": parse_float(row.get("MA20乖離(%)")),
    }
    score = stock_score(metrics)
    signals: list[str] = []
    risk_flags: list[str] = []

    price_change = metrics["price_change_pct"]
    ma20_gap = metrics["ma20_gap_pct"]
    foreign = metrics["foreign_net"]
    trust = metrics["trust_net"]
    margin = metrics["margin_change"]

    if price_change is not None:
        if price_change >= 2:
            signals.append("價格強於短線")
        elif price_change <= -3:
            risk_flags.append("單日跌幅偏大")
    if ma20_gap is not None:
        if ma20_gap > 0:
            signals.append("站上 MA20")
        elif ma20_gap <= -5:
            risk_flags.append("低於 MA20 且乖離偏大")
    if foreign is not None and foreign > 0:
        signals.append("外資買超")
    if trust is not None and trust > 0:
        signals.append("投信買超")
    if foreign is not None and trust is not None and foreign < 0 and trust < 0:
        risk_flags.append("外資與投信同步賣超")
    if margin is not None and price_change is not None and margin > 0 and price_change < 0:
        risk_flags.append("下跌但融資增加")

    return {
        **watch_item,
        "groups": groups,
        "groups_source": "watchlist" if watch_item.get("groups") else ("coverage" if coverage_item else "fallback"),
        "covered": True,
        "status": stock_status(score),
        "score": score,
        "metrics": metrics,
        "signals": signals,
        "risk_flags": risk_flags,
    }


def group_status(avg_score: float | None) -> str:
    if avg_score is None:
        return "缺資料"
    if avg_score >= 70:
        return "強勢族群"
    if avg_score >= 55:
        return "偏強族群"
    if avg_score >= 45:
        return "中性觀察"
    if avg_score >= 30:
        return "偏弱族群"
    return "風險族群"


def summarize_group(name: str, stocks: list[dict[str, Any]]) -> dict[str, Any]:
    covered = [stock for stock in stocks if stock["covered"]]
    scores = [stock["score"] for stock in covered if stock["score"] is not None]
    avg_score = round(mean(scores), 1) if scores else None
    price_changes = [stock["metrics"].get("price_change_pct") for stock in covered]
    price_changes = [value for value in price_changes if value is not None]

    def sum_metric(key: str) -> float | None:
        values = [stock["metrics"].get(key) for stock in covered]
        values = [value for value in values if value is not None]
        return round(sum(values), 2) if values else None

    ranked = sorted(covered, key=lambda stock: stock["score"] or 0, reverse=True)
    leaders = ranked[:3]
    laggards = list(reversed(ranked[-3:])) if len(ranked) > 3 else ranked[-3:]
    theses = [stock["thesis"] for stock in stocks if stock.get("thesis")]
    risks: list[str] = []
    for stock in stocks:
        risks.extend(stock.get("risk_notes", []))

    return {
        "group": name,
        "status": group_status(avg_score),
        "stock_count": len(stocks),
        "covered_count": len(covered),
        "avg_score": avg_score,
        "avg_price_change_pct": round(mean(price_changes), 2) if price_changes else None,
        "total_foreign_net": sum_metric("foreign_net"),
        "total_trust_net": sum_metric("trust_net"),
        "total_dealer_net": sum_metric("dealer_net"),
        "total_margin_change": sum_metric("margin_change"),
        "leaders": [compact_stock(stock) for stock in leaders],
        "laggards": [compact_stock(stock) for stock in laggards],
        "theses": theses,
        "risk_notes": sorted(set(risks)),
        "missing": [compact_stock(stock) for stock in stocks if not stock["covered"]],
    }


def compact_stock(stock: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": stock["code"],
        "name": stock["name"],
        "score": stock["score"],
        "status": stock["status"],
        "price_change_pct": stock.get("metrics", {}).get("price_change_pct"),
        "foreign_net": stock.get("metrics", {}).get("foreign_net"),
        "trust_net": stock.get("metrics", {}).get("trust_net"),
        "risk_flags": stock.get("risk_flags", []),
    }


def build_group_analysis(
    watchlist: list[dict[str, Any]],
    market_report: dict[str, Any],
    coverage_index: dict[str, dict[str, Any]] | None = None,
    *,
    date: str,
    source_report: str,
    source_watchlist: str,
    source_coverage: str | None = None,
) -> dict[str, Any]:
    coverage_index = coverage_index or {}
    stock_rows = index_stock_rows(market_report)
    stock_analyses = [
        build_stock_analysis(item, stock_rows.get(item["code"]), coverage_index.get(item["code"]))
        for item in watchlist
    ]

    groups: dict[str, list[dict[str, Any]]] = {}
    for stock in stock_analyses:
        for group in stock["groups"]:
            groups.setdefault(group, []).append(stock)

    group_summaries = [summarize_group(name, stocks) for name, stocks in sorted(groups.items())]
    group_summaries.sort(key=lambda group: group["avg_score"] if group["avg_score"] is not None else -1, reverse=True)

    return {
        "date": date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_report": source_report,
        "source_watchlist": source_watchlist,
        "source_coverage": source_coverage,
        "groups": group_summaries,
        "stocks": stock_analyses,
        "missing": [compact_stock(stock) for stock in stock_analyses if not stock["covered"]],
        "notes": [
            "分數是研究排序輔助，不是買賣建議。",
            "資料來自既有每日報表；若原始 API 缺值，族群分析會標示缺資料或降低可解讀性。",
        ],
    }


def format_number(value: Any, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


def render_text_report(analysis: dict[str, Any]) -> str:
    lines = [
        f"# Watchlist 族群分析 {analysis['date']}",
        "",
        "本報告用於整理你放入 watchlist 的股票與族群，協助篩出強弱、籌碼與風險觀察點；不是投資建議。",
        "",
    ]
    for group in analysis["groups"]:
        lines.extend(
            [
                f"## {group['group']} - {group['status']}",
                f"- 股票數: {group['stock_count']}，有資料: {group['covered_count']}",
                f"- 平均分數: {format_number(group['avg_score'])}",
                f"- 平均漲跌幅: {format_number(group['avg_price_change_pct'], '%')}",
                f"- 外資合計: {format_number(group['total_foreign_net'], ' 張')}",
                f"- 投信合計: {format_number(group['total_trust_net'], ' 張')}",
                f"- 融資合計: {format_number(group['total_margin_change'], ' 張')}",
            ]
        )
        if group["leaders"]:
            leaders = ", ".join(f"{s['code']} {s['name']}({s['status']} {s['score']})" for s in group["leaders"])
            lines.append(f"- 領先股: {leaders}")
        if group["laggards"]:
            laggards = ", ".join(f"{s['code']} {s['name']}({s['status']} {s['score']})" for s in group["laggards"])
            lines.append(f"- 需留意: {laggards}")
        if group["theses"]:
            lines.append(f"- 研究假設: {'；'.join(group['theses'])}")
        if group["risk_notes"]:
            lines.append(f"- 風險筆記: {'；'.join(group['risk_notes'])}")
        if group["missing"]:
            missing = ", ".join(f"{s['code']} {s['name']}" for s in group["missing"])
            lines.append(f"- 缺資料: {missing}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(analysis: dict[str, Any], json_dir: Path, txt_dir: Path) -> tuple[Path, Path]:
    json_dir.mkdir(parents=True, exist_ok=True)
    txt_dir.mkdir(parents=True, exist_ok=True)
    date = analysis["date"]
    json_path = json_dir / f"group_{date}.json"
    txt_path = txt_dir / f"group_{date}.txt"
    json_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text(render_text_report(analysis), encoding="utf-8")
    return json_path, txt_path


def run(
    *,
    date: str | None = None,
    watchlist_path: Path = DEFAULT_WATCHLIST,
    report_path: Path | None = None,
    coverage_path: Path | None = None,
    json_dir: Path = DEFAULT_GROUP_JSON_DIR,
    txt_dir: Path = DEFAULT_GROUP_TXT_DIR,
) -> tuple[dict[str, Any], Path, Path]:
    selected_report_path = report_path or find_report_path(date)
    selected_date = date or selected_report_path.stem
    selected_coverage_path = coverage_path or find_coverage_path(selected_date)
    watchlist = load_watchlist(watchlist_path)
    market_report = load_market_report(selected_report_path)
    coverage_index = load_coverage_index(selected_coverage_path)
    analysis = build_group_analysis(
        watchlist,
        market_report,
        coverage_index,
        date=selected_date,
        source_report=str(selected_report_path),
        source_watchlist=str(watchlist_path),
        source_coverage=str(selected_coverage_path) if selected_coverage_path else None,
    )
    json_path, txt_path = write_outputs(analysis, json_dir, txt_dir)
    return analysis, json_path, txt_path


def main() -> None:
    parser = argparse.ArgumentParser(description="依 watchlist 產出個股與族群強弱分析")
    parser.add_argument("--date", type=str, default=None, help="指定日期 YYYYMMDD；不指定則使用 outputs/json 最新日期")
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST, help="watchlist JSON 路徑")
    parser.add_argument("--report", type=Path, default=None, help="指定已產生的每日市場 JSON")
    parser.add_argument("--coverage", type=Path, default=None, help="指定題材補充 JSON；不指定則優先使用同日期，否則用最新檔")
    parser.add_argument("--json-dir", type=Path, default=DEFAULT_GROUP_JSON_DIR, help="族群 JSON 輸出資料夾")
    parser.add_argument("--txt-dir", type=Path, default=DEFAULT_GROUP_TXT_DIR, help="族群文字報告輸出資料夾")
    args = parser.parse_args()

    analysis, json_path, txt_path = run(
        date=args.date,
        watchlist_path=args.watchlist,
        report_path=args.report,
        coverage_path=args.coverage,
        json_dir=args.json_dir,
        txt_dir=args.txt_dir,
    )
    print(f"[SAVED] {json_path}")
    print(f"[SAVED] {txt_path}")
    print(f"[INFO] groups={len(analysis['groups'])} stocks={len(analysis['stocks'])} missing={len(analysis['missing'])}")


if __name__ == "__main__":
    main()
