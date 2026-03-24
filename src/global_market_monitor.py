#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全球市場與總經數據監控 (Global Market & Macro Monitor)
獲取全球主要股市指數、原物料、匯率及美國聯準會相關總經數據
輸出為獨立的 JSON 及 Excel 報表
"""

import sys
import os
import argparse
import json
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# 加入 src 路徑以引用共用模組
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from risk_monitor import get_trading_date
except ImportError:
    def get_trading_date(date_str=None):
        if date_str:
            return date_str
        now = datetime.now()
        if now.weekday() == 5:
            now -= timedelta(days=1)
        elif now.weekday() == 6:
            now -= timedelta(days=2)
        return now.strftime("%Y%m%d")

# === 全球市場清單 ===
GLOBAL_ASSETS = {
    "Americas": {
        "標普500": "^GSPC",
        "道瓊工業": "^DJI",
        "納斯達克": "^IXIC",
        "費城半導體": "^SOX"
    },
    "Europe": {
        "德國DAX": "^GDAXI",
        "法國CAC40": "^FCHI",
        "英國FTSE": "^FTSE"
    },
    "AsiaPacific": {
        "日經225": "^N225",
        "南韓KOSPI": "^KS11",
        "台灣加權": "^TWII",
        "香港恆生": "^HSI",
        "滬深300": "000300.SS",
        "澳洲ASX200": "^AXJO",
        "印度SENSEX": "^BSESN"
    },
    "Commodities": {
        "黃金": "GC=F",
        "WTI原油": "CL=F",
        "銅": "HG=F",
        "白銀": "SI=F",
        "黃豆": "ZS=F",
        "玉米": "ZC=F",
        "小麥": "ZW=F"
    },
    "Rates_Forex": {
        "10年美債(%)": "^TNX",
        "比特幣": "BTC-USD",
        "美元/台幣": "USDTWD=X",
        "澳幣/美元": "AUDUSD=X",
        "歐元/美元": "EURUSD=X",
        "美元/日圓": "USDJPY=X",
        "美元指數": "DX-Y.NYB"
    }
}

FRED_API_KEY = "94d4e53f11d11501a06bfb8a9eaa6b16"

class GlobalMarketMonitor:
    def __init__(self, date_str: str):
        self.date_str = date_str
        self.market_data = {}
        self.macro_data = {}
        
    def fetch_yfinance_data(self):
        """抓取 yfinance 資產價格與漲跌幅"""
        print("[INFO] 開始抓取全球股市、原物料及外匯數據...")
        
        for category, assets in GLOBAL_ASSETS.items():
            self.market_data[category] = []
            
            # 建立單次請求的 ticker 列表以加速 (這裡示範逐一抓取以確保資料完整且容錯)
            for name, ticker in assets.items():
                print(f"  > 抓取 {name} ({ticker})...", end="")
                try:
                    asset = yf.Ticker(ticker)
                    # 抓取過去 5 天資料，確保能計算單日變動
                    hist = asset.history(period="5d")
                    if hist.empty:
                        print(" [警告: 無資料]")
                        continue
                        
                    # 取得最後兩筆價格
                    closes = hist['Close']
                    last_close = float(closes.iloc[-1])
                    prev_close = float(closes.iloc[-2]) if len(closes) > 1 else last_close
                    
                    # 計算漲跌幅
                    # 10年美債使用 bps (基點) 為單位
                    if ticker == "^TNX":
                        change_percent = (last_close - prev_close) * 100 # 10年美債直接算基點差異
                        unit = "bp"
                    else:
                        change_percent = ((last_close - prev_close) / prev_close) * 100
                        unit = "%"
                        
                    # 取得資料日期 (以最後一筆為準)
                    date_val = hist.index[-1].strftime("%m/%d")
                    
                    self.market_data[category].append({
                        "name": name,
                        "ticker": ticker,
                        "price": round(last_close, 2),
                        "change": round(change_percent, 2),
                        "unit": unit,
                        "date": date_val
                    })
                    print(" [成功]")
                except Exception as e:
                    print(f" [失敗: {e}]")
                    
        return self.market_data

    def fetch_fred_macro_data(self):
        """抓取 FRED 總經數據"""
        print("\n[INFO] 開始抓取 FRED 美國總經數據...")
        
        # 定義 FRED Series
        series_info = {
            "UNRATE": {"name": "失業率", "unit": "%"},
            "CPIAUCSL": {"name": "通膨率 (CPI YoY)", "unit": "%", "calc_yoy": True},
            "FEDFUNDS": {"name": "基準利率", "unit": "%"}
        }
        
        for series_id, info in series_info.items():
            print(f"  > 抓取 {info['name']} ({series_id})...", end="")
            try:
                # 取得該數列的降序觀測值
                url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json&sort_order=desc&limit=15"
                response = requests.get(url, timeout=10)
                data = response.json()
                
                if "observations" not in data or not data["observations"]:
                    print(" [警告: 無資料]")
                    continue
                
                obs = data["observations"]
                
                # 過濾掉 "." 的無效資料
                valid_obs = [o for o in obs if o["value"] != "."]
                
                if not valid_obs:
                    continue
                    
                latest_obs = valid_obs[0]
                latest_value = float(latest_obs["value"])
                latest_date = latest_obs["date"] # YYYY-MM-DD
                
                formatted_date = datetime.strptime(latest_date, "%Y-%m-%d").strftime("%m/%d")
                
                if info.get("calc_yoy"):
                    # 這邊找一年前的數據 (往後算大約 12 個月的值)
                    # FRED 抓下來是 desc排序，所以 index 12 剛好是一年前
                    if len(valid_obs) >= 13:
                        year_ago_obs = valid_obs[12]
                        year_ago_value = float(year_ago_obs["value"])
                        yoy_change = ((latest_value - year_ago_value) / year_ago_value) * 100
                        val_to_store = yoy_change
                        change_from_prev = yoy_change - (((float(valid_obs[1]["value"]) - float(valid_obs[13]["value"])) / float(valid_obs[13]["value"])) * 100) # 上個月的YoY
                    else:
                        val_to_store = 0.0
                        change_from_prev = 0.0
                    
                    self.macro_data[series_id] = {
                        "name": info["name"],
                        "price": round(val_to_store, 2),
                        "change": round(change_from_prev, 2), # 變動率的變動
                        "date": formatted_date,
                        "unit": info["unit"]
                    }
                else:
                    # 一般的數值 (如失業率、基準利率)
                    prev_value = float(valid_obs[1]["value"]) if len(valid_obs) > 1 else latest_value
                    change = (latest_value - prev_value) # 差異 (bp 或 百分點差異)
                    
                    self.macro_data[series_id] = {
                        "name": info["name"],
                        "price": round(latest_value, 2),
                        "change": round(change, 2), # 百分點變動
                        "date": formatted_date,
                        "unit": info["unit"]
                    }
                print(f" [成功: {latest_date}]")
            except Exception as e:
                print(f" [失敗: {e}]")
                
        return self.macro_data

    def export_data(self):
        """匯出 JSON 與 Excel 報表"""
        # 確保目錄存在
        os.makedirs(os.path.join("outputs", "global_json"), exist_ok=True)
        os.makedirs(os.path.join("outputs", "global_xlsx"), exist_ok=True)
        
        # 整理統一的 JSON 結構
        output_payload = {
            "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data_date": self.date_str,
            "market_data": self.market_data,
            "macro_data": self.macro_data
        }
        
        json_path = os.path.join("outputs", "global_json", f"global_market_{self.date_str}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(output_payload, f, ensure_ascii=False, indent=4)
        print(f"\n[SUCCESS] 已匯出 JSON 至: {json_path}")
        
        # 匯出簡單的 Excel
        excel_path = os.path.join("outputs", "global_xlsx", f"global_market_{self.date_str}.xlsx")
        
        # 用 pandas 建立報表會更簡單
        writer = pd.ExcelWriter(excel_path, engine='openpyxl')
        
        # 先將 Market Data 展開
        market_rows = []
        for cat, assets in self.market_data.items():
            for a in assets:
                market_rows.append({
                    "Category": cat,
                    "Name": a["name"],
                    "Price": a["price"],
                    "Change": f"{a['change']}{a['unit']}",
                    "Date": a["date"]
                })
                
        if market_rows:
            df_mkt = pd.DataFrame(market_rows)
            df_mkt.to_excel(writer, sheet_name="Global Markets", index=False)
            
        macro_rows = []
        for sid, a in self.macro_data.items():
            macro_rows.append({
                "Indicator": a["name"],
                "Value": f"{a['price']}{a['unit']}",
                "Change (pt)": f"{a['change']}{a['unit']}",
                "Date": a["date"]
            })
            
        if macro_rows:
            df_macro = pd.DataFrame(macro_rows)
            df_macro.to_excel(writer, sheet_name="Macro Data", index=False)
            
        writer.close()
        print(f"[SUCCESS] 已匯出 Excel 至: {excel_path}")


def main():
    parser = argparse.ArgumentParser(description="全球市場與聯準會總經數據監控")
    parser.add_argument("--date", type=str, help="指定日期 YYYYMMDD，預設為最新交易日")
    args = parser.parse_args()
    
    # 使用 risk_monitor 中共用的取得交易日邏輯
    target_date = get_trading_date(args.date)
    
    print(f"=== 執行日期: {target_date} ===")
    monitor = GlobalMarketMonitor(target_date)
    monitor.fetch_yfinance_data()
    monitor.fetch_fred_macro_data()
    monitor.export_data()

if __name__ == "__main__":
    main()
