"""Build data/input/quarterly_results.csv (INR crore) from archived quarterly income statements."""
import numpy as np
import pandas as pd

import config as cfg
from collectors.extract_annual_financials import BASIS, pick, read_statement
from utils import now_utc, read_json, safe_name, status_from_counts

Q = {
    "REVENUE_CR": ["Total Revenue", "Operating Revenue"],
    "EBITDA_CR": ["EBITDA", "Normalized EBITDA"],
    "OPERATING_INCOME_CR": ["Operating Income"],
    "NET_INCOME_CR": ["Net Income Common Stockholders", "Net Income"],
}


def extract_symbol(sym):
    folder = cfg.RAW_FILINGS / safe_name(sym)
    q = read_statement(folder / "quarterly_income_stmt.csv")
    if q is None:
        return []
    meta = read_json(folder / "meta.json") or {}
    rows = []
    for d in sorted(q.columns):
        r = {"SYMBOL": sym, "QUARTER_END": d.date().isoformat()}
        for k, c in Q.items():
            r[k] = pick(q, d, c)
        r["EPS"] = pick(q, d, ["Diluted EPS", "Basic EPS"], scale=1)
        r.update(UNITS="INR_CRORE (EPS: INR/share)", BASIS=BASIS,
                 SOURCE=meta.get("source", "Yahoo Finance via yfinance"),
                 FETCHED_AT_UTC=meta.get("fetched_at_utc", now_utc()))
        if pd.notna(r["REVENUE_CR"]) or pd.notna(r["NET_INCOME_CR"]):
            rows.append(r)
    return rows


def run(ctx):
    rows, ok = [], 0
    for sym in ctx.universe["SYMBOL"]:
        r = extract_symbol(sym)
        if r:
            rows += r
            ok += 1
    if rows:
        pd.DataFrame(rows).to_csv(cfg.QUARTERLY_RESULTS_FILE, index=False)
    return status_from_counts(ok, len(ctx.universe), f"{len(rows)} quarterly rows")
