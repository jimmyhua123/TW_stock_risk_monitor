#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一鍵執行所有報告生成工具 (Run All)
統一指定日期，依序執行：
  1. main.py                    → 台灣風險報告 (Excel)
  2. excel_to_json.py           → 轉換為 JSON + TXT
  3. global_market_monitor.py   → 全球市場與總經數據
  4. derivatives_monitor.py     → 期貨與選擇權風險
  5. coverage_enrichment.py     → 個股產業與題材補充
  6. stock_futures_rollover.py  → 股期換月轉倉逆價差監控
  7. daily_briefing.py          → 每日看盤筆記
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

    # --- 步驟 4: 期貨與選擇權風險 ---
    cmd4 = [PYTHON, os.path.join('src', 'derivatives_monitor.py')] + date_args
    run_step(4, '期貨與選擇權風險 (derivatives_monitor.py)', cmd4)

    # --- 步驟 5: 個股產業與題材補充 ---
    cmd5 = [PYTHON, os.path.join('src', 'coverage_enrichment.py')] + date_args
    run_step(5, '個股產業與題材補充 (coverage_enrichment.py)', cmd5)

    # --- 步驟 6: 股期換月轉倉逆價差監控 ---
    cmd6 = [PYTHON, os.path.join('src', 'stock_futures_rollover.py')] + date_args
    run_step(6, '股期換月轉倉逆價差監控 (stock_futures_rollover.py)', cmd6)

    # --- 步驟 7: 每日看盤筆記 ---
    if args.date:
        cmd7 = [PYTHON, os.path.join('src', 'daily_briefing.py'), '--date', args.date]
        run_step(7, '每日看盤筆記 (daily_briefing.py)', cmd7)
    else:
        print("\n[INFO] 未指定 --date，略過每日看盤筆記產生。")

    # --- 完成 ---
    print(f"\n{'='*60}")
    print(f" ✅ 全部完成！")
    print(f"    台灣報告: outputs/monitor_xlsx/{output_xlsx}")
    print(f"    台灣 JSON: outputs/json/")
    print(f"    全球 JSON: outputs/global_json/")
    print(f"    衍生品 JSON: outputs/derivatives_json/")
    print(f"    題材補充 JSON: outputs/coverage_json/")
    print(f"    股期換月價差: outputs/rollover_json/ / outputs/rollover_txt/")
    if args.date:
        print(f"    每日看盤筆記: docs/notes/看盤筆記/{args.date}.md")
    print(f"    啟動儀表板: python web/server.py")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
