#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a daily markdown briefing from the generated market data files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BRIEFING_DIR = PROJECT_ROOT / "docs" / "notes" / "每日看盤筆記"


SIGNAL_LABELS = {
    "risk_off": "風險偏空",
    "risk_on": "風險偏多",
    "neutral": "中性",
    "bearish": "偏空",
    "bullish": "偏多",
    "hedging_pressure": "避險壓力",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def find_latest_file(directory: Path, pattern: str) -> Path | None:
    files = sorted(directory.glob(pattern), key=lambda p: p.name, reverse=True)
    return files[0] if files else None


def data_file_for_date(directory: Path, date: str, pattern: str) -> Path | None:
    exact = directory / pattern.format(date=date)
    if exact.exists():
        return exact
    return find_latest_file(directory, pattern.format(date="*"))


def build_coverage_index(coverage_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in coverage_data.get("items", []):
        code = str(item.get("code", "")).zfill(4)
        if item.get("found") and code.isdigit() and len(code) == 4:
            index[code] = item
    return index


def build_briefing_markdown(
    date: str,
    market_data: dict[str, Any],
    derivatives_data: dict[str, Any] | None = None,
    coverage_data: dict[str, Any] | None = None,
) -> str:
    derivatives_data = derivatives_data or {}
    coverage_index = build_coverage_index(coverage_data or {})

    lines: list[str] = [
        f"# 每日看盤筆記 {date}",
        "",
        "## 市場總覽",
        "",
    ]
    lines.extend(render_overview(market_data.get("總覽", [])))
    lines.extend(render_derivatives(derivatives_data))
    lines.extend(render_stock_table(market_data.get("個股籌碼", []), coverage_index))
    lines.extend(render_warrants(market_data.get("權證監控", [])))
    lines.extend(render_action_notes(market_data.get("個股籌碼", []), derivatives_data, coverage_index))
    return "\n".join(lines).rstrip() + "\n"


def render_overview(items: list[dict[str, Any]]) -> list[str]:
    rows = []
    for item in items[:8]:
        category = item.get("類別", "-")
        indicator = item.get("指標", "-")
        value = format_value(item.get("當日數值"))
        change = format_value(item.get("單日變動"))
        rows.append(f"- {category} / {indicator}: {value} ({change})")

    if not rows:
        rows.append("- 尚無市場總覽資料")
    rows.append("")
    return rows


def render_derivatives(data: dict[str, Any]) -> list[str]:
    summary = data.get("summary", {})
    futures = data.get("futures", {})
    positioning = data.get("positioning", {})
    options = data.get("options", {})

    return [
        "## 期貨 / 選擇權風險",
        "",
        f"- 風險分數: {format_value(summary.get('risk_score'))}",
        f"- 市場傾向: {format_signal(summary.get('bias'))}",
        f"- 台指期基差: {format_signed(futures.get('basis'), 2)} ({format_signed(futures.get('basis_pct'), 2)}%)",
        f"- 外資期貨淨部位: {format_signed(positioning.get('foreign_tx_net_open_interest'), 0)} 口",
        f"- Put/Call Ratio: {format_value(options.get('pc_ratio'))} (5D {format_value(options.get('pc_ratio_5d_avg'))})",
        "",
    ]


def render_stock_table(stocks: list[dict[str, Any]], coverage_index: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "## 自選股籌碼與題材",
        "",
        "| 代號 | 名稱 | 漲跌幅 | 外資 | 投信 | 融資 | MA20乖離 | 題材 |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]

    for stock in sorted(stocks, key=stock_sort_score, reverse=True):
        code = str(stock.get("股票代號", "")).zfill(4)
        coverage = coverage_index.get(code, {})
        themes = ", ".join((coverage.get("themes") or [])[:3]) or "-"
        lines.append(
            "| {code} | {name} | {pct} | {foreign} | {trust} | {margin} | {ma20} | {themes} |".format(
                code=code,
                name=stock.get("股票名稱", "-"),
                pct=format_percent(stock.get("漲跌幅(%)")),
                foreign=format_signed(stock.get("外資當日(張)"), 0),
                trust=format_signed(stock.get("投信當日(張)"), 0),
                margin=format_signed(stock.get("融資增減(張)"), 0),
                ma20=format_percent(stock.get("MA20乖離(%)")),
                themes=themes,
            )
        )

    if not stocks:
        lines.append("| - | - | - | - | - | - | - | - |")
    lines.append("")
    return lines


def render_warrants(warrants: list[dict[str, Any]]) -> list[str]:
    lines = [
        "## 權證監控",
        "",
        "| 代號 | 名稱 | 漲跌幅 | 價差比 | 實質槓桿 |",
        "|---|---|---:|---:|---:|",
    ]

    for warrant in warrants:
        lines.append(
            "| {code} | {name} | {pct} | {spread} | {leverage} |".format(
                code=str(warrant.get("權證代碼", "")).zfill(6),
                name=warrant.get("權證名稱", "-"),
                pct=format_percent(warrant.get("漲跌幅%")),
                spread=format_percent(warrant.get("買賣價差比%")),
                leverage=format_value(warrant.get("實質槓桿")),
            )
        )

    if not warrants:
        lines.append("| - | - | - | - | - |")
    lines.append("")
    return lines


def render_action_notes(
    stocks: list[dict[str, Any]],
    derivatives_data: dict[str, Any],
    coverage_index: dict[str, dict[str, Any]],
) -> list[str]:
    lines = ["## 今日重點提醒", ""]
    bias = derivatives_data.get("summary", {}).get("bias")
    if bias == "risk_off":
        lines.append("- 期權結構偏風險控管，追價部位要降低槓桿與隔日風險。")
    elif bias == "risk_on":
        lines.append("- 期權結構偏正向，仍需確認個股籌碼是否同步。")
    else:
        lines.append("- 期權訊號偏中性，重點回到個股籌碼與題材延續性。")

    hot_names = []
    for stock in stocks:
        code = str(stock.get("股票代號", "")).zfill(4)
        if code in coverage_index and to_float(stock.get("漲跌幅(%)")) > 0 and to_float(stock.get("融資增減(張)")) > 0:
            hot_names.append(f"{code} {stock.get('股票名稱', '-')}")
    if hot_names:
        lines.append(f"- 有題材且融資增加的個股: {', '.join(hot_names[:5])}，留意題材與籌碼是否同向。")
    else:
        lines.append("- 尚未看到明顯的題材加融資同步清單。")

    lines.append("")
    return lines


def stock_sort_score(stock: dict[str, Any]) -> float:
    return abs(to_float(stock.get("漲跌幅(%)"))) + abs(to_float(stock.get("MA20乖離(%)"))) * 0.5


def format_signal(value: Any) -> str:
    return SIGNAL_LABELS.get(str(value), str(value or "-"))


def format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def format_percent(value: Any) -> str:
    num = to_float(value)
    if num != num:
        return "-"
    return f"{num:+.2f}%"


def format_signed(value: Any, digits: int = 2) -> str:
    num = to_float(value)
    if num != num:
        return "-"
    return f"{num:+,.{digits}f}"


def to_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return float("nan")
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def write_briefing(date: str, output_path: Path | None = None) -> Path:
    market_path = data_file_for_date(PROJECT_ROOT / "outputs" / "json", date, "{date}.json")
    if market_path is None:
        raise FileNotFoundError(f"No market JSON found for {date}")

    derivatives_path = data_file_for_date(
        PROJECT_ROOT / "outputs" / "derivatives_json", date, "derivatives_{date}.json"
    )
    coverage_path = data_file_for_date(PROJECT_ROOT / "outputs" / "coverage_json", date, "coverage_{date}.json")

    market_data = load_json(market_path)
    derivatives_data = load_json(derivatives_path) if derivatives_path else {}
    coverage_data = load_json(coverage_path) if coverage_path else {}

    markdown = build_briefing_markdown(date, market_data, derivatives_data, coverage_data)
    output_path = output_path or DEFAULT_BRIEFING_DIR / f"{date}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a daily markdown briefing.")
    parser.add_argument("--date", required=True, help="Report date in YYYYMMDD format.")
    parser.add_argument("--output", type=Path, default=None, help="Optional markdown output path.")
    args = parser.parse_args()

    output_path = write_briefing(args.date, args.output)
    print(f"[OK] daily briefing written: {output_path}")


if __name__ == "__main__":
    main()
