#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Daily workflow for the reports that usually need to be refreshed every trading day."""

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


def build_steps(date: str | None, refresh_coverage: bool = False) -> list[tuple[str, str, list[str]]]:
    date_args = ["--date", date] if date else []
    output_xlsx = f"{date}.xlsx" if date else "risk_report.xlsx"
    market_report = os.path.join("outputs", "json", f"{date}.json" if date else "risk_report.json")

    steps: list[tuple[str, str, list[str]]] = [
        ("1", "台灣風險監控報告", [PYTHON, "main.py", *date_args, "--output", output_xlsx]),
        (
            "2",
            "Excel 轉 JSON / TXT",
            [PYTHON, os.path.join("src", "excel_to_json.py"), os.path.join("outputs", "monitor_xlsx", output_xlsx)],
        ),
        ("3", "期貨與選擇權風險", [PYTHON, os.path.join("src", "derivatives_monitor.py"), *date_args]),
    ]

    if refresh_coverage:
        steps.append(("4", "個股產業與題材補充", [PYTHON, os.path.join("src", "coverage_enrichment.py"), *date_args]))

    group_cmd = [PYTHON, os.path.join("src", "group_monitor.py"), *date_args]
    if not date:
        group_cmd += ["--report", market_report]
    steps.append(("5", "Watchlist 族群分析", group_cmd))

    if date:
        steps.append(("6", "每日看盤筆記", [PYTHON, os.path.join("src", "daily_briefing.py"), "--date", date]))

    return steps


def main() -> None:
    parser = argparse.ArgumentParser(
        description="每日看盤常用流程：台股報表、衍生品、watchlist 族群分析、每日 briefing。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python daily_run.py --date 20260611
  python daily_run.py --date 20260611 --refresh-coverage
        """,
    )
    parser.add_argument("--date", type=str, default=None, help="指定日期 YYYYMMDD；不指定則使用最新交易日")
    parser.add_argument(
        "--refresh-coverage",
        action="store_true",
        help="同時刷新題材補充。watchlist 新增股票、想更新自動 groups 時使用。",
    )
    args = parser.parse_args()

    date_label = args.date or "最新交易日"
    print(f"每日流程啟動：{date_label}")

    for step_num, description, cmd in build_steps(args.date, args.refresh_coverage):
        run_step(step_num, description, cmd)

    print("\n[DONE] daily_run 完成")
    print("    台灣 JSON: outputs/json/")
    print("    衍生品 JSON: outputs/derivatives_json/")
    print("    Watchlist 族群分析: outputs/group_json/ / outputs/group_txt/")
    if args.date:
        print(f"    每日看盤筆記: docs/notes/每日看盤筆記/{args.date}.md")


if __name__ == "__main__":
    main()
