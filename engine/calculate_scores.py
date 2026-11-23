"""Multibagger screening score (0-100) -> data/output/multibagger_scores.csv.

This is a transparent rules-based SCREEN, not a prediction or investment advice.
Each component earns 0..max points via a linear scale between a 'floor' and a 'full marks' value.
A component whose input is missing is NOT counted as zero: it is dropped from both the earned
points and the available points, and COVERAGE shows how much of the 100 points was scoreable.
SCORE = earned / available * 100.

A stock is RANKED only if ALL of these hold (the first failing reason is shown in RANK_NOTE):
  1. READY_FOR_SCORING: fresh prices, >= MIN_PRICE_BARS bars, >= MIN_ANNUAL_YEARS annual periods, valuation present
  2. COVERAGE >= MIN_SCORE_COVERAGE (share of the 100 points that could be scored)
  3. every required pillar (growth, quality, valuation, technical) has >= MIN_PILLAR_COVERAGE of its points scoreable
     - this stops a stock being ranked on its strengths alone because its weak/unknown areas dropped out
  4. market cap within cfg.MCAP_BAND_CR (when MCAP_BAND_ENFORCED); outside it the stock is scored but tiered OUT OF SIZE BAND
Scales are deliberately demanding (full marks = exceptional) so the top of the list is not a crowd of 95+ scores.
"""
import numpy as np
import pandas as pd

import config as cfg
from utils import read_csv_safe, status_from_counts

# name, pillar, source column, max points, floor (0 pts), full (max pts), description
COMPONENTS = [
    ("REV_CAGR",      "Growth",        "REV_CAGR",        10, 0.05, 0.40, "Revenue CAGR (~3y): 5% -> 0 pts, 40%+ -> full"),
    ("PAT_CAGR",      "Growth",        "PAT_CAGR",        10, 0.05, 0.50, "Net profit CAGR (~3y): 5% -> 0, 50%+ -> full"),
    ("QTR_REV_YOY",   "Growth",        "QTR_REV_YOY",      5, 0.05, 0.40, "Latest quarter revenue YoY: 5% -> 0, 40%+ -> full"),
    ("QTR_PAT_YOY",   "Growth",        "QTR_PAT_YOY",      5, 0.05, 0.60, "Latest quarter profit YoY: 5% -> 0, 60%+ -> full"),
    ("ROE",           "Quality",       "ROE",             10, 0.08, 0.30, "ROE: 8% -> 0, 30%+ -> full"),
    ("ROCE",          "Quality",       "ROCE",             8, 0.10, 0.30, "ROCE (non-financials): 10% -> 0, 30%+ -> full"),
    ("CFO_TO_PAT",    "Quality",       "CFO_TO_PAT",       7, 0.40, 1.00, "Operating cash flow / profit: 0.4 -> 0, 1.0+ -> full"),
    ("DEBT_EQUITY",   "Balance sheet", "DEBT_EQUITY",     10, 1.50, 0.10, "Debt/equity (non-financials): 1.5+ -> 0, <=0.1 -> full"),
    ("PEG",           "Valuation",     "PEG",             15, 2.50, 0.80, "PEG (growth capped at 40%): 2.5+ -> 0, <=0.8 -> full"),
    ("ABOVE_SMA200",  "Technical",     "ABOVE_SMA200",     4, None, None, "Price above 200-day average (yes = full)"),
    ("GOLDEN",        "Technical",     "SMA50_ABOVE_SMA200", 3, None, None, "50-day above 200-day average (yes = full)"),
    ("RS_12M",        "Technical",     "RS_12M_VS_NIFTY",  5, 0.00, 0.60, "12m return minus Nifty 50: 0 -> 0, +60pp -> full"),
    ("NEAR_HIGH",     "Technical",     "PCT_FROM_52W_HIGH", 3, -0.30, -0.03, "Distance from 52w high: -30% -> 0, within 3% -> full"),
    ("PROMOTER",      "Ownership",     "PROMOTER_PCT",     3, 25.0, 65.0, "Promoter holding %: 25 -> 0, 65+ -> full"),
    ("PLEDGE",        "Ownership",     "PLEDGE_PCT",       2, 25.0, 0.0, "Promoter pledge %: 25+ -> 0, 0 -> full"),
]
assert sum(c[3] for c in COMPONENTS) == 100


def _points(series: pd.Series, mx, lo, full):
    if lo is None:  # boolean flag
        s = series.map({True: 1.0, False: 0.0, "True": 1.0, "False": 0.0})
        return s * mx
    x = pd.to_numeric(series, errors="coerce")
    return mx * ((x - lo) / (full - lo)).clip(0, 1)


def build_scores(universe, tech, fund, val, valid, sh) -> pd.DataFrame:
    df = universe[["SYMBOL", "NAME OF COMPANY", "INDUSTRY"]].copy() if "NAME OF COMPANY" in universe else universe[["SYMBOL", "INDUSTRY"]].copy()
    for part in (fund, tech, val):
        if not part.empty:
            df = df.merge(part.drop(columns=[c for c in part.columns if c in df.columns and c != "SYMBOL"]), on="SYMBOL", how="left")
    if not sh.empty:
        latest = sh.sort_values("AS_ON_DATE", ascending=False).drop_duplicates("SYMBOL")
        df = df.merge(latest[["SYMBOL", "PROMOTER_PCT", "PLEDGE_PCT"]], on="SYMBOL", how="left")
    for col in ("PROMOTER_PCT", "PLEDGE_PCT"):
        if col not in df:
            df[col] = np.nan
    earned = pd.DataFrame(index=df.index)
    avail = pd.DataFrame(index=df.index)
    for name, _, col, mx, lo, full, _ in COMPONENTS:
        src = df[col] if col in df else pd.Series(np.nan, index=df.index)
        pts = _points(src, mx, lo, full)
        earned[name] = pts
        avail[name] = np.where(pts.notna(), mx, 0)
    for name in earned:
        df[f"PTS_{name}"] = earned[name].round(2)
    df["POINTS_EARNED"] = earned.sum(axis=1, skipna=True).round(2)
    df["POINTS_AVAILABLE"] = avail.sum(axis=1)
    df["COVERAGE"] = (df["POINTS_AVAILABLE"] / 100).round(2)
    df["SCORE"] = np.where(df["POINTS_AVAILABLE"] > 0, df["POINTS_EARNED"] / df["POINTS_AVAILABLE"] * 100, np.nan).round(1)
    # ---- pillar coverage ----
    pillars = {}
    for name, pillar, _, mx, *_ in COMPONENTS:
        pillars.setdefault(pillar, []).append((name, mx))
    for pillar, items in pillars.items():
        tot = sum(mx for _, mx in items)
        df[f"COV_{pillar.upper().replace(' ', '_')}"] = (sum(avail[n] for n, _ in items) / tot).round(2)

    ready = valid.set_index("SYMBOL")["READY_FOR_SCORING"] if not valid.empty else pd.Series(dtype=bool)
    df["READY_FOR_SCORING"] = df["SYMBOL"].map(ready).fillna(False).astype(bool)
    mcap = pd.to_numeric(df["MARKET_CAP_CR"], errors="coerce") if "MARKET_CAP_CR" in df else pd.Series(np.nan, index=df.index)
    lo_cap, hi_cap = cfg.MCAP_BAND_CR
    df["SIZE_BAND"] = np.select([mcap.isna(), mcap < lo_cap, mcap > hi_cap],
                                ["unknown", f"below Rs{lo_cap:,} cr", f"above Rs{hi_cap:,} cr"], default="in band")

    notes = pd.Series("", index=df.index)
    def flag(mask, text):
        nonlocal notes
        add = mask & (notes == "")
        notes = notes.mask(add, text)
    flag(~df["READY_FOR_SCORING"], "data not ready (see ISSUES)")
    flag(df["COVERAGE"] < cfg.MIN_SCORE_COVERAGE, f"coverage < {cfg.MIN_SCORE_COVERAGE:.0%}")
    for pillar in cfg.REQUIRED_PILLARS:
        col = f"COV_{pillar.upper()}"
        flag(df[col] < cfg.MIN_PILLAR_COVERAGE, f"{pillar.lower()} data < {cfg.MIN_PILLAR_COVERAGE:.0%} scoreable")
    df["ELIGIBLE"] = notes == ""
    in_band = df["SIZE_BAND"] == "in band" if cfg.MCAP_BAND_ENFORCED else df["SIZE_BAND"] != "unknown"
    df["RANKED"] = df["ELIGIBLE"] & in_band
    notes = notes.mask(df["ELIGIBLE"] & ~in_band, "size band: " + df["SIZE_BAND"])
    df["RANK_NOTE"] = notes
    df["RANK"] = df["SCORE"].where(df["RANKED"]).rank(ascending=False, method="min")
    df["TIER"] = np.select(
        [~df["ELIGIBLE"], ~df["RANKED"], df["SCORE"] >= 70, df["SCORE"] >= 55],
        ["NOT RANKED", "OUT OF SIZE BAND", "A - strong screen", "B - watchlist"], default="C - weak")
    if not valid.empty:
        df = df.merge(valid[["SYMBOL", "ISSUES"]], on="SYMBOL", how="left")
    return df.sort_values(["RANKED", "SCORE"], ascending=[False, False]).reset_index(drop=True)


def run(ctx):
    r = lambda p: read_csv_safe(p)
    fund, tech, val, valid, sh = r(cfg.FUNDAMENTALS_FILE), r(cfg.TECHNICALS_FILE), r(cfg.VALUATION_METRICS_FILE), r(cfg.VALIDATION_FILE), r(cfg.SHAREHOLDING_FILE)
    if fund.empty and tech.empty:
        return "FAILED", "no fundamentals or technicals available"
    scores = build_scores(ctx.universe, tech, fund, val, valid, sh)
    scores.to_csv(cfg.SCORES_FILE, index=False)
    n = int(scores["RANKED"].sum())
    sc = scores.loc[scores["RANKED"], "SCORE"]
    spread = f"score p10/p50/p90 = {sc.quantile(.1):.0f}/{sc.median():.0f}/{sc.quantile(.9):.0f}" if n else ""
    return ("SUCCESS" if n else "PARTIAL"), (f"{n} ranked of {len(scores)} ({int((scores['TIER'] == 'OUT OF SIZE BAND').sum())} out of size band); "
            f"{spread}; top: {', '.join(scores.loc[scores['RANKED'], 'SYMBOL'].head(3))}")
