#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a daily markdown briefing from the generated market data files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from src.risk_score_expansion import expanded_risk_summary


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BRIEFING_DIR = PROJECT_ROOT / "docs" / "notes" / "每日看盤筆記"


SIGNAL_LABELS = {
    "risk_off": "風險偏高 / 偏空環境",
    "risk_on": "風險偏低 / 偏多環境",
    "neutral": "中性",
    "bearish": "偏空",
    "bullish": "偏多",
    "hedging_pressure": "避險壓力",
    "call_speculation": "Call 投機",
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def find_latest_file(directory: Path, pattern: str) -> Path | None:
    files = sorted(directory.glob(pattern), key=lambda p: p.name, reverse=True)
    return files[0] if files else None


def data_file_for_date(directory: Path, date: str, pattern: str) -> Path | None:
    exact = directory / pattern.format(date=date)
    if exact.exists():
        return exact
    return find_latest_file(directory, pattern.format(date="*"))


def data_file_on_or_before(directory: Path, date: str, pattern: str) -> Path | None:
    candidates = []
    for path in directory.glob(pattern.format(date="*")):
        match = re.search(r"(20\d{6})", path.name)
        if match and match.group(1) <= date:
            candidates.append(path)
    return sorted(candidates, key=lambda p: p.name, reverse=True)[0] if candidates else None


def exact_data_file(directory: Path, date: str, pattern: str) -> Path | None:
    path = directory / pattern.format(date=date)
    return path if path.exists() else None


def build_coverage_index(coverage_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for item in coverage_data.get("items", []):
        code = str(item.get("code", "")).zfill(4)
        if item.get("found") and code.isdigit() and len(code) == 4:
            index[code] = item
    return index


def build_risk_history(date: str, max_points: int = 5) -> list[dict[str, Any]]:
    market_dir = PROJECT_ROOT / "outputs" / "json"
    dates = []
    for path in market_dir.glob("20*.json"):
        report_date = path.stem
        if report_date.isdigit() and len(report_date) == 8 and report_date.startswith(date[:6]) and report_date <= date:
            dates.append(report_date)

    history = []
    for report_date in sorted(dates)[-max_points:]:
        summary = expanded_summary_for_date(report_date)
        if summary:
            history.append(
                {
                    "date": report_date,
                    "score": summary["expanded_score"],
                    "bias": summary["bias"],
                }
            )
    return history


def expanded_summary_for_date(date: str) -> dict[str, Any] | None:
    market_path = exact_data_file(PROJECT_ROOT / "outputs" / "json", date, "{date}.json")
    if market_path is None:
        return None

    derivatives_path = exact_data_file(PROJECT_ROOT / "outputs" / "derivatives_json", date, "derivatives_{date}.json")
    trend_path = exact_data_file(PROJECT_ROOT / "outputs" / "market_trend_json", date, "market_trend_{date}.json")
    breadth_path = exact_data_file(PROJECT_ROOT / "outputs" / "market_breadth_json", date, "market_breadth_{date}.json")
    lending_path = exact_data_file(
        PROJECT_ROOT / "outputs" / "securities_lending_json", date, "securities_lending_{date}.json"
    )
    rotation_path = exact_data_file(
        PROJECT_ROOT / "outputs" / "defensive_rotation_json", date, "defensive_rotation_{date}.json"
    )
    global_path = data_file_on_or_before(PROJECT_ROOT / "outputs" / "global_json", date, "global_market_{date}.json")
    sector_flow_path = data_file_on_or_before(
        PROJECT_ROOT / "outputs" / "us_sector_flow_json", date, "us_sector_flow_{date}.json"
    )

    return expanded_risk_summary(
        load_json(market_path),
        load_json(derivatives_path) if derivatives_path else {},
        load_json(trend_path) if trend_path else {},
        load_json(breadth_path) if breadth_path else {},
        load_json(global_path) if global_path else {},
        load_json(sector_flow_path) if sector_flow_path else {},
        load_json(lending_path) if lending_path else {},
        load_json(rotation_path) if rotation_path else {},
    )


def summarize_risk_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    if not history:
        return {}

    scores = [item["score"] for item in history]
    current = scores[-1]
    previous = scores[-2] if len(scores) >= 2 else None
    ma3 = round(sum(scores[-3:]) / min(len(scores), 3), 1)
    ma5 = round(sum(scores[-5:]) / min(len(scores), 5), 1)
    delta = current - previous if previous is not None else None

    if delta is None:
        trend = "資料不足"
    elif delta <= -10:
        trend = "明顯降溫"
    elif delta >= 10:
        trend = "明顯升溫"
    elif delta < 0:
        trend = "小幅降溫"
    elif delta > 0:
        trend = "小幅升溫"
    else:
        trend = "持平"

    if current <= 40 and ma5 > 40:
        interpretation = "單日分數偏低，但 5 日均值尚未進入低風險區，不宜直接解讀成穩定偏多，只能視為短線風險降溫。"
    elif current <= 40 and ma5 <= 40:
        interpretation = "單日與 5 日均值都偏低，代表低風險環境較有延續性，做多條件相對友善。"
    elif current >= 70 and ma5 >= 70:
        interpretation = "單日與 5 日均值都偏高，代表高風險環境較有延續性，應以防守與控槓桿為主。"
    elif current >= 70 and ma5 < 70:
        interpretation = "單日分數偏高，但 5 日均值尚未同步升高，先視為風險升溫警訊，不宜只靠一天資料翻空。"
    else:
        interpretation = "分數位於中性區，單日方向訊號不足，應搭配 3 日/5 日均值與個股籌碼確認。"

    return {
        "current": current,
        "previous": previous,
        "delta": delta,
        "ma3": ma3,
        "ma5": ma5,
        "trend": trend,
        "interpretation": interpretation,
    }


def build_briefing_markdown(
    date: str,
    market_data: dict[str, Any],
    derivatives_data: dict[str, Any] | None = None,
    coverage_data: dict[str, Any] | None = None,
    market_trend_data: dict[str, Any] | None = None,
    market_breadth_data: dict[str, Any] | None = None,
    global_market_data: dict[str, Any] | None = None,
    us_sector_flow_data: dict[str, Any] | None = None,
    securities_lending_data: dict[str, Any] | None = None,
    risk_history: list[dict[str, Any]] | None = None,
    defensive_rotation_data: dict[str, Any] | None = None,
) -> str:
    derivatives_data = derivatives_data or {}
    coverage_index = build_coverage_index(coverage_data or {})

    lines: list[str] = [
        f"# 每日看盤筆記 {date}",
        "",
        "## 市場總覽",
        "",
    ]
    lines.extend(render_overview(market_data.get("總覽", [])))
    lines.extend(
        render_derivatives(
            derivatives_data,
            market_data,
            market_trend_data,
            market_breadth_data,
            global_market_data,
            us_sector_flow_data,
            securities_lending_data,
            risk_history,
            defensive_rotation_data,
        )
    )
    lines.extend(render_stock_table(market_data.get("個股籌碼", []), coverage_index))
    lines.extend(render_warrants(market_data.get("權證監控", [])))
    lines.extend(render_action_notes(market_data.get("個股籌碼", []), derivatives_data, coverage_index))
    return "\n".join(lines).rstrip() + "\n"


def render_overview(items: list[dict[str, Any]]) -> list[str]:
    rows = []
    for item in items[:8]:
        category = item.get("類別", "-")
        indicator = item.get("指標", "-")
        value = format_value(item.get("當日數值"))
        change = format_value(item.get("單日變動"))
        rows.append(f"- {category} / {indicator}: {value} ({change})")

    if not rows:
        rows.append("- 尚無市場總覽資料")
    rows.append("")
    return rows


def render_derivatives(
    data: dict[str, Any],
    market_data: dict[str, Any] | None = None,
    market_trend_data: dict[str, Any] | None = None,
    market_breadth_data: dict[str, Any] | None = None,
    global_market_data: dict[str, Any] | None = None,
    us_sector_flow_data: dict[str, Any] | None = None,
    securities_lending_data: dict[str, Any] | None = None,
    risk_history: list[dict[str, Any]] | None = None,
    defensive_rotation_data: dict[str, Any] | None = None,
) -> list[str]:
    summary = data.get("summary", {})
    futures = data.get("futures", {})
    positioning = data.get("positioning", {})
    options = data.get("options", {})
    night = data.get("night_session", {})

    lines = [
        "## 期貨 / 選擇權風險",
        "",
        f"- 風險分數: {format_value(summary.get('risk_score'))}",
        f"- 市場傾向: {format_signal(summary.get('bias'))}",
        f"- 台指期基差: {format_signed(futures.get('basis'), 2)} ({format_signed(futures.get('basis_pct'), 2)}%)",
        f"- 外資台指期未平倉淨部位: {format_signed(positioning.get('foreign_tx_net_open_interest'), 0)} 口",
        f"- Put/Call Ratio: {format_value(options.get('pc_ratio'))} (5D {format_value(options.get('pc_ratio_5d_avg'))})",
        f"- TXO skew pressure: {format_value(options.get('skew_pressure'))}",
        f"- TXO IV skew: {format_value(options.get('iv_skew'))}",
        f"- TXF 夜盤漲跌幅: {format_signed(night.get('txf_change_pct'), 2)}%",
        "",
    ]
    lines.extend(render_derivative_score_explanation(futures, positioning, options))
    if market_data is not None:
        lines.extend(
            render_expanded_risk_score(
                market_data,
                data,
                market_trend_data,
                market_breadth_data,
                global_market_data,
                us_sector_flow_data,
                securities_lending_data,
                risk_history,
                defensive_rotation_data,
            )
        )
    lines.extend(render_practical_expansion_criteria())
    return lines


def render_expanded_risk_score(
    market_data: dict[str, Any],
    derivatives_data: dict[str, Any],
    market_trend_data: dict[str, Any] | None = None,
    market_breadth_data: dict[str, Any] | None = None,
    global_market_data: dict[str, Any] | None = None,
    us_sector_flow_data: dict[str, Any] | None = None,
    securities_lending_data: dict[str, Any] | None = None,
    risk_history: list[dict[str, Any]] | None = None,
    defensive_rotation_data: dict[str, Any] | None = None,
) -> list[str]:
    summary = expanded_risk_summary(
        market_data,
        derivatives_data,
        market_trend_data,
        market_breadth_data,
        global_market_data,
        us_sector_flow_data,
        securities_lending_data,
        defensive_rotation_data or {},
    )
    lines = [
        "### 擴充後風險分數",
        "",
        f"- 原期權分數: {summary['base_score']}",
        f"- 擴充因子調整: {summary['adjustment']:+d}",
        f"- 擴充後分數: {summary['expanded_score']} ({format_signal(summary['bias'])})",
    ]
    if summary["factors"]:
        for item in summary["factors"]:
            points = item["points"]
            sign = f"+{points}" if points > 0 else str(points)
            lines.append(f"- {item['name']}: {sign} 分。{item['explanation']}")
    else:
        lines.append("- 目前可用擴充資料未觸發額外加減分。")
    lines.append("")
    lines.extend(render_risk_trend_summary(risk_history or []))
    return lines


def render_risk_trend_summary(history: list[dict[str, Any]]) -> list[str]:
    if not history:
        return []

    trend = summarize_risk_history(history)
    delta = trend.get("delta")
    delta_text = "-" if delta is None else f"{delta:+d}"
    rows = ", ".join(f"{item['date']}={item['score']}" for item in history)
    return [
        "### 風險趨勢",
        "",
        f"- 今日分數: {trend['current']}",
        f"- 前一筆變化: {delta_text} ({trend['trend']})",
        f"- 3日風險均值: {trend['ma3']}",
        f"- 5日風險均值: {trend['ma5']}",
        f"- 最近分數: {rows}",
        f"- 交易解讀: {trend['interpretation']}",
        "",
    ]


def render_derivative_score_explanation(
    futures: dict[str, Any],
    positioning: dict[str, Any],
    options: dict[str, Any],
) -> list[str]:
    factors = [
        explain_basis_score(futures.get("basis")),
        explain_foreign_position_score(positioning.get("foreign_tx_net_open_interest")),
        explain_pc_ratio_score(options.get("pc_ratio")),
    ]

    lines = ["### 風險分數拆解", "", "- 基準分: 50"]
    for title, points, signal, explanation in factors:
        sign = f"+{points}" if points > 0 else str(points)
        lines.append(f"- {title}: {signal}，{sign} 分。{explanation}")
    lines.append("")
    return lines


def explain_basis_score(value: Any) -> tuple[str, int, str, str]:
    basis = to_float(value)
    if basis != basis:
        return ("台指期基差", 0, "unknown", "資料不足，暫不調整風險分數。")
    if basis <= -80:
        return (
            "台指期基差",
            15,
            "bearish",
            "逆價差很大：期貨比現貨便宜，代表期貨市場不願意給現貨估值，可能有避險、放空、結算壓力，所以加分。",
        )
    if basis >= 60:
        return (
            "台指期基差",
            -10,
            "bullish",
            "正價差明顯：期貨比現貨貴，代表期貨市場願意提前反映較高價格，短線風險相對下降，所以扣分。",
        )
    return (
        "台指期基差",
        0,
        "neutral",
        "期貨與現貨接近，沒有明顯多空分歧，視為中性。",
    )


def explain_foreign_position_score(value: Any) -> tuple[str, int, str, str]:
    net_open_interest = to_float(value)
    if net_open_interest != net_open_interest:
        return ("外資台指期未平倉", 0, "unknown", "資料不足，暫不調整風險分數。")
    if net_open_interest <= -10000:
        return (
            "外資台指期未平倉",
            15,
            "bearish",
            "外資留有大幅淨空單，代表外資用期貨押空或避險的部位偏重，大盤風險上升，所以加分。",
        )
    if net_open_interest >= 10000:
        return (
            "外資台指期未平倉",
            -10,
            "bullish",
            "外資留有大幅淨多單，代表外資期貨部位偏多或空單回補，風險相對下降，所以扣分。",
        )
    return (
        "外資台指期未平倉",
        0,
        "neutral",
        "外資期貨淨部位未達明顯多空門檻，視為中性。",
    )


def explain_pc_ratio_score(value: Any) -> tuple[str, int, str, str]:
    pc_ratio = to_float(value)
    if pc_ratio != pc_ratio:
        return ("Put/Call Ratio", 0, "unknown", "資料不足，暫不調整風險分數。")
    if pc_ratio >= 130:
        return (
            "Put/Call Ratio",
            10,
            "hedging_pressure",
            "Put 比例偏高，代表避險或防跌需求升高；雖然不等於一定下跌，但期權結構較需要風險控管，所以加分。",
        )
    if pc_ratio <= 80:
        return (
            "Put/Call Ratio",
            5,
            "call_speculation",
            "Call 比例偏高，可能代表短線追價或槓桿投機升溫；追多擁擠時回檔風險提高，所以小幅加分。",
        )
    return (
        "Put/Call Ratio",
        0,
        "neutral",
        "Put 與 Call 結構未達極端，暫不調整風險分數。",
    )


def render_practical_expansion_criteria() -> list[str]:
    return [
        "### 可擴充判斷標準",
        "",
        "- 現貨趨勢: 加權指數相對 MA5/MA10/MA20 的位置，用來確認現貨趨勢是否真的轉弱或轉強。",
        "- 波動風險: VIX、台指選擇權隱含波動率，用來判斷避險成本是否升高。",
        "- 期貨結構: 近月/次月價差與轉倉變化，用來分辨結算壓力與換倉壓力。",
        "- 選擇權結構: Put/Call 未平倉、最大痛點、上下檔壓力區，用來觀察防守與壓力位置。",
        "- 法人籌碼: 外資現貨、投信買賣超，用來避免只看期貨避險而忽略現貨實際買盤。",
        "- 權值股強弱: 台積電、0050、金融與主流 AI 股，用來衡量大盤是否被少數權值股主導。",
        "- 市場廣度: 上漲家數、下跌家數、創高創低家數，用來判斷盤面健康度。",
        "- 國際風險: SOX、Nasdaq、美元台幣、殖利率，用來反映台股外部壓力。",
        "",
    ]

def render_stock_table(stocks: list[dict[str, Any]], coverage_index: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "## 自選股籌碼與題材",
        "",
        "| 代號 | 名稱 | 漲跌幅 | 外資 | 投信 | 融資 | MA20乖離 | 題材 |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]

    for stock in sorted(stocks, key=stock_sort_score, reverse=True):
        code = str(stock.get("股票代號", "")).zfill(4)
        coverage = coverage_index.get(code, {})
        themes = ", ".join((coverage.get("themes") or [])[:3]) or "-"
        lines.append(
            "| {code} | {name} | {pct} | {foreign} | {trust} | {margin} | {ma20} | {themes} |".format(
                code=code,
                name=stock.get("股票名稱", "-"),
                pct=format_percent(stock.get("漲跌幅(%)")),
                foreign=format_signed(stock.get("外資當日(張)"), 0),
                trust=format_signed(stock.get("投信當日(張)"), 0),
                margin=format_signed(stock.get("融資增減(張)"), 0),
                ma20=format_percent(stock.get("MA20乖離(%)")),
                themes=themes,
            )
        )

    if not stocks:
        lines.append("| - | - | - | - | - | - | - | - |")
    lines.append("")
    return lines


def render_warrants(warrants: list[dict[str, Any]]) -> list[str]:
    lines = [
        "## 權證監控",
        "",
        "| 代號 | 名稱 | 漲跌幅 | 價差比 | 實質槓桿 |",
        "|---|---|---:|---:|---:|",
    ]

    for warrant in warrants:
        lines.append(
            "| {code} | {name} | {pct} | {spread} | {leverage} |".format(
                code=str(warrant.get("權證代碼", "")).zfill(6),
                name=warrant.get("權證名稱", "-"),
                pct=format_percent(warrant.get("漲跌幅%")),
                spread=format_percent(warrant.get("買賣價差比%")),
                leverage=format_value(warrant.get("實質槓桿")),
            )
        )

    if not warrants:
        lines.append("| - | - | - | - | - |")
    lines.append("")
    return lines


def render_action_notes(
    stocks: list[dict[str, Any]],
    derivatives_data: dict[str, Any],
    coverage_index: dict[str, dict[str, Any]],
) -> list[str]:
    lines = ["## 今日重點提醒", ""]
    bias = derivatives_data.get("summary", {}).get("bias")
    if bias == "risk_off":
        lines.append("- 期權結構偏風險控管，追價部位要降低槓桿與隔日風險。")
    elif bias == "risk_on":
        lines.append("- 期權結構偏正向，仍需確認個股籌碼是否同步。")
    else:
        lines.append("- 期權訊號偏中性，重點回到個股籌碼與題材延續性。")

    hot_names = []
    for stock in stocks:
        code = str(stock.get("股票代號", "")).zfill(4)
        if code in coverage_index and to_float(stock.get("漲跌幅(%)")) > 0 and to_float(stock.get("融資增減(張)")) > 0:
            hot_names.append(f"{code} {stock.get('股票名稱', '-')}")
    if hot_names:
        lines.append(f"- 有題材且融資增加的個股: {', '.join(hot_names[:5])}，留意題材與籌碼是否同向。")
    else:
        lines.append("- 尚未看到明顯的題材加融資同步清單。")

    lines.append("")
    return lines


def stock_sort_score(stock: dict[str, Any]) -> float:
    return abs(to_float(stock.get("漲跌幅(%)"))) + abs(to_float(stock.get("MA20乖離(%)"))) * 0.5


def format_signal(value: Any) -> str:
    return SIGNAL_LABELS.get(str(value), str(value or "-"))


def format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def format_percent(value: Any) -> str:
    num = to_float(value)
    if num != num:
        return "-"
    return f"{num:+.2f}%"


def format_signed(value: Any, digits: int = 2) -> str:
    num = to_float(value)
    if num != num:
        return "-"
    return f"{num:+,.{digits}f}"


def to_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return float("nan")
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def write_briefing(date: str, output_path: Path | None = None) -> Path:
    market_path = data_file_for_date(PROJECT_ROOT / "outputs" / "json", date, "{date}.json")
    if market_path is None:
        raise FileNotFoundError(f"No market JSON found for {date}")

    derivatives_path = data_file_for_date(
        PROJECT_ROOT / "outputs" / "derivatives_json", date, "derivatives_{date}.json"
    )
    coverage_path = data_file_for_date(PROJECT_ROOT / "outputs" / "coverage_json", date, "coverage_{date}.json")
    trend_path = data_file_for_date(PROJECT_ROOT / "outputs" / "market_trend_json", date, "market_trend_{date}.json")
    breadth_path = data_file_for_date(
        PROJECT_ROOT / "outputs" / "market_breadth_json", date, "market_breadth_{date}.json"
    )
    global_path = data_file_for_date(PROJECT_ROOT / "outputs" / "global_json", date, "global_market_{date}.json")
    sector_flow_path = data_file_for_date(
        PROJECT_ROOT / "outputs" / "us_sector_flow_json", date, "us_sector_flow_{date}.json"
    )
    lending_path = data_file_for_date(
        PROJECT_ROOT / "outputs" / "securities_lending_json", date, "securities_lending_{date}.json"
    )
    rotation_path = data_file_for_date(
        PROJECT_ROOT / "outputs" / "defensive_rotation_json", date, "defensive_rotation_{date}.json"
    )

    market_data = load_json(market_path)
    derivatives_data = load_json(derivatives_path) if derivatives_path else {}
    coverage_data = load_json(coverage_path) if coverage_path else {}
    market_trend_data = load_json(trend_path) if trend_path else {}
    market_breadth_data = load_json(breadth_path) if breadth_path else {}
    global_market_data = load_json(global_path) if global_path else {}
    us_sector_flow_data = load_json(sector_flow_path) if sector_flow_path else {}
    securities_lending_data = load_json(lending_path) if lending_path else {}
    defensive_rotation_data = load_json(rotation_path) if rotation_path else {}
    risk_history = build_risk_history(date)

    markdown = build_briefing_markdown(
        date,
        market_data,
        derivatives_data,
        coverage_data,
        market_trend_data,
        market_breadth_data,
        global_market_data,
        us_sector_flow_data,
        securities_lending_data,
        risk_history,
        defensive_rotation_data,
    )
    output_path = output_path or DEFAULT_BRIEFING_DIR / f"{date}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a daily markdown briefing.")
    parser.add_argument("--date", required=True, help="Report date in YYYYMMDD format.")
    parser.add_argument("--output", type=Path, default=None, help="Optional markdown output path.")
    args = parser.parse_args()

    output_path = write_briefing(args.date, args.output)
    print(f"[OK] daily briefing written: {output_path}")


if __name__ == "__main__":
    main()
