#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Taiwan futures and options risk monitor."""

import argparse
import csv
import json
import os
import re
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import yfinance as yf

try:
    from risk_monitor import get_trading_date
except ImportError:
    from src.risk_monitor import get_trading_date


TAIFEX_BASE_URL = "https://www.taifex.com.tw"


def parse_number(value: Any) -> Optional[float]:
    """Parse a number from exchange strings such as '23,456', '+1.2%', or '--'."""
    if value is None:
        return None

    text = str(value).strip()
    if not text or text in {"--", "-", "nan", "NaN"}:
        return None

    text = text.replace(",", "").replace("%", "")
    text = text.replace("＋", "+").replace("－", "-")
    text = re.sub(r"[^0-9.+-]", "", text)
    if not text or text in {"+", "-", ".", "+.", "-."}:
        return None

    try:
        number = float(text)
    except ValueError:
        return None

    return int(number) if number.is_integer() else number


def assess_basis(basis: Optional[float]) -> str:
    if basis is None:
        return "unknown"
    if basis <= -80:
        return "bearish"
    if basis >= 60:
        return "bullish"
    return "neutral"


def assess_pc_ratio(pc_ratio: Optional[float]) -> str:
    if pc_ratio is None:
        return "unknown"
    if pc_ratio >= 130:
        return "hedging_pressure"
    if pc_ratio <= 80:
        return "call_speculation"
    return "neutral"


def assess_foreign_futures(net_open_interest: Optional[float]) -> str:
    if net_open_interest is None:
        return "unknown"
    if net_open_interest <= -10000:
        return "bearish"
    if net_open_interest >= 10000:
        return "bullish"
    return "neutral"


def calculate_summary(payload: Dict[str, Any]) -> Dict[str, Any]:
    signals = []
    score = 50

    signal_weights = {
        "bearish": 15,
        "hedging_pressure": 10,
        "call_speculation": 5,
        "bullish": -10,
        "neutral": 0,
        "unknown": 0,
    }

    checks = [
        ("台指期基差", payload.get("futures", {}).get("basis_signal")),
        ("外資期貨部位", payload.get("positioning", {}).get("foreign_tx_net_signal")),
        ("選擇權 Put/Call Ratio", payload.get("options", {}).get("pc_ratio_signal")),
    ]

    for name, signal in checks:
        if not signal or signal == "unknown":
            continue
        score += signal_weights.get(signal, 0)
        signals.append({"name": name, "signal": signal})

    score = max(0, min(100, score))
    if score >= 70:
        bias = "risk_off"
    elif score <= 40:
        bias = "risk_on"
    else:
        bias = "neutral"

    return {
        "risk_score": score,
        "bias": bias,
        "signals": signals,
    }


class DerivativesMonitor:
    def __init__(self, date_str: str):
        self.date_str = date_str
        self.formatted_date = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}"

    def fetch_all(self) -> Dict[str, Any]:
        tx = self.fetch_tx_near_month()
        spot = self.fetch_taiex_spot()
        positioning = self.fetch_foreign_tx_position()
        pc = self.fetch_pc_ratio()

        basis = None
        basis_pct = None
        if tx.get("settlement") is not None and spot is not None:
            basis = round(tx["settlement"] - spot, 2)
            basis_pct = round((basis / spot) * 100, 2) if spot else None

        payload = {
            "date": self.date_str,
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "futures": {
                "tx_near_settlement": tx.get("settlement"),
                "tx_near_change_pct": tx.get("change_pct"),
                "taiex_spot": spot,
                "basis": basis,
                "basis_pct": basis_pct,
                "basis_signal": assess_basis(basis),
            },
            "positioning": {
                "foreign_tx_net_open_interest": positioning.get("foreign_tx_net_open_interest"),
                "foreign_tx_net_signal": assess_foreign_futures(positioning.get("foreign_tx_net_open_interest")),
                "source_note": positioning.get("source_note"),
            },
            "options": {
                "pc_ratio": pc.get("latest"),
                "pc_ratio_5d_avg": pc.get("five_day_avg"),
                "pc_ratio_signal": assess_pc_ratio(pc.get("latest")),
            },
        }
        payload["summary"] = calculate_summary(payload)
        return payload

    def fetch_tx_near_month(self) -> Dict[str, Optional[float]]:
        url = f"{TAIFEX_BASE_URL}/cht/3/futDailyMarketReport"
        params = {
            "queryType": "2",
            "marketCode": "0",
            "dateaddcnt": "",
            "queryDate": self.formatted_date,
            "commodity_id": "TX",
        }

        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            tables = pd.read_html(StringIO(response.text))
            if not tables or tables[0].empty:
                return {"settlement": None, "change_pct": None}

            row = tables[0].iloc[0]
            settlement = parse_number(row.iloc[5]) if len(row) > 5 else None
            change_pct = parse_number(row.iloc[7]) if len(row) > 7 else None
            return {"settlement": settlement, "change_pct": change_pct}
        except Exception as exc:
            print(f"[WARNING] 台指期近月資料取得失敗: {exc}")
            return {"settlement": None, "change_pct": None}

    def fetch_taiex_spot(self) -> Optional[float]:
        try:
            target_date = datetime.strptime(self.date_str, "%Y%m%d")
            hist = yf.Ticker("^TWII").history(
                start=target_date - timedelta(days=7),
                end=target_date + timedelta(days=1),
            )
            if hist.empty:
                return None
            closest_date = min(hist.index, key=lambda item: abs(item.date() - target_date.date()))
            return round(float(hist.loc[closest_date]["Close"]), 2)
        except Exception as exc:
            print(f"[WARNING] 加權指數現貨資料取得失敗: {exc}")
            return None

    def fetch_pc_ratio(self) -> Dict[str, Optional[float]]:
        url = f"{TAIFEX_BASE_URL}/cht/3/pcRatioDown"
        try:
            response = requests.post(url, data={"queryDate": self.formatted_date}, timeout=10)
            response.raise_for_status()
            rows = list(csv.reader(StringIO(response.text)))
            values: List[float] = []
            target_date = int(self.date_str)

            for row in rows[1:]:
                if len(row) < 7:
                    continue
                row_date = row[0].replace("/", "").strip()
                try:
                    if int(row_date) > target_date:
                        continue
                except ValueError:
                    continue

                value = parse_number(row[6])
                if value is not None:
                    values.append(float(value))
                if len(values) >= 5:
                    break

            latest = values[0] if values else None
            five_day_avg = round(sum(values) / len(values), 2) if values else None
            return {"latest": latest, "five_day_avg": five_day_avg}
        except Exception as exc:
            print(f"[WARNING] Put/Call Ratio 資料取得失敗: {exc}")
            return {"latest": None, "five_day_avg": None}

    def fetch_foreign_tx_position(self) -> Dict[str, Any]:
        url = f"{TAIFEX_BASE_URL}/cht/3/futContractsDate"
        try:
            response = requests.get(url, params={"queryDate": self.formatted_date}, timeout=10)
            response.raise_for_status()
            tables = pd.read_html(StringIO(response.text))

            for table in tables:
                candidate = self._extract_foreign_tx_position_from_table(table)
                if candidate is not None:
                    return {
                        "foreign_tx_net_open_interest": candidate,
                        "source_note": "TAIFEX futContractsDate",
                    }
        except Exception as exc:
            print(f"[WARNING] 外資台指期未平倉資料取得失敗: {exc}")

        return {
            "foreign_tx_net_open_interest": None,
            "source_note": "unavailable",
        }

    def _extract_foreign_tx_position_from_table(self, table: pd.DataFrame) -> Optional[int]:
        if table.empty:
            return None

        product_col = self._find_column(table, "商品")
        investor_col = self._find_column(table, "身份")
        net_lots_col = self._find_column(table, "未平倉", "多空淨額", "口數")

        for _, row in table.iterrows():
            product = str(row[product_col]) if product_col is not None else " ".join(str(value) for value in row.values)
            investor = str(row[investor_col]) if investor_col is not None else " ".join(str(value) for value in row.values)

            if "臺股期貨" not in product and "台股期貨" not in product:
                continue
            if "外資" not in investor and "外陸資" not in investor:
                continue

            if net_lots_col is not None:
                value = parse_number(row[net_lots_col])
                return int(value) if value is not None else None

            numbers = [parse_number(value) for value in row.values]
            numbers = [int(value) for value in numbers if isinstance(value, (int, float))]
            plausible_lots = [value for value in numbers if 1000 <= abs(value) <= 300000]
            if plausible_lots:
                return plausible_lots[-1]

        return None

    def _find_column(self, table: pd.DataFrame, *tokens: str):
        for column in table.columns:
            if isinstance(column, tuple):
                column_text = " ".join(str(part) for part in column)
            else:
                column_text = str(column)
            if all(token in column_text for token in tokens):
                return column
        return None

    def export(self, payload: Dict[str, Any]) -> Dict[str, str]:
        json_dir = os.path.join("outputs", "derivatives_json")
        txt_dir = os.path.join("outputs", "derivatives_txt")
        os.makedirs(json_dir, exist_ok=True)
        os.makedirs(txt_dir, exist_ok=True)

        json_path = os.path.join(json_dir, f"derivatives_{self.date_str}.json")
        txt_path = os.path.join(txt_dir, f"derivatives_{self.date_str}.txt")

        with open(json_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

        with open(txt_path, "w", encoding="utf-8") as file:
            file.write(format_report_text(payload))

        return {"json": json_path, "txt": txt_path}


def format_report_text(payload: Dict[str, Any]) -> str:
    summary = payload.get("summary", {})
    futures = payload.get("futures", {})
    positioning = payload.get("positioning", {})
    options = payload.get("options", {})

    lines = [
        f"# 衍生品風險監控 ({payload.get('date', '-')})",
        "",
        "## 總結",
        f"- 風險分數: {summary.get('risk_score', '-')}",
        f"- 盤勢傾向: {summary.get('bias', '-')}",
        "",
        "## 期貨",
        f"- 台指期近月結算價: {futures.get('tx_near_settlement')}",
        f"- 加權指數現貨: {futures.get('taiex_spot')}",
        f"- 期現基差: {futures.get('basis')} ({futures.get('basis_pct')}%)",
        f"- 基差訊號: {futures.get('basis_signal')}",
        "",
        "## 法人期貨部位",
        f"- 外資台指期未平倉淨口數: {positioning.get('foreign_tx_net_open_interest')}",
        f"- 部位訊號: {positioning.get('foreign_tx_net_signal')}",
        "",
        "## 選擇權",
        f"- Put/Call Ratio: {options.get('pc_ratio')}",
        f"- Put/Call Ratio 5日均值: {options.get('pc_ratio_5d_avg')}",
        f"- 選擇權訊號: {options.get('pc_ratio_signal')}",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Taiwan derivatives risk monitor")
    parser.add_argument("--date", type=str, help="交易日期 YYYYMMDD，預設取最近交易日")
    args = parser.parse_args()

    date_str = get_trading_date(args.date)
    monitor = DerivativesMonitor(date_str)
    payload = monitor.fetch_all()
    paths = monitor.export(payload)

    print(f"[SUCCESS] 衍生品 JSON: {paths['json']}")
    print(f"[SUCCESS] 衍生品 TXT: {paths['txt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
