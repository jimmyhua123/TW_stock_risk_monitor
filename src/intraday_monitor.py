import os
import json
import time
import requests
from datetime import datetime
from tabulate import tabulate

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
    # TWSE MIS API allows multiple channels separated by '|'
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
        
        # Build dictionary for quick lookup
        current_data = {}
        for msg in msg_array:
            code = msg.get("c")
            if not code:
                continue
                
            # z: current price (if "-", use latest trade price or open or previous close)
            # y: yesterday close
            # v: accumulated volume
            z = msg.get("z", "-")
            y = msg.get("y", "-")
            v = msg.get("v", "0")
            
            # If there's no trade price yet (z is '-'), try to find an alternative indicating it's just opening without trades yet
            # Sometimes it's better to just show '-' or use 'y' if market closed.
            price = None
            try:
                if z != "-":
                    price = float(z)
                else:
                    b_prices = msg.get("b", "")
                    a_prices = msg.get("a", "")
                    if b_prices and b_prices != "-":
                        best_bid = b_prices.split("_")[0]
                        if best_bid and best_bid != "-":
                            price = float(best_bid)
                    elif a_prices and a_prices != "-":
                        best_ask = a_prices.split("_")[0]
                        if best_ask and best_ask != "-":
                            price = float(best_ask)
            except ValueError:
                pass
            
            prev_close = None
            try:
                if y != "-":
                    prev_close = float(y)
            except ValueError:
                pass
                
            change_pct = "-"
            if price is not None and prev_close is not None and prev_close > 0:
                change_pct_val = ((price - prev_close) / prev_close) * 100
                # color formatting based on change
                color_prefix = ""
                color_suffix = ""
                if change_pct_val > 0:
                    sign = "🔴 +"
                elif change_pct_val < 0:
                    sign = "🟢 "
                else:
                    sign = ""
                change_pct = f"{sign}{change_pct_val:.2f}%"
            elif price is None and prev_close is not None:
                # no trades yet
                change_pct = "0.00%"
            
            price_str = str(price) if price is not None else "-"
                
            current_data[code] = {
                "price": price_str,
                "change_pct": change_pct,
                "volume": v
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
            
            price = None
            prev = None
            try:
                price = float(z) if z != "-" else None
                prev = float(y) if y != "-" else None
            except ValueError:
                pass
            
            change_pct = "-"
            if price is not None and prev is not None and prev > 0:
                change_pct_val = ((price - prev) / prev) * 100
                sign = "🔴 +" if change_pct_val > 0 else "🟢 " if change_pct_val < 0 else ""
                change_pct = f"{sign}{change_pct_val:.2f}%"
            
            data["TWII"] = {
                "name": "加權指數",
                "price": str(price) if price is not None else "-",
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
