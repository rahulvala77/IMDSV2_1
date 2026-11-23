"""Completeness / freshness / sanity checks per symbol -> data/output/validation_report.csv.

A symbol is READY_FOR_SCORING only if prices are fresh, enough annual history exists and a
valuation row exists. Every problem is listed in ISSUES so nothing is silently dropped.
"""
from datetime import date

import pandas as pd

import config as cfg
from utils import read_csv_safe, status_from_counts


def run(ctx):
    tech = read_csv_safe(cfg.TECHNICALS_FILE).set_index("SYMBOL") if cfg.TECHNICALS_FILE.exists() else pd.DataFrame()
    fund = read_csv_safe(cfg.FUNDAMENTALS_FILE).set_index("SYMBOL") if cfg.FUNDAMENTALS_FILE.exists() else pd.DataFrame()
    val = read_csv_safe(cfg.VALUATION_METRICS_FILE).set_index("SYMBOL") if cfg.VALUATION_METRICS_FILE.exists() else pd.DataFrame()
    sh = read_csv_safe(cfg.SHAREHOLDING_FILE)
    sh_syms = set(sh["SYMBOL"]) if not sh.empty else set()
    today = date.today()
    rows = []
    for sym in ctx.universe["SYMBOL"]:
        issues = []
        has_p = sym in tech.index
        age = None
        if has_p:
            age = (today - date.fromisoformat(str(tech.at[sym, "LAST_DATE"]))).days
            if age > cfg.MAX_PRICE_AGE_DAYS:
                issues.append(f"stale prices ({age}d old)")
            if tech.at[sym, "BARS"] < cfg.MIN_PRICE_BARS:
                issues.append(f"only {int(tech.at[sym, 'BARS'])} price bars (<{cfg.MIN_PRICE_BARS}; recent listing?) - 200DMA/12m return unavailable")
        else:
            issues.append("no price data")
        n_ann = int(fund.at[sym, "ANNUAL_ROWS"]) if sym in fund.index else 0
        if n_ann < cfg.MIN_ANNUAL_YEARS:
            issues.append(f"only {n_ann} annual periods (need {cfg.MIN_ANNUAL_YEARS})")
        if sym in fund.index:
            f = fund.loc[sym]
            if pd.notna(f["REVENUE_CR_LATEST"]) and f["REVENUE_CR_LATEST"] <= 0:
                issues.append("non-positive revenue")
            if pd.isna(f.get("QTR_REV_YOY")):
                issues.append("no comparable year-ago quarter")
        has_v = sym in val.index and pd.notna(val.at[sym, "MARKET_CAP_CR"] if "MARKET_CAP_CR" in val else None)
        if not has_v:
            issues.append("no valuation/market cap")
        if sym not in sh_syms:
            issues.append("no shareholding data")
        enough_bars = has_p and tech.at[sym, "BARS"] >= cfg.MIN_PRICE_BARS
        ready = has_p and enough_bars and (age is not None and age <= cfg.MAX_PRICE_AGE_DAYS) and n_ann >= cfg.MIN_ANNUAL_YEARS and has_v
        rows.append({"SYMBOL": sym, "HAS_PRICE": has_p, "PRICE_AGE_DAYS": age, "ANNUAL_ROWS": n_ann,
                     "HAS_VALUATION": has_v, "HAS_SHAREHOLDING": sym in sh_syms,
                     "READY_FOR_SCORING": bool(ready), "ISSUES": "; ".join(issues)})
    rep = pd.DataFrame(rows)
    rep.to_csv(cfg.VALIDATION_FILE, index=False)
    n_ready = int(rep["READY_FOR_SCORING"].sum())
    st, det = status_from_counts(n_ready, len(rep), "ready for scoring")
    return st, det
