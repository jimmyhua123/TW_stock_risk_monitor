"""Risk-score adjustments from already generated market data.

The derivatives monitor remains the source of the base score.  This module
adds small, explainable adjustments from data that is already present in the
daily JSON files.
"""

from __future__ import annotations

import math
import re
from typing import Any


OVERVIEW_KEY_ALIASES = {
    "indicator": ("指標",),
    "value": ("當日數值",),
    "change": ("單日變動",),
}

STOCK_KEY_ALIASES = {
    "code": ("代號",),
    "name": ("名稱",),
    "change_pct": ("漲跌幅(%)",),
    "foreign_daily": ("外資當日(張)",),
    "trust_daily": ("投信當日(張)",),
    "margin_change": ("融資增減(張)",),
    "ma20_gap": ("MA20乖離(%)",),
}

OVERVIEW_FALLBACK_INDEX = {
    "indicator": 1,
    "value": 2,
    "change": 3,
}

STOCK_FALLBACK_INDEX = {
    "code": 0,
    "name": 1,
    "change_pct": 4,
    "foreign_daily": 6,
    "trust_daily": 8,
    "margin_change": 12,
    "ma20_gap": 14,
}


def expanded_risk_summary(
    market_data: dict[str, Any],
    derivatives_data: dict[str, Any],
    market_trend_data: dict[str, Any] | None = None,
    market_breadth_data: dict[str, Any] | None = None,
    global_market_data: dict[str, Any] | None = None,
    us_sector_flow_data: dict[str, Any] | None = None,
    securities_lending_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return base score plus bounded adjustments from available raw data."""
    base_score = to_float(derivatives_data.get("summary", {}).get("risk_score"))
    if math.isnan(base_score):
        base_score = 50.0

    overview = market_data.get("總覽") or market_data.get("概況") or market_data.get("蝮質汗") or []
    stocks = market_data.get("個股籌碼") or market_data.get("自選股") or market_data.get("?蝐Ⅳ") or []

    factors = []
    factors.extend(score_spot_trend(overview))
    factors.extend(score_volatility(overview))
    factors.extend(score_international_risk(overview))
    factors.extend(score_stock_institutional_flow(stocks))
    factors.extend(score_key_stock_strength(stocks))
    factors.extend(score_margin_pressure(stocks))
    if market_trend_data:
        factors.extend(score_market_trend_data(market_trend_data))
    if market_breadth_data:
        factors.extend(score_market_breadth_data(market_breadth_data))
    if global_market_data:
        factors.extend(score_global_market_data(global_market_data))
    if us_sector_flow_data:
        factors.extend(score_us_sector_flow_data(us_sector_flow_data))
    factors.extend(score_derivatives_expansion_data(derivatives_data))
    if securities_lending_data:
        factors.extend(score_securities_lending_data(securities_lending_data))

    raw_adjustment = sum(factor["points"] for factor in factors)
    adjustment = int(clamp(raw_adjustment, -20, 20))
    final_score = clamp(round(base_score + adjustment), 0, 100)
    return {
        "base_score": int(round(base_score)),
        "adjustment": int(adjustment),
        "expanded_score": int(final_score),
        "bias": score_bias(final_score),
        "factors": factors,
    }


def score_derivatives_expansion_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    factors = []
    night = data.get("night_session", {})
    options = data.get("options", {})

    night_change = to_float(night.get("txf_change_pct"))
    if not math.isnan(night_change):
        if night_change <= -1.8:
            factors.append(factor("TXF night session", 8, f"TXF after-hours fell {night_change:+.2f}%, pointing to gap-down risk."))
        elif night_change <= -1.0:
            factors.append(factor("TXF night session", 5, f"TXF after-hours fell {night_change:+.2f}%, adding overnight risk."))
        elif night_change >= 1.0:
            factors.append(factor("TXF night session", -4, f"TXF after-hours rose {night_change:+.2f}%, reducing near-term opening risk."))

    skew = to_float(options.get("skew_pressure"))
    if not math.isnan(skew):
        if skew >= 0.40:
            factors.append(factor("TXO option skew", 6, f"OTM put prices are rich versus calls; skew pressure {skew:+.2f} implies stronger hedging demand."))
        elif skew <= -0.20:
            factors.append(factor("TXO option skew", -3, f"Call-side skew is stronger; skew pressure {skew:+.2f} implies speculative upside demand."))

    iv_skew = to_float(options.get("iv_skew"))
    if not math.isnan(iv_skew):
        if iv_skew >= 0.08:
            factors.append(factor("TXO IV skew", 5, f"OTM put IV is {iv_skew:+.2f} above call IV, showing elevated downside hedge pricing."))
        elif iv_skew <= -0.05:
            factors.append(factor("TXO IV skew", -2, f"Call IV is richer than put IV by {abs(iv_skew):.2f}, showing upside speculation."))

    return factors


def score_securities_lending_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    market = data.get("market", {})
    items = data.get("watchlist_items", [])
    factors = []
    daily_change = to_float(market.get("total_daily_change"))
    daily_ratio = to_float(market.get("daily_change_ratio"))

    if not math.isnan(daily_ratio):
        if daily_ratio >= 0.05:
            factors.append(factor("Securities lending", 5, f"Market lending short balance increased {daily_ratio:.2%} in one day, showing rising short/hedging pressure."))
        elif daily_ratio <= -0.05:
            factors.append(factor("Securities lending", -3, f"Market lending short balance decreased {abs(daily_ratio):.2%} in one day, easing short pressure."))
    elif not math.isnan(daily_change) and daily_change >= 10000:
        factors.append(factor("Securities lending", 4, f"Market lending short balance increased by {daily_change:,.0f}, showing rising short/hedging pressure."))

    watch_increases = [item for item in items if to_float(item.get("daily_change")) >= 1000]
    if len(watch_increases) >= 3:
        names = ", ".join(f"{item.get('code')} {item.get('name')}" for item in watch_increases[:5])
        factors.append(factor("Watchlist lending pressure", 4, f"Watchlist 有 {len(watch_increases)} 檔借券賣出餘額單日增加超過 1,000 股：{names}。借券賣出餘額增加通常代表放空或避險需求升高，不一定馬上看跌，但籌碼壓力增加，所以加分。"))

    return factors


def score_global_market_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    market_data = data.get("market_data", {})
    assets = []
    for items in market_data.values():
        if isinstance(items, list):
            assets.extend(items)

    def by_ticker(ticker: str) -> dict[str, Any] | None:
        for item in assets:
            if item.get("ticker") == ticker:
                return item
        return None

    factors = []
    nasdaq_change = to_float((by_ticker("^IXIC") or {}).get("change"))
    spx_change = to_float((by_ticker("^GSPC") or {}).get("change"))
    usd_twd_change = to_float((by_ticker("USDTWD=X") or {}).get("change"))
    dxy_change = to_float((by_ticker("DX-Y.NYB") or {}).get("change"))
    ten_year_bp = to_float((by_ticker("^TNX") or {}).get("change"))

    if not math.isnan(nasdaq_change):
        if nasdaq_change <= -2:
            factors.append(factor("Nasdaq", 4, f"Nasdaq fell {nasdaq_change:+.2f}%, increasing pressure on Taiwan tech sentiment."))
        elif nasdaq_change >= 2:
            factors.append(factor("Nasdaq", -3, f"Nasdaq rose {nasdaq_change:+.2f}%, supporting risk appetite for growth and tech stocks."))

    if not math.isnan(spx_change):
        if spx_change <= -1.5:
            factors.append(factor("S&P 500", 3, f"S&P 500 fell {spx_change:+.2f}%, showing broader global risk-off pressure."))
        elif spx_change >= 1.5:
            factors.append(factor("S&P 500", -2, f"S&P 500 rose {spx_change:+.2f}%, showing broader global risk appetite."))

    if not math.isnan(usd_twd_change):
        if usd_twd_change >= 0.4:
            factors.append(factor("USD/TWD", 3, f"USD/TWD rose {usd_twd_change:+.2f}%, implying TWD weakness and possible foreign-flow pressure."))
        elif usd_twd_change <= -0.4:
            factors.append(factor("USD/TWD", -2, f"USD/TWD fell {usd_twd_change:+.2f}%, implying TWD strength and less foreign-flow pressure."))

    if not math.isnan(dxy_change) and dxy_change >= 0.5:
        factors.append(factor("DXY", 2, f"US Dollar Index rose {dxy_change:+.2f}%, usually tightening liquidity for risk assets."))

    if not math.isnan(ten_year_bp):
        if ten_year_bp >= 10:
            factors.append(factor("US 10Y yield", 2, f"US 10Y yield rose {ten_year_bp:+.0f} bp, adding valuation pressure."))
        elif ten_year_bp <= -10:
            factors.append(factor("US 10Y yield", -1, f"US 10Y yield fell {ten_year_bp:+.0f} bp, easing valuation pressure."))

    return factors


def score_us_sector_flow_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    periods = data.get("periods", {})
    six_month = periods.get("6M") or periods.get("6mo") or {}
    sectors = six_month.get("sectors", [])
    if not sectors:
        return []

    tech = next((item for item in sectors if item.get("ticker") == "XLK"), None)
    semis = next((item for item in sectors if item.get("ticker") in {"SMH", "SOXX"}), None)
    factors = []

    for label, item in (("US tech sector", tech), ("US semiconductor ETF", semis)):
        if not item:
            continue
        alpha = to_float(item.get("alpha_pct"))
        if math.isnan(alpha):
            continue
        if alpha <= -5:
            factors.append(factor(label, 4, f"{item.get('ticker')} 近 6 個月落後 SPY {abs(alpha):.2f}%，代表美股相關族群領導力轉弱，會提高台股科技股外部壓力。"))
        elif alpha >= 5:
            factors.append(factor(label, -3, f"{item.get('ticker')} 近 6 個月領先 SPY {alpha:.2f}%，代表美股相關族群仍有領導力，對台股科技鏈是外部支撐，所以扣分。"))

    return factors


def score_market_trend_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    factors = []
    indices = data.get("indices", {})
    twii = indices.get("TWII", {})
    gap_ma20 = to_float(twii.get("gap_ma20_pct"))
    gap_ma5 = to_float(twii.get("gap_ma5_pct"))

    if not math.isnan(gap_ma20):
        if gap_ma20 <= -3:
            factors.append(factor("大盤 MA20", 8, f"加權指數低於 MA20 {gap_ma20:+.2f}%，中期趨勢偏弱。"))
        elif gap_ma20 >= 3:
            factors.append(factor("大盤 MA20", -6, f"加權指數高於 MA20 {gap_ma20:+.2f}%，中期趨勢偏強。"))

    if not math.isnan(gap_ma5):
        if gap_ma5 <= -1.5:
            factors.append(factor("大盤 MA5", 4, f"加權指數低於 MA5 {gap_ma5:+.2f}%，短線轉弱。"))
        elif gap_ma5 >= 1.5:
            factors.append(factor("大盤 MA5", -3, f"加權指數高於 MA5 {gap_ma5:+.2f}%，短線偏強。"))

    return factors


def score_market_breadth_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    breadth = data.get("breadth", {})
    total = int(to_float(breadth.get("total")) if not math.isnan(to_float(breadth.get("total"))) else 0)
    if total == 0:
        return []

    advance_ratio = to_float(breadth.get("advance_ratio"))
    decline_ratio = to_float(breadth.get("decline_ratio"))
    limit_down = int(to_float(breadth.get("limit_down")) if not math.isnan(to_float(breadth.get("limit_down"))) else 0)
    limit_up = int(to_float(breadth.get("limit_up")) if not math.isnan(to_float(breadth.get("limit_up"))) else 0)

    factors = []
    if not math.isnan(decline_ratio) and decline_ratio >= 0.65:
        factors.append(factor("市場廣度", 8, f"下跌家數占比 {decline_ratio:.1%}，盤面廣度偏弱。"))
    elif not math.isnan(advance_ratio) and advance_ratio >= 0.65:
        factors.append(factor("市場廣度", -7, f"上漲家數占比 {advance_ratio:.1%}，盤面廣度偏強。"))

    if limit_down >= 20:
        factors.append(factor("跌停壓力", 5, f"跌停家數 {limit_down} 家，流動性壓力升高。"))
    elif limit_up >= 20:
        factors.append(factor("漲停動能", -4, f"漲停家數 {limit_up} 家，短線風險偏好升溫。"))

    return factors


def score_spot_trend(overview: list[dict[str, Any]]) -> list[dict[str, Any]]:
    factors = []
    twii = find_overview_item(overview, "TWII")
    otc = find_overview_item(overview, "OTC")

    twii_change = overview_change(twii)
    if not math.isnan(twii_change):
        if twii_change <= -1.5:
            factors.append(factor("現貨趨勢", 8, f"加權指數下跌 {twii_change:+.2f}%，現貨趨勢轉弱。"))
        elif twii_change <= -0.8:
            factors.append(factor("現貨趨勢", 4, f"加權指數下跌 {twii_change:+.2f}%，短線偏弱。"))
        elif twii_change >= 1.5:
            factors.append(factor("現貨趨勢", -6, f"加權指數上漲 {twii_change:+.2f}%，現貨買盤偏強。"))
        elif twii_change >= 0.8:
            factors.append(factor("現貨趨勢", -3, f"加權指數上漲 {twii_change:+.2f}%，短線風險下降。"))

    otc_change = overview_change(otc)
    if not math.isnan(otc_change):
        if otc_change <= -1.5:
            factors.append(factor("櫃買趨勢", 4, f"櫃買指數下跌 {otc_change:+.2f}%，中小型股風險升高。"))
        elif otc_change >= 1.5:
            factors.append(factor("櫃買趨勢", -4, f"櫃買指數上漲 {otc_change:+.2f}%，市場風險偏好改善。"))

    return factors


def score_volatility(overview: list[dict[str, Any]]) -> list[dict[str, Any]]:
    vix = find_overview_item(overview, "VIX")
    value = overview_value(vix)
    change = overview_change(vix)
    factors = []

    if not math.isnan(value) and value >= 25:
        factors.append(factor("波動風險", 8, f"VIX 位於 {value:.2f}，避險價格偏高。"))
    elif not math.isnan(change) and change >= 10:
        factors.append(factor("波動風險", 6, f"VIX 單日上升 {change:+.2f}%，避險需求升溫。"))
    elif not math.isnan(value) and value <= 18 and (math.isnan(change) or change <= 0):
        factors.append(factor("波動風險", -4, f"VIX 位於 {value:.2f} 且未上升，波動壓力下降。"))

    return factors


def score_international_risk(overview: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sox = find_overview_item(overview, "SOX")
    sox_change = overview_change(sox)
    if math.isnan(sox_change):
        return []
    if sox_change <= -2:
        return [factor("國際風險", 6, f"SOX 下跌 {sox_change:+.2f}%，台股科技權值外部壓力升高。")]
    if sox_change >= 2:
        return [factor("國際風險", -5, f"SOX 上漲 {sox_change:+.2f}%，科技股外部風險下降。")]
    return []


def score_stock_institutional_flow(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    foreign_sum = sum_field(stocks, "foreign_daily")
    trust_sum = sum_field(stocks, "trust_daily")
    if math.isnan(foreign_sum) and math.isnan(trust_sum):
        return []

    foreign = 0 if math.isnan(foreign_sum) else foreign_sum
    trust = 0 if math.isnan(trust_sum) else trust_sum
    total = foreign + trust

    if foreign < 0 and trust < 0:
        return [factor("法人籌碼", 6, f"自選股外資與投信同步賣超，合計 {total:,.0f} 張。")]
    if foreign > 0 and trust > 0:
        return [factor("法人籌碼", -5, f"自選股外資與投信同步買超，合計 {total:,.0f} 張。")]
    if foreign <= -10000:
        return [factor("法人籌碼", 4, f"自選股外資合計賣超 {foreign:,.0f} 張。")]
    if foreign >= 10000:
        return [factor("法人籌碼", -4, f"自選股外資合計買超 {foreign:,.0f} 張。")]
    return []


def score_key_stock_strength(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    key_codes = {"0050", "2330", "2308", "2454"}
    covered = [stock for stock in stocks if stock_code(stock) in key_codes]
    changes = [stock_float(stock, "change_pct") for stock in covered]
    changes = [value for value in changes if not math.isnan(value)]
    ma20_gaps = [stock_float(stock, "ma20_gap") for stock in covered]
    ma20_gaps = [value for value in ma20_gaps if not math.isnan(value)]

    factors = []
    if changes:
        avg_change = sum(changes) / len(changes)
        if avg_change <= -1:
            factors.append(factor("權值股強弱", 5, f"權值觀察股平均下跌 {avg_change:+.2f}%，大盤支撐轉弱。"))
        elif avg_change >= 1:
            factors.append(factor("權值股強弱", -4, f"權值觀察股平均上漲 {avg_change:+.2f}%，大盤支撐改善。"))

    if ma20_gaps:
        avg_ma20 = sum(ma20_gaps) / len(ma20_gaps)
        if avg_ma20 <= -3:
            factors.append(factor("權值股 MA20", 4, f"權值觀察股平均低於 MA20 {avg_ma20:+.2f}%，趨勢偏弱。"))
        elif avg_ma20 >= 3:
            factors.append(factor("權值股 MA20", -3, f"權值觀察股平均高於 MA20 {avg_ma20:+.2f}%，趨勢偏強。"))

    return factors


def score_margin_pressure(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    usable = []
    for stock in stocks:
        change = stock_float(stock, "change_pct")
        margin = stock_float(stock, "margin_change")
        if not math.isnan(change) and not math.isnan(margin):
            usable.append((change, margin))
    if not usable:
        return []

    weak_with_margin = sum(1 for change, margin in usable if change < 0 and margin > 0)
    ratio = weak_with_margin / len(usable)
    if ratio >= 0.30:
        return [factor("融資壓力", 5, f"{weak_with_margin}/{len(usable)} 檔下跌但融資增加，籌碼承接壓力偏高。")]
    return []


def factor(name: str, points: int, explanation: str) -> dict[str, Any]:
    return {"name": name, "points": points, "explanation": explanation}


def score_bias(score: float) -> str:
    if score >= 70:
        return "risk_off"
    if score <= 40:
        return "risk_on"
    return "neutral"


def find_overview_item(items: list[dict[str, Any]], token: str) -> dict[str, Any] | None:
    token = token.lower()
    for item in items:
        indicator = str(get_alias(item, "indicator", "")).lower()
        if token in indicator:
            return item
    return None


def overview_value(item: dict[str, Any] | None) -> float:
    return to_float(get_alias(item or {}, "value"))


def overview_change(item: dict[str, Any] | None) -> float:
    return to_float(get_alias(item or {}, "change"))


def get_alias(mapping: dict[str, Any], alias_group: str, default: Any = None) -> Any:
    for key in OVERVIEW_KEY_ALIASES[alias_group]:
        if key in mapping:
            return mapping.get(key)
    values = list(mapping.values())
    fallback_index = OVERVIEW_FALLBACK_INDEX[alias_group]
    if len(values) > fallback_index:
        return values[fallback_index]
    return default


def stock_value(stock: dict[str, Any], alias_group: str) -> Any:
    for key in STOCK_KEY_ALIASES[alias_group]:
        if key in stock:
            return stock.get(key)
    values = list(stock.values())
    fallback_index = STOCK_FALLBACK_INDEX[alias_group]
    if len(values) > fallback_index:
        return values[fallback_index]
    return None


def stock_float(stock: dict[str, Any], alias_group: str) -> float:
    return to_float(stock_value(stock, alias_group))


def stock_code(stock: dict[str, Any]) -> str:
    value = stock_value(stock, "code")
    try:
        return str(int(value)).zfill(4)
    except (TypeError, ValueError):
        return str(value or "").zfill(4)


def sum_field(stocks: list[dict[str, Any]], alias_group: str) -> float:
    values = [stock_float(stock, alias_group) for stock in stocks]
    values = [value for value in values if not math.isnan(value)]
    return sum(values) if values else float("nan")


def to_float(value: Any) -> float:
    if value is None or value == "":
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    text = text.replace(",", "").replace("%", "")
    text = re.sub(r"[^0-9.+-]", "", text)
    if text in {"", "+", "-", ".", "+.", "-."}:
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def clamp(value: float, low: int, high: int) -> float:
    return max(low, min(high, value))
