#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build structured US sector relative-strength data from yfinance prices."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "us_sector_flow_json"
YFINANCE_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "yfinance"

BENCHMARK = "SPY"
SECTOR_TICKERS = {
    "XLK": "Technology",
    "XLV": "Health Care",
    "XLF": "Financials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLE": "Energy",
    "XLI": "Industrials",
    "XLB": "Materials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
    "SMH": "Semiconductors",
}

WINDOWS = {
    "1M": 21,
    "3M": 63,
    "6M": 126,
    "1Y": 252,
}


def fetch_close_prices(period: str = "2y") -> pd.DataFrame:
    YFINANCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if hasattr(yf, "set_tz_cache_location"):
        yf.set_tz_cache_location(str(YFINANCE_CACHE_DIR))
    tickers = list(SECTOR_TICKERS) + [BENCHMARK]
    data = yf.download(tickers, period=period, progress=False, auto_adjust=True)
    return normalize_close_frame(data)


def normalize_close_frame(data: pd.DataFrame) -> pd.DataFrame:
    if isinstance(data.columns, pd.MultiIndex):
        if "Close" in data.columns.get_level_values(0):
            closes = data["Close"]
        elif "Adj Close" in data.columns.get_level_values(0):
            closes = data["Adj Close"]
        else:
            closes = data.xs(data.columns.get_level_values(0)[0], axis=1, level=0)
    elif "Close" in data.columns:
        closes = data[["Close"]]
    else:
        closes = data

    closes = closes.dropna(how="all").ffill().dropna(how="all")
    return closes


def summarize_sector_flow(
    closes: pd.DataFrame,
    *,
    benchmark: str = BENCHMARK,
    windows: dict[str, int] = WINDOWS,
) -> dict[str, Any]:
    if benchmark not in closes.columns:
        raise ValueError(f"benchmark column is missing: {benchmark}")

    periods: dict[str, Any] = {}
    for label, trading_days in windows.items():
        if len(closes) < 2:
            continue
        start_index = max(0, len(closes) - trading_days - 1)
        frame = closes.iloc[start_index:].dropna(axis=1, how="all").ffill()
        if len(frame) < 2 or benchmark not in frame.columns:
            continue

        start = frame.iloc[0]
        end = frame.iloc[-1]
        benchmark_return = pct_return(start[benchmark], end[benchmark])

        sectors = []
        for ticker, name in SECTOR_TICKERS.items():
            if ticker not in frame.columns:
                continue
            sector_return = pct_return(start[ticker], end[ticker])
            if sector_return is None or benchmark_return is None:
                continue
            sectors.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "return_pct": round(sector_return, 2),
                    "benchmark_return_pct": round(benchmark_return, 2),
                    "alpha_pct": round(sector_return - benchmark_return, 2),
                }
            )

        sectors.sort(key=lambda item: item["alpha_pct"], reverse=True)
        periods[label] = {
            "start_date": frame.index[0].strftime("%Y-%m-%d"),
            "end_date": frame.index[-1].strftime("%Y-%m-%d"),
            "benchmark": benchmark,
            "sectors": sectors,
        }

    return {"periods": periods}


def pct_return(start: Any, end: Any) -> float | None:
    try:
        start_value = float(start)
        end_value = float(end)
    except (TypeError, ValueError):
        return None
    if start_value == 0 or pd.isna(start_value) or pd.isna(end_value):
        return None
    return (end_value / start_value - 1) * 100


def build_payload(date: str, closes: pd.DataFrame) -> dict[str, Any]:
    payload = summarize_sector_flow(closes)
    payload.update(
        {
            "date": date,
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "yfinance",
        }
    )
    return payload


def has_usable_sector_data(payload: dict[str, Any]) -> bool:
    for period in payload.get("periods", {}).values():
        if period.get("sectors"):
            return True
    return False


def write_payload(payload: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"us_sector_flow_{payload['date']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch structured US sector relative-strength data.")
    parser.add_argument("--date", required=True, help="Output date in YYYYMMDD format.")
    parser.add_argument("--period", default="2y", help="yfinance history period, default: 2y.")
    args = parser.parse_args()

    closes = fetch_close_prices(args.period)
    payload = build_payload(args.date, closes)
    if not has_usable_sector_data(payload):
        print("[ERROR] no usable US sector data was downloaded")
        return 1
    path = write_payload(payload)
    print(f"[OK] US sector flow written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
