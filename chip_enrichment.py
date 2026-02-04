#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台灣個股籌碼進階指標模組
提供分點日報、借券賣出、成本基準等進階分析指標
支援 fetch_then_simulate_missing 模式
"""

import requests
import pandas as pd
import random
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import time


class ChipEnrichmentFetcher:
    """籌碼進階指標抓取器"""
    
    FINMIND_API_URL = "https://api.finmindtrade.com/api/v4/data"
    FINMIND_BROKER_URL = "https://api.finmindtrade.com/api/v4/taiwan_stock_trading_daily_report"
    
    # 模擬參數邊界
    SIMULATION_BOUNDS = {
        'broker_buy_sell_diff': (-50, 50),
        'chip_concentration_5d': (-10.0, 10.0),
        'sbl_sell_balance': (0, 1_000_000),
        'short_cover_days': (0.0, 30.0),
    }
    
    def __init__(self, date_str: str, finmind_token: str = None):
        """
        Args:
            date_str: 日期字串，格式 YYYYMMDD
            finmind_token: FinMind API token (sponsor 會員可取得分點資料)
        """
        self.date_str = date_str
        self.finmind_token = finmind_token
        self.formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        self.random_seed = 42
        
        # 快取
        self._sbl_cache = {}
        self._ohlcv_cache = {}
        self._broker_cache = {}
    
    def _get_headers(self) -> Dict[str, str]:
        """取得 API 請求 headers"""
        if self.finmind_token:
            return {"Authorization": f"Bearer {self.finmind_token}"}
        return {}
    
    def _simulate_value(self, stock_code: str, metric_name: str, bounds: Tuple[float, float]) -> float:
        """
        產生確定性模擬值
        使用 stock_code + date + metric_name 作為種子確保可重現性
        """
        seed_str = f"{stock_code}_{self.date_str}_{metric_name}_{self.random_seed}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        return rng.uniform(bounds[0], bounds[1])
    
    # ========================================
    # 1. Broker Branch Analytics (分點日報)
    # ========================================
    
    def fetch_broker_branch_data(self, stock_code: str) -> Optional[pd.DataFrame]:
        """
        抓取個股分點資料 (需 sponsor 會員)
        Returns: DataFrame with columns [securities_trader, buy, sell, securities_trader_id]
        """
        if not self.finmind_token:
            return None
        
        cache_key = f"{stock_code}_{self.date_str}"
        if cache_key in self._broker_cache:
            return self._broker_cache[cache_key]
        
        try:
            params = {
                "data_id": stock_code,
                "date": self.formatted_date,
            }
            response = requests.get(
                self.FINMIND_BROKER_URL,
                headers=self._get_headers(),
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('msg') != 'success' or not data.get('data'):
                return None
            
            df = pd.DataFrame(data['data'])
            self._broker_cache[cache_key] = df
            return df
            
        except Exception as e:
            print(f"[WARNING] 抓取分點資料失敗 ({stock_code}): {e}")
            return None
    
    def calculate_broker_buy_sell_diff(self, stock_code: str) -> Tuple[int, str, int]:
        """
        計算券商買賣家數差 (Metric A)
        Returns: (value, data_source, is_simulated)
        """
        df = self.fetch_broker_branch_data(stock_code)
        
        if df is not None and not df.empty:
            # 計算每個券商的淨買賣
            df['net_buy'] = df['buy'].astype(int) - df['sell'].astype(int)
            
            # 買入券商數 (net_buy > 0)
            buying_count = (df['net_buy'] > 0).sum()
            # 賣出券商數 (net_buy < 0)
            selling_count = (df['net_buy'] < 0).sum()
            
            diff = int(buying_count - selling_count)
            return (diff, 'fetched', 0)
        
        # 模擬
        bounds = self.SIMULATION_BOUNDS['broker_buy_sell_diff']
        simulated = int(self._simulate_value(stock_code, 'broker_buy_sell_diff', bounds))
        return (simulated, 'simulated', 1)
    
    def fetch_broker_branch_data_5d(self, stock_code: str) -> Optional[pd.DataFrame]:
        """
        抓取過去 5 個交易日的分點資料
        """
        if not self.finmind_token:
            return None
        
        try:
            # 計算過去 5 個交易日
            base_date = datetime.strptime(self.date_str, '%Y%m%d')
            trading_days = []
            check_date = base_date
            
            while len(trading_days) < 5:
                if check_date.weekday() < 5:  # 跳過週末
                    trading_days.append(check_date.strftime('%Y-%m-%d'))
                check_date -= timedelta(days=1)
            
            all_data = []
            for date in trading_days:
                params = {
                    "data_id": stock_code,
                    "date": date,
                }
                response = requests.get(
                    self.FINMIND_BROKER_URL,
                    headers=self._get_headers(),
                    params=params,
                    timeout=15
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get('msg') == 'success' and data.get('data'):
                    df = pd.DataFrame(data['data'])
                    all_data.append(df)
                
                time.sleep(0.3)  # 避免請求過快
            
            if all_data:
                return pd.concat(all_data, ignore_index=True)
            return None
            
        except Exception as e:
            print(f"[WARNING] 抓取5日分點資料失敗 ({stock_code}): {e}")
            return None
    
    def calculate_chip_concentration_5d(self, stock_code: str, volume_5d: int) -> Tuple[float, str, int]:
        """
        計算5日籌碼集中度 (Metric B)
        Formula: (Sum(Top15 Buyers) - |Sum(Top15 Sellers)|) / Sum(total_volume_5d) * 100
        
        Args:
            stock_code: 股票代碼
            volume_5d: 過去5日總成交量 (張) - 需從外部提供
            
        Returns: (value, data_source, is_simulated)
        """
        df = self.fetch_broker_branch_data_5d(stock_code)
        
        if df is not None and not df.empty and volume_5d > 0:
            # 計算每個券商的5日淨買賣
            df['net_buy'] = df['buy'].astype(int) - df['sell'].astype(int)
            broker_net = df.groupby('securities_trader_id')['net_buy'].sum().reset_index()
            
            # 排序找出 Top15 買家和 Top15 賣家
            broker_net_sorted = broker_net.sort_values('net_buy', ascending=False)
            
            top15_buyers = broker_net_sorted.head(15)['net_buy'].sum()
            top15_sellers = broker_net_sorted.tail(15)['net_buy'].sum()
            
            # 轉換成股數單位 (成交量是張，分點是股)
            volume_5d_shares = volume_5d * 1000
            
            concentration = (top15_buyers - abs(top15_sellers)) / volume_5d_shares * 100
            return (round(concentration, 2), 'fetched', 0)
        
        # 模擬
        bounds = self.SIMULATION_BOUNDS['chip_concentration_5d']
        simulated = round(self._simulate_value(stock_code, 'chip_concentration_5d', bounds), 2)
        return (simulated, 'simulated', 1)
    
    # ========================================
    # 2. SBL Stock Analysis (借券賣出)
    # ========================================
    
    def fetch_sbl_balance(self, stock_code: str) -> Optional[Dict[str, Any]]:
        """
        抓取個股借券賣出餘額
        使用 TaiwanDailyShortSaleBalances 資料集
        """
        cache_key = f"{stock_code}_{self.date_str}"
        if cache_key in self._sbl_cache:
            return self._sbl_cache[cache_key]
        
        try:
            params = {
                "dataset": "TaiwanDailyShortSaleBalances",
                "data_id": stock_code,
                "start_date": self.formatted_date,
                "end_date": self.formatted_date,
            }
            response = requests.get(
                self.FINMIND_API_URL,
                headers=self._get_headers(),
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('msg') == 'success' and data.get('data'):
                df = pd.DataFrame(data['data'])
                if not df.empty:
                    result = df.iloc[-1].to_dict()
                    self._sbl_cache[cache_key] = result
                    return result
            
            return None
            
        except Exception as e:
            print(f"[WARNING] 抓取借券賣出餘額失敗 ({stock_code}): {e}")
            return None
    
    def calculate_sbl_sell_balance(self, stock_code: str) -> Tuple[int, str, int]:
        """
        取得借券賣出餘額 (Metric C)
        Returns: (value in shares, data_source, is_simulated)
        """
        sbl_data = self.fetch_sbl_balance(stock_code)
        
        if sbl_data and 'SBLShortSalesCurrentDayBalance' in sbl_data:
            balance = int(sbl_data['SBLShortSalesCurrentDayBalance'])
            return (balance, 'fetched', 0)
        
        # 模擬
        bounds = self.SIMULATION_BOUNDS['sbl_sell_balance']
        simulated = int(self._simulate_value(stock_code, 'sbl_sell_balance', bounds))
        return (simulated, 'simulated', 1)
    
    def calculate_short_cover_days(self, stock_code: str, avg_volume_5d: float) -> Tuple[float, str, int]:
        """
        計算短回補天數 (Metric D)
        Formula: SBL_Sell_Balance / Average_Daily_Volume_5D
        
        Args:
            stock_code: 股票代碼
            avg_volume_5d: 過去5日平均成交量 (張)
            
        Returns: (value in days, data_source, is_simulated)
        """
        sbl_balance, sbl_source, sbl_simulated = self.calculate_sbl_sell_balance(stock_code)
        
        if avg_volume_5d > 0:
            # 轉換成股數單位
            avg_volume_5d_shares = avg_volume_5d * 1000
            cover_days = sbl_balance / avg_volume_5d_shares
            return (round(cover_days, 2), sbl_source, sbl_simulated)
        
        # 模擬
        bounds = self.SIMULATION_BOUNDS['short_cover_days']
        simulated = round(self._simulate_value(stock_code, 'short_cover_days', bounds), 2)
        return (simulated, 'simulated', 1)
    
    # ========================================
    # 3. Cost Basis Metrics (成本基準)
    # ========================================
    
    def fetch_ohlcv_history(self, stock_code: str, days: int = 20) -> Optional[pd.DataFrame]:
        """
        抓取個股 OHLCV 歷史數據
        使用 TaiwanStockPrice 資料集
        """
        cache_key = f"{stock_code}_{self.date_str}_{days}"
        if cache_key in self._ohlcv_cache:
            return self._ohlcv_cache[cache_key]
        
        try:
            # 計算起始日期 (多抓一些確保有足夠交易日)
            end_date = datetime.strptime(self.date_str, '%Y%m%d')
            start_date = end_date - timedelta(days=days + 15)
            
            params = {
                "dataset": "TaiwanStockPrice",
                "data_id": stock_code,
                "start_date": start_date.strftime('%Y-%m-%d'),
                "end_date": self.formatted_date,
            }
            response = requests.get(
                self.FINMIND_API_URL,
                headers=self._get_headers(),
                params=params,
                timeout=15
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('msg') == 'success' and data.get('data'):
                df = pd.DataFrame(data['data'])
                df = df.sort_values('date', ascending=False).head(days)
                self._ohlcv_cache[cache_key] = df
                return df
            
            return None
            
        except Exception as e:
            print(f"[WARNING] 抓取 OHLCV 資料失敗 ({stock_code}): {e}")
            return None
    
    def calculate_vwap_20d_approx(self, stock_code: str, close_price: float = None) -> Tuple[float, str, int]:
        """
        計算 20 日近似 VWAP (Metric E)
        Formula: Sum((High + Low + Close) / 3 * Volume) / Sum(Volume) over 20 days
        
        Args:
            stock_code: 股票代碼
            close_price: 當日收盤價 (用於模擬時的基準)
            
        Returns: (value, data_source, is_simulated)
        """
        df = self.fetch_ohlcv_history(stock_code, 20)
        
        if df is not None and len(df) >= 10:  # 至少需要 10 天資料
            # 計算 Typical Price
            df['typical_price'] = (df['max'].astype(float) + 
                                   df['min'].astype(float) + 
                                   df['close'].astype(float)) / 3
            
            # 成交量 (Trading_Volume 是股數)
            df['volume'] = df['Trading_Volume'].astype(float)
            
            # VWAP = Σ(TP * Vol) / Σ(Vol)
            total_tp_vol = (df['typical_price'] * df['volume']).sum()
            total_vol = df['volume'].sum()
            
            if total_vol > 0:
                vwap = total_tp_vol / total_vol
                return (round(vwap, 2), 'fetched', 0)
        
        # 模擬: 基於收盤價 ±5% 範圍
        if close_price and close_price > 0:
            bounds = (close_price * 0.95, close_price * 1.05)
            simulated = round(self._simulate_value(stock_code, 'vwap_20d_approx', bounds), 2)
            return (simulated, 'simulated', 1)
        
        return (0.0, 'simulated', 1)
    
    def calculate_vwap_bias(self, stock_code: str, close_price: float) -> Tuple[float, str, int]:
        """
        計算 VWAP 乖離率 (Metric F)
        Formula: (Close - VWAP_20D) / VWAP_20D * 100
        
        Args:
            stock_code: 股票代碼
            close_price: 當日收盤價
            
        Returns: (value in %, data_source, is_simulated)
        """
        vwap, vwap_source, vwap_simulated = self.calculate_vwap_20d_approx(stock_code, close_price)
        
        if vwap > 0 and close_price > 0:
            bias = (close_price - vwap) / vwap * 100
            return (round(bias, 2), vwap_source, vwap_simulated)
        
        return (0.0, 'simulated', 1)
    
    # ========================================
    # Main Enrichment Method
    # ========================================
    
    def enrich_stock(self, stock_code: str, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        對單一股票進行籌碼進階指標計算
        
        Args:
            stock_code: 股票代碼
            stock_data: 現有的股票資料 dict，需包含:
                - close: 收盤價
                - volume: 成交量 (張)
                - volume_5d: 過去5日成交量 (張, 可選)
                
        Returns: 增加新欄位的 dict
        """
        close_price = stock_data.get('close', 0) or 0
        volume = stock_data.get('volume', 0) or 0
        
        # 計算 5 日平均成交量 (如果沒有提供，用當日成交量估算)
        volume_5d = stock_data.get('volume_5d', volume * 5) or (volume * 5)
        avg_volume_5d = volume_5d / 5 if volume_5d > 0 else volume
        
        # 用於追蹤是否有任何欄位被模擬
        any_simulated = 0
        sources = []
        
        # Metric A: Broker Buy Sell Diff
        broker_diff, src_a, sim_a = self.calculate_broker_buy_sell_diff(stock_code)
        any_simulated |= sim_a
        sources.append(src_a)
        
        # Metric B: Chip Concentration 5D
        chip_conc, src_b, sim_b = self.calculate_chip_concentration_5d(stock_code, volume_5d)
        any_simulated |= sim_b
        sources.append(src_b)
        
        # Metric C: SBL Sell Balance
        sbl_balance, src_c, sim_c = self.calculate_sbl_sell_balance(stock_code)
        any_simulated |= sim_c
        sources.append(src_c)
        
        # Metric D: Short Cover Days
        cover_days, src_d, sim_d = self.calculate_short_cover_days(stock_code, avg_volume_5d)
        any_simulated |= sim_d
        sources.append(src_d)
        
        # Metric E: VWAP 20D Approx
        vwap_20d, src_e, sim_e = self.calculate_vwap_20d_approx(stock_code, close_price)
        any_simulated |= sim_e
        sources.append(src_e)
        
        # Metric F: VWAP Bias
        vwap_bias, src_f, sim_f = self.calculate_vwap_bias(stock_code, close_price)
        any_simulated |= sim_f
        sources.append(src_f)
        
        # 決定整體 data_source
        overall_source = 'simulated' if any_simulated else 'fetched'
        if 'fetched' in sources and 'simulated' in sources:
            overall_source = 'partial'
        
        # 更新 stock_data
        enriched = stock_data.copy()
        enriched.update({
            'broker_buy_sell_diff': broker_diff,
            'chip_concentration_5d': chip_conc,
            'sbl_sell_balance': sbl_balance,
            'short_cover_days': cover_days,
            'vwap_20d_approx': vwap_20d,
            'vwap_bias': vwap_bias,
            'data_source': overall_source,
            'is_simulated': any_simulated,
        })
        
        return enriched
    
    def enrich_all(self, stock_data_dict: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """
        對所有股票進行籌碼進階指標計算
        
        Args:
            stock_data_dict: {stock_code: stock_data} 格式的資料
            
        Returns: 增加新欄位的資料 dict
        """
        enriched = {}
        total = len(stock_data_dict)
        
        for i, (code, data) in enumerate(stock_data_dict.items(), 1):
            print(f"    處理籌碼進階指標: {code} ({i}/{total})")
            enriched[code] = self.enrich_stock(code, data)
            time.sleep(0.2)  # 避免請求過快
        
        return enriched


def main():
    """測試用主程式"""
    import argparse
    
    parser = argparse.ArgumentParser(description='籌碼進階指標抓取器測試')
    parser.add_argument('--date', type=str, help='日期 (YYYYMMDD)')
    parser.add_argument('--stock', type=str, default='2330', help='股票代碼')
    parser.add_argument('--token', type=str, default=None, help='FinMind API token')
    
    args = parser.parse_args()
    
    # 預設使用今天
    if not args.date:
        from datetime import date
        args.date = date.today().strftime('%Y%m%d')
    
    print(f"\n[INFO] 測試籌碼進階指標 - {args.date} - {args.stock}")
    print("=" * 60)
    
    fetcher = ChipEnrichmentFetcher(args.date, args.token)
    
    # 模擬現有的 stock_data
    test_data = {
        'close': 580.0,
        'volume': 25000,
        'volume_5d': 120000,
    }
    
    enriched = fetcher.enrich_stock(args.stock, test_data)
    
    print(f"\n結果:")
    print(f"  Broker_Buy_Sell_Diff: {enriched['broker_buy_sell_diff']}")
    print(f"  Chip_Concentration_5D: {enriched['chip_concentration_5d']}%")
    print(f"  SBL_Sell_Balance: {enriched['sbl_sell_balance']:,} shares")
    print(f"  Short_Cover_Days: {enriched['short_cover_days']} days")
    print(f"  VWAP_20D_Approx: {enriched['vwap_20d_approx']}")
    print(f"  VWAP_Bias: {enriched['vwap_bias']}%")
    print(f"  Data Source: {enriched['data_source']}")
    print(f"  Is Simulated: {enriched['is_simulated']}")


if __name__ == '__main__':
    main()
