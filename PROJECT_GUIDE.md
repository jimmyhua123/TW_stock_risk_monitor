# TW Stock Risk Monitor 使用指南

這個專案定位是「個人化台股研究助理」：你先把感興趣的股票、族群、題材與研究假設放進 `data/config/watchlist.json`，程式每天抓取台股、籌碼、衍生品、全球市場與既有報表資料，再輸出 Excel、JSON、文字報告與 Web Dashboard。

它不是券商下單系統，也不是投資建議工具。它的價值在於把你自己的觀察清單變成每天可比較、可追蹤、可丟進 NotebookLM/筆記系統的研究材料。

## 快速開始

1. 安裝 Python 依賴：

```bash
pip install -r requirements.txt
```

2. 產生指定日期的完整報告：

```bash
python run_all.py --date 20260612
```

3. 每日看盤建議使用較輕量的日更流程：

```bash
python daily_run.py --date 20260612
```

4. 低頻或月底更新較重資料：

```bash
python monthly_run.py --date 20260612
```

5. 盤中即時觀察 watchlist 漲跌：

```bash
python src/intraday_monitor.py
```

6. 只產生 watchlist 族群分析：

```bash
python src/group_monitor.py --date 20260611
```

7. 開啟 Web Dashboard：

```bash
python web/server.py
```

瀏覽器開啟 `http://localhost:8080`。

## Watchlist 格式

最小格式仍然支援，只要 `code` 和 `name`。族群分析會優先從 `outputs/coverage_json/coverage_YYYYMMDD.json` 的 sector、industry、themes 自動推導 `groups`；其他欄位可以保持空白。

```json
{
  "watchlist": [
    {"code": "2330", "name": "台積電"},
    {"code": "2454", "name": "聯發科"}
  ]
}
```

如果你想自己控制族群，也可以加入 `groups`、研究假設、同業與風險筆記：

```json
{
  "watchlist": [
    {
      "code": "2330",
      "name": "台積電",
      "groups": ["半導體", "AI", "先進製程"],
      "thesis": "AI 伺服器需求與先進製程報價能力",
      "peers": ["2454", "3034", "3661"],
      "risk_notes": ["匯率", "美國科技股修正", "資本支出循環"],
      "priority": "core"
    }
  ]
}
```

可參考範例檔：

```bash
data/config/watchlist.example.json
```

欄位說明：

- `code`：股票代號，必要。程式會把 `50` 和 `0050` 視為同一檔。
- `name`：股票名稱，必要。
- `groups`：族群或題材，可放多個，例如 `["AI", "散熱", "伺服器"]`。未填時會自動推導。
- `thesis`：你為什麼關注這檔股票。
- `peers`：同業或可比較標的。
- `risk_notes`：你想每天提醒自己的風險。
- `priority`：自訂重要性，例如 `core`、`watch`、`reference`。

## 主要命令

| 命令 | 用途 |
| --- | --- |
| `python run_all.py --date YYYYMMDD` | 一鍵產出主要報告、JSON/TXT、族群分析與補充資料 |
| `python daily_run.py --date YYYYMMDD` | 每日看盤常用流程，略過不一定需要日更的全球市場、股期換月與題材補充 |
| `python daily_run.py --date YYYYMMDD --refresh-coverage` | 每日流程加上題材補充刷新；新增 watchlist 股票或想更新自動 groups 時使用 |
| `python daily_run.py --date YYYYMMDD --force-refresh` | 即使當日 JSON 已存在，也重新抓取日更資料 |
| `python monthly_run.py --date YYYYMMDD` | 低頻/月度刷新全球市場、題材補充與股期換月 |
| `python monthly_run.py --date YYYYMMDD --include-sector-flow` | 低頻流程加上較重的美股產業資金流報告 |
| `python src/intraday_monitor.py` | 盤中即時觀察 watchlist 漲跌與輸出 MMDD 盤中筆記 |
| `python main.py --date YYYYMMDD --output YYYYMMDD.xlsx` | 產出台股風險 Excel |
| `python src/excel_to_json.py outputs/monitor_xlsx/YYYYMMDD.xlsx` | 將 Excel 轉成 JSON/TXT |
| `python src/group_monitor.py --date YYYYMMDD` | 依 watchlist 產生族群分析 |
| `python src/global_market_monitor.py --date YYYYMMDD` | 產生全球市場與總經資料 |
| `python src/derivatives_monitor.py --date YYYYMMDD` | 產生期貨與選擇權風險資料 |
| `python src/coverage_enrichment.py --date YYYYMMDD` | 產生題材與產業補充 |
| `python web/server.py` | 啟動本機 Dashboard |
| `python -m unittest discover -v` | 跑單元測試 |

## 輸出位置

| 目錄 | 內容 |
| --- | --- |
| `outputs/monitor_xlsx/` | 台股風險 Excel |
| `outputs/json/` | 台股風險 JSON |
| `outputs/txt/` | 台股風險文字稿 |
| `outputs/group_json/` | watchlist 族群分析 JSON |
| `outputs/group_txt/` | watchlist 族群分析文字報告 |
| `outputs/global_json/` | 全球市場 JSON |
| `outputs/derivatives_json/` | 期貨選擇權 JSON |
| `outputs/coverage_json/` | 題材補充 JSON |
| `docs/notes/每日看盤筆記/` | `daily_briefing.py` 產出的每日結構化 briefing |
| `docs/notes/看盤筆記/` | 你原本的即時盤中漲跌幅與手動看盤筆記 |

## Watchlist 族群分析怎麼看

`src/group_monitor.py` 會讀：

- `data/config/watchlist.json`
- `outputs/json/YYYYMMDD.json` 裡的 `個股籌碼`
- `outputs/coverage_json/coverage_YYYYMMDD.json` 或最新 coverage 檔，用來在 watchlist 只放 `code/name` 時自動補 groups

它會輸出：

- 每個族群的平均分數與狀態
- 族群平均漲跌幅
- 外資、投信、自營商、融資合計
- 領先股與需留意股票
- 你在 watchlist 裡寫的研究假設與風險筆記
- 缺資料股票

分數是研究排序輔助，不是買賣建議。它目前主要根據漲跌幅、MA20 乖離、外資/投信/自營商、融資增減做粗略評估。

## 資料準確度與限制

這個專案使用 TWSE、TPEx、TAIFEX、yfinance 等外部資料來源。它適合做研究輔助，但需要注意：

- 外部 API 可能延遲、缺值或改版。
- 海外市場資料來自 yfinance，和正式付費資料源可能有差異。
- 若每日原始 JSON 缺某檔股票，族群分析會標成缺資料。
- 報告中的分數是排序與提醒，不代表基本面估值或交易訊號。
- 重要決策前仍應回查官方交易所、券商或付費資料源。

## 建議工作流

1. 平常看到有興趣的股票或題材，先補進 `data/config/watchlist.json`。
2. 可以只放 `code/name`；程式會用 coverage 資料自動推導 groups。
3. 如果你想手動控制，也可以用 `groups` 把股票歸到族群，例如 AI、散熱、PCB、半導體設備。
4. 用 `thesis` 寫下你關注它的理由，用 `risk_notes` 寫下你想每天提醒自己的風險。
5. 盤中需要快速看 watchlist 漲跌時跑：

```bash
python src/intraday_monitor.py
```

6. 收盤後跑日常流程：

```bash
python daily_run.py --date YYYYMMDD
```

7. 如果你剛新增 watchlist 股票，想讓程式重新抓題材並推導 groups：

```bash
python daily_run.py --date YYYYMMDD --refresh-coverage
```

8. 每月或低頻更新較重資料時跑：

```bash
python monthly_run.py --date YYYYMMDD
```

9. 先讀 `outputs/group_txt/group_YYYYMMDD.txt`，看今天哪個族群最強、哪幾檔需要追蹤。
10. 再打開 Excel/Web Dashboard 看細節。

`daily_run.py` 會優先使用既有輸出，避免同一天重複打 API：

- 已有 `outputs/json/YYYYMMDD.json` 時，不重跑 `main.py` 和 `excel_to_json.py`。
- 已有 `outputs/derivatives_json/derivatives_YYYYMMDD.json` 時，不重跑衍生品抓取。
- 已有 `outputs/coverage_json/coverage_YYYYMMDD.json` 時，不重跑題材補充。
- `group_monitor.py` 和 `daily_briefing.py` 會使用上述既有資料做本地分析。

如果資料源當天有修正，或你想強制重抓，使用 `--force-refresh`。

## 開發與測試

目前測試使用標準庫 `unittest`：

```bash
python -m unittest discover -v
```

若安裝了 `pytest`，也可以：

```bash
python -m pytest
```

新增功能時，建議先補測試，再改實作。尤其是資料解析、代號正規化、JSON 輸出格式與風險分數這類邏輯，應保持可回歸測試。
