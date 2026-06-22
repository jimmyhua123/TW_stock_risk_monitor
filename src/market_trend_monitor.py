#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compute broad-index moving-average trend from existing daily JSON files."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from .risk_score_expansion import find_overview_item, overview_value
except ImportError:
    from risk_score_expansion import find_overview_item, overview_value


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MARKET_JSON_DIR = PROJECT_ROOT / "outputs" / "json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "market_trend_json"


INDEX_TOKENS = {
    "TWII": "TWII",
    "OTC": "OTC",
}


def build_market_trend(date: str, market_json_dir: Path = DEFAULT_MARKET_JSON_DIR) -> dict[str, Any]:
    series = collect_index_series(date, market_json_dir)
    indices = {name: summarize_index(values) for name, values in series.items()}
    return {
        "date": date,
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(market_json_dir),
        "indices": indices,
    }


def collect_index_series(date: str, market_json_dir: Path) -> dict[str, list[dict[str, Any]]]:
    series: dict[str, list[dict[str, Any]]] = {name: [] for name in INDEX_TOKENS}
    for path in sorted(market_json_dir.glob("*.json")):
        file_date = path.stem
        if not (file_date.isdigit() and len(file_date) == 8 and file_date <= date):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            continue
        overview = payload.get("總覽") or payload.get("概況") or payload.get("蝮質汗") or []
        for name, token in INDEX_TOKENS.items():
            item = find_overview_item(overview, token)
            value = overview_value(item)
            if value == value:
                series[name].append({"date": file_date, "close": value})
    return series


def summarize_index(values: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [float(item["close"]) for item in values]
    dates = [item["date"] for item in values]
    latest = closes[-1] if closes else None
    latest_date = dates[-1] if dates else None
    result: dict[str, Any] = {
        "latest_date": latest_date,
        "latest": round(latest, 2) if latest is not None else None,
        "observations": len(closes),
    }
    for window in (5, 10, 20):
        ma = moving_average(closes, window)
        result[f"ma{window}"] = ma
        result[f"gap_ma{window}_pct"] = gap_pct(latest, ma)
    return result


def moving_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return round(sum(values[-window:]) / window, 2)


def gap_pct(latest: float | None, ma: float | None) -> float | None:
    if latest is None or ma in (None, 0):
        return None
    return round(((latest - ma) / ma) * 100, 2)


def export_market_trend(payload: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"market_trend_{payload['date']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build market trend metrics from existing market JSON files.")
    parser.add_argument("--date", required=True, help="Report date in YYYYMMDD format.")
    parser.add_argument("--market-json-dir", type=Path, default=DEFAULT_MARKET_JSON_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    payload = build_market_trend(args.date, args.market_json_dir)
    path = export_market_trend(payload, args.output_dir)
    print(f"[OK] market trend written: {path}")


if __name__ == "__main__":
    main()
