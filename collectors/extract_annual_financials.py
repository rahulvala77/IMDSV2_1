"""Build data/input/annual_financials.csv from archived statements (INR crore).

Units: Yahoo reports absolute currency units; we divide by 1e7 -> INR crore. EPS is per share.
Reporting basis (standalone vs consolidated) is NOT exposed by Yahoo -> BASIS column says so.
Missing line items stay blank.
"""
import logging

import numpy as np
import pandas as pd

import config as cfg
from utils import now_utc, read_json, safe_name, status_from_counts

INCOME = {
    "REVENUE_CR": ["Total Revenue", "Operating Revenue"],
    "EBITDA_CR": ["EBITDA", "Normalized EBITDA"],
    "OPERATING_INCOME_CR": ["Operating Income", "Total Operating Income As Reported"],
    "EBIT_CR": ["EBIT"],
    "INTEREST_EXPENSE_CR": ["Interest Expense", "Interest Expense Non Operating"],
    "NET_INCOME_CR": ["Net Income Common Stockholders", "Net Income"],
}
BALANCE = {
    "TOTAL_ASSETS_CR": ["Total Assets"],
    "CURRENT_LIABILITIES_CR": ["Current Liabilities", "Total Current Liabilities"],
    "TOTAL_DEBT_CR": ["Total Debt"],
    "EQUITY_CR": ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"],
    "CASH_CR": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
}
CASH = {
    "CFO_CR": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "CAPEX_CR": ["Capital Expenditure"],
    "FCF_CR": ["Free Cash Flow"],
}
EPS_ROWS = ["Diluted EPS", "Basic EPS"]
BASIS = "NOT_DISCLOSED_BY_SOURCE"


def read_statement(path):
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col=0)
    df.columns = pd.to_datetime(df.columns, errors="coerce")
    return df.loc[:, df.columns.notna()]


def pick(df, col, candidates, scale=cfg.CRORE):
    if df is None or col not in df.columns:
        return np.nan
    for name in candidates:
        if name in df.index:
            v = df.at[name, col]
            if pd.notna(v):
                return float(v) / scale
    return np.nan


def extract_symbol(sym) -> list:
    folder = cfg.RAW_FILINGS / safe_name(sym)
    inc, bal, cf = (read_statement(folder / f"{n}.csv") for n in ("income_stmt", "balance_sheet", "cashflow"))
    if inc is None:
        return []
    meta = read_json(folder / "meta.json") or {}
    rows = []
    for d in sorted(inc.columns):
        r = {"SYMBOL": sym, "FY_END": d.date().isoformat()}
        for k, c in INCOME.items():
            r[k] = pick(inc, d, c)
        r["EPS"] = pick(inc, d, EPS_ROWS, scale=1)
        for k, c in BALANCE.items():
            r[k] = pick(bal, d, c)
        for k, c in CASH.items():
            r[k] = pick(cf, d, c)
        r.update(UNITS="INR_CRORE (EPS: INR/share)", BASIS=BASIS,
                 SOURCE=meta.get("source", "Yahoo Finance via yfinance"),
                 FETCHED_AT_UTC=meta.get("fetched_at_utc", now_utc()))
        # drop periods where the provider gave nothing useful
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
        pd.DataFrame(rows).to_csv(cfg.ANNUAL_FINANCIAL_FILE, index=False)
    return status_from_counts(ok, len(ctx.universe), f"{len(rows)} annual rows")
