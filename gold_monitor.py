#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
黃金監控系統 (Gold Monitor)
監控黃金期貨、現貨、台股黃金ETF，提供槓桿ETF持倉切換建議
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')


class GoldMonitor:
    """黃金市場監控與分析系統"""
    
    def __init__(self):
        """初始化監控標的"""
        self.symbols = {
            'GC=F': 'COMEX黃金期貨',
            'XAUUSD=X': '黃金現貨(美元)',
            '00708L.TW': '元大S&P黃金正2',
            '00635U.TW': '元大S&P黃金',
            'TWD=X': '美元/台幣',
            'DX-Y.NYB': '美元指數'
        }
        self.data = {}
        self.market_data = {}
    
    def fetch_data(self):
        """抓取所有標的即時數據"""
        print("📊 正在抓取黃金市場數據...\n")
        
        for symbol, name in self.symbols.items():
            try:
                ticker = yf.Ticker(symbol)
                
                # 獲取歷史數據（最近5天用於計算變化）
                hist = ticker.history(period='5d')
                
                if hist.empty:
                    print(f"⚠️  {name} ({symbol}) - 無數據")
                    continue
                
                # 取得最新價格
                current_price = hist['Close'].iloc[-1]
                
                # 計算今日漲跌幅
                if len(hist) >= 2:
                    prev_close = hist['Close'].iloc[-2]
                    change_pct = ((current_price - prev_close) / prev_close) * 100
                else:
                    change_pct = 0
                
                # 計算5日波動率
                if len(hist) >= 5:
                    volatility = hist['Close'].pct_change().std() * 100
                else:
                    volatility = 0
                
                self.data[symbol] = {
                    'name': name,
                    'price': current_price,
                    'change_pct': change_pct,
                    'volatility_5d': volatility,
                    'volume': hist['Volume'].iloc[-1] if 'Volume' in hist.columns else 0
                }
                
                print(f"✅ {name}: ${current_price:.2f} ({change_pct:+.2f}%)")
                
            except Exception as e:
                print(f"❌ {name} ({symbol}) 抓取失敗: {str(e)}")
                self.data[symbol] = None
        
        print("\n" + "="*60 + "\n")
    
    def calculate_metrics(self):
        """計算關鍵指標"""
        print("🔍 計算關鍵指標...\n")
        
        self.market_data = {}
        
        # 1. 理論現貨台幣價
        if self.data.get('XAUUSD=X') and self.data.get('TWD=X'):
            gold_spot_usd = self.data['XAUUSD=X']['price']
            usd_twd = self.data['TWD=X']['price']
            theoretical_twd_price = gold_spot_usd * usd_twd
            
            self.market_data['理論現貨台幣價(元/盎司)'] = theoretical_twd_price
            print(f"💰 理論現貨台幣價: ${theoretical_twd_price:,.0f} TWD/ozs")
        
        # 2. 槓桿追蹤效率
        if self.data.get('00708L.TW') and self.data.get('GC=F'):
            etf_change = self.data['00708L.TW']['change_pct']
            futures_change = self.data['GC=F']['change_pct']
            
            expected_change = futures_change * 2
            tracking_efficiency = (etf_change / expected_change * 100) if expected_change != 0 else 0
            tracking_error = etf_change - expected_change
            
            self.market_data['槓桿追蹤效率(%)'] = tracking_efficiency
            self.market_data['追蹤誤差(%)'] = tracking_error
            
            print(f"📈 00708L 漲跌幅: {etf_change:+.2f}%")
            print(f"📊 GC=F 期貨漲跌幅: {futures_change:+.2f}% (理論2倍: {expected_change:+.2f}%)")
            print(f"⚡ 追蹤效率: {tracking_efficiency:.1f}% (追蹤誤差: {tracking_error:+.2f}%)")
        
        # 3. 美元指數強弱
        if self.data.get('DX-Y.NYB'):
            dxy_change = self.data['DX-Y.NYB']['change_pct']
            dxy_price = self.data['DX-Y.NYB']['price']
            
            self.market_data['美元指數變化(%)'] = dxy_change
            self.market_data['美元指數水平'] = dxy_price
            
            dxy_status = "🔴 強勢" if dxy_change > 0.5 else "🟢 弱勢" if dxy_change < -0.5 else "🟡 中性"
            print(f"\n💵 美元指數: {dxy_price:.2f} ({dxy_change:+.2f}%) - {dxy_status}")
        
        # 4. 黃金期貨波動率
        if self.data.get('GC=F'):
            volatility = self.data['GC=F']['volatility_5d']
            self.market_data['黃金5日波動率(%)'] = volatility
            
            vol_status = "🔥 高波動" if volatility > 1.5 else "📉 低波動"
            print(f"📊 黃金期貨5日波動率: {volatility:.2f}% - {vol_status}")
        
        print("\n" + "="*60 + "\n")
    
    def generate_recommendation(self):
        """生成操作建議"""
        print("💡 操作建議分析\n")
        
        recommendations = []
        action = "觀望"  # 預設
        
        # 獲取關鍵數據
        gc_change = self.data.get('GC=F', {}).get('change_pct', 0)
        gc_volatility = self.data.get('GC=F', {}).get('volatility_5d', 0)
        dxy_change = self.data.get('DX-Y.NYB', {}).get('change_pct', 0)
        tracking_error = self.market_data.get('追蹤誤差(%)', 0)
        
        # 趨勢判斷
        print("【趨勢判斷】")
        if gc_change > 1.0:
            trend = "🚀 強勢上漲"
            recommendations.append("黃金期貨強勢上漲，適合續抱 00708L 放大收益")
            action = "續抱 00708L"
        elif gc_change < -1.0:
            trend = "📉 明顯下跌"
            recommendations.append("黃金期貨下跌，槓桿ETF損耗加劇，建議立即切換至 AU9901 或 00635U")
            action = "⚠️ 立即切換至 AU9901"
        elif abs(gc_change) < 0.3:
            trend = "😐 盤整震盪"
            recommendations.append("黃金期貨盤整，槓桿損耗風險高，建議切換至 AU9901 避開時間價值流失")
            action = "建議切換至 AU9901"
        else:
            trend = "🔄 震盪走勢"
            recommendations.append("黃金期貨震盪，可觀察後再決定")
        
        print(f"  COMEX黃金期貨趨勢: {trend} ({gc_change:+.2f}%)")
        
        # 宏觀風險
        print("\n【宏觀風險】")
        if dxy_change > 0.5:
            print(f"  ⚠️  美元指數強勢上漲 ({dxy_change:+.2f}%)，黃金承壓下行風險高")
            recommendations.append("美元走強，黃金通常承壓，建議降低槓桿或轉入現貨")
            if action == "續抱 00708L":
                action = "謹慎續抱 00708L (注意美元風險)"
        elif dxy_change < -0.5:
            print(f"  ✅ 美元指數走弱 ({dxy_change:+.2f}%)，利好黃金上漲")
            recommendations.append("美元走弱，利好黃金，槓桿ETF表現可能更佳")
        else:
            print(f"  ➖ 美元指數中性 ({dxy_change:+.2f}%)，對黃金影響有限")
        
        # 波動率警示
        print("\n【波動率警示】")
        if gc_volatility > 1.5:
            print(f"  🔥 黃金波動率偏高 ({gc_volatility:.2f}%)，槓桿ETF風險較高")
            recommendations.append("高波動環境下，槓桿ETF可能產生較大追蹤誤差")
        else:
            print(f"  ✅ 黃金波動率正常 ({gc_volatility:.2f}%)")
        
        # 追蹤效率檢查
        print("\n【追蹤效率檢查】")
        if abs(tracking_error) > 1.0:
            print(f"  ⚠️  追蹤誤差較大 ({tracking_error:+.2f}%)，可能存在折溢價風險")
            recommendations.append("00708L 追蹤誤差偏大，留意是否有異常溢價(適合賣出)或折價")
        else:
            print(f"  ✅ 追蹤效率正常 (誤差: {tracking_error:+.2f}%)")
        
        # 最終建議
        print("\n" + "="*60)
        print(f"\n🎯 【最終操作建議】: {action}")
        print("\n📋 【理由說明】:")
        for i, rec in enumerate(recommendations, 1):
            print(f"  {i}. {rec}")
        
        print("\n" + "="*60 + "\n")
        
        return action, recommendations
    
    def generate_markdown_report(self):
        """生成 Markdown 報告"""
        print("📄 生成 Markdown 報告...\n")
        
        report = []
        report.append("# 🏅 黃金市場監控報告")
        report.append(f"\n**報告時間**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # 即時價格表格
        report.append("## 📊 即時價格與漲跌幅\n")
        report.append("| 標的代碼 | 名稱 | 最新價格 | 今日漲跌幅 | 5日波動率 |")
        report.append("|---------|------|---------|-----------|----------|")
        
        for symbol in ['GC=F', 'XAUUSD=X', '00708L.TW', '00635U.TW', 'TWD=X', 'DX-Y.NYB']:
            if self.data.get(symbol):
                d = self.data[symbol]
                price_format = f"${d['price']:,.2f}"
                change_format = f"{d['change_pct']:+.2f}%"
                vol_format = f"{d['volatility_5d']:.2f}%"
                report.append(f"| {symbol} | {d['name']} | {price_format} | {change_format} | {vol_format} |")
        
        # 關鍵指標
        report.append("\n## 🔍 關鍵指標分析\n")
        report.append("| 指標名稱 | 數值 |")
        report.append("|---------|------|")
        
        if '理論現貨台幣價(元/盎司)' in self.market_data:
            val = self.market_data['理論現貨台幣價(元/盎司)']
            report.append(f"| 理論現貨台幣價 (元/盎司) | ${val:,.0f} TWD |")
        
        if '槓桿追蹤效率(%)' in self.market_data:
            eff = self.market_data['槓桿追蹤效率(%)']
            err = self.market_data['追蹤誤差(%)']
            report.append(f"| 00708L 槓桿追蹤效率 | {eff:.1f}% |")
            report.append(f"| 00708L 追蹤誤差 | {err:+.2f}% |")
        
        if '美元指數變化(%)' in self.market_data:
            dxy_chg = self.market_data['美元指數變化(%)']
            dxy_lvl = self.market_data['美元指數水平']
            report.append(f"| 美元指數 (DXY) | {dxy_lvl:.2f} ({dxy_chg:+.2f}%) |")
        
        if '黃金5日波動率(%)' in self.market_data:
            vol = self.market_data['黃金5日波動率(%)']
            report.append(f"| 黃金期貨 5日波動率 | {vol:.2f}% |")
        
        # 操作建議
        action, recommendations = self.generate_recommendation()
        
        report.append("\n## 💡 操作建議總結\n")
        report.append(f"### 🎯 建議行動: **{action}**\n")
        report.append("#### 📋 分析理由:\n")
        for i, rec in enumerate(recommendations, 1):
            report.append(f"{i}. {rec}")
        
        # 風險提示
        report.append("\n---\n")
        report.append("### ⚠️ 風險提示\n")
        report.append("- **槓桿ETF風險**: 00708L 為 2 倍槓桿 ETF，適合短期操作，長期持有會有時間損耗")
        report.append("- **匯率風險**: 黃金以美元計價，台幣兌美元波動會影響台股黃金ETF表現")
        report.append("- **追蹤誤差**: ETF 可能與標的資產產生折溢價，需注意盤中價格異常")
        report.append("- **市場風險**: 本報告僅供參考，投資決策請自行判斷並承擔風險\n")
        
        markdown_text = "\n".join(report)
        
        # 輸出到文件
        output_file = f"gold_monitor_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(markdown_text)
        
        print(f"✅ 報告已保存至: {output_file}\n")
        print("="*60)
        print(markdown_text)
        print("="*60)
        
        return markdown_text
    
    def run(self):
        """執行完整監控流程"""
        print("\n" + "="*60)
        print("🏅 黃金市場監控系統啟動")
        print("="*60 + "\n")
        
        # 1. 抓取數據
        self.fetch_data()
        
        # 2. 計算指標
        self.calculate_metrics()
        
        # 3. 生成報告
        self.generate_markdown_report()


def main():
    """主程式入口"""
    monitor = GoldMonitor()
    monitor.run()


if __name__ == "__main__":
    main()
