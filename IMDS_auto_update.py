#!/usr/bin/env python3
"""IMDS v2.0 orchestrator.

Examples (PowerShell, venv active):
    py IMDS_auto_update.py --limit 10                     # smoke test on 10 symbols
    py IMDS_auto_update.py                                # full run
    py IMDS_auto_update.py --stages technical_data_collection,technical_calc
    py IMDS_auto_update.py --skip shareholding_extraction # if NSE blocks you
    py IMDS_auto_update.py --offline                      # recompute from already-downloaded data
"""
import argparse
import logging
import sys
from datetime import datetime, timezone

import pandas as pd

import config as cfg
from utils import Ctx, load_universe

from collectors import (download_financial_filings, download_technical_data, download_valuation_data,
                        extract_annual_financials, extract_quarterly_results, extract_shareholding)
from engine import (build_report, calculate_fundamentals, calculate_scores, calculate_technicals,
                    calculate_valuations, validate_data)

# (stage name, module, needs network)
STAGES = [
    ("technical_data_collection", download_technical_data, True),
    ("financial_filings_collection", download_financial_filings, True),
    ("valuation_data_collection", download_valuation_data, True),
    ("shareholding_extraction", extract_shareholding, True),
    ("annual_financial_extraction", extract_annual_financials, False),
    ("quarterly_results_extraction", extract_quarterly_results, False),
    ("technical_calc", calculate_technicals, False),
    ("fundamentals_calc", calculate_fundamentals, False),
    ("valuation_calculation", calculate_valuations, False),
    ("data_validation", validate_data, False),
    ("multibagger_scoring", calculate_scores, False),
    ("excel_report", build_report, False),
]


def setup_logging():
    log_file = cfg.LOGS / f"imds_{datetime.now():%Y%m%d_%H%M%S}.log"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s",
                        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)])
    for noisy in ("yfinance", "urllib3", "peewee"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, help="only the first N symbols (smoke test)")
    ap.add_argument("--stages", help="comma-separated stage names to run (default: all)")
    ap.add_argument("--skip", help="comma-separated stage names to skip")
    ap.add_argument("--offline", action="store_true", help="skip all network stages")
    ap.add_argument("--force", action="store_true", help="ignore cached raw statements")
    ap.add_argument("--workers", type=int, default=cfg.DEFAULT_WORKERS)
    args = ap.parse_args(argv)

    setup_logging()
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    universe = load_universe(limit=args.limit)
    logging.info("IMDS v2.0 run - universe: %d symbols", len(universe))
    ctx = Ctx(universe, args.limit, args.workers, args.force)

    wanted = set(args.stages.split(",")) if args.stages else None
    skipped = set(args.skip.split(",")) if args.skip else set()
    names = {s[0] for s in STAGES}
    for bad in (wanted or set()) | skipped:
        if bad not in names:
            ap.error(f"unknown stage '{bad}'. Valid: {', '.join(sorted(names))}")

    rows = [(started, "universe_validation", "SUCCESS", f"{len(universe)} unique active symbols")]
    for name, mod, net in STAGES:
        if (wanted and name not in wanted) or name in skipped or (args.offline and net):
            rows.append((started, name, "SKIPPED", "not selected / offline"))
            continue
        logging.info(">>> %s", name)
        try:
            status, details = mod.run(ctx)
        except Exception as exc:  # noqa: BLE001 - one stage must not kill the pipeline
            logging.exception("Stage %s crashed", name)
            status, details = "FAILED", f"{type(exc).__name__}: {exc}"
        logging.info("<<< %s: %s - %s", name, status, details)
        rows.append((started, name, status, details))
        pd.DataFrame(rows, columns=["RUN_TIMESTAMP_UTC", "STAGE", "STATUS", "DETAILS"]).to_csv(cfg.STATUS_FILE, index=False)

    # re-write final status (the report stage reads the status file, so refresh it once more)
    pd.DataFrame(rows, columns=["RUN_TIMESTAMP_UTC", "STAGE", "STATUS", "DETAILS"]).to_csv(cfg.STATUS_FILE, index=False)
    logging.info("Done. Status: %s", cfg.STATUS_FILE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
