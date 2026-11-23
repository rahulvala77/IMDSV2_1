"""Download daily OHLCV history from Yahoo Finance (via yfinance) into data/price_history/<SYMBOL>.csv.

Source: Yahoo Finance - third-party, unofficial. Prices are NOT adjusted for splits/bonus by NSE;
we store Yahoo's split-adjusted `Close` plus `Adj Close` so the user can see both.
"""
import logging

import pandas as pd

import config as cfg
from utils import retry, safe_name, status_from_counts


def _save(df: pd.DataFrame, name: str) -> bool:
    df = df.dropna(how="all")
    if df.empty or "Close" not in df.columns or df["Close"].dropna().empty:
        return False
    df.index.name = "Date"
    df.to_csv(cfg.PRICE_HISTORY / f"{name}.csv")
    return True


def _download(tickers, period):
    import yfinance as yf
    return yf.download(tickers, period=period, group_by="ticker", auto_adjust=False,
                       threads=True, progress=False)


def run(ctx):
    uni = ctx.universe
    pairs = list(zip(uni["SYMBOL"], uni["YAHOO_TICKER"]))
    ok, failed = 0, []

    # benchmark first (needed for relative strength)
    try:
        b = retry(lambda: _download([cfg.BENCHMARK_TICKER], cfg.PRICE_PERIOD), label="benchmark")
        if isinstance(b.columns, pd.MultiIndex):
            b = b[cfg.BENCHMARK_TICKER]
        if not _save(b, cfg.BENCHMARK_FILE_NAME):
            logging.warning("Benchmark %s returned no data; relative strength will be blank.", cfg.BENCHMARK_TICKER)
    except Exception as exc:  # noqa: BLE001
        logging.warning("Benchmark download failed: %s", exc)

    for i in range(0, len(pairs), cfg.PRICE_BATCH_SIZE):
        batch = pairs[i:i + cfg.PRICE_BATCH_SIZE]
        tickers = [t for _, t in batch]
        logging.info("Prices: batch %d-%d of %d", i + 1, i + len(batch), len(pairs))
        try:
            data = retry(lambda: _download(tickers, cfg.PRICE_PERIOD), label="price batch")
        except Exception as exc:  # noqa: BLE001
            logging.error("Batch failed: %s", exc)
            failed += [s for s, _ in batch]
            continue
        for sym, tk in batch:
            try:
                sub = data[tk] if isinstance(data.columns, pd.MultiIndex) else data
                if _save(sub.copy(), safe_name(sym)):
                    ok += 1
                else:
                    failed.append(sym)
            except KeyError:
                failed.append(sym)
    if failed:
        logging.warning("No price data for %d symbols (first 15): %s", len(failed), failed[:15])
    return status_from_counts(ok, len(pairs), f"failed sample: {failed[:5]}" if failed else "")
