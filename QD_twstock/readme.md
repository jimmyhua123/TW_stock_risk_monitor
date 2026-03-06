# 台灣股市 看 資金流向，選產業 再從該產業裡面篩選

## 使用方式

```bash
cd TW_stock_risk_monitor/QD_twstock
```

### 1. 
```bash
python top_down_strategy.py
```

### 2. 指定日期執行 (回測或補跑資料使用)
```bash
python top_down_strategy.py --20260305

```

### 3. 輸出在result資料夾

我覺得這策略可行但需要優化，比如長時間 資金流向 等等