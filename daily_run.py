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


def dated_output_paths(date: str | None, project_root: Path = PROJECT_ROOT) -> dict[str, Path]:
    return {
        "market_json": project_root / "outputs" / "json" / (f"{date}.json" if date else "risk_report.json"),
        "monitor_xlsx": project_root / "outputs" / "monitor_xlsx" / (f"{date}.xlsx" if date else "risk_report.xlsx"),
        "derivatives_json": project_root / "outputs" / "derivatives_json" / f"derivatives_{date}.json" if date else project_root / "outputs" / "derivatives_json",
        "coverage_json": project_root / "outputs" / "coverage_json" / f"coverage_{date}.json" if date else project_root / "outputs" / "coverage_json",
        "market_trend_json": project_root / "outputs" / "market_trend_json" / f"market_trend_{date}.json" if date else project_root / "outputs" / "market_trend_json",
        "market_breadth_json": project_root / "outputs" / "market_breadth_json" / f"market_breadth_{date}.json" if date else project_root / "outputs" / "market_breadth_json",
        "securities_lending_json": project_root / "outputs" / "securities_lending_json" / f"securities_lending_{date}.json" if date else project_root / "outputs" / "securities_lending_json",
        "defensive_rotation_json": project_root / "outputs" / "defensive_rotation_json" / f"defensive_rotation_{date}.json" if date else project_root / "outputs" / "defensive_rotation_json",
    }


def build_steps(
    date: str | None,
    refresh_coverage: bool = False,
    *,
    force_refresh: bool = False,
    project_root: Path = PROJECT_ROOT,
    verbose: bool = False,
) -> list[tuple[str, str, list[str]]]:
    date_args = ["--date", date] if date else []
    output_xlsx = f"{date}.xlsx" if date else "risk_report.xlsx"
    market_report = os.path.join("outputs", "json", f"{date}.json" if date else "risk_report.json")
    outputs = dated_output_paths(date, project_root)

    steps: list[tuple[str, str, list[str]]] = []

    if force_refresh or not outputs["market_json"].is_file():
        steps.append(("1", "台灣風險監控報告", [PYTHON, "main.py", *date_args, "--output", output_xlsx]))
        steps.append(
            (
                "2",
                "Excel 轉 JSON / TXT",
                [PYTHON, os.path.join("src", "excel_to_json.py"), os.path.join("outputs", "monitor_xlsx", output_xlsx)],
            )
        )
    else:
        if verbose:
            print(f"[SKIP] 已有台灣 JSON，略過重抓: {outputs['market_json']}")

    if force_refresh or not outputs["derivatives_json"].is_file():
        steps.append(("3", "期貨與選擇權風險", [PYTHON, os.path.join("src", "derivatives_monitor.py"), *date_args]))
    else:
        if verbose:
            print(f"[SKIP] 已有衍生品 JSON，略過重抓: {outputs['derivatives_json']}")

    if date and (force_refresh or not outputs["market_trend_json"].is_file()):
        steps.append(("3a", "Market trend metrics", [PYTHON, "-m", "src.market_trend_monitor", *date_args]))
    elif date and verbose:
        print(f"[SKIP] Market trend JSON exists: {outputs['market_trend_json']}")

    if date and (force_refresh or not outputs["market_breadth_json"].is_file()):
        steps.append(("3b", "Market breadth metrics", [PYTHON, "-m", "src.market_breadth_monitor", *date_args]))
    elif date and verbose:
        print(f"[SKIP] Market breadth JSON exists: {outputs['market_breadth_json']}")

    if date and (force_refresh or not outputs["securities_lending_json"].is_file()):
        steps.append(("3c", "Securities lending metrics", [PYTHON, "-m", "src.securities_lending_monitor", *date_args]))
    elif date and verbose:
        print(f"[SKIP] Securities lending JSON exists: {outputs['securities_lending_json']}")

    if date and (force_refresh or not outputs["defensive_rotation_json"].is_file()):
        steps.append(("3d", "Defensive rotation metrics", [PYTHON, "-m", "src.defensive_rotation_monitor", *date_args]))
    elif date and verbose:
        print(f"[SKIP] Defensive rotation JSON exists: {outputs['defensive_rotation_json']}")

    if refresh_coverage or (date and not outputs["coverage_json"].is_file()):
        steps.append(("4", "個股產業與題材補充", [PYTHON, os.path.join("src", "coverage_enrichment.py"), *date_args]))
    elif date:
        if verbose:
            print(f"[SKIP] 已有題材補充 JSON，略過重抓: {outputs['coverage_json']}")

    group_cmd = [PYTHON, os.path.join("src", "group_monitor.py"), *date_args]
    if not date:
        group_cmd += ["--report", market_report]
    steps.append(("5", "Watchlist 族群分析", group_cmd))

    if date:
        steps.append(("6", "每日看盤筆記", [PYTHON, "-m", "src.daily_briefing", "--date", date]))

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
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="即使已有當日輸出，也重新抓取所有日更資料。",
    )
    args = parser.parse_args()

    date_label = args.date or "最新交易日"
    print(f"每日流程啟動：{date_label}")

    for step_num, description, cmd in build_steps(
        args.date,
        args.refresh_coverage,
        force_refresh=args.force_refresh,
        verbose=True,
    ):
        run_step(step_num, description, cmd)

    print("\n[DONE] daily_run 完成")
    print("    台灣 JSON: outputs/json/")
    print("    衍生品 JSON: outputs/derivatives_json/")
    print("    Watchlist 族群分析: outputs/group_json/ / outputs/group_txt/")
    if args.date:
        print(f"    每日看盤筆記: docs/notes/每日看盤筆記/{args.date}.md")


if __name__ == "__main__":
    main()
