#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣股市交易日曆模組
提供基於加權指數 (^TWII) 的真實交易日期緩存與查詢功能
"""

import yfinance as yf
import pandas as pd
import json
import os
import requests
from datetime import datetime, timedelta
from typing import List, Optional

class TradingCalendar:
    """交易日曆管理器"""
    
    def __init__(self, cache_file: str = "trading_days.json", holiday_cache_file: str = "twse_holidays.json"):
        # 取得當前檔案所在目錄的絕對路徑
        current_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(os.path.dirname(current_dir), 'data', 'raw')
        self.cache_file = os.path.join(data_dir, cache_file)
        self.holiday_cache_file = os.path.join(data_dir, holiday_cache_file)
        self.trading_days = self._load_cache(self.cache_file)
        self.twse_holidays = self._load_cache(self.holiday_cache_file)
    
    def _load_cache(self, filepath: Optional[str] = None) -> List[str]:
        """從本地讀取交易日快取"""
        target_file = filepath if filepath else self.cache_file
        if os.path.exists(target_file):
            try:
                with open(target_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[WARNING] 讀取快取失敗 ({target_file}): {e}")
        return []
        
    def _save_cache(self, days: List[str], filepath: Optional[str] = None):
        """將交易日儲存至本地快取"""
        target_file = filepath if filepath else self.cache_file
        try:
            with open(target_file, 'w', encoding='utf-8') as f:
                json.dump(days, f, indent=2)
            # print(f"[INFO] 成功儲存 {len(days)} 筆資料至快取: {target_file}")
        except Exception as e:
            print(f"[ERROR] 儲存快取失敗 ({target_file}): {e}")
            
    def update_calendar(self, years_back: int = 10, force: bool = False):
        """
        更新交易日快取
        Args:
            years_back: 抓取過去幾年的數據
            force: 是否強制重新抓取 (忽略當天是否已更新)
        """
        today_str = datetime.now().strftime('%Y%m%d')
        
        # 若已有快取，且包含近期日期（例如過去5天內），就預設不強制更新，除非指定 force
        if not force and self.trading_days:
            # 檢查快取中最新的日期是否足夠新 (例如在過去 7 天內)
            latest_cached = max(self.trading_days)
            latest_date = datetime.strptime(latest_cached, '%Y%m%d')
            if (datetime.now() - latest_date).days < 7:
                 return self.trading_days
        
        print("[INFO] 正在從 Yahoo Finance 更新台灣股市交易日曆...")
        start_date = (datetime.now() - timedelta(days=365 * years_back)).strftime('%Y-%m-%d')
        try:
            # 取得台灣加權指數 (^TWII) 的歷史數據
            twii = yf.Ticker('^TWII')
            hist = twii.history(start=start_date)
            
            if hist.empty:
                print("[WARNING] 無法獲取 ^TWII 歷史數據。")
                return self.trading_days
                
            # 將 timezone-aware datetime index 轉換為 YYYYMMDD 字串清單
            new_trading_days = hist.index.strftime('%Y%m%d').tolist()
            
            # 去除重複並排序
            new_trading_days = sorted(list(set(new_trading_days)))
            
            self.trading_days = new_trading_days
            self._save_cache(self.trading_days)
            print(f"[INFO] 交易日曆更新完成，共 {len(self.trading_days)} 天。")
            
        except Exception as e:
            print(f"[ERROR] 更新交易日曆發生錯誤: {e}")
            
        return self.trading_days

    def get_previous_trading_days(self, target_date_str: str, num_days: int, buffer_days: int = 0) -> List[str]:
        """
        取得往回推 N 個實際交易日的日期清單
        
        Args:
            target_date_str: 目標日期字串 YYYYMMDD
            num_days: 需要的交易日數量
            
        Returns:
            實際交易日期清單 [YYYYMMDD, ...]，長度剛好為 num_days
        """
        if not self.trading_days:
            self.update_calendar()
            
        if not self.trading_days:
             print("[ERROR] 無法取得交易日曆，回退到原始推算模式")
             # Fallback
             target_date = datetime.strptime(target_date_str, '%Y%m%d')
             days = []
             current = target_date
             while len(days) < num_days:
                 if current.weekday() < 5:
                     days.append(current.strftime('%Y%m%d'))
                 current -= timedelta(days=1)
             return list(reversed(days))

        # 智慧判斷：如果 target_date_str <= 今天，且不包含在 trading_days 內
        # 我們檢查它是否為週末或國定假日，如果都不是，代表它應該要有資料，我們就強制更新
        today_str = datetime.now().strftime('%Y%m%d')
        if target_date_str <= today_str and target_date_str not in self.trading_days:
            try:
                dt = datetime.strptime(target_date_str, '%Y%m%d')
                is_weekend = dt.weekday() >= 5
                
                if not is_weekend:
                    holidays = self._fetch_twse_holidays()
                    is_holiday = target_date_str in holidays
                    if not is_holiday:
                        print(f"[INFO] 目標日期 {target_date_str} 疑似為新的交易日且尚未快取，強制向 Yahoo Finance 更新最新資料...")
                        self.update_calendar(force=True)
            except ValueError:
                pass

        # 篩選出所有小於等於 target_date_str 的交易日
        valid_days = [d for d in self.trading_days if d <= target_date_str]
        
        if not valid_days:
            # 可能是很早以前的日期或是剛好還沒更新到今天
             print(f"[WARNING] 找不到 {target_date_str} 或之前的交易紀錄。")
             self.update_calendar(force=True)
             valid_days = [d for d in self.trading_days if d <= target_date_str]
             
             if not valid_days:
                  return []

        # 取最後 num_days 筆
        result = valid_days[-num_days:]
        
        if len(result) < num_days:
            print(f"[WARNING] 快取的交易日數量不足 ({len(result)} < {num_days})，將抓取更早之前的歷史。")
            self.update_calendar(years_back=20, force=True) # 嘗試抓取更多
            valid_days = [d for d in self.trading_days if d <= target_date_str]
            result = valid_days[-num_days:]
            
        return result

    def _fetch_twse_holidays(self) -> List[str]:
        """從 TWSE OpenAPI 獲取當年度休假日"""
        if self.twse_holidays and len(self.twse_holidays) > 0:
            return self.twse_holidays
        
        url = "https://openapi.twse.com.tw/v1/holidaySchedule/holidaySchedule"
        try:
            res = requests.get(url, timeout=10)
            data = res.json()
            holidays = []
            for item in data:
                date_str = item.get("Date", "")
                # TWSE 格式通常是民國年，例如 1150101 (長度7)
                if len(date_str) == 7:
                    roc_year = int(date_str[:3])
                    gregorian_year = roc_year + 1911
                    gregorian_date = f"{gregorian_year}{date_str[3:]}"
                    holidays.append(gregorian_date)
                elif len(date_str) == 6:
                    roc_year = int(date_str[:2])
                    gregorian_year = roc_year + 1911
                    gregorian_date = f"{gregorian_year}{date_str[2:]}"
                    holidays.append(gregorian_date)
            
            # 若今年有特殊補班日 (週六開市)，未來可擴充於此，但TWSE近期已少見補班開市
            
            self.twse_holidays = sorted(list(set(holidays)))
            self._save_cache(self.twse_holidays, self.holiday_cache_file)
            return self.twse_holidays
        except Exception as e:
            print(f"[ERROR] 無法取得 TWSE 休假日曆: {e}")
            return []

    def get_future_trading_days(self, target_date_str: str, num_days: int) -> List[str]:
        """
        取得從目標日期開始往後推的 N 個實際交易日的日期清單 (包含目標日若本身為交易日)
        
        Args:
            target_date_str: 目標日期字串 YYYYMMDD
            num_days: 需要的交易日數量
            
        Returns:
            實際交易日期清單 [YYYYMMDD, ...]
        """
        holidays = self._fetch_twse_holidays()
        try:
            target_date = datetime.strptime(target_date_str, '%Y%m%d')
        except ValueError:
             print(f"[ERROR] 目標日期格式錯誤: {target_date_str}")
             return []
             
        days = []
        current = target_date
        
        # 為了避免無窮迴圈，設一個上限 (如 365天)
        max_iterations = num_days * 3 + 30 
        iterations = 0
        
        while len(days) < num_days and iterations < max_iterations:
            current_str = current.strftime('%Y%m%d')
            # 判斷是否為週末 (0=週一, ..., 5=週六, 6=週日) 或 名列於 TWSE 休假日
            is_weekend = current.weekday() >= 5
            is_holiday = current_str in holidays
            
            if not is_weekend and not is_holiday:
                days.append(current_str)
            
            current += timedelta(days=1)
            iterations += 1
            
        return days

# 提供統一的單例供其他模組匯入使用
_calendar_instance = None

def get_calendar() -> TradingCalendar:
    global _calendar_instance
    if _calendar_instance is None:
        _calendar_instance = TradingCalendar()
        # 自動初始化或更新(若需要)
        _calendar_instance.update_calendar()
    return _calendar_instance

def get_previous_trading_days(target_date_str: str, num_days: int, buffer_days: int = 0) -> List[str]:
    """快捷函數，直接調用全域日曆實例"""
    cal = get_calendar()
    return cal.get_previous_trading_days(target_date_str, num_days, buffer_days=buffer_days)

def get_future_trading_days(target_date_str: str, num_days: int) -> List[str]:
    """快捷函數：取得未來的交易日"""
    cal = get_calendar()
    return cal.get_future_trading_days(target_date_str, num_days)

if __name__ == '__main__':
    cal = TradingCalendar()
    cal.update_calendar(force=True)
    
    print("\n=== 測試查詢交易日 ===")
    test_date = datetime.now().strftime('%Y%m%d')
    days = cal.get_previous_trading_days(test_date, 5)
    print(f"從 {test_date} 往前推 5 個交易日: {days}")
    
    past_date = "20240215" # 剛過完農曆年開市第一天
    days = cal.get_previous_trading_days(past_date, 5)
    print(f"從 {past_date} 往前推 5 個交易日 (應跳過春節): {days}")
    
    print("\n=== 測試未來交易日預測 ===")
    future_days = cal.get_future_trading_days(test_date, 10)
    print(f"從 {test_date} 往後推 10 個交易日: {future_days}")
