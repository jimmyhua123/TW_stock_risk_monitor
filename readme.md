# 台灣股市風險監控系統

## 使用方式

```bash
cd TW_stock_risk_monitor
```

### 整合報告（大盤 + 歷史統計 + 個股籌碼 + 進階指標）
```bash
python main.py --date 20260205 --output 20260205.xlsx


python main.py --date 20260203 --output 20260204.xlsx --token YOUR_FINMIND_TOKEN
```

輸出 Excel 包含三個工作表：
- **總覽**：大盤指標（外資、投信、VIX、費半等）
- **詳細數據**：5日/20日歷史統計
- **個股籌碼**：自選股的籌碼流向、結構分析與進階籌碼指標

---

### 個股籌碼監控（獨立執行）
```bash
python stock_monitor.py
python stock_monitor.py --date 20260203
python stock_monitor.py --date 20260203 --csv  # 同時輸出 CSV
python stock_monitor.py --token YOUR_FINMIND_TOKEN  # 使用 FinMind API 抓取分點資料
```

#### 進階籌碼指標
新增 6 項進階指標（模式：fetch_then_simulate_missing）：
- **Broker_Buy_Sell_Diff**: 買賣券商家數差
- **Chip_Concentration_5D**: 5日籌碼集中度 (%)
- **SBL_Sell_Balance**: 借券賣出餘額 (股)
- **Short_Cover_Days**: 短回補天數
- **VWAP_20D_Approx**: 20日近似VWAP
- **VWAP_Bias**: VWAP乖離率 (%)

> 注意：分點資料需 FinMind sponsor 會員，無 token 時將使用模擬值

#### 編輯自選股清單
修改 `watchlist.json`：
```json
{
  "watchlist": [
    {"code": "2330", "name": "台積電"},
    {"code": "2454", "name": "聯發科"}
  ]
}
```

---

### 黃金動態監控
```bash
python gold_monitor.py
python gold_monitor.py --date 2026-01-28
```

---

### 單日/多日數據
```bash
# 單日風險監控
python risk_monitor.py --date 20260203

# 多日歷史統計
python risk_monitor_history.py 20260203
```

### 輔助工具
#### Excel 轉 JSON (AI 易讀格式)
將產生的 Excel 報表轉換為 JSON 格式，方便丟給 AI (如 ChatGPT/Claude) 進行分析。
```bash
python excel_to_json.py monitor_xlsx/20260205.xlsx
```

## 注意事項
1. 融資融券餘額資料 要 21:30 後才會有
2. 執行太多次會被 台灣證券交易所 會鎖 IP 隔1-2小時後再執行
3. 可以自己在watchlist.json 新增想監控的股票