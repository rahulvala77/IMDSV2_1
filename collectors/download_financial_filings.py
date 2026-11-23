"""Fetch financial statements per symbol and archive them untouched in data/raw_filings/<SYMBOL>/.

Source: Yahoo Finance via yfinance (income statement, balance sheet, cash flow - annual; income
statement - quarterly). This is a *third-party aggregation*, not the official NSE/BSE XBRL filing.
Each folder gets meta.json with source, fetch time and provider version so values stay traceable.
"""
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import config as cfg
from utils import now_utc, polite_sleep, read_json, retry, safe_name, status_from_counts

STATEMENTS = {
    "income_stmt": "income_stmt",
    "balance_sheet": "balance_sheet",
    "cashflow": "cashflow",
    "quarterly_income_stmt": "quarterly_income_stmt",
}


def _fresh(meta_path) -> bool:
    meta = read_json(meta_path)
    if not meta or meta.get("status") != "OK":
        return False
    try:
        age = datetime.now(timezone.utc) - datetime.fromisoformat(meta["fetched_at_utc"])
        return age.days < cfg.RAW_MAX_AGE_DAYS
    except Exception:  # noqa: BLE001
        return False


def fetch_symbol(sym, ticker, force=False):
    import yfinance as yf
    folder = cfg.RAW_FILINGS / safe_name(sym)
    folder.mkdir(parents=True, exist_ok=True)
    meta_path = folder / "meta.json"
    if not force and _fresh(meta_path):
        return sym, "CACHED", ""
    polite_sleep()
    t = yf.Ticker(ticker)
    got = []
    for name, attr in STATEMENTS.items():
        df = retry(lambda a=attr: getattr(t, a), label=f"{sym}:{name}")
        if df is not None and not df.empty:
            df.to_csv(folder / f"{name}.csv")
            got.append(name)
    status = "OK" if len(got) == len(STATEMENTS) else ("PARTIAL" if got else "EMPTY")
    meta = {"symbol": sym, "ticker": ticker, "source": "Yahoo Finance via yfinance (third-party, unofficial)",
            "source_url": f"https://finance.yahoo.com/quote/{ticker}/financials",
            "fetched_at_utc": now_utc(), "yfinance_version": getattr(yf, "__version__", "?"),
            "statements": got, "status": "OK" if got else "EMPTY"}
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return sym, status, ",".join(got)


def run(ctx):
    pairs = list(zip(ctx.universe["SYMBOL"], ctx.universe["YAHOO_TICKER"]))
    ok, bad = 0, []
    with ThreadPoolExecutor(max_workers=ctx.workers) as ex:
        futs = {ex.submit(fetch_symbol, s, t, ctx.force): s for s, t in pairs}
        for n, f in enumerate(as_completed(futs), 1):
            s = futs[f]
            try:
                _, st, _ = f.result()
                if st in ("OK", "CACHED", "PARTIAL"):
                    ok += 1
                else:
                    bad.append(f"{s}:{st}")
            except Exception as exc:  # noqa: BLE001
                bad.append(f"{s}:ERR {str(exc)[:60]}")
            if n % 25 == 0:
                logging.info("Statements: %d/%d done", n, len(pairs))
    if bad:
        logging.warning("Statement fetch problems (%d), first 10: %s", len(bad), bad[:10])
    return status_from_counts(ok, len(pairs), f"problems sample: {bad[:3]}" if bad else "")
