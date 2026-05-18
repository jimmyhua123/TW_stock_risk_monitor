#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票期貨換月轉倉逆價差監控 (Stock Futures Roll-Over Spread Monitor)
從台灣期交所 (TAIFEX) 爬取自選股的股票期貨近月/遠月結算價，
計算換月價差與年化利率，並依據數值給出警示判斷。

判斷邏輯（年化逆價差利率）：
  [!!] > 15%  → 高逆價差警示（融券鎖死 / 除息旺季 / 極端恐慌）
  [!]  5%~15% → 中度逆價差（留意轉倉成本）
  [OK] < 5%  → 正常範圍
  [^]  正價差  → 遠月 > 近月（正常正價差，空頭轉倉有利）

流程：
  Step 1: 從 TAIFEX 爬取股票代號→期貨代碼對照表（select#commodity_id2t）
  Step 2: 用期貨代碼（如 CDF）查詢每日行情，取近月/遠月結算價
  Step 3: 計算換月年化逆價差並給出判斷
"""

import argparse
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from risk_monitor import get_trading_date
except ImportError:
    try:
        from src.risk_monitor import get_trading_date
    except ImportError:
        def get_trading_date(date_str: Optional[str] = None) -> str:
            if date_str:
                return date_str
            now = datetime.now()
            if now.weekday() == 5:
                now -= timedelta(days=1)
            elif now.weekday() == 6:
                now -= timedelta(days=2)
            return now.strftime("%Y%m%d")


TAIFEX_BASE_URL = "https://www.taifex.com.tw"
WATCHLIST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "config", "watchlist.json"
)

# 快取對照表（同一次執行只爬一次）
_CODE_MAP_CACHE: Dict[str, str] = {}   # { "2330": "CDF", "2454": "DVF", ... }


# ─────────────────────────────────────────────
# 工具函式
# ─────────────────────────────────────────────

def load_watchlist() -> List[Dict[str, str]]:
    """載入自選股清單，過濾掉權證（代號 6 位數）"""
    if not os.path.exists(WATCHLIST_PATH):
        print(f"[WARNING] watchlist.json 不存在: {WATCHLIST_PATH}")
        return []
    with open(WATCHLIST_PATH, encoding="utf-8") as f:
        data = json.load(f)
    stocks = []
    for item in data.get("watchlist", []):
        code = str(item.get("code", "")).strip()
        if code.isdigit() and len(code) == 4:
            stocks.append({"code": code, "name": item.get("name", code)})
    return stocks


def parse_number(value: Any) -> Optional[float]:
    """解析期交所字串數字，如 '23,456' 或 '--'"""
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("＋", "+").replace("－", "-")
    if not text or text in {"--", "-", "nan", "NaN", ""}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def get_third_wednesday(year: int, month: int) -> datetime:
    """計算指定月份第三個星期三（股票期貨到期日）"""
    first_day = datetime(year, month, 1)
    days_to_wed = (2 - first_day.weekday()) % 7
    first_wed = first_day + timedelta(days=days_to_wed)
    return first_wed + timedelta(weeks=2)


def calc_days_between_contracts(query_date: str) -> Tuple[int, str, str]:
    """
    根據查詢日期，計算近月到遠月合約的天數差。
    台灣股票期貨到期日：每月第三個星期三。

    Returns: (days_diff, near_month_label, far_month_label)
    """
    d = datetime.strptime(query_date, "%Y%m%d")
    year, month = d.year, d.month

    near_expiry = get_third_wednesday(year, month)

    if d >= near_expiry:
        # 近月已到期，推至下月
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        near_expiry = get_third_wednesday(next_year, next_month)

        far_month = next_month + 1 if next_month < 12 else 1
        far_year = next_year if next_month < 12 else next_year + 1
        far_expiry = get_third_wednesday(far_year, far_month)
    else:
        far_month = month + 1 if month < 12 else 1
        far_year = year if month < 12 else year + 1
        far_expiry = get_third_wednesday(far_year, far_month)

    days_diff = max((far_expiry - near_expiry).days, 1)
    return days_diff, near_expiry.strftime("%Y/%m"), far_expiry.strftime("%Y/%m")


# ─────────────────────────────────────────────
# Step 1: 爬取股票代號 → 期貨代碼對照表
# ─────────────────────────────────────────────

def fetch_code_mapping(formatted_date: str) -> Dict[str, str]:
    """
    從 TAIFEX 期貨每日行情頁面的 <select id="commodity_id2t"> 爬取
    股票代號 → 期貨代碼對照表。
    
    選項格式範例：
      <option value="CDF">2330台積電期貨 ( CD)</option>
      <option value="DVF">2454聯發科期貨 (DVF)</option>
    
    Returns: { "2330": "CDF", "2454": "DVF", ... }
    """
    global _CODE_MAP_CACHE
    if _CODE_MAP_CACHE:
        return _CODE_MAP_CACHE

    url = (
        f"{TAIFEX_BASE_URL}/cht/3/futDailyMarketReport"
        f"?queryType=2&marketCode=0&dateaddcnt=&queryDate={formatted_date}"
        f"&commodity_id=specialid&commodity_id2=CDF"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        select = soup.find("select", {"id": "commodity_id2t"})
        if not select:
            print("[WARNING] 找不到 commodity_id2t 選單，對照表為空")
            return {}

        mapping: Dict[str, str] = {}
        for opt in select.find_all("option"):
            futures_code = opt.get("value", "").strip()
            text = opt.get_text(strip=True)
            # 文字格式：「2330台積電期貨 ( CD)」或「2454聯發科期貨 (DVF)」
            # 前 4 碼若是數字即為股票代號
            if len(text) >= 4 and text[:4].isdigit():
                stock_code = text[:4]
                # 排除小型股期（含「小型」字樣）
                if "小型" not in text and futures_code:
                    mapping[stock_code] = futures_code

        print(f"[INFO] 對照表建立完成，共 {len(mapping)} 檔標準股票期貨")
        _CODE_MAP_CACHE = mapping
        return mapping

    except Exception as exc:
        print(f"[WARNING] 對照表爬取失敗: {exc}")
        return {}


# ─────────────────────────────────────────────
# Step 2: 用期貨代碼查詢每日行情
# ─────────────────────────────────────────────

def fetch_stock_futures(futures_code: str, formatted_date: str) -> Dict[str, Any]:
    """
    使用期貨代碼（如 'CDF'）查詢 TAIFEX 每日行情，
    返回近月與遠月結算價。
    """
    url = f"{TAIFEX_BASE_URL}/cht/3/futDailyMarketReport"
    params = {
        "queryType": "2",
        "marketCode": "0",
        "dateaddcnt": "",
        "queryDate": formatted_date,
        "commodity_id": "specialid",
        "commodity_id2": futures_code,
    }

    try:
        resp = requests.get(url, params=params, timeout=12)
        resp.raise_for_status()
        tables = pd.read_html(StringIO(resp.text))
        if not tables or tables[0].empty:
            return {"error": "no_data"}

        df = tables[0]
        rows = []
        for _, row in df.iterrows():
            row_vals = [str(v).strip() for v in row.values]
            # 找合約月份欄（格式可能為 "202605" 或 "202605.0"）
            month_col_idx = None
            month_clean = None
            for i, val in enumerate(row_vals):
                # 去除小數點後的 .0（TAIFEX 有時以浮點回傳）
                candidate = val.split(".")[0] if "." in val else val
                if len(candidate) == 6 and candidate.isdigit():
                    month_col_idx = i
                    month_clean = candidate
                    break
            if month_col_idx is None:
                continue

            # 找結算價欄（第 5 欄 = 最後成交價/結算價）
            settlement = None
            if len(row_vals) > 5:
                settlement = parse_number(row_vals[5])
            # 若第 5 欄無效，掃描後續欄找第一個合理正數
            if settlement is None or settlement <= 0:
                for val in row_vals[4:]:
                    candidate_val = parse_number(val)
                    if candidate_val and candidate_val > 10:
                        settlement = candidate_val
                        break

            if settlement is not None and settlement > 0:
                rows.append({
                    "month_label": month_clean,
                    "settlement": settlement,
                })

        rows.sort(key=lambda x: x["month_label"])

        if len(rows) == 0:
            return {"error": "parse_failed"}
        if len(rows) == 1:
            return {"near": rows[0], "far": None, "error": "only_one_month"}

        return {"near": rows[0], "far": rows[1], "all_months": rows}

    except Exception as exc:
        return {"error": str(exc)}


# ─────────────────────────────────────────────
# Step 3: 計算換月逆價差與年化利率
# ─────────────────────────────────────────────

def calculate_rollover(
    near_price: float,
    far_price: float,
    days_diff: int,
    threshold_high: float,
    threshold_medium: float,
) -> Dict[str, Any]:
    """
    計算換月價差與年化利率。

    逆價差：近月 > 遠月（多方轉倉有利；空方換月成本高）
    正價差：近月 < 遠月（空頭轉倉有利）

    年化利率 = (近月 - 遠月) / 遠月 × (365 / days_diff) × 100
    """
    spread = round(near_price - far_price, 2)
    spread_pct = round((spread / far_price) * 100, 4) if far_price else None
    annualized_pct = (
        round(spread_pct * (365 / days_diff), 2)
        if spread_pct is not None else None
    )

    if annualized_pct is None:
        return {
            "spread": spread, "spread_pct": spread_pct,
            "annualized_pct": annualized_pct, "days_diff": days_diff,
            "signal": "unknown", "emoji": "❓",
            "terminal": "[?]", "description": "無法計算",
        }

    if annualized_pct > threshold_high:
        signal, emoji, terminal = "high_backwardation", "🔴", "[!!]"
        description = (
            f"高逆價差警示（年化 {annualized_pct:.1f}%）"
            "——可能因融券鎖死、除息季或極端恐慌造成；空方換月成本極高"
        )
    elif annualized_pct > threshold_medium:
        signal, emoji, terminal = "medium_backwardation", "🟡", "[!] "
        description = (
            f"中度逆價差（年化 {annualized_pct:.1f}%）——留意轉倉成本"
        )
    elif annualized_pct >= 0:
        signal, emoji, terminal = "normal_backwardation", "🟢", "[OK]"
        description = f"正常逆價差（年化 {annualized_pct:.1f}%）"
    else:
        signal, emoji, terminal = "contango", "⬆️", "[^] "
        description = (
            f"正價差（遠月溢價，年化 {abs(annualized_pct):.1f}%）"
            "——空頭轉倉有利，多方換月需付溢價"
        )

    return {
        "spread": spread,
        "spread_pct": spread_pct,
        "annualized_pct": annualized_pct,
        "days_diff": days_diff,
        "signal": signal,
        "emoji": emoji,
        "terminal": terminal,
        "description": description,
    }


# ─────────────────────────────────────────────
# 主監控類別
# ─────────────────────────────────────────────

class StockFuturesRolloverMonitor:
    def __init__(self, date_str: str,
                 threshold_high: float = 15.0,
                 threshold_medium: float = 5.0):
        self.date_str = date_str
        self.formatted_date = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}"
        self.threshold_high = threshold_high
        self.threshold_medium = threshold_medium
        self.days_diff, self.near_label, self.far_label = calc_days_between_contracts(date_str)
        self.code_map: Dict[str, str] = {}

    def run(self, stocks: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        results = []

        # 建立對照表（只爬一次）
        print(f"\n[Step 1] 建立股票代號 → 期貨代碼對照表...")
        self.code_map = fetch_code_mapping(self.formatted_date)

        print(f"[Step 2] 開始查詢每日行情")
        print(f"  近月合約：{self.near_label}，遠月合約：{self.far_label}，"
              f"天數差：{self.days_diff} 天")
        print(f"  警示門檻：年化 > {self.threshold_high}% 高警示，"
              f"> {self.threshold_medium}% 中度注意\n")

        for i, stock in enumerate(stocks):
            code = stock["code"]
            name = stock["name"]
            prefix = f"  [{i+1:02d}/{len(stocks)}] {name}({code})"

            # 查對照表
            futures_code = self.code_map.get(code)
            if not futures_code:
                print(f"{prefix} ... 無股票期貨（不在期交所上市）")
                results.append({
                    "code": code, "name": name,
                    "futures_code": None,
                    "near_month": self.near_label, "near_price": None,
                    "far_month": self.far_label, "far_price": None,
                    "rollover": None, "status": "no_futures",
                    "note": "此股未在期交所上市股票期貨",
                })
                continue

            # 查詢每日行情
            raw = fetch_stock_futures(futures_code, self.formatted_date)
            error = raw.get("error")

            if error and error != "only_one_month":
                print(f"{prefix}({futures_code}) [X] 查無資料 ({error})")
                results.append({
                    "code": code, "name": name,
                    "futures_code": futures_code,
                    "near_month": self.near_label, "near_price": None,
                    "far_month": self.far_label, "far_price": None,
                    "rollover": None, "status": "no_data",
                    "note": f"查無行情資料 ({error})",
                })
                time.sleep(0.3)
                continue

            near = raw.get("near")
            far = raw.get("far")
            near_price = near["settlement"] if near else None
            far_price = far["settlement"] if far else None

            if near_price is None:
                print(f"{prefix}({futures_code}) [X] 近月結算價為空")
                results.append({
                    "code": code, "name": name,
                    "futures_code": futures_code,
                    "near_month": self.near_label, "near_price": None,
                    "far_month": self.far_label, "far_price": None,
                    "rollover": None, "status": "no_price",
                    "note": "近月結算價無資料",
                })
                time.sleep(0.3)
                continue

            if far_price is None:
                print(f"{prefix}({futures_code}) [!] 近月={near_price}，無遠月資料")
                results.append({
                    "code": code, "name": name,
                    "futures_code": futures_code,
                    "near_month": near["month_label"], "near_price": near_price,
                    "far_month": self.far_label, "far_price": None,
                    "rollover": None, "status": "no_far_month",
                    "note": "無遠月合約資料",
                })
                time.sleep(0.3)
                continue

            rollover = calculate_rollover(
                near_price, far_price, self.days_diff,
                self.threshold_high, self.threshold_medium,
            )
            ann = rollover["annualized_pct"]
            print(
                f"{prefix}({futures_code}) {rollover['terminal']}"
                f" 近={near_price} / 遠={far_price}"
                f" | 差={rollover['spread']:+.0f}"
                f" | 年化={ann:+.1f}%"
            )

            results.append({
                "code": code,
                "name": name,
                "futures_code": futures_code,
                "near_month": near["month_label"],
                "near_price": near_price,
                "far_month": far["month_label"],
                "far_price": far_price,
                "rollover": rollover,
                "status": "ok",
                "note": rollover["description"],
            })
            time.sleep(0.4)

        return results

    def export(self, results: List[Dict[str, Any]]) -> Dict[str, str]:
        out_dir = os.path.join("outputs", "rollover_json")
        txt_dir = os.path.join("outputs", "rollover_txt")
        os.makedirs(out_dir, exist_ok=True)
        os.makedirs(txt_dir, exist_ok=True)

        payload = {
            "date": self.date_str,
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "near_contract": self.near_label,
            "far_contract": self.far_label,
            "days_diff": self.days_diff,
            "threshold_high_pct": self.threshold_high,
            "threshold_medium_pct": self.threshold_medium,
            "stocks": results,
        }

        json_path = os.path.join(out_dir, f"rollover_{self.date_str}.json")
        txt_path = os.path.join(txt_dir, f"rollover_{self.date_str}.txt")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(self._format_report(results))

        return {"json": json_path, "txt": txt_path}

    def _format_report(self, results: List[Dict[str, Any]]) -> str:
        th = self.threshold_high
        tm = self.threshold_medium
        lines = [
            f"# 股期換月轉倉逆價差監控報告 ({self.date_str})",
            f"近月合約：{self.near_label}　遠月合約：{self.far_label}"
            f"　天數差：{self.days_diff} 天",
            "",
            "## 判斷門檻",
            f"  🔴 年化逆價差 > {th}%  → 高警示（融券鎖死 / 除息 / 極端恐慌）",
            f"  🟡 年化逆價差 {tm}%~{th}% → 中度注意",
            f"  🟢 年化逆價差 < {tm}% → 正常範圍",
            f"  ⬆️  正價差（遠月 > 近月）→ 空頭轉倉有利",
            "",
            "## 個股監控結果",
            "",
        ]

        def is_signal(r: Dict, *sigs: str) -> bool:
            rv = r.get("rollover")
            return rv is not None and rv["signal"] in sigs

        alerts = [r for r in results if is_signal(r, "high_backwardation")]
        mediums = [r for r in results if is_signal(r, "medium_backwardation")]
        normals = [r for r in results if is_signal(r, "normal_backwardation", "contango")]
        no_data = [r for r in results if r.get("rollover") is None]

        def fmt_row(r: Dict[str, Any]) -> str:
            rv = r["rollover"]
            return (
                f"  {rv['emoji']} {r['name']} ({r['code']} / {r.get('futures_code', '?')})"
                f" | 近={r['near_price']} / 遠={r['far_price']}"
                f" | 價差={rv['spread']:+.0f} ({rv['spread_pct']:+.2f}%)"
                f" | 年化={rv['annualized_pct']:+.1f}%"
                f"\n      → {rv['description']}"
            )

        if alerts:
            lines.append("### 🔴 高逆價差警示")
            lines.extend(fmt_row(r) for r in alerts)
            lines.append("")

        if mediums:
            lines.append("### 🟡 中度逆價差（留意）")
            lines.extend(fmt_row(r) for r in mediums)
            lines.append("")

        if normals:
            lines.append("### 🟢 正常 / 正價差")
            lines.extend(fmt_row(r) for r in normals)
            lines.append("")

        if no_data:
            lines.append("### -- 無股期資料（該股可能無股票期貨）")
            for r in no_data:
                lines.append(f"  - {r['name']} ({r['code']})：{r.get('note', '')}")
            lines.append("")

        lines.append("---")
        lines.append(f"報告產出時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────

def main() -> int:
    # Windows 終端強制 UTF-8 輸出
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="股票期貨換月轉倉逆價差監控",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python src/stock_futures_rollover.py
  python src/stock_futures_rollover.py --date 20260518
  python src/stock_futures_rollover.py --codes 2330 2454 2345
  python src/stock_futures_rollover.py --threshold-high 10 --threshold-medium 3
        """
    )
    parser.add_argument("--date", type=str, default=None,
                        help="查詢日期 YYYYMMDD（預設：最近交易日）")
    parser.add_argument("--codes", nargs="+", type=str, default=None,
                        help="指定股票代號（預設：讀取 watchlist.json）")
    parser.add_argument("--threshold-high", type=float, default=15.0,
                        help="高警示門檻年化%%（預設 15.0）")
    parser.add_argument("--threshold-medium", type=float, default=5.0,
                        help="中度注意門檻年化%%（預設 5.0）")
    args = parser.parse_args()

    date_str = get_trading_date(args.date)

    if args.codes:
        stocks = [{"code": c, "name": c} for c in args.codes]
    else:
        stocks = load_watchlist()

    if not stocks:
        print("[ERROR] 無法取得股票清單，請確認 watchlist.json 或使用 --codes 參數")
        return 1

    print(f"╔══════════════════════════════════════════╗")
    print(f"║  股期換月轉倉逆價差監控 — {date_str}  ║")
    print(f"╚══════════════════════════════════════════╝")

    monitor = StockFuturesRolloverMonitor(
        date_str,
        threshold_high=args.threshold_high,
        threshold_medium=args.threshold_medium,
    )
    results = monitor.run(stocks)
    paths = monitor.export(results)

    ok = [r for r in results if r.get("rollover")]
    high_alerts = [r for r in ok if r["rollover"]["signal"] == "high_backwardation"]

    print(f"\n{'='*50}")
    print(f" 完成！共 {len(ok)}/{len(results)} 檔有股期資料")
    if high_alerts:
        print(f" 高逆價差警示：{', '.join(r['name'] for r in high_alerts)}")
    print(f"    JSON: {paths['json']}")
    print(f"    TXT : {paths['txt']}")
    print(f"{'='*50}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
