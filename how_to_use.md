# 台灣股市風險監控系統

## 專案結構

此專案已經過重構，結構如下：
- `src/`：所有的 Python 爬蟲與運算核心程式。
- `data/`：存放設定檔（如 `config/watchlist.json`）與原始快取資料（如 `raw/trading_days.json`）。
- `outputs/`：所有的程式產出報告都會集中於此，包含 `json/`、`monitor_xlsx/`、`txt/` 與 `reports/`。
- `docs/`：存放看盤筆記與圖表等文件。
- `web/`：視覺化網頁儀表板，用來以 HTML 檢視轉換後的 json 檔案。
- `main.py`：整合風險報告主要執行入口。

---

## 使用方式

```bash
cd TW_stock_risk_monitor
```

### 0. 一鍵執行所有報告 (run_all.py) ⭐ 推薦
一次產出台灣風險報告 + JSON/TXT + 全球市場與總經數據，統一指定日期：
```bash
# 使用今天的交易日
python run_all.py

# 指定日期
python run_all.py --date 20260416
```

### 1. 整合風險報告（推薦）
一鍵生成包含大盤、歷史統計與個股籌碼的完整 Excel 報告。
```bash
# 生成今天的報告
python main.py

# 生成指定日期的報告
python main.py --date 20260407 --output 20260407.xlsx

python main.py --date 20260121 --output 20260121.xlsx
```

輸出內容會儲存在 `outputs/monitor_xlsx/` 內：
- **總覽**：大盤指標（外資、投信、VIX、費半等）
- **詳細數據**：5日/20日歷史統計
- **個股籌碼**：自選股的籌碼流向與結構分析

---

### 2. 視覺化網頁儀表板 (Web Dashboard)
本專案包含了一個高質感的多頁面網頁儀表板，可直接瀏覽四類資料：
1. 確保已經產出近期的報告（透過 `python main.py` 或 `python src/global_market_monitor.py`）。
2. 啟動本地伺服器：
```bash
python web/server.py
```
3. 瀏覽器開啟 `http://localhost:8080`，即可透過上方 Tab 切換查看：
   - **台灣風險總覽** (`outputs/json/`)
   - **全球市場與總經** (`outputs/global_json/`)
   - **美股板塊資金** (`outputs/reports/`)
   - **策略選股報告** (`QD_twstock/result/`)

---

### 3. 個股籌碼監控（獨立執行）
```bash
python src/stock_monitor.py
python src/stock_monitor.py --date 20260205
```

#### 編輯自選股清單
修改 `data/config/watchlist.json`，在 `watchlist` 陣列中加入想監控的股票代號與名稱：
```json
{
  "watchlist": [
    {"code": "2330", "name": "台積電"},
    {"code": "2454", "name": "聯發科"}
  ]
}
```

---

### 4. 個股多日資料回補 (backfill_stock.py)
專為新加入自選股或想回測特定股票所設計的工具。

**特點：**
- 自動略過休假日。
- 支援動態合併至現有報表 (`--merge`)，不會覆蓋或錯置進階欄位。

```bash
# 產生獨立包含多天資料（按天分頁）的 Excel
python src/backfill_stock.py --codes 6669 6223 --days 20 --date 20260226

# 將回補資料直接併入每天已存在的 outputs/monitor_xlsx/YYYYMMDD.xlsx 中
python src/backfill_stock.py --codes 3167 --days 30 --date 20260410 --merge
```

---

### 5. 盤中即時監控 (intraday_monitor.py)
擷取大盤、期貨及自選股(`data/config/watchlist.json`)的最新盤中走勢與漲跌百分比，並將結果自動附加到 `docs/notes/看盤筆記/MMDD.md` 內。
```bash
python src/intraday_monitor.py
```

---

### 6. 批量執行指令工具 (batch_runner.py)
用來連續多天自動執行帶有日期的指令，自動略過假日，方便一次性抓取多天報告。

```bash
# 連續取得過去 30 天的整合風險報告
python src/batch_runner.py --cmd "python main.py --date {date} --output {date}.xlsx" --days 30 --end-date 20260409

# 從指定日期往前推 30 天執行
python src/batch_runner.py --cmd "python main.py --date {date} --output {date}.xlsx" --days 30 --end-date 20260409
```

---

### 7. 美股 11 大板塊資金流向與輪動分析 (us_sector_funds_flow.py)
抓取美股 11 大板塊 ETF 與大盤 (SPY) 過去 6 個月的歷史數據。
```bash
python src/us_sector_funds_flow.py
```
執行後會在 `outputs/reports/` 資料夾下自動生成帶有時間流水號的 HTML 分析報告。

---

### 8. 全球市場與總經數據監控 (global_market_monitor.py)
抓取美國、歐洲、亞太股市指數、原物料、匯率及聯準會 FRED 總經數據。
```bash
python src/global_market_monitor.py
```
執行後會在 `outputs/global_json/` 與 `outputs/global_xlsx/` 資料夾下生成 `global_market_YYYYMMDD.json` 及 `.xlsx`，生成的 JSON 檔案也可直接拖拉入 Web Dashboard 查看。

---

### 其他輔助工具
```bash
# 單日風險監控 (僅顯示於終端機)
python src/risk_monitor.py

# 多日歷史統計
python src/risk_monitor_history.py 20260205

# 批量執行時也會一併產出所有 txt for notebooklm
python src/excel_to_json.py

# 若你想單獨把某個現有的 json 轉為 txt，可使用新參數
python src/excel_to_json.py --json2txt outputs/json/20260205.json
```

## 注意事項
1. **資料更新時間**：融資融券餘額通常約 **21:30** 後更新，建議在此之後執行以取得完整數據。
2. **避免頻繁請求**：證交所 API 有流量限制，過度頻繁執行可能會導致 IP 被鎖定，建議間隔 1-2 小時。
3. **自訂監控**：隨時可以編輯 `data/config/watchlist.json` 來增減監控的個股。