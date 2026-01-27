使用方式
```
cd TW_stock_risk_monitor
```
抓指定日期（例如 2026/01/20）
```
python risk_monitor.py --date 20260123
```
不指定日期（用今天，週末自動回退）
```
python risk_monitor.py
```

# 單日數據
python risk_monitor.py --date 20260123
# 多日數據測試
python risk_monitor_history.py 20260123
# 整合報告（單日 + 多日）
python main.py --date 20260123 --output report.xlsx# TW_stock_risk_monitor
