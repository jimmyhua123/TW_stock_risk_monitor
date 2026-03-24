#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一鍵執行所有報告生成工具 (Run All)
統一指定日期，依序執行：
  1. main.py           → 台灣風險報告 (Excel)
  2. excel_to_json.py   → 轉換為 JSON + TXT
  3. global_market_monitor.py → 全球市場與總經數據
  4. top_down_strategy.py    → QD策略選股報告
"""

import os
import sys
import subprocess
import argparse
from datetime import datetime

# 專案根目錄
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable  # 使用與本腳本相同的 Python 解譯器


def run_step(step_num, description, cmd, cwd=None):
    """執行一個步驟，印出結果"""
    work_dir = cwd or PROJECT_ROOT
    print(f"\n{'='*60}")
    print(f" 步驟 {step_num}：{description}")
    print(f" 指令：{' '.join(cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=work_dir)
    if result.returncode != 0:
        print(f"[WARNING] 步驟 {step_num} 回傳非零代碼: {result.returncode}，繼續執行...")
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description='一鍵執行所有報告生成工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  # 使用今天的交易日
  python run_all.py

  # 指定日期
  python run_all.py --date 20260320
        """
    )
    parser.add_argument('--date', type=str, default=None,
                        help='指定日期 YYYYMMDD（不指定則使用最新交易日）')
    args = parser.parse_args()

    # 日期參數
    date_args = ['--date', args.date] if args.date else []
    date_str = args.date or '最新交易日'

    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  一鍵執行所有報告 — 日期: {date_str:<17s} ║")
    print(f"╚══════════════════════════════════════════════╝")

    # --- 步驟 1: 台灣風險報告 ---
    output_xlsx = f"{args.date}.xlsx" if args.date else "risk_report.xlsx"
    cmd1 = [PYTHON, 'main.py'] + date_args + ['--output', output_xlsx]
    run_step(1, '台灣風險監控報告 (main.py)', cmd1)

    # --- 步驟 2: Excel → JSON + TXT ---
    xlsx_path = os.path.join('outputs', 'monitor_xlsx', output_xlsx)
    cmd2 = [PYTHON, os.path.join('src', 'excel_to_json.py'), xlsx_path]
    run_step(2, 'Excel 轉 JSON / TXT (excel_to_json.py)', cmd2)

    # --- 步驟 3: 全球市場與總經 ---
    cmd3 = [PYTHON, os.path.join('src', 'global_market_monitor.py')] + date_args
    run_step(3, '全球市場與總經數據 (global_market_monitor.py)', cmd3)

    # --- 步驟 4: QD Top-Down 策略選股 ---
    qd_dir = os.path.join(PROJECT_ROOT, 'QD_twstock')
    cmd4 = [PYTHON, 'top_down_strategy.py'] + date_args
    run_step(4, 'QD Top-Down 策略選股 (top_down_strategy.py)', cmd4, cwd=qd_dir)

    # --- 完成 ---
    print(f"\n{'='*60}")
    print(f" ✅ 全部完成！")
    print(f"    台灣報告: outputs/monitor_xlsx/{output_xlsx}")
    print(f"    台灣 JSON: outputs/json/")
    print(f"    全球 JSON: outputs/global_json/")
    print(f"    策略報告: QD_twstock/result/")
    print(f"    啟動儀表板: python web/server.py")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
