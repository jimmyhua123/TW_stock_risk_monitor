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
python top_down_strategy.py --20260319

```

### 3. 輸出在result資料夾

我覺得這策略可行但需要優化，比如長時間 資金流向 等等

### 4. 批量執行指令工具 (batch_runner.py)
用來連續多天自動執行帶有日期的指令，自動略過假日，方便一次性抓取多天報告。

