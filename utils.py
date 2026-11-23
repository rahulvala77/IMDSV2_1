"""Shared helpers. Modules use `import config as cfg` so paths can be redirected in tests."""
import json
import logging
import random
import re
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import config as cfg


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_name(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(symbol))


def load_universe(limit=None, active_only=True) -> pd.DataFrame:
    if not cfg.UNIVERSE_FILE.exists():
        raise FileNotFoundError(f"Missing {cfg.UNIVERSE_FILE}. Copy stock_universe.csv into data/input/.")
    df = pd.read_csv(cfg.UNIVERSE_FILE, dtype=str, encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    if "SYMBOL" not in df.columns:
        raise ValueError("stock_universe.csv must contain a SYMBOL column.")
    df["SYMBOL"] = df["SYMBOL"].str.strip()
    df = df[df["SYMBOL"].notna() & (df["SYMBOL"] != "")]
    dups = int(df["SYMBOL"].duplicated().sum())
    if dups:
        logging.warning("Universe has %d duplicate symbols; keeping first occurrence.", dups)
    df = df.drop_duplicates("SYMBOL", keep="first")
    if active_only and "ACTIVE_STATUS" in df.columns:
        df = df[df["ACTIVE_STATUS"].fillna("ACTIVE").str.upper() == "ACTIVE"]
    fallback = df["SYMBOL"] + ".NS"
    if "YAHOO_TICKER" not in df.columns:
        df["YAHOO_TICKER"] = fallback
    else:
        t = df["YAHOO_TICKER"].fillna("").str.strip()
        df["YAHOO_TICKER"] = t.where(t != "", fallback)
    if "INDUSTRY" not in df.columns:
        df["INDUSTRY"] = np.nan
    if limit:
        df = df.head(int(limit))
    return df.reset_index(drop=True)


def retry(fn, tries=3, base=2.0, label=""):
    """Call fn(); on exception back off and retry. Re-raises the last error."""
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - provider errors vary widely
            if attempt == tries:
                raise
            wait = base ** attempt + random.random()
            logging.debug("%s failed (%s); retry %d in %.1fs", label, exc, attempt, wait)
            time.sleep(wait)


def polite_sleep():
    time.sleep(random.uniform(*cfg.REQUEST_SLEEP))


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def is_financial(industry) -> bool:
    return str(industry).strip() in cfg.FINANCIAL_INDUSTRIES


def read_csv_safe(path, **kw) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, **kw)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


class Ctx:
    """Run options handed to every stage."""
    def __init__(self, universe, limit=None, workers=None, force=False):
        self.universe = universe
        self.limit = limit
        self.workers = workers or cfg.DEFAULT_WORKERS
        self.force = force


def status_from_counts(ok: int, total: int, extra: str = ""):
    if total == 0:
        return "FAILED", "no symbols processed"
    if ok == total:
        return "SUCCESS", f"{ok}/{total} symbols. {extra}".strip()
    if ok == 0:
        return "FAILED", f"0/{total} symbols succeeded. {extra}".strip()
    return "PARTIAL", f"{ok}/{total} symbols. {extra}".strip()
