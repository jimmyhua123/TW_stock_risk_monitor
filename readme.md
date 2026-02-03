# 台灣股市風險監控系統

## 使用方式

```bash
cd TW_stock_risk_monitor
```

### 整合報告（大盤 + 歷史統計 + 個股籌碼）
```bash
python main.py --date 20260203 --output 20260203.xlsx
```

輸出 Excel 包含三個工作表：
- **總覽**：大盤指標（外資、投信、VIX、費半等）
- **詳細數據**：5日/20日歷史統計
- **個股籌碼**：自選股的籌碼流向與結構分析

---

### 個股籌碼監控（獨立執行）
```bash
python stock_monitor.py
python stock_monitor.py --date 20260203
```

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