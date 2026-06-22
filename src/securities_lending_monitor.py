#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch TWSE securities lending / short selling balance summary."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

try:
    from .derivatives_monitor import parse_number
    from .risk_monitor import get_trading_date
except ImportError:
    from derivatives_monitor import parse_number
    from risk_monitor import get_trading_date


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "securities_lending_json"
TWSE_TWT93U_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U"


def summarize_lending_rows(rows: list[dict[str, Any]], watch_codes: set[str] | None = None) -> dict[str, Any]:
    watch_codes = watch_codes or set()
    total_balance = 0.0
    total_daily_change = 0.0
    items = []

    for row in rows:
        code = normalize_code(first_existing(row, "code", "證券代號", "股票代號", "有價證券代號"))
        if not code:
            continue
        name = first_existing(row, "name", "證券名稱", "股票名稱", "有價證券名稱") or code
        balance = parse_number(first_existing(row, "lending_balance", "借券賣出餘額", "借券賣出餘額(股)", "借券賣出餘額(張)"))
        daily_change = parse_number(first_existing(row, "daily_change", "借券賣出當日增減", "借券賣出今日增減", "借券賣出增減"))
        if daily_change is None:
            previous = parse_number(row.get("lending_previous_balance"))
            if balance is not None and previous is not None:
                daily_change = balance - previous
        if balance is None:
            balance = 0
        if daily_change is None:
            daily_change = 0

        total_balance += float(balance)
        total_daily_change += float(daily_change)
        if code in watch_codes:
            items.append(
                {
                    "code": code,
                    "name": str(name),
                    "lending_balance": balance,
                    "daily_change": daily_change,
                }
            )

    daily_change_ratio = round(total_daily_change / total_balance, 4) if total_balance else None
    items.sort(key=lambda item: abs(float(item["daily_change"] or 0)), reverse=True)
    return {
        "market": {
            "total_lending_balance": int(total_balance),
            "total_daily_change": int(total_daily_change),
            "daily_change_ratio": daily_change_ratio,
        },
        "watchlist_items": items,
    }


def first_existing(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping:
            return mapping.get(key)
    return None


def normalize_code(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.isdigit():
        return text.zfill(4)
    return ""


def load_watch_codes(path: Path = PROJECT_ROOT / "data" / "config" / "watchlist.json") -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    codes = set()
    for item in data.get("watchlist", []):
        code = normalize_code(item.get("code"))
        if code:
            codes.add(code)
    return codes


def fetch_twse_lending_rows(date: str) -> list[dict[str, Any]]:
    response = requests.get(
        TWSE_TWT93U_URL,
        params={"response": "json", "date": date},
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    raw_rows = payload.get("data") or []
    rows = []
    for raw in raw_rows:
        if isinstance(raw, dict):
            rows.append(raw)
        else:
            rows.append(normalize_twt93u_row(raw))
    return rows


def normalize_twt93u_row(raw: list[Any]) -> dict[str, Any]:
    return {
        "code": raw[0] if len(raw) > 0 else "",
        "name": raw[1] if len(raw) > 1 else "",
        "short_previous_balance": raw[2] if len(raw) > 2 else None,
        "short_sold": raw[3] if len(raw) > 3 else None,
        "short_bought": raw[4] if len(raw) > 4 else None,
        "short_spot_returned": raw[5] if len(raw) > 5 else None,
        "short_balance": raw[6] if len(raw) > 6 else None,
        "lending_previous_balance": raw[8] if len(raw) > 8 else None,
        "lending_sold": raw[9] if len(raw) > 9 else None,
        "lending_returned": raw[10] if len(raw) > 10 else None,
        "lending_adjusted": raw[11] if len(raw) > 11 else None,
        "lending_balance": raw[12] if len(raw) > 12 else None,
    }


def build_payload(date: str, rows: list[dict[str, Any]], watch_codes: set[str] | None = None) -> dict[str, Any]:
    summary = summarize_lending_rows(rows, watch_codes)
    return {
        "date": date,
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "TWSE twt93u",
        **summary,
    }


def write_payload(payload: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"securities_lending_{payload['date']}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch TWSE securities lending summary.")
    parser.add_argument("--date", type=str, default=None, help="Trading date in YYYYMMDD format.")
    args = parser.parse_args()

    date = get_trading_date(args.date)
    rows = fetch_twse_lending_rows(date)
    payload = build_payload(date, rows, load_watch_codes())
    path = write_payload(payload)
    print(f"[OK] securities lending written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
