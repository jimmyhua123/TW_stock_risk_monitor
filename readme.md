# 台灣股市風險監控系統

## 使用方式

```bash
cd TW_stock_risk_monitor
```

### 1. 整合風險報告（推薦）
一鍵生成包含大盤、歷史統計與個股籌碼的完整 Excel 報告。
```bash
# 生成今天的報告
python main.py

# 生成指定日期的報告
python main.py --date 20260302 --output 20260302.xlsx

python main.py --date 20260211 --output 20260211.xlsx

```

輸出內容：
- **總覽**：大盤指標（外資、投信、VIX、費半等）
- **詳細數據**：5日/20日歷史統計
- **個股籌碼**：自選股的籌碼流向與結構分析

---

### 2. 個股籌碼監控（獨立執行）
```bash
python stock_monitor.py
python stock_monitor.py --date 20260205
python stock_monitor.py --csv  # 同時輸出 CSV
```

#### 編輯自選股清單
修改 `watchlist.json`，在 `watchlist` 陣列中加入想監控的股票代號與名稱：
```json
{
  "watchlist": [
    {"code": "2330", "name": "台積電"},
    {"code": "2454", "name": "聯發科"}
  ]
}
```

---

### 3. 個股多日資料回補 (backfill_stock.py)
專為新加入自選股或想回測特定股票所設計的工具。

**特點：**
- 自動略過休假日。
- 支援動態合併至現有報表 (`--merge`)，不會覆蓋或錯置進階欄位。
- 支援區分與輸出股票的「市場別」(上市/上櫃)。
- 即使只輸入代號，系統也會自動尋找名稱補上。

```bash
# 產生獨立包含多天資料（按天分頁）的 Excel
python backfill_stock.py --codes 6669 6223 --days 20 --date 20260226

# 將回補資料直接併入每天已存在的 monitor_xlsx/YYYYMMDD.xlsx 中
python backfill_stock.py --codes 3138 --days 20 --date 20260302 --merge
```

---

### 4. 黃金動態監控
```bash
python gold_monitor.py
python gold_monitor.py --date 2026-02-23
```

---

### 其他輔助工具
```bash
# 單日風險監控 (僅顯示於終端機)
python risk_monitor.py

# 多日歷史統計
python risk_monitor_history.py 20260205

# 批量轉換  Excel 轉 JSON (給AI 分析用)
python excel_to_json.py
```

## 注意事項
1. **資料更新時間**：融資融券餘額通常約 **21:30** 後更新，建議在此之後執行以取得完整數據。
2. **避免頻繁請求**：證交所 API 有流量限制，過度頻繁執行可能會導致 IP 被鎖定，建議間隔 1-2 小時。
3. **自訂監控**：隨時可以編輯 `watchlist.json` 來增減監控的個股。