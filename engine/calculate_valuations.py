"""Valuation ratios -> data/output/valuation_metrics.csv.

Uses only provider-supplied ratios. PE/EV-EBITDA <= 0 are set blank (loss-making / meaningless).
PEG = PE_TTM / (PAT CAGR in %), only when both are positive. The growth used is capped at
cfg.PEG_GROWTH_CAP (40%): triple-digit growth off a tiny base would otherwise make an expensive
stock (e.g. P/E 100) look cheap. PEG_GROWTH_USED shows the capped figure that was applied.
"""
import numpy as np
import pandas as pd

import config as cfg
from utils import read_csv_safe, status_from_counts


def run(ctx):
    val = read_csv_safe(cfg.VALUATION_FILE)
    if val.empty:
        return "FAILED", "valuation.csv missing/empty - run valuation_data_collection first"
    fund = read_csv_safe(cfg.FUNDAMENTALS_FILE)
    df = val.merge(fund[["SYMBOL", "PAT_CAGR"]], on="SYMBOL", how="left") if not fund.empty else val.assign(PAT_CAGR=np.nan)
    for c in ("PE_TTM", "PE_FORWARD", "PB", "EV_EBITDA", "MARKET_CAP", "PAT_CAGR"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    for c in ("PE_TTM", "PE_FORWARD", "EV_EBITDA", "PB"):
        df.loc[df[c] <= 0, c] = np.nan
    df["MARKET_CAP_CR"] = df["MARKET_CAP"] / cfg.CRORE
    df["EARNINGS_YIELD"] = 1 / df["PE_TTM"]
    df["PEG_GROWTH_USED"] = df["PAT_CAGR"].clip(upper=cfg.PEG_GROWTH_CAP)
    g = df["PEG_GROWTH_USED"] * 100
    df["PEG"] = np.where((df["PE_TTM"] > 0) & (g > 0), df["PE_TTM"] / g, np.nan)
    keep = ["SYMBOL", "PRICE", "MARKET_CAP_CR", "PE_TTM", "PE_FORWARD", "PB", "EV_EBITDA", "EARNINGS_YIELD", "PEG_GROWTH_USED", "PEG", "FETCHED_AT_UTC"]
    out = df[[c for c in keep if c in df.columns]]
    out = out[out["SYMBOL"].isin(ctx.universe["SYMBOL"])]
    out.to_csv(cfg.VALUATION_METRICS_FILE, index=False)
    return status_from_counts(len(out), len(ctx.universe), f"PEG available for {int(out['PEG'].notna().sum())}")
