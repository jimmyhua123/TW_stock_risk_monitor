#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Monthly/low-frequency workflow for heavier refresh jobs."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable


def run_step(step_num: str, description: str, cmd: list[str]) -> int:
    print(f"\n{'=' * 60}")
    print(f" 步驟 {step_num}：{description}")
    print(f" 指令：{' '.join(cmd)}")
    print(f"{'=' * 60}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"[WARNING] 步驟 {step_num} 回傳非零代碼: {result.returncode}，繼續執行...")
    return result.returncode


def build_steps(date: str | None, *, include_sector_flow: bool = False) -> list[tuple[str, str, list[str]]]:
    date_args = ["--date", date] if date else []
    steps: list[tuple[str, str, list[str]]] = [
        ("1", "全球市場與總經資料", [PYTHON, os.path.join("src", "global_market_monitor.py"), *date_args]),
        ("2", "個股產業與題材補充", [PYTHON, os.path.join("src", "coverage_enrichment.py"), *date_args]),
        ("3", "股期換月轉倉逆價差監控", [PYTHON, os.path.join("src", "stock_futures_rollover.py"), *date_args]),
    ]

    if include_sector_flow:
        steps.append(("4", "美股產業資金流報告", [PYTHON, "-m", "src.us_sector_flow_monitor", *date_args]))

    return steps


def main() -> None:
    parser = argparse.ArgumentParser(
        description="低頻/月度刷新流程：全球市場、題材補充、股期換月與可選的美股產業資金流。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python monthly_run.py --date 20260612
  python monthly_run.py --date 20260612 --include-sector-flow
        """,
    )
    parser.add_argument("--date", type=str, default=None, help="指定日期 YYYYMMDD；不指定則使用最新交易日")
    parser.add_argument(
        "--include-sector-flow",
        action="store_true",
        help="包含較重的美股產業資金流報告，會從 yfinance 抓 10 年資料。",
    )
    args = parser.parse_args()

    print(f"低頻/月度流程啟動：{args.date or '最新交易日'}")
    for step_num, description, cmd in build_steps(args.date, include_sector_flow=args.include_sector_flow):
        run_step(step_num, description, cmd)

    print("\n[DONE] monthly_run 完成")
    print("    全球市場: outputs/global_json/ / outputs/global_xlsx/")
    print("    題材補充: outputs/coverage_json/ / outputs/coverage_txt/")
    print("    股期換月: outputs/rollover_json/ / outputs/rollover_txt/")
    if args.include_sector_flow:
        print("    美股產業資金流: outputs/reports/")


if __name__ == "__main__":
    main()
