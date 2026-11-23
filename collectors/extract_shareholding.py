"""Promoter / public shareholding and promoter pledge from NSE's public website API.

IMPORTANT: NSE has no documented public API. These are the JSON endpoints the nseindia.com
website itself calls; they need browser-like headers + a cookie from the home page, can block
you (HTTP 401/403), and can change without notice. So:
  * the raw JSON for every symbol is archived in data/raw_filings/<SYMBOL>/nse_*.json,
  * field mapping is defensive (several candidate key names),
  * if a field can't be found it stays blank - nothing is guessed.
Test with:  py IMDS_auto_update.py --stages shareholding_extraction --limit 5
and open data/raw_filings/<SYMBOL>/nse_shareholding.json if PROMOTER_PCT comes out blank.
"""
import json
import logging
import time

import pandas as pd
import requests

import config as cfg
from utils import now_utc, polite_sleep, safe_name, status_from_counts

BASE = "https://www.nseindia.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0 Safari/537.36")
PROMOTER_KEYS = ["pr_and_prgrp", "promoterAndPromoterGroup", "promoter", "PROMOTER"]
PUBLIC_KEYS = ["public_val", "publicVal", "public", "PUBLIC"]
DATE_KEYS = ["date", "asOnDate", "quarter", "period_ended", "DATE"]
PLEDGE_KEYS = ["percSharesPledged", "perPledged", "pledgedPercentage", "percPromoterShares", "percOfTotalShares"]


class NSE:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                               "Accept-Language": "en-US,en;q=0.9", "Referer": BASE + "/"})
        self._warm()

    def _warm(self):
        self.s.get(BASE, timeout=20)
        self.s.get(BASE + "/companies-listing/corporate-filings-shareholding-pattern", timeout=20)

    def get(self, path, params):
        for attempt in (1, 2, 3):
            r = self.s.get(BASE + path, params=params, timeout=25)
            if r.status_code in (401, 403):
                time.sleep(2 * attempt)
                self._warm()
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("blocked by NSE (401/403) after 3 attempts")


def _first(row, keys):
    for k in keys:
        if k in row and row[k] not in (None, "", "-"):
            return row[k]
    return None


def _num(x):
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return float("nan")


def _rows(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("data", "rows", "records"):
            if isinstance(payload.get(k), list):
                return payload[k]
    return []


def parse_shareholding(sym, payload):
    out = []
    for r in _rows(payload):
        if not isinstance(r, dict):
            continue
        d = pd.to_datetime(_first(r, DATE_KEYS), errors="coerce", dayfirst=True)
        out.append({"SYMBOL": sym, "AS_ON_DATE": d.date().isoformat() if pd.notna(d) else None,
                    "PROMOTER_PCT": _num(_first(r, PROMOTER_KEYS)),
                    "PUBLIC_PCT": _num(_first(r, PUBLIC_KEYS)), "PLEDGE_PCT": float("nan")})
    out = [r for r in out if r["AS_ON_DATE"]]
    return sorted(out, key=lambda r: r["AS_ON_DATE"], reverse=True)


def parse_pledge(payload):
    rows = [r for r in _rows(payload) if isinstance(r, dict)]
    for r in rows:  # endpoint lists newest first
        v = _num(_first(r, PLEDGE_KEYS))
        if v == v:
            return v
    return float("nan")


def run(ctx):
    syms = list(ctx.universe["SYMBOL"])
    try:
        nse = NSE()
    except Exception as exc:  # noqa: BLE001
        return "FAILED", f"could not open NSE session: {exc}. Try again later / from another network."
    rows, ok, bad = [], 0, []
    for n, sym in enumerate(syms, 1):
        folder = cfg.RAW_FILINGS / safe_name(sym)
        folder.mkdir(parents=True, exist_ok=True)
        try:
            polite_sleep()
            sh = nse.get("/api/corporate-share-holdings-master", {"index": "equities", "symbol": sym})
            (folder / "nse_shareholding.json").write_text(json.dumps(sh)[:2_000_000], encoding="utf-8")
            parsed = parse_shareholding(sym, sh)
            polite_sleep()
            try:
                pl = nse.get("/api/corporate-pledgedata", {"index": "equities", "symbol": sym})
                (folder / "nse_pledge.json").write_text(json.dumps(pl)[:2_000_000], encoding="utf-8")
                if parsed:
                    parsed[0]["PLEDGE_PCT"] = parse_pledge(pl)
            except Exception as exc:  # noqa: BLE001 - pledge is optional
                logging.debug("%s pledge: %s", sym, exc)
            if parsed and any(p["PROMOTER_PCT"] == p["PROMOTER_PCT"] for p in parsed):
                for p in parsed:
                    p.update(SOURCE="NSE website API (unofficial endpoint)", FETCHED_AT_UTC=now_utc())
                rows += parsed
                ok += 1
            else:
                bad.append(sym)
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{sym}:{str(exc)[:40]}")
        if n % 25 == 0:
            logging.info("Shareholding: %d/%d", n, len(syms))
    if rows:
        pd.DataFrame(rows).to_csv(cfg.SHAREHOLDING_FILE, index=False)
    if bad:
        logging.warning("Shareholding missing for %d symbols, first 10: %s", len(bad), bad[:10])
    return status_from_counts(ok, len(syms), f"{len(rows)} rows")
