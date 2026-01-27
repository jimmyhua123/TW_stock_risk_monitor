#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣股市風險監控爬蟲
抓取多項金融指標，用於評估市場風險狀況
"""

import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from tabulate import tabulate
import argparse
import json
from io import StringIO
import sys
from typing import Dict, Any, Optional


class TWSEFetcher:
    """台灣證交所數據抓取器"""
    
    BASE_URL = "https://www.twse.com.tw"
    
    def __init__(self, date_str: str):
        """
        Args:
            date_str: 日期字串，格式 YYYYMMDD
        """
        self.date_str = date_str
        self.formatted_date = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}"
        
    def fetch_institutional_investors(self) -> Dict[str, Any]:
        """
        抓取三大法人買賣超數據（整體市場彙總）
        Returns:
            {
                'foreign_net': 外資買賣超金額（億元）,
                'trust_net': 投信買賣超金額（億元）,
                'dealer_net': 自營商買賣超金額（億元）,
                'total_net': 三大法人合計（億元）
            }
        """
        try:
            # TWSE 三大法人買賣超彙總表 API
            url = f"{self.BASE_URL}/fund/BFI82U"
            params = {
                'response': 'json',
                'dayDate': self.date_str,
                'type': 'day'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data['stat'] != 'OK':
                raise ValueError(f"TWSE API返回錯誤: {data.get('stat')}")
            
            # 解析數據
            # data 格式：
            # ['自營商(自行買賣)', '買進金額', '賣出金額', '買賣差額']
            # ['自營商(避險)', '買進金額', '賣出金額', '買賣差額']
            # ['投信', '買進金額', '賣出金額', '買賣差額']
            # ['外資及陸資(不含外資自營商)', '買進金額', '賣出金額', '買賣差額']
            # ['外資自營商', '買進金額', '賣出金額', '買賣差額']
            # ['合計', '買進金額', '賣出金額', '買賣差額']
            
            foreign_net = None
            trust_net = None
            dealer_net = None
            total_net = None
            
            for row in data.get('data', []):
                if len(row) >= 4:
                    category = row[0]
                    net_amount = float(row[3].replace(',', '')) / 100_000_000  # 轉為億元
                    
                    if '外資及陸資' in category and '不含' in category:
                        foreign_net = round(net_amount, 2)
                    elif category == '投信':
                        trust_net = round(net_amount, 2)
                    elif '自營商(自行買賣)' in category:
                        dealer_net = round(net_amount, 2)
                    elif category == '合計':
                        total_net = round(net_amount, 2)
            
            return {
                'foreign_net': foreign_net,
                'trust_net': trust_net,
                'dealer_net': dealer_net,
                'total_net': total_net
            }
        except Exception as e:
            print(f"[WARNING] 抓取三大法人數據失敗: {e}")
            return {
                'foreign_net': None,
                'trust_net': None,
                'dealer_net': None,
                'total_net': None
            }
    
    def fetch_margin_trading(self) -> Dict[str, float]:
        """
        抓取融資融券變化
        Returns:
            {
                'margin_change': 融資變化（億元）,
                'short_change': 融券變化（張）
            }
        """
        try:
            # TWSE 融資融券 API
            url = f"{self.BASE_URL}/rwd/zh/marginTrading/MI_MARGN"
            params = {
                'response': 'json',
                'date': self.date_str,
                'selectType': 'ALL'
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data['stat'] != 'OK':
                raise ValueError(f"融資融券API返回錯誤: {data.get('stat')}")
            
            # 解析數據 - tables[0] 是信用交易統計
            # 第三行 (data[2]) 包含融資金額數據
            table_data = data['tables'][0]['data']
            if len(table_data) > 2:
                margin_row = table_data[2]  # 融資金額(仟元)
                # 前日餘額在 index 1, 今日餘額在 index 2
                prev_balance = float(margin_row[1].replace(',', ''))
                today_balance = float(margin_row[2].replace(',', ''))
                # 轉換為億元
                margin_change = (today_balance - prev_balance) / 100_000
                
                return {
                    'margin_change': round(margin_change, 2),
                    'short_change': None  # 融券數據在不同位置，暫時省略
                }
                    
        except Exception as e:
            print(f"[WARNING] 抓取融資融券數據失敗: {e}")
            
        return {
            'margin_change': None,
            'short_change': None
        }


class TAIFEXFetcher:
    """台灣期貨交易所數據抓取器"""
    
    BASE_URL = "https://www.taifex.com.tw"
    
    def __init__(self, date_str: str):
        """
        Args:
            date_str: 日期字串，格式 YYYYMMDD
        """
        self.date_str = date_str
        # TAIFEX 使用 YYYY/MM/DD 格式
        self.formatted_date = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:]}"
    
    def fetch_options_pc_ratio(self) -> Optional[float]:
        """
        抓取選擇權 Put/Call Ratio
        Returns:
            P/C Ratio 百分比
        """
        try:
            # 期交所 P/C Ratio 頁面 (HTML)
            url = f"{self.BASE_URL}/cht/3/pcRatio"
            params = {
                'queryDate': self.formatted_date,  # 使用 YYYY/MM/DD 格式
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            # 使用 pandas 解析 HTML 表格
            tables = pd.read_html(StringIO(response.text))
            
            # 尋找包含 P/C Ratio 的表格
            for table in tables:
                if '買賣權未平倉量比率%' in table.columns or '買賣權未平倉量比率%' in str(table.values):
                    # 找到包含日期的行
                    for idx, row in table.iterrows():
                        if self.formatted_date in str(row.values):
                            # P/C Ratio 通常在特定欄位
                            pc_value = row['買賣權未平倉量比率%'] if '買賣權未平倉量比率%' in table.columns else None
                            if pc_value:
                                return float(str(pc_value).replace('%', '').replace(',', ''))
                    
                    # 如果沒有找到特定日期，取第一個數值
                    if '買賣權未平倉量比率%' in table.columns:
                        pc_value = table['買賣權未平倉量比率%'].iloc[0]
                        return float(str(pc_value).replace('%', '').replace(',', ''))
                
        except Exception as e:
            print(f"[WARNING] 抓取選擇權 P/C Ratio 失敗: {e}")
            
        return None
    
    def fetch_futures_position(self) -> Dict[str, Any]:
        """
        抓取期貨未平倉數據
        Returns:
            {
                'foreign_net': 外資淨部位（口）,
            }
        """
        try:
            # 期交所三大法人期貨頁面 (HTML)
            url = f"{self.BASE_URL}/cht/3/futContractsDate"
            params = {
                'queryDate': self.formatted_date,  # 使用 YYYY/MM/DD 格式
            }
            
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            # 使用 pandas 解析 HTML 表格
            tables = pd.read_html(StringIO(response.text))
            
            # 尋找三大法人表格
            for table in tables:
                # 跳過太小的表格
                if len(table) < 2 or len(table.columns) < 5:
                    continue
                    
                # 尋找 TX (台指期) 的數據
                for idx, row in table.iterrows():
                    row_str = ' '.join([str(v) for v in row.values])
                    
                    # 檢查是否是 TX 的行
                    if 'TX' in row_str or '臺股期貨' in row_str or '台股期货' in row_str:
                        # 嘗試從各個欄位提取數值
                        for col_idx, value in enumerate(row.values):
                            try:
                                # 清理數值字串
                                value_str = str(value).replace(',', '').replace(' ', '').strip()
                                
                                # 檢查是否為有效的數字（包括負數）
                                if value_str and value_str != 'nan' and value_str != '--':
                                    # 嘗試轉換為數字
                                    if value_str.lstrip('-').replace('.', '').isdigit():
                                        num_value = int(float(value_str))
                                        # 外資淨部位通常是較大的數字（絕對值 > 1000）
                                        if abs(num_value) > 1000:
                                            return {'foreign_net': num_value}
                            except:
                                continue
            
        except Exception as e:
            print(f"[WARNING] 抓取期貨未平倉數據失敗: {e}")
            
        return {
            'foreign_net': None
        }


class YahooFinanceFetcher:
    """Yahoo Finance 數據抓取器（國際金融指標）"""
    
    SYMBOLS = {
        'us_10y': '^TNX',      # 美債10年殖利率
        'gold': 'GC=F',        # 黃金期貨
        'usd_twd': 'TWD=X',    # 美元/台幣
        'sox': '^SOX',         # 費城半導體指數
        'vix': '^VIX'          # 恐慌指數
    }
    
    def __init__(self, date_str: str):
        """
        Args:
            date_str: 日期字串，格式 YYYYMMDD
        """
        self.date_str = date_str
        self.target_date = datetime.strptime(date_str, '%Y%m%d')
    
    def fetch_all(self) -> Dict[str, Any]:
        """
        抓取所有 Yahoo Finance 指標
        Returns:
            {
                'us_10y': {'value': X.XX, 'change_pct': X.XX},
                'gold': {...},
                ...
            }
        """
        results = {}
        
        for key, symbol in self.SYMBOLS.items():
            try:
                # 抓取前後幾天的數據以確保有資料
                start_date = self.target_date - timedelta(days=7)
                end_date = self.target_date + timedelta(days=1)
                
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start_date, end=end_date)
                
                if hist.empty:
                    print(f"[WARNING] {symbol} 無數據")
                    results[key] = {'value': None, 'change_pct': None}
                    continue
                
                # 取最接近目標日期的數據
                closest_date = min(hist.index, key=lambda x: abs(x.date() - self.target_date.date()))
                latest_data = hist.loc[closest_date]
                
                value = round(latest_data['Close'], 2)
                
                # 計算變化百分比（與前一天比較）
                change_pct = None
                if len(hist) >= 2:
                    idx = hist.index.get_loc(closest_date)
                    if idx > 0:
                        prev_close = hist.iloc[idx - 1]['Close']
                        change_pct = round(((value - prev_close) / prev_close) * 100, 2)
                
                results[key] = {
                    'value': value,
                    'change_pct': change_pct
                }
                
            except Exception as e:
                print(f"[WARNING] 抓取 {symbol} 失敗: {e}")
                results[key] = {'value': None, 'change_pct': None}
        
        return results


class RiskMonitor:
    """風險監控主類別"""
    
    def __init__(self, date_str: str):
        """
        Args:
            date_str: 日期字串，格式 YYYYMMDD
        """
        self.date_str = date_str
        self.data = {}
    
    def fetch_all_data(self):
        """抓取所有數據"""
        print(f"[INFO] 開始抓取 {self.date_str} 的風險監控數據...\n")
        
        # 1. Yahoo Finance 國際指標
        print("[1/3] 抓取國際金融指標...")
        yf_fetcher = YahooFinanceFetcher(self.date_str)
        yf_data = yf_fetcher.fetch_all()
        
        # 2. 台灣證交所
        print("[2/3] 抓取台灣證交所數據...")
        twse_fetcher = TWSEFetcher(self.date_str)
        institutional = twse_fetcher.fetch_institutional_investors()
        margin = twse_fetcher.fetch_margin_trading()
        
        # 3. 台灣期貨交易所
        print("[3/3] 抓取台灣期貨交易所數據...")
        taifex_fetcher = TAIFEXFetcher(self.date_str)
        pc_ratio = taifex_fetcher.fetch_options_pc_ratio()
        futures = taifex_fetcher.fetch_futures_position()
        
        # 整合數據
        self.data = {
            'date': self.date_str,
            'indicators': [
                {
                    'category': '總經',
                    'name': '美債10年殖利率',
                    'value': yf_data['us_10y']['value'],
                    'change': yf_data['us_10y']['change_pct'],
                    'unit': '%',
                    'risk': self._assess_risk('us_10y', yf_data['us_10y']['change_pct'])
                },
                {
                    'category': '總經',
                    'name': '黃金指數 (GC=F)',
                    'value': yf_data['gold']['value'],
                    'change': yf_data['gold']['change_pct'],
                    'unit': '$',
                    'risk': self._assess_risk('gold', yf_data['gold']['change_pct'])
                },
                {
                    'category': '貨幣',
                    'name': '美元/台幣匯率',
                    'value': yf_data['usd_twd']['value'],
                    'change': yf_data['usd_twd']['change_pct'],
                    'unit': '',
                    'risk': self._assess_risk('usd_twd', yf_data['usd_twd']['change_pct'])
                },
                {
                    'category': '現貨',
                    'name': '費半指數 (SOX)',
                    'value': yf_data['sox']['value'],
                    'change': yf_data['sox']['change_pct'],
                    'unit': '',
                    'risk': self._assess_risk('sox', yf_data['sox']['change_pct'])
                },
                {
                    'category': '情緒',
                    'name': '恐慌指數 (VIX)',
                    'value': yf_data['vix']['value'],
                    'change': yf_data['vix']['change_pct'],
                    'unit': '',
                    'risk': self._assess_risk('vix', yf_data['vix']['value'])
                },
                {
                    'category': '籌碼',
                    'name': '外資現貨',
                    'value': institutional['foreign_net'],
                    'change': None,
                    'unit': '億',
                    'risk': self._assess_risk('foreign_net', institutional['foreign_net'])
                },
                {
                    'category': '籌碼',
                    'name': '投信現貨',
                    'value': institutional['trust_net'],
                    'change': None,
                    'unit': '億',
                    'risk': self._assess_risk('trust_net', institutional['trust_net'])
                },
                {
                    'category': '籌碼',
                    'name': '選擇權 P/C Ratio',
                    'value': pc_ratio,
                    'change': None,
                    'unit': '%',
                    'risk': self._assess_risk('pc_ratio', pc_ratio)
                },
                {
                    'category': '籌碼',
                    'name': '三大法人合計',
                    'value': institutional['total_net'],
                    'change': None,
                    'unit': '億',
                    'risk': self._assess_risk('total_net', institutional['total_net'])
                },
                {
                    'category': '籌碼',
                    'name': '外資期貨未平倉',
                    'value': futures['foreign_net'],
                    'change': None,
                    'unit': '口',
                    'risk': self._assess_risk('foreign_futures', futures['foreign_net'])
                },
                {
                    'category': '結算',
                    'name': '融資融券變化',
                    'value': margin['margin_change'],
                    'change': None,
                    'unit': '億',
                    'risk': self._assess_risk('margin', margin['margin_change'])
                },
            ]
        }
        
        print("\n[SUCCESS] 數據抓取完成！\n")
    
    def _assess_risk(self, indicator: str, value: Optional[float]) -> str:
        """
        評估風險等級
        Returns:
            '安全' | '警戒' | '危險'
        """
        if value is None:
            return '無資料'
        
        # 簡單的風險評估邏輯（可根據需求調整）
        risk_rules = {
            'vix': [(20, '安全'), (30, '警戒'), (float('inf'), '危險')],
            'foreign_net': [(0, '危險'), (100, '警戒'), (float('inf'), '安全')],
            'total_net': [(-200, '危險'), (0, '警戒'), (float('inf'), '安全')],
        }
        
        if indicator in risk_rules:
            for threshold, level in risk_rules[indicator]:
                if value < threshold:
                    return level
        
        return '中性'
    
    def display(self):
        """以表格形式顯示數據"""
        print(f"{'='*80}")
        print(f"重點列表：全球黃金型「通膨至上」，台股籌碼凸顯「土洋同步齊殺」的壓邊緣勢局。")
        print(f"{'='*80}\n")
        
        table_data = []
        for indicator in self.data['indicators']:
            value_str = f"{indicator['value']}{indicator['unit']}" if indicator['value'] is not None else "N/A"
            change_str = f"{indicator['change']:+.2f}%" if indicator['change'] is not None else ""
            
            # 風險指示符
            risk_emoji = {
                '安全': '[V]',
                '警戒': '[!]',
                '危險': '[X]',
                '中性': '[-]',
                '無資料': '[?]'
            }
            
            table_data.append([
                indicator['category'],
                indicator['name'],
                value_str,
                change_str,
                f"{risk_emoji.get(indicator['risk'], '[-]')} {indicator['risk']}"
            ])
        
        headers = ['類別', '開鍵指標', '最新數值', '單日變動', '風險燈號']
        print(tabulate(table_data, headers=headers, tablefmt='grid'))
        print()
    
    def export_json(self, filename: str = 'risk_data.json'):
        """匯出為 JSON 檔案"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        print(f"[SAVED] 數據已儲存至 {filename}")


def get_trading_date(date_str: Optional[str] = None) -> str:
    """
    取得交易日期，如果是週末則回退到週五
    Args:
        date_str: 日期字串 YYYYMMDD，若為 None 則使用今天
    Returns:
        交易日期字串 YYYYMMDD
    """
    if date_str:
        target_date = datetime.strptime(date_str, '%Y%m%d')
    else:
        target_date = datetime.now()
    
    # 如果是週末，回退到週五
    weekday = target_date.weekday()
    if weekday == 5:  # 週六
        target_date -= timedelta(days=1)
    elif weekday == 6:  # 週日
        target_date -= timedelta(days=2)
    
    return target_date.strftime('%Y%m%d')


def main():
    """主程式"""
    parser = argparse.ArgumentParser(
        description='台灣股市風險監控爬蟲',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 抓取指定日期
  python risk_monitor.py --date 20260120
  
  # 抓取今天（週末自動回退）
  python risk_monitor.py
  
  # 匯出 JSON
  python risk_monitor.py --date 20260120 --json output.json
        """
    )
    
    parser.add_argument(
        '--date',
        type=str,
        help='指定日期 (格式: YYYYMMDD)，不指定則使用今天'
    )
    
    parser.add_argument(
        '--json',
        type=str,
        help='匯出 JSON 檔案路徑'
    )
    
    args = parser.parse_args()
    
    # 取得交易日期
    trading_date = get_trading_date(args.date)
    
    if args.date and args.date != trading_date:
        print(f"[INFO] 指定日期為週末，已調整為 {trading_date}\n")
    
    # 執行爬蟲
    try:
        monitor = RiskMonitor(trading_date)
        monitor.fetch_all_data()
        monitor.display()
        
        if args.json:
            monitor.export_json(args.json)
    
    except KeyboardInterrupt:
        print("\n\n[WARNING] 程式被使用者中斷")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] 執行失敗: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
