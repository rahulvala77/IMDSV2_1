"""Growth, profitability, cash-flow and leverage metrics -> data/output/fundamentals.csv.

Rules: missing stays NaN; CAGR is NaN when either endpoint is <= 0 (meaningless);
leverage, ROCE and CFO/PAT are NaN for financial companies (not comparable).
"""
import numpy as np
import pandas as pd

import config as cfg
from utils import is_financial, read_csv_safe, status_from_counts

nan = np.nan


def cagr(first, last, years):
    if pd.isna(first) or pd.isna(last) or first <= 0 or last <= 0 or years <= 0:
        return nan
    return (last / first) ** (1 / years) - 1


def div(a, b):
    return a / b if pd.notna(a) and pd.notna(b) and b != 0 else nan


def annual_metrics(a: pd.DataFrame, financial: bool) -> dict:
    a = a.sort_values("FY_END").reset_index(drop=True)
    a["FY_END"] = pd.to_datetime(a["FY_END"])
    n = len(a)
    last = a.iloc[-1]
    out = {"LATEST_FY_END": last["FY_END"].date().isoformat(), "ANNUAL_ROWS": n}
    k = min(3, n - 1)
    if k >= 2:
        first = a.iloc[-1 - k]
        yrs = (last["FY_END"] - first["FY_END"]).days / 365.25
        out["REV_CAGR"] = cagr(first["REVENUE_CR"], last["REVENUE_CR"], yrs)
        out["PAT_CAGR"] = cagr(first["NET_INCOME_CR"], last["NET_INCOME_CR"], yrs)
        out["CAGR_YEARS"] = round(yrs, 1)
        m0, m1 = div(first["OPERATING_INCOME_CR"], first["REVENUE_CR"]), div(last["OPERATING_INCOME_CR"], last["REVENUE_CR"])
        out["OPM_CHANGE_PP"] = (m1 - m0) * 100 if pd.notna(m0) and pd.notna(m1) else nan
    else:
        out.update(REV_CAGR=nan, PAT_CAGR=nan, CAGR_YEARS=nan, OPM_CHANGE_PP=nan)
    out["OPM"] = div(last["OPERATING_INCOME_CR"], last["REVENUE_CR"])
    out["NPM"] = div(last["NET_INCOME_CR"], last["REVENUE_CR"])
    eq = last["EQUITY_CR"]
    prev_eq = a.iloc[-2]["EQUITY_CR"] if n >= 2 else nan
    avg_eq = np.nanmean([eq, prev_eq]) if pd.notna(eq) or pd.notna(prev_eq) else nan
    out["ROE"] = div(last["NET_INCOME_CR"], avg_eq) if pd.notna(avg_eq) and avg_eq > 0 else nan
    if financial:
        out["ROCE"] = nan
        out["DEBT_EQUITY"] = nan
    else:
        ebit = last["EBIT_CR"] if pd.notna(last["EBIT_CR"]) else last["OPERATING_INCOME_CR"]
        cap = last["TOTAL_ASSETS_CR"] - last["CURRENT_LIABILITIES_CR"] if pd.notna(last["TOTAL_ASSETS_CR"]) and pd.notna(last["CURRENT_LIABILITIES_CR"]) else nan
        out["ROCE"] = div(ebit, cap) if pd.notna(cap) and cap > 0 else nan
        out["DEBT_EQUITY"] = div(last["TOTAL_DEBT_CR"], eq) if pd.notna(eq) and eq > 0 else nan
    # For lenders, loan disbursals sit in operating cash flow, so CFO/PAT is meaningless (e.g. -9x) -> blank
    out["CFO_TO_PAT"] = nan if financial else (div(last["CFO_CR"], last["NET_INCOME_CR"]) if pd.notna(last["NET_INCOME_CR"]) and last["NET_INCOME_CR"] > 0 else nan)
    out["FCF_POSITIVE"] = bool(last["FCF_CR"] > 0) if pd.notna(last["FCF_CR"]) else nan
    out["REVENUE_CR_LATEST"] = last["REVENUE_CR"]
    out["PAT_CR_LATEST"] = last["NET_INCOME_CR"]
    return out


def quarterly_metrics(q: pd.DataFrame) -> dict:
    out = {"LATEST_QTR_END": None, "QTR_REV_YOY": nan, "QTR_PAT_YOY": nan}
    if q.empty:
        return out
    q = q.copy()
    q["QUARTER_END"] = pd.to_datetime(q["QUARTER_END"])
    q = q.sort_values("QUARTER_END", ascending=False).reset_index(drop=True)
    cur = q.iloc[0]
    out["LATEST_QTR_END"] = cur["QUARTER_END"].date().isoformat()
    gap = (cur["QUARTER_END"] - q["QUARTER_END"]).dt.days
    match = q[(gap - 365).abs() <= 20]
    if match.empty:
        return out
    prev = match.iloc[0]
    if pd.notna(cur["REVENUE_CR"]) and pd.notna(prev["REVENUE_CR"]) and prev["REVENUE_CR"] > 0:
        out["QTR_REV_YOY"] = cur["REVENUE_CR"] / prev["REVENUE_CR"] - 1
    if pd.notna(cur["NET_INCOME_CR"]) and pd.notna(prev["NET_INCOME_CR"]) and prev["NET_INCOME_CR"] > 0:
        out["QTR_PAT_YOY"] = cur["NET_INCOME_CR"] / prev["NET_INCOME_CR"] - 1
    return out


def run(ctx):
    ann = read_csv_safe(cfg.ANNUAL_FINANCIAL_FILE)
    qtr = read_csv_safe(cfg.QUARTERLY_RESULTS_FILE)
    if ann.empty:
        return "FAILED", "annual_financials.csv missing/empty - run annual_financial_extraction first"
    ind = dict(zip(ctx.universe["SYMBOL"], ctx.universe["INDUSTRY"]))
    rows = []
    for sym, a in ann.groupby("SYMBOL"):
        if sym not in ind:
            continue
        fin = is_financial(ind[sym])
        r = {"SYMBOL": sym, "IS_FINANCIAL": fin, **annual_metrics(a, fin)}
        r.update(quarterly_metrics(qtr[qtr["SYMBOL"] == sym] if not qtr.empty else qtr))
        rows.append(r)
    if rows:
        pd.DataFrame(rows).to_csv(cfg.FUNDAMENTALS_FILE, index=False)
    return status_from_counts(len(rows), len(ctx.universe))
