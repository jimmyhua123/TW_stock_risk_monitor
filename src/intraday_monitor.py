import os
import json
import time
import requests
from datetime import datetime
from tabulate import tabulate

def safe_float(val, default=None):
    if val is None or val == "-" or val == "":
        return default
    try:
        return float(str(val).replace(",", ""))
    except ValueError:
        return default

def load_watchlist(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("watchlist", [])
    except Exception as e:
        print(f"Error loading watchlist: {e}")
        return []

def fetch_intraday_data(watchlist):
    if not watchlist:
        return []

    # Prepare batch query for both TSE and OTC
    ex_ch_list = []
    for item in watchlist:
        code = item['code']
        ex_ch_list.append(f"tse_{code}.tw")
        ex_ch_list.append(f"otc_{code}.tw")
    
    ex_ch_str = "|".join(ex_ch_list)
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch={ex_ch_str}&json=1&delay=0"
    
    try:
        res = requests.get(url, headers={'Accept-Language':'zh-TW'}, timeout=10)
        res_json = res.json()
        
        msg_array = res_json.get("msgArray", [])
        
        current_data = {}
        for msg in msg_array:
            code = msg.get("c")
            if not code:
                continue
            
            # z: current price, y: yesterday close, v: accumulated volume
            # u: limit up price, w: limit down price
            z_val = msg.get("z", "-")
            y_val = msg.get("y", "-")
            v_val = msg.get("v", "0")
            u_val = msg.get("u", "-")
            w_val = msg.get("w", "-")
            
            price = safe_float(z_val)
            prev_close = safe_float(y_val)
            limit_up = safe_float(u_val)
            limit_down = safe_float(w_val)
            
            # If z is missing (common when locked at limit up/down with no trades yet)
            # fallback to best bid/ask
            if price is None or price <= 0:
                b_prices = msg.get("b", "")
                a_prices = msg.get("a", "")
                if b_prices and b_prices != "-":
                    price = safe_float(b_prices.split("_")[0])
                elif a_prices and a_prices != "-":
                    price = safe_float(a_prices.split("_")[0])
            
            # Avoid 0.0 price unless it's genuinely 0 (not possible for stocks)
            if price is not None and price <= 0:
                price = None

            # Skip placeholders that have no valid price/prev_close/volume
            if price is None and prev_close is None and v_val == "0":
                continue

            change_pct = "-"
            status_indicator = ""
            
            if price is not None and prev_close is not None and prev_close > 0:
                # Detect Limit Up/Down
                if limit_up and price >= limit_up:
                    status_indicator = " 🏆[漲停]"
                elif limit_down and price <= limit_down:
                    status_indicator = " 🧊[跌停]"
                
                change_pct_val = ((price - prev_close) / prev_close) * 100
                sign = "🔴 +" if change_pct_val > 0 else "🟢 " if change_pct_val < 0 else ""
                change_pct = f"{sign}{change_pct_val:.2f}%{status_indicator}"
            elif price is None and prev_close is not None:
                change_pct = "0.00%"

            price_str = f"{price:.2f}" if price is not None else "-"
            
            # Merging logic: Only update if we don't have this code or the new one is more "valid"
            # (i.e., has a real price/prev_close vs the previous placeholder)
            if code not in current_data or (price_str != "-" and current_data[code]["price"] == "-"):
                current_data[code] = {
                    "price": price_str,
                    "change_pct": change_pct,
                    "volume": v_val
                }
            
        return current_data
        
    except Exception as e:
        print(f"Error fetching data: {e}")
        return {}

def fetch_index_and_futures():
    data = {}
    
    # Fetch 加權指數 (TWII)
    try:
        url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_t00.tw&json=1&delay=0"
        res = requests.get(url, headers={'Accept-Language':'zh-TW'}, timeout=5)
        msg_array = res.json().get("msgArray", [])
        if msg_array:
            msg = msg_array[0]
            z = msg.get("z", "-")
            y = msg.get("y", "-")
            
            try:
                price = safe_float(z)
                prev = safe_float(y)
            except ValueError:
                pass
            
            change_pct = "-"
            if price is not None and prev is not None and prev > 0:
                change_pct_val = ((price - prev) / prev) * 100
                sign = "🔴 +" if change_pct_val > 0 else "🟢 " if change_pct_val < 0 else ""
                change_pct = f"{sign}{change_pct_val:.2f}%"
            
            data["TWII"] = {
                "name": "加權指數",
                "price": f"{price:.2f}" if price is not None else "-",
                "change_pct": change_pct,
                "volume": msg.get("v", "-")
            }
    except Exception as e:
        print(f"Error fetching TWII: {e}")
        
    # Fetch 台指近 (TXF)
    try:
        url = "https://mis.taifex.com.tw/futures/api/getQuoteList"
        payload = {'MarketType':'0', 'SymbolType':'F', 'KindID':'1', 'CID':'TXF', 'ExpireMonths':'', 'SymbolFormat':'0'}
        res = requests.post(url, json=payload, timeout=5)
        items = res.json().get('RtData', {}).get('QuoteList', [])
        
        # The first item is usually the near month
        if items:
            item = items[0]
            price = item.get('CLastPrice', '-')
            change_rate = item.get('CDiffRate', '-')
            
            change_pct = "-"
            if change_rate != "-":
                try:
                    change_pct_val = float(change_rate)
                    sign = "🔴 +" if change_pct_val > 0 else "🟢 " if change_pct_val < 0 else ""
                    change_pct = f"{sign}{change_pct_val:.2f}%"
                except ValueError:
                    pass
                
            data["TXF"] = {
                "name": "台指近",
                "price": str(price),
                "change_pct": change_pct,
                "volume": item.get('CTotalVolume', '-') or "-"
            }
    except Exception as e:
        print(f"Error fetching TXF: {e}")
        
    return data

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    watchlist_path = os.path.join(base_dir, "data", "config", "watchlist.json")
    
    print("Loading watchlist...")
    watchlist = load_watchlist(watchlist_path)
    if not watchlist:
        print("Watchlist empty or not found.")
        return
        
    print("Fetching intraday data...")
    market_data = fetch_intraday_data(watchlist)
    index_data = fetch_index_and_futures()
    
    now = datetime.now()
    date_str = now.strftime("%m%d")
    time_str = now.strftime("%H:%M:%S")
    
    notes_dir = os.path.join(base_dir, "docs", "notes", "看盤筆記")
    os.makedirs(notes_dir, exist_ok=True)
    
    md_filepath = os.path.join(notes_dir, f"{date_str}.md")
    
    # Prepare table
    headers = ["代號", "股名", "成交價", "漲跌幅%", "成交量"]
    table_data = []
    
    # Add index and futures first
    if "TWII" in index_data:
        d = index_data["TWII"]
        table_data.append(["t00.tw", d["name"], d["price"], d["change_pct"], d["volume"]])
    if "TXF" in index_data:
        d = index_data["TXF"]
        table_data.append(["TXF", d["name"], d["price"], d["change_pct"], d["volume"]])
        
    # Add a separator if index data exists
    if index_data:
        table_data.append(["---", "---", "---", "---", "---"])
    
    for item in watchlist:
        code = item["code"]
        name = item["name"]
        
        if code in market_data:
            data = market_data[code]
            table_data.append([code, name, data["price"], data["change_pct"], data["volume"]])
        else:
            table_data.append([code, name, "-", "-", "-"])
            
    table_str = tabulate(table_data, headers=headers, tablefmt="github")
    
    # Append to markdown
    output_block = f"\n\n### 🕒 盤中數據紀錄 ({time_str})\n\n{table_str}\n"
    
    with open(md_filepath, "a", encoding="utf-8") as f:
        f.write(output_block)
        
    print(f"Data appended to {md_filepath}")

if __name__ == "__main__":
    main()
