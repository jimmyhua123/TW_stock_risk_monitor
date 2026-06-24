#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Measure defensive relative strength as a supplementary market-risk input.

The monitor intentionally treats financial and Swiss outperformance as a
context signal, not as proof of an imminent market decline.  A weak benchmark
trend is required before it emits a downtrend-risk signal, and a strong DXY
regime downgrades the EWL/SPY read to USD-led defence.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "defensive_rotation_json"
YFINANCE_CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "yfinance"

TAIWAN_BENCHMARK = "^TWII"
TAIWAN_FINANCIAL_PROXY = "0055.TW"
US_BENCHMARK = "SPY"
SWISS_DEFENSIVE_PROXY = "EWL"
USD_INDEX = "DX-Y.NYB"
WINDOW_DAYS = 20
RELATIVE_STRENGTH_THRESHOLD_PCT = 3.0
WEAK_TREND_THRESHOLD_PCT = -1.0
STRONG_DOLLAR_THRESHOLD_PCT = 2.0


def fetch_close_prices(period: str = "1y") -> pd.DataFrame:
    """Download the five prices used by this monitor."""
    YFINANCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if hasattr(yf, "set_tz_cache_location"):
        yf.set_tz_cache_location(str(YFINANCE_CACHE_DIR))
    tickers = [TAIWAN_BENCHMARK, TAIWAN_FINANCIAL_PROXY, US_BENCHMARK, SWISS_DEFENSIVE_PROXY, USD_INDEX]
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
    return closes.dropna(how="all").ffill().dropna(how="all")


def summarize_defensive_rotation(closes: pd.DataFrame, *, window: int = WINDOW_DAYS) -> dict[str, Any]:
    """Summarize Taiwan and US defensive rotation from aligned close prices."""
    taiwan = summarize_pair(closes, TAIWAN_FINANCIAL_PROXY, TAIWAN_BENCHMARK, window)
    us = summarize_pair(closes, SWISS_DEFENSIVE_PROXY, US_BENCHMARK, window)
    dxy_return = trailing_return(closes, USD_INDEX, window)

    taiwan["signal"] = classify_taiwan_signal(taiwan)
    us["dxy_return_pct"] = dxy_return
    us["signal"] = classify_us_signal(us, dxy_return)

    signals = {taiwan["signal"], us["signal"]}
    summary_signal = "elevated_downtrend_risk" if "downtrend_risk" in signals else "neutral"
    return {
        "window_days": window,
        "taiwan": taiwan,
        "us": us,
        "summary": {"signal": summary_signal},
    }


def summarize_pair(closes: pd.DataFrame, defensive: str, benchmark: str, window: int) -> dict[str, Any]:
    defensive_return = trailing_return(closes, defensive, window)
    benchmark_return = trailing_return(closes, benchmark, window)
    benchmark_gap = gap_from_moving_average(closes, benchmark, window)
    relative_return = None
    if defensive_return is not None and benchmark_return is not None:
        relative_return = round(((1 + defensive_return / 100) / (1 + benchmark_return / 100) - 1) * 100, 2)

    return {
        "defensive_ticker": defensive,
        "benchmark_ticker": benchmark,
        "defensive_return_pct": defensive_return,
        "benchmark_return_pct": benchmark_return,
        "benchmark_gap_ma_pct": benchmark_gap,
        "relative_strength": {"ratio": f"{defensive}/{benchmark}", "return_pct": relative_return},
    }


def trailing_return(closes: pd.DataFrame, ticker: str, window: int) -> float | None:
    if ticker not in closes.columns or len(closes) < window + 1:
        return None
    values = closes[ticker].dropna()
    if len(values) < window + 1:
        return None
    start = float(values.iloc[-window - 1])
    end = float(values.iloc[-1])
    if start == 0:
        return None
    return round((end / start - 1) * 100, 2)


def gap_from_moving_average(closes: pd.DataFrame, ticker: str, window: int) -> float | None:
    if ticker not in closes.columns:
        return None
    values = closes[ticker].dropna()
    if len(values) < window:
        return None
    moving_average = float(values.iloc[-window:].mean())
    latest = float(values.iloc[-1])
    if moving_average == 0:
        return None
    return round((latest / moving_average - 1) * 100, 2)


def classify_taiwan_signal(metrics: dict[str, Any]) -> str:
    relative = metrics["relative_strength"]["return_pct"]
    benchmark_gap = metrics["benchmark_gap_ma_pct"]
    benchmark_return = metrics["benchmark_return_pct"]
    if relative is None or benchmark_gap is None or benchmark_return is None:
        return "unavailable"
    if benchmark_return <= -5 and metrics["defensive_return_pct"] <= -3:
        return "broad_risk_off"
    if relative >= RELATIVE_STRENGTH_THRESHOLD_PCT and benchmark_gap <= WEAK_TREND_THRESHOLD_PCT:
        return "downtrend_risk"
    if relative >= RELATIVE_STRENGTH_THRESHOLD_PCT:
        return "healthy_rotation"
    return "neutral"


def classify_us_signal(metrics: dict[str, Any], dxy_return: float | None) -> str:
    relative = metrics["relative_strength"]["return_pct"]
    benchmark_gap = metrics["benchmark_gap_ma_pct"]
    if relative is None or benchmark_gap is None:
        return "unavailable"
    if relative >= RELATIVE_STRENGTH_THRESHOLD_PCT and dxy_return is not None and dxy_return >= STRONG_DOLLAR_THRESHOLD_PCT:
        return "usd_defense"
    if relative >= RELATIVE_STRENGTH_THRESHOLD_PCT and benchmark_gap <= WEAK_TREND_THRESHOLD_PCT:
        return "downtrend_risk"
    if relative >= RELATIVE_STRENGTH_THRESHOLD_PCT:
        return "defensive_rotation"
    return "neutral"


def build_payload(date: str, closes: pd.DataFrame) -> dict[str, Any]:
    payload = summarize_defensive_rotation(closes)
    payload.update({"date": date, "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "source": "yfinance"})
    return payload


def has_usable_rotation_data(payload: dict[str, Any]) -> bool:
    return payload.get("taiwan", {}).get("signal") != "unavailable" or payload.get("us", {}).get("signal") != "unavailable"


def write_payload(payload: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"defensive_rotation_{payload['date']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build defensive-rotation relative-strength signals.")
    parser.add_argument("--date", required=True, help="Output date in YYYYMMDD format.")
    parser.add_argument("--period", default="1y", help="yfinance history period, default: 1y.")
    args = parser.parse_args()
    payload = build_payload(args.date, fetch_close_prices(args.period))
    if not has_usable_rotation_data(payload):
        print("[ERROR] no usable defensive-rotation data was downloaded")
        return 1
    path = write_payload(payload)
    print(f"[OK] defensive rotation written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
