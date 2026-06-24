# ADR-001: Use defensive rotation as a bounded risk input

## Status

Accepted — 2026-06-24

## Context

Financial-sector strength can be a normal Taiwan equity rotation, while EWL strength can reflect either Swiss defensive demand or a strong-US-dollar regime. Neither observation alone establishes that the market will fall.

## Decision

Add `src.defensive_rotation_monitor` as a supplementary, 20-trading-day relative-strength monitor:

- Taiwan: `0055.TW / ^TWII`.
- US defensive read: `EWL / SPY`.
- A relative-strength threshold is only classified as `downtrend_risk` when its benchmark is at least 1% below its 20-day average.
- When 20-day DXY appreciation is at least 2%, the EWL signal is classified as `usd_defense` and does not add Swiss-defensive risk points.
- Confirmed Taiwan and Swiss downtrend-risk signals add only +3 each to the expanded risk score; broad Taiwan risk-off adds +4. Normal rotation adds no score adjustment.

The daily workflow writes `outputs/defensive_rotation_json/defensive_rotation_YYYYMMDD.json`; daily briefings and risk-history calculations load this file when it exists.

## Consequences

- The signal is explainable and cannot dominate the score by itself.
- `0055.TW` is an ETF proxy for Taiwan financials, not the official financial-sector index; its composition and tracking difference must be considered when reviewing results.
- The monitor requires sufficient yfinance price history. Missing inputs produce `unavailable`, not an inferred market view.
- Thresholds are heuristics and should be reviewed against historical data before being used for position sizing.
