"""Collect market/valuation fields Yahoo actually supplies into data/input/valuation.csv.

Only fields returned by the provider are stored; anything missing stays blank (never 0).
"""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

import config as cfg
from utils import now_utc, polite_sleep, retry, status_from_counts

FIELDS = {
    "currentPrice": "PRICE", "marketCap": "MARKET_CAP", "enterpriseValue": "ENTERPRISE_VALUE",
    "trailingPE": "PE_TTM", "forwardPE": "PE_FORWARD", "priceToBook": "PB",
    "enterpriseToEbitda": "EV_EBITDA", "trailingEps": "EPS_TTM", "bookValue": "BOOK_VALUE_PS",
    "dividendYield": "DIVIDEND_YIELD_RAW", "sharesOutstanding": "SHARES_OUT",
    "heldPercentInsiders": "INSIDER_HELD_PCT_YAHOO", "heldPercentInstitutions": "INSTITUTION_HELD_PCT_YAHOO",
    "currency": "CURRENCY", "financialCurrency": "FINANCIAL_CURRENCY",
}


def fetch(sym, ticker):
    import yfinance as yf
    polite_sleep()
    info = retry(lambda: yf.Ticker(ticker).get_info(), label=f"{sym}:info") or {}
    row = {"SYMBOL": sym, "YAHOO_TICKER": ticker}
    for src, dst in FIELDS.items():
        row[dst] = info.get(src)
    row["SOURCE"] = "Yahoo Finance via yfinance (third-party, unofficial)"
    row["FETCHED_AT_UTC"] = now_utc()
    return row


def run(ctx):
    pairs = list(zip(ctx.universe["SYMBOL"], ctx.universe["YAHOO_TICKER"]))
    rows, bad = [], []
    with ThreadPoolExecutor(max_workers=ctx.workers) as ex:
        futs = {ex.submit(fetch, s, t): s for s, t in pairs}
        for n, f in enumerate(as_completed(futs), 1):
            try:
                r = f.result()
                if r.get("PRICE") is None and r.get("MARKET_CAP") is None:
                    bad.append(futs[f])
                else:
                    rows.append(r)
            except Exception as exc:  # noqa: BLE001
                bad.append(f"{futs[f]}:{str(exc)[:50]}")
            if n % 25 == 0:
                logging.info("Valuation info: %d/%d done", n, len(pairs))
    if rows:
        df = pd.DataFrame(rows).sort_values("SYMBOL")
        # merge with earlier run so a partial re-run doesn't drop good rows
        old = pd.read_csv(cfg.VALUATION_FILE) if cfg.VALUATION_FILE.exists() else pd.DataFrame()
        if not old.empty:
            old = old[~old["SYMBOL"].isin(df["SYMBOL"])]
            df = pd.concat([old, df], ignore_index=True)
        df.to_csv(cfg.VALUATION_FILE, index=False)
    if bad:
        logging.warning("No valuation data for %d symbols, first 10: %s", len(bad), bad[:10])
    return status_from_counts(len(rows), len(pairs))
