#!/usr/bin/env python3
"""50-200 DMA Convergence Strategy Scanner."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    lower_map = {c.strip().lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in lower_map:
            return lower_map[cand.lower()]
    for c in df.columns:
        cl = c.strip().lower()
        for cand in candidates:
            if cand.lower() in cl:
                return c
    return None


def load_fundamentals(csv_path: Path, cfg: Dict) -> Dict[str, Dict]:
    """Load Screener.in CSV and return passing symbols mapped to fundamental metrics."""
    if not csv_path.exists():
        return {}

    df = pd.read_csv(csv_path)
    if df.empty:
        return {}

    sym_col = _find_col(df, ["NSE Code", "Symbol", "Ticker"])
    mcap_col = _find_col(df, ["Market Capitalization", "Market Cap"])
    sales_col = _find_col(df, ["Sales growth 3Years", "3Y Sales CAGR"])
    pat_col = _find_col(df, ["Profit growth 3Years", "3Y PAT CAGR"])
    roce_col = _find_col(df, ["Return on capital employed", "ROCE"])
    roe_col = _find_col(df, ["Return on equity", "ROE"])
    de_col = _find_col(df, ["Debt to equity", "D/E"])
    ocf_col = _find_col(df, ["Cash from operations", "OCF", "3Y OCF"])
    pledge_col = _find_col(df, ["Pledged percentage", "Pledge"])

    if not sym_col:
        return {}

    fcfg = cfg["fundamentals"]
    min_mcap = cfg["universe"]["min_market_cap_cr"]
    passing: Dict[str, Dict] = {}

    for _, row in df.iterrows():
        sym = str(row.get(sym_col, "")).strip().upper()
        if not sym or sym == "NAN":
            continue

        def num(col: Optional[str], default: float = 0.0) -> float:
            if not col:
                return default
            val = pd.to_numeric(row.get(col), errors="coerce")
            return float(val) if pd.notna(val) else default

        mcap = num(mcap_col, 999999.0 if not mcap_col else 0.0)
        sales = num(sales_col, 999.0 if not sales_col else 0.0)
        pat = num(pat_col, 999.0 if not pat_col else 0.0)
        roce = num(roce_col, 999.0 if not roce_col else 0.0)
        roe = num(roe_col, 999.0 if not roe_col else 0.0)
        de = num(de_col, 0.0)
        ocf = num(ocf_col, 1.0 if not ocf_col else 0.0)
        pledge = num(pledge_col, 0.0)

        if mcap < min_mcap:
            continue
        if sales < fcfg["min_sales_3y_cagr"]:
            continue
        if pat < fcfg["min_pat_3y_cagr"]:
            continue
        if roce < fcfg["min_roce"]:
            continue
        if roe < fcfg["min_roe"]:
            continue
        if de > fcfg["max_debt_to_equity"]:
            continue
        if fcfg["require_positive_ocf"] and ocf <= 0:
            continue
        if pledge > fcfg["max_pledge_pct"]:
            continue

        passing[sym] = {
            "market_cap_cr": round(mcap, 1),
            "sales_3y_cagr": round(sales, 1),
            "pat_3y_cagr": round(pat, 1),
            "roce": round(roce, 1),
            "roe": round(roe, 1),
            "de": round(de, 2),
            "pledge_pct": round(pledge, 2),
        }

    return passing


def scan_market(
    history_df: pd.DataFrame,
    fundamentals: Dict[str, Dict],
    cfg: Dict,
    portfolio_capital: float,
    regime_normal: bool = True,
) -> Dict:
    """Run 50-200 DMA convergence & breakout scan across all symbols."""
    if history_df.empty:
        return {"trade_date": None, "breakouts": [], "forming": [], "regime_normal": regime_normal}

    df = history_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["symbol", "date"]).drop_duplicates(["symbol", "date"], keep="last")

    latest_date = df["date"].max()
    trade_date_str = latest_date.strftime("%Y-%m-%d")

    dcfg = cfg["discovery"]
    ecfg = cfg["entry"]
    rcfg = cfg["risk"]
    min_turnover = cfg["universe"]["min_median_turnover_cr"]

    risk_pct = rcfg["risk_per_trade_pct"] * (1.0 if regime_normal else rcfg["regime_cut_factor"])
    risk_budget_inr = portfolio_capital * (risk_pct / 100.0)
    max_pos_inr = portfolio_capital * (rcfg["max_position_pct"] / 100.0)

    breakouts: List[Dict] = []
    forming: List[Dict] = []

    use_fund_filter = len(fundamentals) > 0

    for symbol, g in df.groupby("symbol", sort=False):
        if use_fund_filter and symbol not in fundamentals:
            continue
        if len(g) < 211:  # Need 200 DMA + 10-day slope lookback
            continue
        if g["date"].iloc[-1] != latest_date:
            continue

        g = g.reset_index(drop=True)
        close = g["close"]
        high = g["high"]
        low = g["low"]
        vol = g["volume"]

        # Liquidity check: 20-day median turnover >= 1 Cr
        med_turnover = float(g["turnover_cr"].tail(20).median())
        if med_turnover < min_turnover:
            continue

        dma50 = close.rolling(50).mean()
        dma200 = close.rolling(200).mean()
        ratio = dma50 / dma200

        # True Range & ATR(14)
        prev_c = close.shift(1)
        tr = pd.concat([
            (high - low),
            (high - prev_c).abs(),
            (low - prev_c).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(rcfg["atr_period"]).mean()

        # Prior 20-day high & prior 20-day average volume (excluding today)
        high_20d_prev = high.shift(1).rolling(ecfg["breakout_lookback_days"]).max()
        vol_20d_avg_prev = vol.shift(1).rolling(ecfg["breakout_lookback_days"]).mean()

        idx = len(g) - 1
        lb = dcfg["slope_lookback_days"]

        c_now = float(close.iloc[idx])
        d50_now = float(dma50.iloc[idx])
        d200_now = float(dma200.iloc[idx])
        r_now = float(ratio.iloc[idx])

        d50_prev = float(dma50.iloc[idx - lb])
        d200_prev = float(dma200.iloc[idx - lb])
        r_prev = float(ratio.iloc[idx - lb])

        atr_now = float(atr.iloc[idx])
        h20_prev = float(high_20d_prev.iloc[idx])
        v_now = float(vol.iloc[idx])
        v20_avg = float(vol_20d_avg_prev.iloc[idx])

        if any(np.isnan(x) for x in [d50_now, d200_now, r_now, d50_prev, d200_prev, r_prev, atr_now, h20_prev, v20_avg]):
            continue

        slope_ok = (d50_now > d50_prev) and (r_now > r_prev) and (d200_now >= d200_prev * dcfg["dma200_flat_tolerance"])
        vol_mult_now = (v_now / v20_avg) if v20_avg > 0 else 0.0
        fund_info = fundamentals.get(symbol, {})

        # 1) Confirmed Breakout Signal
        is_breakout = (
            c_now > d200_now
            and c_now > h20_prev
            and vol_mult_now >= ecfg["volume_multiplier"]
            and slope_ok
            and (r_now >= dcfg["ratio_min"])
        )

        if is_breakout:
            swing_low = float(low.tail(rcfg["swing_low_lookback_days"]).min())
            atr_stop = c_now - rcfg["stop_atr_multiplier"] * atr_now
            stop_loss = round(min(swing_low, atr_stop), 2)
            risk_per_share = max(round(c_now - stop_loss, 2), 0.01)
            max_entry = round(c_now * (1.0 + ecfg["max_gap_pct"] / 100.0), 2)

            qty_by_risk = int(risk_budget_inr // risk_per_share)
            qty_by_cap = int(max_pos_inr // c_now)
            qty = max(min(qty_by_risk, qty_by_cap), 0)
            pos_value = round(qty * c_now, 2)

            breakouts.append({
                "symbol": symbol,
                "close": round(c_now, 2),
                "max_entry": max_entry,
                "stop_loss": stop_loss,
                "risk_per_share": risk_per_share,
                "qty": qty,
                "position_value": pos_value,
                "dma50": round(d50_now, 2),
                "dma200": round(d200_now, 2),
                "ratio": round(r_now, 4),
                "vol_mult": round(vol_mult_now, 2),
                "atr14": round(atr_now, 2),
                "med_turnover_cr": round(med_turnover, 2),
                **fund_info,
            })
            continue

        # 2) Forming Watchlist (Discovery Zone 0.94 - 0.96)
        is_forming = (
            dcfg["ratio_min"] <= r_now <= dcfg["ratio_max"]
            and c_now > d50_now
            and c_now < d200_now
            and slope_ok
        )

        if is_forming:
            dist_to_200_pct = round(((d200_now - c_now) / c_now) * 100.0, 2)
            forming.append({
                "symbol": symbol,
                "close": round(c_now, 2),
                "dma50": round(d50_now, 2),
                "dma200": round(d200_now, 2),
                "ratio": round(r_now, 4),
                "dist_to_200_pct": dist_to_200_pct,
                "med_turnover_cr": round(med_turnover, 2),
                **fund_info,
            })

    breakouts.sort(key=lambda x: x["vol_mult"], reverse=True)
    forming.sort(key=lambda x: x["ratio"], reverse=True)

    return {
        "trade_date": trade_date_str,
        "regime_normal": regime_normal,
        "portfolio_capital_inr": portfolio_capital,
        "risk_per_trade_pct": round(risk_pct, 2),
        "risk_budget_inr": round(risk_budget_inr, 2),
        "breakouts": breakouts,
        "forming": forming,
    }
