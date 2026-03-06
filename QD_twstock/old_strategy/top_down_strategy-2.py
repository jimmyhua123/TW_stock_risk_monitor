import sys
# 解決 Windows 終端機顯示特殊符號時的 UnicodeEncodeError (cp950) 問題
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np
import requests
import warnings
import logging
import datetime
import urllib.request
import json
import time
import re
from io import StringIO
import yfinance as yf

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def get_recent_trading_days(days=5):
    """取得最近 N 天的台股交易日格式 (排除週末)"""
    today = datetime.datetime.now()
    if today.hour < 15: # 下午 15:00 前視為抓取上一個交易日
        today -= datetime.timedelta(days=1)
        
    trading_days = []
    current_date = today
    while len(trading_days) < days:
        if current_date.weekday() < 5:  # 0-4 為週一至週五
            trading_days.append(current_date)
        current_date -= datetime.timedelta(days=1)
    
    return [d.strftime('%Y%m%d') for d in trading_days], [d.strftime('%Y/%m/%d') for d in trading_days], [(d.year-1911, d.month, d.day) for d in trading_days]

def macro_and_term_structure_filter(taiex_df, vix_term_df=None):
    """
    模組 1：總體經濟與期限結構過濾器
    - taiex_df: 大盤日 K 線的 DataFrame
    - vix_term_df: (可選) VIX 期貨報價 DataFrame
    """
    signals = {
        'High_Volatility_Warning': False,
        'ATR_Percentile': 0.0,
        'VIX_Contrarian_Buy': False
    }
    
    # 1. 計算真實波動幅度 (True Range) 與 14日滾動 ATR
    df = taiex_df.copy()
    if not df.empty and len(df) > 14:
        df['H-L'] = df['High'] - df['Low']
        df['H-PC'] = (df['High'] - df['Close'].shift(1)).abs()
        df['L-PC'] = (df['Low'] - df['Close'].shift(1)).abs()
        df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
        df['ATR_14'] = df['TR'].rolling(window=14).mean()
        
        if len(df) >= 252:
            # 計算過去 252 個交易日的 ATR 百分位數 (0~100)
            df['ATR_Percentile'] = df['ATR_14'].rolling(window=252).apply(
                lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100, raw=False
            )
            
            latest_percentile = df['ATR_Percentile'].iloc[-1]
            if not pd.isna(latest_percentile):
                signals['ATR_Percentile'] = round(latest_percentile, 2)
                
                # 當日 ATR 突破過去一年 90% 的水準，視為極端波動市況
                if latest_percentile > 90:
                    signals['High_Volatility_Warning'] = True

    # 2. VIX 期限結構過濾 (近月 vs 遠月)
    if vix_term_df is not None and not vix_term_df.empty and len(vix_term_df) >= 2:
        vix_term_df = vix_term_df.copy()
        # 計算價差比率: > 1 代表近月大於遠月 (逆價差，市場恐慌)
        # 假設欄位為 'Near_Month' 和 'Far_Month'
        if 'Near_Month' in vix_term_df.columns and 'Far_Month' in vix_term_df.columns:
            vix_term_df['Spread_Ratio'] = vix_term_df['Near_Month'] / vix_term_df['Far_Month']
            
            latest_ratio = vix_term_df['Spread_Ratio'].iloc[-1]
            prev_ratio = vix_term_df['Spread_Ratio'].iloc[-2]
            
            if pd.notna(latest_ratio) and pd.notna(prev_ratio):
                # 條件：呈現逆價差 (>1.0) 且開始收斂 (今天比昨天小) -> 恐慌情緒見頂反轉，為反向做多訊號
                if (latest_ratio > 1.0) and (latest_ratio < prev_ratio):
                    signals['VIX_Contrarian_Buy'] = True

    return signals

def fetch_taifex_institutional():
    """
    抓取台灣期交所 (TAIFEX) 每日三大法人期貨淨未平倉資料 (大臺指 TXF)
    """
    logging.info("拉取期交所三大法人期貨未平倉...")
    url = "https://www.taifex.com.tw/cht/3/futContractsDate"
    try:
        res = requests.get(url, timeout=10)
        res.encoding = 'utf-8'
        try:
            # 嘗試使用 pandas 直接解析 table
            tables = pd.read_html(StringIO(res.text))
            if len(tables) >= 3:
                df = tables[2] # 通常是第三個 table
                # 尋找「大臺指」(TXF) 的列
                txf_rows = df[df.iloc[:, 1].astype(str).str.contains('大臺指', na=False)]
                if not txf_rows.empty:
                    # 外資、投信、自營商的多空淨額通常在特定欄位，這裡用相對位置提取
                    # 表格結構：自營商(多,空,淨), 投信(多,空,淨), 外資(多,空,淨)
                    # 需要確認期交所最新的 column 索引，這裡進行保守取值
                    # 先找自營商(2,3,4, 5,6,7, 8,9,10, 11,12) 
                    # 未平倉餘額的淨額(多空淨額)：自營商(11), 投信(13), 外資(15)
                    # 注意：MultiIndex 或是 header 的欄位數可能有變，建議用正則或確切定位
                    
                    # 簡化爬蟲：直接搜尋 HTML 中的數字 (比較 robust)
                    pass # 若 read_html 取得格式複雜，改用正則或 BeautifulSoup
        except:
            pass
            
        # 替代方案：透過正則表達式快速抓取 TXF 外資、投信、自營商的「未平倉淨額」
        # 尋找 <th align="left"  class="12bk">大臺指</th> 後面的 td 內容
        match = re.search(r'>大\s*臺\s*指<.*?未平倉餘額.*?<td[^>]*>.*?</td>.*?<td[^>]*>.*?</td>.*?<td[^>]*>([^<]+)</td>.*?<td[^>]*>.*?</td>.*?<td[^>]*>.*?</td>.*?<td[^>]*>([^<]+)</td>.*?<td[^>]*>.*?</td>.*?<td[^>]*>.*?</td>.*?<td[^>]*>([^<]+)</td>', res.text, re.DOTALL)
        
        if match:
            # match.group(1): 自營商淨額, 2: 投信淨額, 3: 外資淨額
            dealer_oi = int(match.group(1).replace(',', '').strip())
            trust_oi = int(match.group(2).replace(',', '').strip())
            foreign_oi = int(match.group(3).replace(',', '').strip())
            return {
                'Foreign_OI': foreign_oi,
                'Trust_OI': trust_oi,
                'Dealer_OI': dealer_oi
            }
        else:
            logging.warning("期交所網頁解析失敗，使用備用全區塊比對")
            # 更寬鬆的正則
            blocks = re.findall(r'>大\s*臺\s*指<(.+?)</tr>', res.text, re.DOTALL)
            if blocks:
                tds = re.findall(r'<td[^>]*>([^<]*)</td>', blocks[0])
                if len(tds) >= 15:
                    dealer_oi = int(tds[10].replace(',', '').strip()) # 自營商未平倉淨額
                    trust_oi = int(tds[12].replace(',', '').strip())  # 投信未平倉淨額
                    foreign_oi = int(tds[14].replace(',', '').strip()) # 外資未平倉淨額
                    return {
                        'Foreign_OI': foreign_oi,
                        'Trust_OI': trust_oi,
                        'Dealer_OI': dealer_oi
                    }
    except Exception as e:
        logging.warning(f"無法取得期貨法人資料: {e}")
    
    return {'Foreign_OI': 0, 'Trust_OI': 0, 'Dealer_OI': 0}

def smart_money_futures_filter(futures_data):
    """
    模組 2：三大法人期貨籌碼動能過濾器
    """
    total_net_oi = futures_data['Foreign_OI'] + futures_data['Trust_OI'] + futures_data['Dealer_OI']
    
    if total_net_oi > 5000:
        signal = 'Bullish'
    elif total_net_oi < -5000:
        signal = 'Bearish'
    else:
        signal = 'Neutral'
        
    return {
        'Total_Net_OI': total_net_oi,
        'Signal': signal
    }

def calc_rsi(price_series, period=14):
    """計算 RSI 指標"""
    delta = price_series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def sector_rotation_lead_lag(lead_df, lag_df, lead_name="航運業", lag_name="半導體業"):
    """
    模組 3：產業傳遞熵與輪動領先指標
    """
    if len(lead_df) < 74 or len(lag_df) < 74:
        return {'Warning': '資料長度不足以計算 60 日 RSI 相關性', 'Lag_Watchlist_Triggered': False}
        
    # 1. 計算雙方 14日 RSI
    rsi_lead = calc_rsi(lead_df['Close'], period=14).fillna(50)
    rsi_lag = calc_rsi(lag_df['Close'], period=14).fillna(50)
    
    # 2. 計算過去 60 天 RSI 的滾動相關係數
    rolling_corr = rsi_lead.rolling(window=60).corr(rsi_lag)
    latest_corr = rolling_corr.iloc[-1]
    
    # 3. 判斷領先產業的動能熱度 (如: 最近 5 日均量 > 最近 20 日均量的 1.3 倍，且 RSI > 60)
    lead_vol_5ma = lead_df['Volume'].rolling(5).mean().iloc[-1]
    lead_vol_20ma = lead_df['Volume'].rolling(20).mean().iloc[-1]
    lead_momentum_strong = (lead_vol_5ma > 1.3 * lead_vol_20ma) and (rsi_lead.iloc[-1] > 60)
    
    # 4. 判斷是否將落後產業列入 Watchlist
    lag_watchlist_triggered = False
    if lead_momentum_strong and pd.notna(latest_corr) and latest_corr > 0.5:
        lag_watchlist_triggered = True
        
    return {
        'Lead_Sector': lead_name,
        'Lag_Sector': lag_name,
        'Latest_60d_Corr': round(latest_corr, 3) if pd.notna(latest_corr) else 0,
        'Lead_Momentum_Strong': lead_momentum_strong,
        'Lag_Watchlist_Triggered': lag_watchlist_triggered
    }

def fetch_industry_mapping():
    """取得上市櫃公司代號與產業類別的對應，並整理成 DataFrame"""
    logging.info("拉取上市櫃公司產業類別...")
    mapping = {}
    
    # 產業代碼對應名稱
    industry_names = {
        '01': '水泥工業', '02': '食品工業', '03': '塑膠工業', '04': '紡織纖維', '05': '電機機械',
        '06': '電器電纜', '07': '化學生技醫療', '08': '玻璃陶瓷', '09': '造紙工業', '10': '鋼鐵工業',
        '11': '橡膠工業', '12': '汽車工業', '13': '電子工業', '14': '建材營造', '15': '航運業',
        '16': '觀光餐旅', '17': '金融保險', '18': '貿易百貨', '19': '綜合', '20': '其他',
        '21': '化學工業', '22': '生技醫療業', '23': '油電燃氣業', '24': '半導體業', '25': '電腦及週邊設備業',
        '26': '光電業', '27': '通信網路業', '28': '電子零組件業', '29': '電子通路業', '30': '資訊服務業',
        '31': '其他電子業', '32': '文化創意業', '33': '農業科技業', '34': '電子商務業', '35': '綠能環保',
        '36': '數位雲端', '37': '運動休閒', '38': '居家生活', '80': '管理股票'
    }

    # 上市
    try:
        url_twse = 'https://openapi.twse.com.tw/v1/opendata/t187ap03_L'
        with urllib.request.urlopen(url_twse) as response:
            data = json.loads(response.read().decode('utf-8'))
            for row in data:
                code = row.get('公司代號')
                ind_code = row.get('產業別')
                if code and ind_code:
                    mapping[code] = {'市場': '上市', '產業': industry_names.get(ind_code, f'其他({ind_code})')}
    except Exception as e:
        logging.warning(f"取得上市產業別失敗: {e}")

    # 上櫃
    try:
        url_tpex = 'https://openapi.twse.com.tw/v1/opendata/t187ap03_O'
        with urllib.request.urlopen(url_tpex) as response:
            data = json.loads(response.read().decode('utf-8'))
            for row in data:
                code = row.get('公司代號')
                ind_code = row.get('產業別')
                if code and ind_code:
                    mapping[code] = {'市場': '上櫃', '產業': industry_names.get(ind_code, f'其他({ind_code})')}
    except Exception as e:
        logging.warning(f"取得上櫃產業別失敗: {e}")

    df_mapping = pd.DataFrame.from_dict(mapping, orient='index')
    return df_mapping

def fetch_institutional_3d():
    """取得近 3 個交易日外資與投信的買賣超數據 (合計)"""
    dates_str_twse, _, dates_tpex = get_recent_trading_days(3)
    
    foreign_net = {}
    trust_net = {}
    
    logging.info(f"拉取近三日法人買賣超 ({dates_str_twse[-1]} ~ {dates_str_twse[0]})...")
    
    # === 上市 (T86) ===
    for d in dates_str_twse:
        try:
            url = "https://www.twse.com.tw/fund/T86"
            res = requests.get(url, params={'response': 'json', 'date': d, 'selectType': 'ALLBUT0999'}, timeout=10)
            data = res.json()
            if data.get('stat') == 'OK' and 'data' in data:
                for row in data['data']:
                    code = row[0].strip()
                    # row[4] 為外陸資買賣超, row[10] 為投信買賣超
                    f_net = int(row[4].replace(',', '')) if row[4] else 0
                    t_net = int(row[10].replace(',', '')) if row[10] else 0
                    foreign_net[code] = foreign_net.get(code, 0) + f_net
                    trust_net[code] = trust_net.get(code, 0) + t_net
            time.sleep(1) # 避免 Request 過於頻繁
        except Exception as e:
            logging.warning(f"無法取得上市 {d} 法人資料: {e}")

    # === 上櫃 ===
    for y, m, d in dates_tpex:
        try:
            date_str = f"{y}/{m:02d}/{d:02d}"
            url = "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php"
            res = requests.get(url, params={'l': 'zh-tw', 'd': date_str, 'se': 'EW', 't': 'D'}, timeout=10)
            data = res.json()
            if 'aaData' in data:
                for row in data['aaData']:
                    code = row[0].strip()
                    # 上櫃法人對應欄位 (依 Tpex API, row[4]是外資淨, row[10]是投信淨, 或 row[7]/row[13])
                    # 此處取最穩定的外資及陸資買賣超(不含外資自營商) -> row[4] / 投信 -> row[10]  (有些日期可能微調)
                    try:
                        f_net = int(str(row[4]).replace(',', ''))
                        t_net = int(str(row[10]).replace(',', ''))
                        foreign_net[code] = foreign_net.get(code, 0) + f_net
                        trust_net[code] = trust_net.get(code, 0) + t_net
                    except:
                        pass
            elif 'tables' in data and len(data['tables']) > 0:
                 # 新版上櫃 API 格式
                 for row in data['tables'][0]['data']:
                    code = row[0].strip()
                    try:
                        f_net = int(str(row[4]).replace(',', ''))
                        t_net = int(str(row[10]).replace(',', ''))
                        foreign_net[code] = foreign_net.get(code, 0) + f_net
                        trust_net[code] = trust_net.get(code, 0) + t_net
                    except:
                        pass
            time.sleep(1)
        except Exception as e:
            logging.warning(f"無法取得上櫃 {date_str} 法人資料: {e}")

    # 轉換成 張數
    foreign_3d = {k: v / 1000 for k, v in foreign_net.items()}
    trust_3d = {k: v / 1000 for k, v in trust_net.items()}
    
    df = pd.DataFrame({'foreign_buy_3d': foreign_3d, 'trust_buy_3d': trust_3d})
    return df

def fetch_sector_daily_trading(target_date_str):
    """階段一極度粗篩：透過官方或替代方式計算當日產業強弱 (取代原本抓取所有個股的寫法)"""
    logging.info(f"階段一：獲取市場各產業資金流向 (基準日: {target_date_str})")
    
    # 策略需求：抓取「上市與上櫃」之類股日成交資訊
    # 由於歷史資料抓取容易被擋，實務上最穩定的「快速估算」方式為利用 yfinance 抓取我們已經 mapping 好的個股，
    # 「但只抓最近 5 天資料，且只抓 Close, Open, Volume」，不計算複雜指標。
    # 這裡我們保留 yfinance 的寫法但大幅縮減 period="5d" 以達成極速粗篩，
    # 或是直接呼叫官方 API (若可用)。
    # 為確證符合「不需要先取得所有股票歷史資料」之要求，此處可選擇抓取大盤類股指數 (^TW01, ^TW13 等)。
    # 不過為了能準確計算「收紅比例」，我們採用「極輕量個股切片」：只抓 1 天，不計算均線。
    pass
    
def fetch_market_data(mapping_df, max_date_str, target_industries=None):
    """階段二技術面中篩：利用 yfinance 批次取得指定產業個股近 80 日的技術面資料"""
    yf_tickers = []
    ticker_mapping = {}
    
    for code, row in mapping_df.iterrows():
        # 如果有指定產業，則只抓取該產業內的股票
        if target_industries and row['產業'] not in target_industries:
            continue
            
        if row['市場'] == '上市':
            yf_ticker = f"{code}.TW"
        else:
            yf_ticker = f"{code}.TWO"
        yf_tickers.append(yf_ticker)
        ticker_mapping[yf_ticker] = code
        
    logging.info(f"階段二：透過 yfinance 獲取目標產業 ({len(yf_tickers)} 檔) 近 80 日技術面資料...")
    """取得近 3 個交易日外資與投信的買賣超數據 (合計)"""
    dates_str_twse, _, dates_tpex = get_recent_trading_days(3)
    
    foreign_net = {}
    trust_net = {}
    
    logging.info(f"拉取近三日法人買賣超 ({dates_str_twse[-1]} ~ {dates_str_twse[0]})...")
    
    # === 上市 (T86) ===
    for d in dates_str_twse:
        try:
            url = "https://www.twse.com.tw/fund/T86"
            res = requests.get(url, params={'response': 'json', 'date': d, 'selectType': 'ALLBUT0999'}, timeout=10)
            data = res.json()
            if data.get('stat') == 'OK' and 'data' in data:
                for row in data['data']:
                    code = row[0].strip()
                    # row[4] 為外陸資買賣超, row[10] 為投信買賣超
                    f_net = int(row[4].replace(',', '')) if row[4] else 0
                    t_net = int(row[10].replace(',', '')) if row[10] else 0
                    foreign_net[code] = foreign_net.get(code, 0) + f_net
                    trust_net[code] = trust_net.get(code, 0) + t_net
            time.sleep(1) # 避免 Request 過於頻繁
        except Exception as e:
            logging.warning(f"無法取得上市 {d} 法人資料: {e}")

    # === 上櫃 ===
    for y, m, d in dates_tpex:
        try:
            date_str = f"{y}/{m:02d}/{d:02d}"
            url = "https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php"
            res = requests.get(url, params={'l': 'zh-tw', 'd': date_str, 'se': 'EW', 't': 'D'}, timeout=10)
            data = res.json()
            if 'aaData' in data:
                for row in data['aaData']:
                    code = row[0].strip()
                    # 上櫃法人對應欄位 (依 Tpex API, row[4]是外資淨, row[10]是投信淨, 或 row[7]/row[13])
                    # 此處取最穩定的外資及陸資買賣超(不含外資自營商) -> row[4] / 投信 -> row[10]  (有些日期可能微調)
                    try:
                        f_net = int(str(row[4]).replace(',', ''))
                        t_net = int(str(row[10]).replace(',', ''))
                        foreign_net[code] = foreign_net.get(code, 0) + f_net
                        trust_net[code] = trust_net.get(code, 0) + t_net
                    except:
                        pass
            elif 'tables' in data and len(data['tables']) > 0:
                 # 新版上櫃 API 格式
                 for row in data['tables'][0]['data']:
                    code = row[0].strip()
                    try:
                        f_net = int(str(row[4]).replace(',', ''))
                        t_net = int(str(row[10]).replace(',', ''))
                        foreign_net[code] = foreign_net.get(code, 0) + f_net
                        trust_net[code] = trust_net.get(code, 0) + t_net
                    except:
                        pass
            time.sleep(1)
        except Exception as e:
            logging.warning(f"無法取得上櫃 {date_str} 法人資料: {e}")

    # 轉換成 張數
    foreign_3d = {k: v / 1000 for k, v in foreign_net.items()}
    trust_3d = {k: v / 1000 for k, v in trust_net.items()}
    
    df = pd.DataFrame({'foreign_buy_3d': foreign_3d, 'trust_buy_3d': trust_3d})
    return df

def fetch_market_data(mapping_df, max_date_str, target_industries=None):
    """階段二技術面中篩：利用 yfinance 批次取得指定產業個股近 80 日的技術面資料"""
    # 組合 YF 格式代號
    yf_tickers = []
    ticker_mapping = {} # yf -> twse/tpex  (e.g., '2330.TW' -> '2330')
    
    for code, row in mapping_df.iterrows():
        # 如果有指定產業，則只抓取該產業內的股票
        if target_industries is not None and row['產業'] not in target_industries:
            continue
            
        if row['市場'] == '上市':
            yf_ticker = f"{code}.TW"
        else:
            yf_ticker = f"{code}.TWO"
        yf_tickers.append(yf_ticker)
        ticker_mapping[yf_ticker] = code
        
        
    logging.info(f"階段二：透過 yfinance 獲取目標產業 ({len(yf_tickers)} 檔) 歷史價量資料 (約需 5~10 秒)...")
    
    # 將獲取天數維持 80 天，以保證 60 日 RSI 計算與 MA 準確
    data = yf.download(yf_tickers, period="80d", group_by='ticker', threads=True)
    
    # 將 target_date_str (YYYYMMDD) 轉為 yfinance 可接受的字串 (YYYY-MM-DD)
    max_date_yf_format = f"{max_date_str[:4]}-{max_date_str[4:6]}-{max_date_str[6:]}"
    
    results = {}
    valid_dates_set = set()
    
    for ticker in yf_tickers:
        try:
            if ticker not in data.columns.levels[0]:
                continue
                
            df_stock = data[ticker].dropna(subset=['Close', 'Volume'])
            # 確保擷取的價量資料不超過盤中最新交易日 (需與 T86 籌碼日同步)
            df_stock = df_stock.loc[:max_date_yf_format]
            
            if len(df_stock) < 20: 
                continue
            
            latest_date = df_stock.index[-1]
            valid_dates_set.add(latest_date)
            
            close = df_stock['Close'].values.flatten()
            volume = df_stock['Volume'].values.flatten()
            open_p = df_stock['Open'].values.flatten()
            high_p = df_stock['High'].values.flatten()
            low_p = df_stock['Low'].values.flatten()
            
            # 計算 14 日 ATR
            if len(close) > 1:
                tr1 = high_p[1:] - low_p[1:]
                tr2 = np.abs(high_p[1:] - close[:-1])
                tr3 = np.abs(low_p[1:] - close[:-1])
                tr = np.maximum.reduce([tr1, tr2, tr3])
                atr14 = np.mean(tr[-14:]) if len(tr) >= 14 else np.mean(tr)
            else:
                atr14 = 0
                
            # 計算區間 20 日報酬率 (RS 計算基礎)
            rs_20d = (close[-1] / close[-21]) - 1 if len(close) >= 21 else 0
            
            results[ticker_mapping[ticker]] = {
                'latest_close': close[-1],
                'latest_open': open_p[-1],
                'latest_volume': volume[-1],
                'atr14': atr14,
                'rs_20d': rs_20d,
                # 均線
                'ma5': np.mean(close[-5:]),
                'ma20': np.mean(close[-20:]),
                # 成交額 (粗略以收盤價 * 成交量)
                'latest_vol_amount': volume[-1] * close[-1],
                'vol_amount_1d': volume[-1] * close[-1],
                'vol_amount_2d': volume[-2] * close[-2],
                'vol_amount_3d': volume[-3] * close[-3],
                'vol_amount_4d': volume[-4] * close[-4],
                'vol_amount_5d': volume[-5] * close[-5],
                # 5日均量
                'avg_vol_amount_5d': np.mean(volume[-5:] * close[-5:])
            }
        except:
            pass
            
    if not results:
        return pd.DataFrame()
        
    df_market = pd.DataFrame.from_dict(results, orient='index')
    if valid_dates_set:
        latest = sorted(list(valid_dates_set))[-1]
        logging.info(f"成功獲取資料，以最新交易日為基準: {latest.strftime('%Y-%m-%d')}")
        
    return df_market

def main():
    logging.info("開始執行 Top-Down 策略 (輕量化 API 版)...")
    
    # 1. 抓取產業分類與對應表
    df_industry = fetch_industry_mapping()
    if df_industry.empty:
        logging.error("無法取得產業分類表，程式結束")
        return
        
    # 決定近期的盤後基準日 (避免盤中擷取到今日不完整的籌碼和價格)
    recent_days_str, _, _ = get_recent_trading_days(1)
    target_date_str = recent_days_str[0]
        
    # 2. 抓取大盤 (TAIEX) 多空濾網與總經波動率警示
    logging.info("獲取大盤加權指數(^TWII)與VIX資料以判定 Market Regime...")
    # 為了計算 252 日 ATR 分位數，需要拉 300 天資料
    taiex_data = yf.download("^TWII", period="300d", progress=False)
    
    # 取近三個月與近一個月的 VIX 作為期限結構替代
    vix_data = yf.download(["^VIX", "^VIX3M"], period="14d", progress=False)
    vix_term_df = pd.DataFrame()
    if not vix_data.empty and '^VIX' in vix_data.columns.levels[1] and '^VIX3M' in vix_data.columns.levels[1]:
        # yfinance multi-index: ('Close', '^VIX')
        vix_term_df['Near_Month'] = vix_data['Close']['^VIX']
        vix_term_df['Far_Month'] = vix_data['Close']['^VIX3M']
        
    macro_signals = macro_and_term_structure_filter(taiex_data, vix_term_df)
    
    if taiex_data.empty:
        logging.warning("無法取得大盤資料，預設為多頭模式")
        market_regime = 'bull'
        taiex_rs_20d = 0
    else:
        # 只取 taiex 原本計算 MA 需要的部分長度即可，不影響後續
        t_close_series = taiex_data['Close']
        if isinstance(t_close_series, pd.DataFrame):
             t_close = t_close_series.iloc[:, 0].values.flatten()
        else:
             t_close = t_close_series.values.flatten()
             
        t_ma20 = np.mean(t_close[-20:])
        t_ma60 = np.mean(t_close[-60:]) if len(t_close) >= 60 else t_ma20
        t_ma20_yest = np.mean(t_close[-21:-1]) if len(t_close) >= 21 else t_ma20
        taiex_rs_20d = (t_close[-1] / t_close[-21]) - 1 if len(t_close) >= 21 else 0
        
        if t_close[-1] > t_ma20 and t_ma20 > t_ma60 and t_ma20 > t_ma20_yest:
            market_regime = 'bull'
        else:
            market_regime = 'bear'
            
        logging.info(f"大盤判定: {'全面偏多' if market_regime == 'bull' else '警戒/空頭'} (收盤:{t_close[-1]:.0f}, 20MA:{t_ma20:.0f}, 60MA:{t_ma60:.0f})")
        
        # 覆寫 Market Regime (總經與期限過濾器)
        if macro_signals['High_Volatility_Warning']:
            market_regime = 'bear'
            logging.warning(f"⚠️ 系統偵測大盤 ATR(波動率) 位於過去一年 {macro_signals['ATR_Percentile']}% 高點，強制進入防禦模式！")
        if macro_signals['VIX_Contrarian_Buy']:
            logging.info("💡【VIX反向作多訊號】期貨期限結構呈現逆價差收斂，市場恐慌極值可能已過，適合佈局超跌錯殺股！")

    # 3. 階段一：極度粗篩 (全市場產業資金流向與漲跌比例)
    # 優化作法：原先是抓取 80天全市場，現在改為只獲取全市場近 5 天的價量切片資料，
    # 速度極快，不會造成 yfinance 卡頓。
    logging.info("階段一：計算全市場產業資金流向及收紅比例...")
    
    yf_all_tickers = [f"{code}.TW" if row['市場'] == '上市' else f"{code}.TWO" for code, row in df_industry.iterrows()]
    ticker_to_code = {f"{c}.TW": c for c in df_industry[df_industry['市場'] == '上市'].index}
    ticker_to_code.update({f"{c}.TWO": c for c in df_industry[df_industry['市場'] == '上櫃'].index})
    
    # 極度粗篩：只抓 5 天，算出各個股 5 日成交額與今日收盤狀態
    quick_data = yf.download(yf_all_tickers, period="5d", group_by='ticker', threads=True, progress=False)
    
    quick_results = []
    max_date_yf_format = f"{target_date_str[:4]}-{target_date_str[4:6]}-{target_date_str[6:]}"
    market_red_count = 0
    market_total_count = 0
    
    for ticker in yf_all_tickers:
        try:
            if ticker not in quick_data.columns.levels[0]: continue
            df_quick = quick_data[ticker].dropna(subset=['Close', 'Volume']).loc[:max_date_yf_format]
            if len(df_quick) == 0: continue
            
            close = df_quick['Close'].values
            open_p = df_quick['Open'].values
            volume = df_quick['Volume'].values
            
            # 今日成交額 (收盤 * 量)
            vol_amt_1d = close[-1] * volume[-1]
            avg_5d_amt = np.mean(close[-5:] * volume[-5:]) if len(close) >= 5 else vol_amt_1d
            is_red = close[-1] > open_p[-1]
            
            if is_red: market_red_count += 1
            market_total_count += 1
            
            code = ticker_to_code[ticker]
            quick_results.append({
                'Code': code,
                '產業': df_industry.loc[code, '產業'],
                'vol_amt_1d': vol_amt_1d,
                'avg_5d_amt': avg_5d_amt,
                'is_red': is_red
            })
        except:
            pass
            
    df_quick_all = pd.DataFrame(quick_results)
    
    # 計算產業資金比與增長率
    industry_1d = df_quick_all.groupby('產業')['vol_amt_1d'].sum()
    industry_5d = df_quick_all.groupby('產業')['avg_5d_amt'].sum()
    
    market_1d = industry_1d.sum()
    market_5d = industry_5d.sum()
    
    today_ratio = industry_1d / market_1d
    avg_5d_ratio = industry_5d / market_5d
    
    inflow_growth = (today_ratio - avg_5d_ratio) / avg_5d_ratio.replace(0, np.nan)
    inflow_growth = inflow_growth.fillna(0)
    
    # 計算收紅比例
    red_ratio = df_quick_all.groupby('產業')['is_red'].mean()
    market_red_ratio = market_red_count / max(1, market_total_count)
    logging.info(f"今日大盤整體收紅比例基準為: {market_red_ratio:.2%}")
    
    strong_categories = red_ratio[red_ratio > market_red_ratio].index
    valid_growth = inflow_growth.loc[inflow_growth.index.isin(strong_categories)]
    top_5_industries = valid_growth.sort_values(ascending=False).head(5).index.tolist()
    
    weak_categories = red_ratio[red_ratio < market_red_ratio].index
    valid_decline = inflow_growth.loc[inflow_growth.index.isin(weak_categories)]
    bottom_5_industries = valid_decline.sort_values(ascending=True).head(5).index.tolist()
    
    # 4. 階段二：技術面中篩 (只針對 Top 5 強弱產業)
    target_sectors = top_5_industries + bottom_5_industries
    df_market = fetch_market_data(df_industry, target_date_str, target_industries=target_sectors)
    
    if df_market.empty:
        logging.error("無法取得目標產業的技術面資料，程式結束")
        return
        
    # 計算相對大盤強度 (區間 RS)
    if 'rs_20d' in df_market.columns:
        df_market['rs_20d'] = (df_market['rs_20d'] - taiex_rs_20d) * 100
        
    # 4. 抓取法人 (現貨與期貨)
    df_inst = fetch_institutional_3d()
    taifex_oi = fetch_taifex_institutional()
    smart_money = smart_money_futures_filter(taifex_oi)
    logging.info(f"期貨三大法人淨未平倉: {smart_money['Total_Net_OI']} 口 ({smart_money['Signal']})")
    
    # [預留] 5. 抓取融資借券 (目前給定 0)
    # df_margin = fetch_margin_data()
    # 這裡我們手動初始化欄位模擬未來的實作
    
    # 6. 資料合併
    df_all = df_market.join(df_industry).join(df_inst).fillna(0)
    df_all['margin_dec'] = False # 融資是否減少預設False
    df_all['sbl_dec'] = False # 借券是否減少預設False
    
    # ==============================================================
    # (已經在上方移往 Stage 1)
    # ==============================================================

    # ==============================================================
    # 第二步：產業內部「個股篩選」
    # ==============================================================
    logging.info("進行 20MA、籌碼及流動性過濾...")
    
    # 條件 1. 股價趨勢：今日收盤價 > 20MA 且 5MA > 20MA
    # 5. 新增：改用標準化 ATR 動態乖離率控制 (收盤價 - 20MA <= 2 * ATR)
    cond_ma20 = (df_all['latest_close'] > df_all['ma20']) & \
                (df_all['ma5'] > df_all['ma20']) & \
                ((df_all['latest_close'] - df_all['ma20']) <= 2 * df_all['atr14'])
                
    # 弱勢：今日 < 20MA 且 5MA < 20MA
    cond_ma20_weak = (df_all['latest_close'] < df_all['ma20']) & \
                     (df_all['ma5'] < df_all['ma20'])
    
    # 條件 2. 籌碼過濾：結合期貨 Smart Money 訊號動態調整現貨門檻
    if smart_money['Signal'] == 'Bullish':
        # 期貨大買，放寬現貨法人的過濾條件
        cond_chip = (df_all['foreign_buy_3d'] > -1000) & (df_all['trust_buy_3d'] > -1000)
        cond_chip_weak = (df_all['foreign_buy_3d'] < 1000) & (df_all['trust_buy_3d'] < 1000) & \
                         ((df_all['foreign_buy_3d'] + df_all['trust_buy_3d']) < 0)
    elif smart_money['Signal'] == 'Bearish':
        # 期貨大空，嚴格要求現貨不可賣超
        cond_chip = (df_all['foreign_buy_3d'] > 0) & (df_all['trust_buy_3d'] > 0)
        cond_chip_weak = (df_all['foreign_buy_3d'] < 0) & (df_all['trust_buy_3d'] < 0)
    else:
        # Neutral: 原本的設定
        cond_chip = (df_all['foreign_buy_3d'] > -500) & (df_all['trust_buy_3d'] > -500) & \
                    ((df_all['foreign_buy_3d'] + df_all['trust_buy_3d']) > 0)
        cond_chip_weak = (df_all['foreign_buy_3d'] < 500) & (df_all['trust_buy_3d'] < 500) & \
                         ((df_all['foreign_buy_3d'] + df_all['trust_buy_3d']) < 0)
    
    # 條件 3. 流動性過濾：均測量 > 5000萬, 今日大於 1.3倍 (適應中大型股)
    cond_liquidity = (df_all['avg_vol_amount_5d'] > 50_000_000) & \
                     (df_all['latest_vol_amount'] > df_all['avg_vol_amount_5d'] * 1.3)
    
    # 條件 4. 產業
    cond_industry = df_all['產業'].isin(top_5_industries)
    cond_industry_weak = df_all['產業'].isin(bottom_5_industries)
    
    # 綜合運算 (已不需要再加入法人期貨過濾，因為先前的 DataFrame 只包含了目標產業)
    filter_cond = cond_industry & cond_ma20 & cond_liquidity
    filter_cond_weak = cond_industry_weak & cond_ma20_weak & cond_liquidity
    
    final_stocks = df_all[filter_cond].copy()
    final_weak_stocks = df_all[filter_cond_weak].copy()
    
    # 若大盤處於警戒/空頭模式，強制將「做多標的」的輸出數量上限縮減 50% (每產業只取前 2 名)
    if market_regime == 'bear':
        logging.info("大盤處於警戒/空頭模式，啟動防禦機制：強制縮減做多名單上限 (每產業取前 2 名)")
        final_stocks = final_stocks.sort_values(['產業', 'rs_20d'], ascending=[True, False])
        final_stocks = final_stocks.groupby('產業').head(2)
    
    # ==============================================================
    # 6. 新增：籌碼與基本面精篩 (高成本 API 留到最後)
    # 說明：因為針對全市場 1700 檔股票呼叫 yfinance.info 會耗時過久(API限制)，
    # 因此我們將這個濾網加在「第二步過濾完成後的少量名單」上，保持極致的輕量化與速度。
    # 同時在這裡呼叫 fetch_institutional_3d 的資料，避免抓取無用個股的籌碼
    # ==============================================================
    logging.info(f"階段三：針對最後 {len(final_stocks)} 檔強勢股與 {len(final_weak_stocks)} 檔弱勢股進行籌碼與基本面(YoY)精篩...")
    
    # 只針對精篩出的名單去取得外資投信買賣超
    # 我們可以利用原先的 fetch_institutional_3d()，但這個函數目前是抓全市場
    # 我們仍利用現有全市場的籌碼 df_inst，因為它是由證交所 CSV 快速組成的，速度夠快
    # （我們將過濾條件移到這裡）
    
    def apply_chip_and_yoy_filter(df, is_weak=False):
        if len(df) == 0:
            return df
            
        pass_mask = []
        for code in df.index:
            try:
                # 1. 檢驗籌碼條件
                f_buy = df.loc[code, 'foreign_buy_3d'] if 'foreign_buy_3d' in df.columns else 0
                t_buy = df.loc[code, 'trust_buy_3d'] if 'trust_buy_3d' in df.columns else 0
                
                if smart_money['Signal'] == 'Bullish':
                    chip_pass = (f_buy > -1000) and (t_buy > -1000)
                    chip_weak_pass = (f_buy < 1000) and (t_buy < 1000) and ((f_buy + t_buy) < 0)
                elif smart_money['Signal'] == 'Bearish':
                    chip_pass = (f_buy > 0) and (t_buy > 0)
                    chip_weak_pass = (f_buy < 0) and (t_buy < 0)
                else:
                    chip_pass = (f_buy > -500) and (t_buy > -500) and ((f_buy + t_buy) > 0)
                    chip_weak_pass = (f_buy < 500) and (t_buy < 500) and ((f_buy + t_buy) < 0)
                    
                if not (chip_weak_pass if is_weak else chip_pass):
                    pass_mask.append(False)
                    continue
                    
                # 2. 檢驗營收年增率 (只要非衰退就放行)
                market_type = df_industry.loc[code, '市場'] if code in df_industry.index else '上市'
                yf_ticker = f"{code}.TW" if market_type == '上市' else f"{code}.TWO"
                
                info = yf.Ticker(yf_ticker).info
                rev_growth = info.get('revenueGrowth', 0)
                
                if is_weak:
                    pass_mask.append(True) # 弱勢股不測營收
                else:
                    pass_mask.append(rev_growth is None or rev_growth > 0)
                    
            except Exception as e:
                pass_mask.append(True) # 例外則放行
                
        return df[pass_mask]

    final_stocks = apply_chip_and_yoy_filter(final_stocks, is_weak=False)
    final_weak_stocks = apply_chip_and_yoy_filter(final_weak_stocks, is_weak=True)
    
    # ==============================================================
    # 第三步：資料格式整理與終端輸出與存檔
    # ==============================================================
    
    import os
    if not os.path.exists('result'):
        os.makedirs('result')
        
    latest_date_str = target_date_str
    # latest_date_str = datetime.datetime.now().strftime('%Y%m%d')
    output_file = f"result/{latest_date_str}_top_down.md"
    
    output_lines = []
    output_lines.append(f"# Top-Down 策略選股報告 ({latest_date_str})\n")
    
    output_lines.append(f"## 【第一步(A)：強勢資金流入產業 (Top 5)】")
    if macro_signals['ATR_Percentile'] > 0:
        macro_str = f"📊 大盤波動率(ATR)位於近一年 {macro_signals['ATR_Percentile']}% 分位"
        output_lines.append(f"> {macro_str}")
        print(f"\n{macro_str}")
    if macro_signals['VIX_Contrarian_Buy']:
        vix_str = "💡 【VIX反向作多訊號】期貨期限結構呈現逆價差收斂，恐慌情緒見頂！"
        output_lines.append(f"> {vix_str}")
        print(vix_str)
        
    oi_str = f"🏦 期貨三大法人動能: {smart_money['Signal']} (淨未平倉 {smart_money['Total_Net_OI']} 口)"
    output_lines.append(f"> {oi_str}\n")
    print(oi_str)
    
    print("\n" + "=" * 55)
    print("【第一步(A)：強勢資金流入產業 (Top 5)】")
    for ind in top_5_industries:
        line = f"- 產業: **{ind}** | 今日資金佔比: {today_ratio.get(ind, 0):.2%} | 資金流入增長率: {inflow_growth.get(ind, 0):.1%}"
        output_lines.append(line)
        print(f"  ● 產業: {ind:<8} | 今日資金佔比: {today_ratio.get(ind, 0):.2%} | 資金流入增長率: {inflow_growth.get(ind, 0):.1%}")
    output_lines.append("")
    
    # 執行模組 3: 產業傳遞熵與輪動 (如果航運業在強勢名單中，檢查半導體)
    if "航運業" in top_5_industries:
        try:
            # 重建航運與半導體的簡易歷史指數 (使用 yfinance 抓回來的 df_market 原始資料)
            # 因為 df_market 只存當天最新值，我們需要重新拿 data 來重組產業 K 線
            # 這裡簡單抓前 80 天
            pass # (簡化處理見下方實作)
            
            # 使用我們下載的 yfinance data 重組產業指數
            ship_tickers = [yf_ticker for code, yf_ticker in ticker_mapping.items() if df_mapping.loc[code, '產業'] == '航運業']
            semi_tickers = [yf_ticker for code, yf_ticker in ticker_mapping.items() if df_mapping.loc[code, '產業'] == '半導體業']
            
            if 'df_market' in locals() and not df_market.empty:
                # 重新拉取 df_market 的歷史資料供模組 3 運算
                ship_close = df_market.loc[df_market.index.isin(ship_tickers)]['latest_close']
                ship_df = pd.DataFrame({'Close': ship_close, 'Volume': df_market.loc[df_market.index.isin(ship_tickers)]['latest_volume']})
                
                rot_data = yf.download(ship_tickers + semi_tickers, period="80d", group_by='ticker', threads=True, progress=False)
                ship_close_hist = rot_data.loc[:, (slice(None), ship_tickers)]['Close'].mean(axis=1) if len(ship_tickers) > 0 else pd.Series()
                ship_vol_hist = rot_data.loc[:, (slice(None), ship_tickers)]['Volume'].sum(axis=1) if len(ship_tickers) > 0 else pd.Series()
                ship_df_hist = pd.DataFrame({'Close': ship_close_hist, 'Volume': ship_vol_hist}).dropna()
                
                semi_close_hist = rot_data.loc[:, (slice(None), semi_tickers)]['Close'].mean(axis=1) if len(semi_tickers) > 0 else pd.Series()
                semi_vol_hist = rot_data.loc[:, (slice(None), semi_tickers)]['Volume'].sum(axis=1) if len(semi_tickers) > 0 else pd.Series()
                semi_df_hist = pd.DataFrame({'Close': semi_close_hist, 'Volume': semi_vol_hist}).dropna()
                
                if len(ship_df_hist) >= 74 and len(semi_df_hist) >= 74:
                    rotation_res = sector_rotation_lead_lag(ship_df_hist, semi_df_hist)
                
                    if rotation_res.get('Lag_Watchlist_Triggered'):
                        rot_msg = f"💡 【產業領先指標觸發】: 航運業爆量且與半導體業正相關 ({rotation_res['Latest_60d_Corr']})，已自動將半導體潛力股納入關注！"
                        output_lines.append(f"> {rot_msg}\n")
                        print(f"\n{rot_msg}")
                        # 強制將半導體業塞入前排觀察名單
                        if "半導體業" not in top_5_industries:
                            top_5_industries.append("半導體業")
        except Exception as e:
            logging.warning(f"產業輪動計算失敗: {e}")
    
    tech_industries = {"半導體業", "電子零組件業", "電腦及週邊設備業", "光電業", "電子通路業", "通信網路業", "資訊服務業", "其他電子業"}
    tech_count = sum(1 for ind in top_5_industries if ind in tech_industries)
    if tech_count >= 3:
        risk_msg = "⚠️ 【總經風險預警】：目前 Top 5 資金流入產業高度集中於科技類股。此結構對「美國 10 年期公債殖利率 (US10Y)」及「美元兌新台幣 (USD/TWD)」極度敏感。若近期新台幣出現急貶趨勢，需嚴格防範外資無差別提款導致的流動性回撤風險。"
        output_lines.append(f"> {risk_msg}\n\n")
        print(f"\n{risk_msg}")
        
    output_lines.append("## 【第一步(B)：弱勢資金流出產業 (Top 5)】")
    print("-" * 55)
    print("【第一步(B)：弱勢資金流出產業 (Top 5)】")
    for ind in bottom_5_industries:
        line = f"- 產業: **{ind}** | 今日資金佔比: {today_ratio.get(ind, 0):.2%} | 資金流入增長率: {inflow_growth.get(ind, 0):.1%}"
        output_lines.append(line)
        print(f"  ● 產業: {ind:<8} | 今日資金佔比: {today_ratio.get(ind, 0):.2%} | 資金流入增長率: {inflow_growth.get(ind, 0):.1%}")
    print("=" * 55)
    output_lines.append("")
    
    def format_and_print_result(df, title, is_markdown=False):
        print(f"\n【{title}】")
        if is_markdown:
            output_lines.append(f"## 【{title}】\n")
            
        if len(df) > 0:
            df_target = pd.DataFrame(index=df.index)
            df_target.index.name = '股票代號'
            df_target['產業別'] = df['產業']
            df_target['今日收盤價'] = df['latest_close'].round(2)
            
            # 報表擴充欄位: 資金流入倍數、區間RS強度
            df_target['資金流入倍數'] = (df['vol_amount_1d'] / df['avg_vol_amount_5d']).round(2)
            df_target['區間 RS 強度(%)'] = df['rs_20d'].round(1)
            
            df_target['今日成交額(萬)'] = (df['latest_vol_amount'] / 10000).astype(int)
            df_target['5日均量(萬)'] = (df['avg_vol_amount_5d'] / 10000).astype(int)
            df_target['近3日外資(張)'] = df['foreign_buy_3d'].round(0).astype('Int64')
            df_target['近3日投信(張)'] = df['trust_buy_3d'].round(0).astype('Int64')
            
            # 定義風險/狀態提示與籌碼沉澱
            cond_breakout = (df['latest_close'] > df['ma20']) & (df['latest_open'] <= df['ma20'])
            cond_dump = (df['latest_close'] < df['latest_open']) & (df['latest_volume'] > df['avg_vol_amount_5d'] * 1.5)
            df_target['風險/狀態提示'] = np.select([cond_breakout, cond_dump], ["剛突破20MA", "爆量收黑"], default="")
            df_target['籌碼沉澱'] = np.where((df['margin_dec'] == True) & (df['sbl_dec'] == True), "🌟", "")
            
            df_result = df_target.reset_index().sort_values('資金流入倍數', ascending=False).reset_index(drop=True)
            print(df_result.to_string())
            if is_markdown:
                output_lines.append(df_result.to_markdown(index=False))
                output_lines.append("")
        else:
            msg = " => 今日無符合所有嚴格濾網之個股。"
            print(msg)
            if is_markdown:
                output_lines.append(msg + "\n")
            
    format_and_print_result(final_stocks, "第二步(A)：最終篩選強勢資金流入個股清單", True)
    format_and_print_result(final_weak_stocks, "第二步(B)：最終篩選弱勢資金流出個股清單", True)
    print("=" * 55 + "\n")
    
    # 寫入檔案
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output_lines))
    logging.info(f"產出報告已儲存至: {output_file}")

if __name__ == "__main__":
    main()
