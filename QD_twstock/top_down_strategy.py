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
import os
from io import StringIO
import yfinance as yf

warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# 加入上一層目錄以便引用 trading_calendar
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from trading_calendar import get_calendar
except ImportError:
    pass

def get_recent_trading_days(days=5, base_date=None):
    """取得最近 N 天的台股交易日格式 (排除週末)
    若有提供 base_date (datetime.datetime 物件)，則以該日為基準"""
    if base_date:
        today = base_date
    else:
        today = datetime.datetime.now()
        if today.hour < 15: # 下午 15:00 前視為抓取上一個交易日
            today -= datetime.timedelta(days=1)
            
    try:
        target_date_str = today.strftime('%Y%m%d')
        cal = get_calendar()
        trading_days_str = cal.get_previous_trading_days(target_date_str, days)
        # 反轉順序以符合原本回傳格式 (由新到舊)
        trading_days = [datetime.datetime.strptime(d, '%Y%m%d') for d in reversed(trading_days_str)]
    except Exception as e:
        logging.warning(f"使用交易日曆失敗({e})，退回基本日期推算")
        trading_days = []
        current_date = today
        while len(trading_days) < days:
            if current_date.weekday() < 5:  # 0-4 為週一至週五
                trading_days.append(current_date)
            current_date -= datetime.timedelta(days=1)
    
    return [d.strftime('%Y%m%d') for d in trading_days], [d.strftime('%Y/%m/%d') for d in trading_days], [(d.year-1911, d.month, d.day) for d in trading_days]

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

def fetch_institutional_5d(base_date=None):
    """取得近 5 個交易日外資與投信的買賣超數據 (合計)"""
    dates_str_twse, _, dates_tpex = get_recent_trading_days(5, base_date)
    
    foreign_net = {}
    trust_net = {}
    
    logging.info(f"拉取近五日法人買賣超 ({dates_str_twse[-1]} ~ {dates_str_twse[0]})...")
    
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
    foreign_5d = {k: v / 1000 for k, v in foreign_net.items()}
    trust_5d = {k: v / 1000 for k, v in trust_net.items()}
    
    df = pd.DataFrame({'foreign_buy_5d': foreign_5d, 'trust_buy_5d': trust_5d})
    return df

def fetch_market_data(mapping_df, max_date_str, target_industries=None):
    """利用 yfinance 批次取得指定產業 (或全市場) 個股近 60 日的技術面資料"""
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
        
    logging.info(f"透過 yfinance 獲取 ({len(yf_tickers)} 檔) 近 60 日歷史價量資料...")
    
    # 取得近 60 日資料 (確保 20MA 計算準確與 14-day ATR 波動計算)
    data = yf.download(yf_tickers, period="60d", group_by='ticker', threads=True)
    
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
                
            # 計算區間報酬率 (RS 計算基礎)
            stock_ret_20d = (close[-1] / close[-21]) - 1 if len(close) >= 21 else 0
            stock_ret_5d = (close[-1] / close[-6]) - 1 if len(close) >= 6 else 0
            stock_ret_5d_yest = (close[-2] / close[-7]) - 1 if len(close) >= 7 else 0
            
            # 成交額 (粗略以收盤價 * 成交量)
            vol_amount_array = volume * close
            vol_amount_60d = np.pad(vol_amount_array[-60:], (max(0, 60 - len(vol_amount_array[-60:])), 0), 'constant')
            
            results[ticker_mapping[ticker]] = {
                'latest_close': close[-1],
                'latest_open': open_p[-1],
                'latest_volume': volume[-1],
                'atr14': atr14,
                'stock_ret_20d': stock_ret_20d,
                'stock_ret_5d': stock_ret_5d,
                'stock_ret_5d_yest': stock_ret_5d_yest,
                # 均線
                'ma5': np.mean(close[-5:]),
                'ma20': np.mean(close[-20:]),
                # 歷史近60日資金
                'vol_amount_60d': vol_amount_60d,
                'latest_vol_amount': vol_amount_array[-1],
                # 5日均量
                'avg_vol_amount_5d': np.mean(vol_amount_array[-5:]),
                # 收紅盤判斷 (收盤 > 開盤)
                'is_red': close[-1] > open_p[-1]
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
    import argparse
    parser = argparse.ArgumentParser(description="Top-Down 股市策略程式")
    # 支援 --date 20260305 或直接把 --20260305 當作未知參數解析
    parser.add_argument('--date', type=str, default=None, help="指定日期, 格式為 YYYYMMDD (例如 --date 20260305)")
    args, unknown = parser.parse_known_args()
    
    # 嘗試從 unknown 參數中捕捉類似 --20260305 的格式
    if not args.date and unknown:
        for arg in unknown:
            if arg.startswith('--') and len(arg) == 10 and arg[2:].isdigit():
                args.date = arg[2:]
                break
    
    base_date = None
    if args.date:
        date_str = args.date.lstrip('-')
        if len(date_str) == 8 and date_str.isdigit():
            base_date = datetime.datetime.strptime(date_str, '%Y%m%d')
            logging.info(f"使用者指定執行基準日: {date_str}")
        else:
            logging.warning(f"輸入日期格式有誤: {args.date}，將使用預設最新交易日。")
            
    logging.info("開始執行 Top-Down 策略 (輕量化 API 版)...")
    
    # ==============================================================
    # 第一步：全市場產業資金流向分析
    # ==============================================================
    
    # 1. 抓取產業分類與對應表
    df_industry = fetch_industry_mapping()
    if df_industry.empty:
        logging.error("無法取得產業分類表，程式結束")
        return
        
    # 決定近期的盤後基準日 (避免盤中擷取到今日不完整的籌碼和價格)
    recent_days_str, _, _ = get_recent_trading_days(1, base_date)
    target_date_str = recent_days_str[0]
        
    # 2. 抓取大盤與總經指標 (TAIEX, ^TNX, TWD=X)
    logging.info("獲取大盤加權指數(^TWII)與總經指標以判定 Market Regime...")
    
    taiex_ret_20d, taiex_ret_5d, taiex_ret_5d_yest = 0, 0, 0
    market_regime = 'bull'
    tnx_risk = False
    twd_risk = False
    
    # (1) 大盤判定
    taiex_data = yf.download("^TWII", period="60d", progress=False)
    if taiex_data.empty:
        logging.warning("無法取得大盤資料，預設為多頭模式")
    else:
        t_close_series = taiex_data['Close']
        t_close = t_close_series.iloc[:, 0].values.flatten() if isinstance(t_close_series, pd.DataFrame) else t_close_series.values.flatten()
             
        t_ma20 = np.mean(t_close[-20:])
        t_ma60 = np.mean(t_close[-60:]) if len(t_close) >= 60 else t_ma20
        t_ma20_yest = np.mean(t_close[-21:-1]) if len(t_close) >= 21 else t_ma20
        
        taiex_ret_20d = (t_close[-1] / t_close[-21]) - 1 if len(t_close) >= 21 else 0
        taiex_ret_5d = (t_close[-1] / t_close[-6]) - 1 if len(t_close) >= 6 else 0
        taiex_ret_5d_yest = (t_close[-2] / t_close[-7]) - 1 if len(t_close) >= 7 else 0
        
        if len(t_close) > 0 and t_close[-1] > t_ma20 and t_ma20 > t_ma60 and t_ma20 > t_ma20_yest:
            market_regime = 'bull'
        else:
            market_regime = 'bear'
            
        logging.info(f"大盤判定: {'全面偏多' if market_regime == 'bull' else '警戒/空頭'}")

    # (2) 總經風險判定
    try:
        macro_data = yf.download(["^TNX", "TWD=X"], period="60d", group_by='ticker', progress=False)
        # ^TNX 美債10年期
        if "^TNX" in macro_data.columns.levels[0]:
            tnx_c = macro_data["^TNX"]["Close"].dropna().values.flatten()
            if len(tnx_c) >= 20:
                tnx_ma5 = np.mean(tnx_c[-5:])
                tnx_ma20 = np.mean(tnx_c[-20:])
                tnx_ma20_yest = np.mean(tnx_c[-21:-1])
                if tnx_ma5 > tnx_ma20 and tnx_ma20 > tnx_ma20_yest:
                    tnx_risk = True
        
        # TWD=X 匯率
        if "TWD=X" in macro_data.columns.levels[0]:
            twd_c = macro_data["TWD=X"]["Close"].dropna().values.flatten()
            if len(twd_c) >= 20:
                twd_ma5 = np.mean(twd_c[-5:])
                twd_ma20 = np.mean(twd_c[-20:])
                twd_ma20_yest = np.mean(twd_c[-21:-1])
                if twd_ma5 > twd_ma20 and twd_ma20 > twd_ma20_yest:
                    twd_risk = True
    except Exception as e:
        logging.warning(f"取得總經指標失敗: {e}")

    # 3. 獲取全市場近 60 日的價量資料
    logging.info("第一步：計算全市場產業資金流向及收紅比例...")
    df_market = fetch_market_data(df_industry, target_date_str, target_industries=None)
    
    if df_market.empty:
        logging.error("無法取得全市場技術面資料，程式結束")
        return
    
    # 合併產業資訊
    df_market_full = df_market.join(df_industry).fillna(0)
    
    # 計算「產業資金佔比」與「Trend Score」
    def sum_arrays(series):
        valid_arrays = [arr for arr in series.values if isinstance(arr, np.ndarray) and len(arr) == 60]
        if not valid_arrays: return np.zeros(60)
        return np.sum(np.stack(valid_arrays), axis=0)

    industry_vol_60d = df_market_full.groupby('產業')['vol_amount_60d'].apply(sum_arrays)
    
    market_vol_60d = np.zeros(60)
    for arr in industry_vol_60d:
        market_vol_60d += arr
        
    market_vol_60d_safe = np.where(market_vol_60d == 0, 1, market_vol_60d)
    industry_ratio_sq = {ind: arr / market_vol_60d_safe for ind, arr in industry_vol_60d.items()}
    
    industry_stats = {}
    for ind, ratios in industry_ratio_sq.items():
        today_ratio = ratios[-1]
        avg_5d = np.mean(ratios[-5:])
        avg_20d = np.mean(ratios[-20:])
        avg_60d = np.mean(ratios)
        
        slope_1d = (today_ratio / avg_5d - 1) if avg_5d > 0 else 0
        slope_5d = (avg_5d / avg_20d - 1) if avg_20d > 0 else 0
        slope_20d = (avg_20d / avg_60d - 1) if avg_60d > 0 else 0
        
        industry_stats[ind] = {
            'today_ratio': today_ratio,
            'slope_1d': slope_1d,
            'slope_5d': slope_5d,
            'slope_20d': slope_20d,
        }
    
    df_ind_stats = pd.DataFrame.from_dict(industry_stats, orient='index')
    
    df_ind_stats['rank_1d'] = df_ind_stats['slope_1d'].rank(pct=True)
    df_ind_stats['rank_5d'] = df_ind_stats['slope_5d'].rank(pct=True)
    df_ind_stats['rank_20d'] = df_ind_stats['slope_20d'].rank(pct=True)
    
    df_ind_stats['trend_score'] = 0.2 * df_ind_stats['rank_1d'] + 0.3 * df_ind_stats['rank_5d'] + 0.5 * df_ind_stats['rank_20d']
    
    # 計算資金集中度穩定性 (過去 20 日進前 5 名次數)
    df_ratios_20d = pd.DataFrame({ind: ratios[-20:] for ind, ratios in industry_ratio_sq.items()})
    top5_counts = {}
    for i in range(20):
        daily_top5 = df_ratios_20d.iloc[i].nlargest(5).index
        for ind in daily_top5:
            top5_counts[ind] = top5_counts.get(ind, 0) + 1
            
    df_ind_stats['top5_days_20d'] = pd.Series(top5_counts)
    if df_ind_stats['top5_days_20d'].isnull().all():
        df_ind_stats['top5_days_20d'] = 0
    df_ind_stats['top5_days_20d'] = df_ind_stats['top5_days_20d'].fillna(0).astype(int)
    
    # 計算收紅比例 (收盤 > 開盤)
    red_ratio = df_market_full.groupby('產業')['is_red'].mean()
    market_red_ratio = df_market_full['is_red'].mean()
    logging.info(f"今日大盤整體收紅比例基準為: {market_red_ratio:.2%}")
    
    # 篩選強/弱勢產業 (各取 Top 5)，改以 trend_score 排序
    strong_categories = red_ratio[red_ratio > market_red_ratio].index
    valid_strong = df_ind_stats.loc[df_ind_stats.index.isin(strong_categories)]
    top_5_industries = valid_strong.sort_values(by='trend_score', ascending=False).head(5).index.tolist()
    
    # 總經風險預警動態調整 ATR 門檻
    atr_limit = 2.0
    tech_industries = {"半導體業", "電子零組件業", "電腦及週邊設備業", "光電業", "電子通路業", "通信網路業", "資訊服務業", "其他電子業"}
    tech_count = sum(1 for ind in top_5_industries if ind in tech_industries)
    if tnx_risk and tech_count >= 3:
        atr_limit = 1.5
        logging.warning(f"觸發殖利率與科技股集中風險，將 ATR 濾網收緊至 {atr_limit} 倍")
    
    weak_categories = red_ratio[red_ratio < market_red_ratio].index
    valid_weak = df_ind_stats.loc[df_ind_stats.index.isin(weak_categories)]
    bottom_5_industries = valid_weak.sort_values(by='trend_score', ascending=True).head(5).index.tolist()
    
    # 計算相對大盤強度 (區間 RS)
    if 'stock_ret_20d' in df_market.columns:
        df_market['rs_20d'] = (df_market['stock_ret_20d'] - taiex_ret_20d) * 100
        df_market['rs_5d'] = (df_market['stock_ret_5d'] - taiex_ret_5d) * 100
        df_market['rs_5d_yest'] = (df_market['stock_ret_5d_yest'] - taiex_ret_5d_yest) * 100
        
    # 4. 抓取法人 (現貨)
    df_inst = fetch_institutional_5d(base_date)
    
    # 5. 資料合併
    df_all = df_market.join(df_industry).join(df_inst).fillna(0)
    df_all['margin_dec'] = False  # 融資是否減少預設 False
    df_all['sbl_dec'] = False    # 借券是否減少預設 False
    
    # ==============================================================
    # 第二步：產業內部「個股篩選」
    # ==============================================================
    logging.info("進行 RS 強度、20MA、籌碼及流動性過濾...")
    
    # 條件 1. 技術面 (RS 動能、趨勢與動態 ATR 乖離)
    # 動能 RS 條件：長線跑贏大盤 (RS_20 > 0) 且 短期動能加速 (今日 RS_5 > 昨日 RS_5)
    cond_rs = (df_all['rs_20d'] > 0) & (df_all['rs_5d'] > df_all['rs_5d_yest'])
    
    # 強勢：今日收盤 > 20MA 且 5MA > 20MA 且乖離 <= 動態 ATR (預設2倍, 風險時1.5倍)
    cond_ma20 = (df_all['latest_close'] > df_all['ma20']) & \
                (df_all['ma5'] > df_all['ma20']) & \
                ((df_all['latest_close'] - df_all['ma20']) <= atr_limit * df_all['atr14'])
                
    # 弱勢：今日收盤 < 20MA 且 5MA < 20MA
    cond_ma20_weak = (df_all['latest_close'] < df_all['ma20']) & \
                     (df_all['ma5'] < df_all['ma20'])
    
    # 條件 2. 籌碼面 (基本門檻)
    # 籌碼集中：近 5 日外資與投信合計買超張數 > 0 (進階的總股本比例過濾在下一步處理)
    cond_chip = (df_all['foreign_buy_5d'] + df_all['trust_buy_5d']) > 0
    # 弱勢籌碼
    cond_chip_weak = (df_all['foreign_buy_5d'] + df_all['trust_buy_5d']) < 0
    
    # 條件 3. 流動性：5日均量 > 5000萬, 今日 > 1.3 倍
    cond_liquidity = (df_all['avg_vol_amount_5d'] > 50_000_000) & \
                     (df_all['latest_vol_amount'] > df_all['avg_vol_amount_5d'] * 1.3)
    
    # 條件 4. 產業
    cond_industry = df_all['產業'].isin(top_5_industries)
    cond_industry_weak = df_all['產業'].isin(bottom_5_industries)
    
    # 綜合篩選
    filter_cond = cond_industry & cond_rs & cond_ma20 & cond_chip & cond_liquidity
    filter_cond_weak = cond_industry_weak & cond_ma20_weak & cond_chip_weak & cond_liquidity
    
    final_stocks = df_all[filter_cond].copy()
    final_weak_stocks = df_all[filter_cond_weak].copy()
    
    # 若大盤處於警戒/空頭模式，強制將「做多標的」的輸出數量上限縮減 (每產業只取前 2 名)
    if market_regime == 'bear':
        logging.info("大盤處於警戒/空頭模式，啟動防禦機制：強制縮減做多名單上限 (每產業取前 2 名)")
        final_stocks = final_stocks.sort_values(['產業', 'rs_20d'], ascending=[True, False])
        final_stocks = final_stocks.groupby('產業').head(2)
    
    # ==============================================================
    # 基本面精篩 (高成本 API 留到最後)
    # 只針對通過前述篩選的少數名單檢查營收 YoY
    # ==============================================================
    logging.info(f"針對最後 {len(final_stocks)} 檔強勢股與 {len(final_weak_stocks)} 檔弱勢股進行基本面(YoY)精篩...")
    
    def apply_advanced_filters(df, is_weak=False):
        """對做多候選股檢查: 1.營收年增率 > 0  2.近5日外資投信買超佔總股本 > 0.5%"""
        if len(df) == 0 or is_weak:
            return df
            
        pass_mask = []
        for code in df.index:
            try:
                market_type = df_industry.loc[code, '市場'] if code in df_industry.index else '上市'
                yf_ticker = f"{code}.TW" if market_type == '上市' else f"{code}.TWO"
                
                info = yf.Ticker(yf_ticker).info
                rev_growth = info.get('revenueGrowth', 0)
                shares_out = info.get('sharesOutstanding')
                
                # 條件A: 營收 YoY > 0 放行，查無資料也放行 (避免錯殺)
                cond_rev = (rev_growth is None or rev_growth > 0)
                
                # 條件B: 近5日外資與投信合計買超張數佔總股本比例 > 0.5%
                cond_chip_ratio = True
                if shares_out and shares_out > 0:
                    foreign_5d = df.loc[code, 'foreign_buy_5d']
                    trust_5d = df.loc[code, 'trust_buy_5d']
                    total_buy_shares = (foreign_5d + trust_5d) * 1000 # 轉換為股數
                    chip_ratio = total_buy_shares / shares_out
                    cond_chip_ratio = (chip_ratio > 0.005)
                
                pass_mask.append(cond_rev and cond_chip_ratio)
                    
            except Exception as e:
                pass_mask.append(True)  # 例外則放行
                
        return df[pass_mask]

    final_stocks = apply_advanced_filters(final_stocks, is_weak=False)
    final_weak_stocks = apply_advanced_filters(final_weak_stocks, is_weak=True)
    
    # ==============================================================
    # 第三步：結果呈現與總經風險預警
    # ==============================================================
    
    if not os.path.exists('result'):
        os.makedirs('result')
        
    latest_date_str = target_date_str
    output_file = f"result/{latest_date_str}_top_down.md"
    
    output_lines = []
    output_lines.append(f"# Top-Down 策略選股報告 ({latest_date_str})\n")
    
    output_lines.append(f"## 【第一步(A)：強勢資金流入產業 (Top 5)】")
        
    print("\n" + "=" * 70)
    print("【第一步(A)：強勢資金流入產業 (Top 5)】")
    for ind in top_5_industries:
        stats = df_ind_stats.loc[ind]
        line = f"- 產業: **{ind}** | 今日資金佔比: {stats['today_ratio']:.2%} | Trend Score: {stats['trend_score']:.2f} | 近20日進榜天數: {int(stats['top5_days_20d'])}天"
        output_lines.append(line)
        print(f"  ● 產業: {ind:<8} | 今日資金佔比: {stats['today_ratio']:.2%} | Trend Score: {stats['trend_score']:.2f} | 近20日進榜天數: {int(stats['top5_days_20d'])}天")
    output_lines.append("")
    
    # 匯率預警 (Macro Risk Warning)
    if twd_risk:
        risk_msg = "⚠️ 【外資提款與匯率貶值風險警示】：近期美元兌新台幣(TWD=X)呈現連續貶值趨勢，需嚴防外資無差別提款引發流動性回撤風險！"
        output_lines.insert(1, f"> {risk_msg}\n")
        print(f"\n{risk_msg}")
        
    output_lines.append("## 【第一步(B)：弱勢資金流出產業 (Top 5)】")
    print("-" * 70)
    print("【第一步(B)：弱勢資金流出產業 (Top 5)】")
    for ind in bottom_5_industries:
        stats = df_ind_stats.loc[ind]
        line = f"- 產業: **{ind}** | 今日資金佔比: {stats['today_ratio']:.2%} | Trend Score: {stats['trend_score']:.2f} | 近20日進榜天數: {int(stats['top5_days_20d'])}天"
        output_lines.append(line)
        print(f"  ● 產業: {ind:<8} | 今日資金佔比: {stats['today_ratio']:.2%} | Trend Score: {stats['trend_score']:.2f} | 近20日進榜天數: {int(stats['top5_days_20d'])}天")
    print("=" * 70)
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
            df_target['近5日外資(張)'] = df['foreign_buy_5d'].round(0).astype('Int64')
            df_target['近5日投信(張)'] = df['trust_buy_5d'].round(0).astype('Int64')
            
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
