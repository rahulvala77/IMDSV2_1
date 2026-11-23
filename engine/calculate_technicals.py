"""Trend, momentum, relative strength and volume metrics from price history -> technicals.csv."""
import numpy as np
import pandas as pd

import config as cfg
from utils import safe_name, status_from_counts

TD = {"RET_1M": 21, "RET_3M": 63, "RET_6M": 126, "RET_12M": 252}


def rsi(close: pd.Series, n=14) -> float:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    last_dn = dn.iloc[-1]
    if pd.isna(last_dn):
        return np.nan
    if last_dn == 0:
        return 100.0
    return float(100 - 100 / (1 + up.iloc[-1] / last_dn))


def load_prices(path):
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    if "Close" not in df.columns:
        return None
    df = df[~df.index.duplicated()].sort_index()
    return df.dropna(subset=["Close"])


def ret(close, n):
    return float(close.iloc[-1] / close.iloc[-1 - n] - 1) if len(close) > n else np.nan


def metrics(df: pd.DataFrame, bench_ret12=np.nan) -> dict:
    c = df["Close"].astype(float)
    out = {"LAST_DATE": c.index[-1].date().isoformat(), "BARS": len(c), "CLOSE": float(c.iloc[-1])}
    for k, n in TD.items():
        out[k] = ret(c, n)
    sma50 = c.rolling(50).mean().iloc[-1] if len(c) >= 50 else np.nan
    sma200 = c.rolling(200).mean().iloc[-1] if len(c) >= 200 else np.nan
    out.update(SMA50=sma50, SMA200=sma200, RSI14=rsi(c))
    out["ABOVE_SMA200"] = bool(c.iloc[-1] > sma200) if pd.notna(sma200) else np.nan
    out["SMA50_ABOVE_SMA200"] = bool(sma50 > sma200) if pd.notna(sma50) and pd.notna(sma200) else np.nan
    win = c.iloc[-252:]
    out["HIGH_52W"] = float(win.max())
    out["PCT_FROM_52W_HIGH"] = float(c.iloc[-1] / win.max() - 1)
    if "Volume" in df.columns and len(df) >= 100:
        v = df["Volume"].astype(float)
        base = v.iloc[-100:].mean()
        out["VOL_RATIO_20_100"] = float(v.iloc[-20:].mean() / base) if base > 0 else np.nan
    else:
        out["VOL_RATIO_20_100"] = np.nan
    out["RS_12M_VS_NIFTY"] = out["RET_12M"] - bench_ret12 if pd.notna(out["RET_12M"]) and pd.notna(bench_ret12) else np.nan
    return out


def run(ctx):
    bench = load_prices(cfg.PRICE_HISTORY / f"{cfg.BENCHMARK_FILE_NAME}.csv")
    b12 = ret(bench["Close"].astype(float), TD["RET_12M"]) if bench is not None else np.nan
    rows = []
    for sym in ctx.universe["SYMBOL"]:
        df = load_prices(cfg.PRICE_HISTORY / f"{safe_name(sym)}.csv")
        if df is None or len(df) < 30:
            continue
        rows.append({"SYMBOL": sym, **metrics(df, b12)})
    if rows:
        pd.DataFrame(rows).to_csv(cfg.TECHNICALS_FILE, index=False)
    return status_from_counts(len(rows), len(ctx.universe), "" if pd.notna(b12) else "Nifty benchmark missing -> RS blank")
