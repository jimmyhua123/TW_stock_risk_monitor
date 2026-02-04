#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣股市風險監控 - 歷史統計模組
提供多日數據抓取和統計分析功能
"""

import requests
import pandas as pd
import time
from datetime import datetime, timedelta
from io import StringIO
from typing import Dict, Any, List


def get_previous_trading_days(target_date_str: str, num_days: int, buffer_days: int = 15) -> List[str]:
    """
    取得往前推 N 個交易日的日期清單（跳過週末）
    會額外加上緩衝天數，確保即使有假日也能獲得足夠數據
    
    Args:
        target_date_str: 目標日期字串 YYYYMMDD
        num_days: 需要的交易日數量
        buffer_days: 額外的緩衝天數（預設15天，用於處理市場假日）
    Returns:
       交易日期清單 [YYYYMMDD, ...]，長度為 num_days + buffer_days
    """
    target_date = datetime.strptime(target_date_str, '%Y%m%d')
    trading_days = []
    current = target_date
    
    # 抓取 num_days + buffer_days 個工作日，確保有足夠的候選日期
    while len(trading_days) < (num_days + buffer_days):
        if current.weekday() < 5:  # 0=週一, 4=週五
            trading_days.append(current.strftime('%Y%m%d'))
        current -= timedelta(days=1)
    
    return list(reversed(trading_days))


class HistoricalDataFetcher:
    """歷史數據抓取器"""
    
    TWSE_BASE_URL = "https://www.twse.com.tw"
    TAIFEX_BASE_URL = "https://www.taifex.com.tw"
    
    def __init__(self, date_str: str):
        self.date_str = date_str
    
    def fetch_institutional_history(self, num_days: int = 20) -> Dict[str, Any]:
        """
        抓取多日三大法人數據並計算統計值
        Args:
            num_days: 需要抓取的天數（預設20天）
        Returns:
            包含歷史統計的字典
        """
        # 使用緩衝天數確保獲得足夠數據（即使遇到假日）
        trading_days = get_previous_trading_days(self.date_str, num_days, buffer_days=15)
        history = {'foreign': [], 'trust': [], 'total': []}
        
        print(f"[INFO] 抓取過去 {num_days} 個交易日的三大法人數據（含緩衝：共嘗試 {len(trading_days)} 天）...")
        
        for i, date in enumerate(trading_days):
            try:
                url = f"{self.TWSE_BASE_URL}/fund/BFI82U"
                params = {'response': 'json', 'dayDate': date, 'type': 'day'}
                
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if data['stat'] == 'OK':
                    for row in data.get('data', []):
                        if len(row) >= 4:
                            category = row[0]
                            net_amount = float(row[3].replace(',', '')) / 100_000_000
                            
                            if '外資及陸資' in category and '不含' in category:
                                history['foreign'].append(net_amount)
                            elif category == '投信':
                                history['trust'].append(net_amount)
                            elif category == '合計':
                                history['total'].append(net_amount)
                
                if i < len(trading_days) - 1:
                    time.sleep(1.5)  # TWSE API 限制
                    
            except Exception as e:
                print(f"[WARNING] 抓取 {date} 數據失敗: {e}")
                continue
        
        print(f"[INFO] 成功抓取 {len(history['foreign'])} 筆外資數據")
        return self._calculate_stats(history)
    
    def fetch_margin_history(self, num_days: int = 20) -> Dict[str, Any]:
        """抓取多日融資融券數據並計算統計值"""
        # 使用緩衝天數確保獲得足夠數據
        trading_days = get_previous_trading_days(self.date_str, num_days, buffer_days=15)
        margin_changes = []
        
        print(f"[INFO] 抓取過去 {num_days} 個交易日的融資融券數據（含緩衝：共嘗試 {len(trading_days)} 天）...")
        
        for i, date in enumerate(trading_days):
            try:
                url = f"{self.TWSE_BASE_URL}/rwd/zh/marginTrading/MI_MARGN"
                params = {'response': 'json', 'date': date, 'selectType': 'ALL'}
                
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                if data['stat'] == 'OK' and len(data['tables'][0]['data']) > 2:
                    margin_row = data['tables'][0]['data'][2]
                    prev_balance = float(margin_row[1].replace(',', ''))
                    today_balance = float(margin_row[2].replace(',', ''))
                    margin_change = (today_balance - prev_balance) / 100_000
                    margin_changes.append(margin_change)
                
                if i < len(trading_days) - 1:
                    time.sleep(1.5)  # TWSE API 限制
                    
            except Exception as e:
                print(f"[WARNING] 抓取 {date} 融資數據失敗: {e}")
                continue
        
        print(f"[INFO] 成功抓取 {len(margin_changes)} 筆融資數據")
        return {
            'margin_5d_avg': self._calc_avg(margin_changes, 5),
            'margin_5d_sum': self._calc_sum(margin_changes, 5),
            'margin_20d_avg': self._calc_avg(margin_changes, 20),
            'margin_20d_sum': self._calc_sum(margin_changes, 20),
        }
    
    def fetch_pc_ratio_history(self, num_days: int = 5) -> Dict[str, Any]:
        """抓取多日 P/C Ratio 並計算統計值"""
        # 5 日數據使用較小的緩衝天數
        trading_days = get_previous_trading_days(self.date_str, num_days, buffer_days=5)
        pc_ratios = []
        
        print(f"[INFO] 抓取過去 {num_days} 個交易日的 P/C Ratio（含緩衝：共嘗試 {len(trading_days)} 天）...")
        
        for i, date in enumerate(trading_days):
            try:
                formatted_date = f"{date[:4]}/{date[4:6]}/{date[6:]}"
                url = f"{self.TAIFEX_BASE_URL}/cht/3/pcRatio"
                params = {'queryDate': formatted_date}
                
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                
                tables = pd.read_html(StringIO(response.text))
                
                for table in tables:
                    if '買賣權未平倉量比率%' in table.columns:
                        pc_value = table['買賣權未平倉量比率%'].iloc[0]
                        pc_ratios.append(float(str(pc_value).replace('%', '').replace(',', '')))
                        break
                
                if i < len(trading_days) - 1:
                    time.sleep(1.5)  # TWSE API 限制
                    
            except Exception as e:
                print(f"[WARNING] 抓取 {date} P/C Ratio 失敗: {e}")
                continue
        
        print(f"[INFO] 成功抓取 {len(pc_ratios)} 筆 P/C Ratio 數據")
        return {'pc_5d_avg': self._calc_avg(pc_ratios, 5)}
    
    def fetch_futures_history(self, num_days: int = 5) -> Dict[str, Any]:
        """抓取多日外資期貨淨部位並計算統計值"""
        # 5 日數據使用較小的緩衝天數
        trading_days = get_previous_trading_days(self.date_str, num_days, buffer_days=5)
        futures_positions = []
        
        print(f"[INFO] 抓取過去 {num_days} 個交易日的外資期貨淨部位（含緩衝：共嘗試 {len(trading_days)} 天）...")
        
        for i, date in enumerate(trading_days):
            try:
                formatted_date = f"{date[:4]}/{date[4:6]}/{date[6:]}"
                url = f"{self.TAIFEX_BASE_URL}/cht/3/futContractsDate"
                params = {'queryDate': formatted_date}
                
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                
                tables = pd.read_html(StringIO(response.text))
                
                for table in tables:
                    if len(table) < 2 or len(table.columns) < 5:
                        continue
                        
                    for idx, row in table.iterrows():
                        row_str = ' '.join([str(v) for v in row.values])
                        
                        if 'TX' in row_str or '臺股期貨' in row_str:
                            for value in row.values:
                                try:
                                    value_str = str(value).replace(',', '').replace(' ', '').strip()
                                    if value_str and value_str != 'nan' and value_str != '--':
                                        if value_str.lstrip('-').replace('.', '').isdigit():
                                            num_value = int(float(value_str))
                                            if abs(num_value) > 1000:
                                                futures_positions.append(num_value)
                                                break
                                except:
                                    continue
                            break
                    if futures_positions and len(futures_positions) == i + 1:
                        break
                
                if i < len(trading_days) - 1:
                    time.sleep(1.5)  # TWSE API 限制
                    
            except Exception as e:
                print(f"[WARNING] 抓取 {date} 期貨淨部位失敗: {e}")
                continue
        
        print(f"[INFO] 成功抓取 {len(futures_positions)} 筆期貨淨部位數據")
        return {'futures_5d_avg': self._calc_avg(futures_positions, 5, as_int=True)}
    
    def _calculate_stats(self, history: Dict[str, List]) -> Dict[str, Any]:
        """計算三大法人的統計值"""
        return {
            'foreign_5d_avg': self._calc_avg(history['foreign'], 5),
            'foreign_5d_sum': self._calc_sum(history['foreign'], 5),
            'foreign_20d_avg': self._calc_avg(history['foreign'], 20),
            'foreign_20d_sum': self._calc_sum(history['foreign'], 20),
            'trust_5d_avg': self._calc_avg(history['trust'], 5),
            'trust_5d_sum': self._calc_sum(history['trust'], 5),
        }
    
    def _calc_avg(self, data_list: List, days: int, as_int: bool = False):
        """計算平均值"""
        if len(data_list) >= days:
            recent = data_list[-days:]
            avg = sum(recent) / len(recent)
            return int(round(avg)) if as_int else round(avg, 2)
        return None
    
    def _calc_sum(self, data_list: List, days: int):
        """計算總和"""
        if len(data_list) >= days:
            recent = data_list[-days:]
            return round(sum(recent), 2)
        return None


if __name__ == '__main__':
    # 測試用
    import sys
    if len(sys.argv) > 1:
        date = sys.argv[1]
    else:
        date = '20260123'
    
    fetcher = HistoricalDataFetcher(date)
    
    print("=== 測試歷史數據抓取 ===\n")
    inst_hist = fetcher.fetch_institutional_history(20)
    print(f"\n三大法人歷史統計: {inst_hist}")
    
    margin_hist = fetcher.fetch_margin_history(20)
    print(f"\n融資融券歷史統計: {margin_hist}")
    
    pc_hist = fetcher.fetch_pc_ratio_history(5)
    print(f"\nP/C Ratio歷史統計: {pc_hist}")
    
    futures_hist = fetcher.fetch_futures_history(5)
    print(f"\n期貨歷史統計: {futures_hist}")
