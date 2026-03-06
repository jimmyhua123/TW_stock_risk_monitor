#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量執行指令小程式 Batch Runner
用來連續多天執行帶有日期的指令，例如：
python batch_runner.py --cmd "python main.py --date {date} --output {date}.xlsx" --days 30
"""

import os
import sys
import argparse
import subprocess
import time
from datetime import datetime

# 嘗試載入現有的交易日查詢函數
try:
    from risk_monitor import get_trading_date
    from risk_monitor_history import get_previous_trading_days
except ImportError:
    print("[ERROR] 無法載入 risk_monitor 或 risk_monitor_history 模組，請確保在 TW_stock_risk_monitor 目錄下執行。")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='批量執行指令工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 跑過去 30 天的 main.py
  python batch_runner.py --cmd "python main.py --date {date} --output 2026_{date}.xlsx" --days 30

  # 從指定日期 (20260301) 往前推 5 天執行
  python batch_runner.py --cmd "python main.py --date {date}" --days 5 --end-date 20260301
        """
    )

    parser.add_argument('--cmd', type=str, required=True,
                        help='要執行的指令模板，例如 "python main.py --date {date}"，其中的 {date} 會被自動替換為 YYYYMMDD 格式的日期')
    parser.add_argument('--days', type=int, default=1,
                        help='要跑幾個交易日 (預設: 1)')
    parser.add_argument('--end-date', type=str, default=None,
                        help='結束日期 YYYYMMDD (不指定則使用最新交易日)')
    parser.add_argument('--sleep', type=int, default=5,
                        help='每次執行間隔的秒數 (預設: 5秒，避免觸發 API 限制)')
    parser.add_argument('--dry-run', action='store_true',
                        help='測試模式：只印出會執行的指令，但不實際執行')

    args = parser.parse_args()

    # 確認是否包含 {date} 模板
    if '{date}' not in args.cmd:
        print("[WARNING] 您的 --cmd 指令中沒有包含 '{date}'，這會導致每次跑的指令都一樣喔！")
        time.sleep(2)

    # 取得結束日期 (如果有指定，則直接用；沒指定則取得最新交易日)
    if args.end_date:
        # 單純格式驗證
        try:
            datetime.strptime(args.end_date, '%Y%m%d')
            end_date_str = args.end_date
        except ValueError:
            print("[ERROR] 日期格式錯誤，請輸入 YYYYMMDD，例如 20260301")
            sys.exit(1)
    else:
        end_date_str = get_trading_date()

    print(f"[INFO] 準備開始批量執行...")
    print(f"  > 目標天數: {args.days} 個交易日")
    print(f"  > 結束日期: {end_date_str}")
    
    # 取得前 N 個交易日列表 (舊到新)
    # 這裡將 buffer_days 設小一點即可，因為我們主要依賴 risk_monitor_history 幫我們找有開市的日子
    trading_dates = get_previous_trading_days(end_date_str, args.days, buffer_days=15)
    
    # get_previous_trading_days 會給我們 target_date 往前推天數的 list
    # 取最後的 args.days 筆就好，因為可能超過
    trading_dates = trading_dates[-args.days:]

    print(f"[INFO] 即將執行的日期列表 (共 {len(trading_dates)} 天):")
    for d in trading_dates:
        print(f"  - {d}")
    print("-" * 50)

    # 開始執行
    for i, date_str in enumerate(trading_dates, 1):
        # 將 {date} 替換成真實的日期
        run_cmd = args.cmd.format(date=date_str)
        
        print(f"\n[{i}/{len(trading_dates)}] 正在執行日期: {date_str} ...")
        print(f"  > 執行指令: {run_cmd}")

        if args.dry_run:
            print("  > [Dry Run] 跳過實際執行")
            continue

        try:
            # 實際執行
            result = subprocess.run(run_cmd, shell=True, check=True)
            print(f"  > [OK] 執行成功 ({date_str})")
        except subprocess.CalledProcessError as e:
            print(f"  > [ERROR] 執行失敗，回傳碼: {e.returncode}")
            # 可以選擇中斷或繼續，這裡選擇繼續，但提示使用者
            print(f"  > [WARNING] 發生錯誤，但仍將繼續執行下一天的指令...")
        
        # 間隔休息 (最後一天不用等)
        if i < len(trading_dates) and args.sleep > 0 and not args.dry_run:
            print(f"  > 休息 {args.sleep} 秒...")
            time.sleep(args.sleep)

    print("\n[SUCCESS] 批量執行任務完成！")


if __name__ == '__main__':
    main()
