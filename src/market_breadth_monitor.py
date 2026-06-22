#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compute broad market breadth from TWSE/TPEx closing price data."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .stock_monitor import StockDataFetcher
except ImportError:
    from stock_monitor import StockDataFetcher


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "market_breadth_json"


def calculate_breadth(price_data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    universe = []
    for code, item in price_data.items():
        normalized_code = str(code).zfill(4)
        if not (normalized_code.isdigit() and len(normalized_code) == 4):
            continue
        pct_change = to_float(item.get("pct_change"))
        if pct_change != pct_change:
            continue
        universe.append((normalized_code, pct_change))

    total = len(universe)
    advances = sum(1 for _, pct in universe if pct > 0)
    declines = sum(1 for _, pct in universe if pct < 0)
    unchanged = sum(1 for _, pct in universe if pct == 0)
    limit_up = sum(1 for _, pct in universe if pct >= 9.8)
    limit_down = sum(1 for _, pct in universe if pct <= -9.8)

    return {
        "total": total,
        "advances": advances,
        "declines": declines,
        "unchanged": unchanged,
        "advance_ratio": ratio(advances, total),
        "decline_ratio": ratio(declines, total),
        "advance_decline_ratio": round(advances / declines, 2) if declines else None,
        "limit_up": limit_up,
        "limit_down": limit_down,
    }


def fetch_market_breadth(date: str) -> dict[str, Any]:
    fetcher = StockDataFetcher(date)
    prices = fetcher.fetch_stock_prices(include_warrants=False)
    breadth = calculate_breadth(prices)
    return {
        "date": date,
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "TWSE MI_INDEX + TPEx daily_close_quotes",
        "breadth": breadth,
    }


def export_market_breadth(payload: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"market_breadth_{payload['date']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def ratio(value: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(value / total, 4)


def to_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return float("nan")
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build market breadth metrics from TWSE/TPEx closes.")
    parser.add_argument("--date", required=True, help="Report date in YYYYMMDD format.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    payload = fetch_market_breadth(args.date)
    path = export_market_breadth(payload, args.output_dir)
    print(f"[OK] market breadth written: {path}")


if __name__ == "__main__":
    main()
