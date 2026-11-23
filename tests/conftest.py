import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as cfg  # noqa: E402

PATHS = ["DATA", "INPUT", "RAW_FILINGS", "PRICE_HISTORY", "OUTPUT", "REPORTS", "LOGS"]
FILES = {"UNIVERSE_FILE": "input/stock_universe.csv", "TECHNICALS_FILE": "input/technicals.csv",
         "ANNUAL_FINANCIAL_FILE": "input/annual_financials.csv", "QUARTERLY_RESULTS_FILE": "input/quarterly_results.csv",
         "SHAREHOLDING_FILE": "input/shareholding.csv", "VALUATION_FILE": "input/valuation.csv",
         "FUNDAMENTALS_FILE": "output/fundamentals.csv", "VALUATION_METRICS_FILE": "output/valuation_metrics.csv",
         "VALIDATION_FILE": "output/validation_report.csv", "SCORES_FILE": "output/multibagger_scores.csv",
         "STATUS_FILE": "output/pipeline_status.csv"}


def _prices(n, drift, seed, end=None):
    rng = np.random.default_rng(seed)
    end = end or date.today()
    idx = pd.bdate_range(end=end, periods=n)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, 0.01, n)))
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close,
                         "Adj Close": close, "Volume": rng.integers(1e5, 2e5, n)}, index=idx)


def _statement(path, rows: dict, dates):
    df = pd.DataFrame(rows, index=[pd.Timestamp(d) for d in dates]).T
    df.columns = [str(c) for c in df.columns]
    df.to_csv(path)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    for name in PATHS:
        sub = {"DATA": "data", "INPUT": "data/input", "RAW_FILINGS": "data/raw_filings", "PRICE_HISTORY": "data/price_history",
               "OUTPUT": "data/output", "REPORTS": "reports", "LOGS": "logs"}[name]
        p = tmp_path / sub
        p.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(cfg, name, p)
    for name, rel in FILES.items():
        monkeypatch.setattr(cfg, name, tmp_path / "data" / rel if rel.startswith(("input", "output")) else tmp_path / rel)

    syms = {  # symbol: (industry, rev growth, profit growth, n_annual, price drift)
        "GROW": ("Capital Goods", 0.25, 0.35, 4, 0.003),
        "SLOW": ("Capital Goods", 0.02, -0.05, 4, -0.001),
        "BANKX": ("Financial Services", 0.18, 0.22, 4, 0.002),
        "NEWCO": ("Chemicals", 0.30, 0.30, 2, 0.002),
        "STALE": ("Chemicals", 0.20, 0.20, 4, 0.002),
        "NEWLIST": ("Capital Goods", 0.30, 0.40, 4, 0.003),     # only ~120 price bars (recent IPO)
        "BIGCAP": ("Capital Goods", 0.25, 0.35, 4, 0.003),      # Rs 2 lakh crore market cap
        "LOWBASE": ("Capital Goods", 0.40, 1.30, 4, 0.003),     # 130% profit CAGR, P/E 100
        "LOSS": ("Healthcare", 0.10, 0.0, 4, 0.001),
    }
    uni = pd.DataFrame([{"SYMBOL": s, "NAME OF COMPANY": f"{s} Ltd", "YAHOO_TICKER": f"{s}.NS", "INDUSTRY": v[0],
                         "ACTIVE_STATUS": "ACTIVE"} for s, v in syms.items()])
    uni.to_csv(cfg.UNIVERSE_FILE, index=False)

    fy = ["2025-03-31", "2024-03-31", "2023-03-31", "2022-03-31"]
    qs = ["2026-09-30", "2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"]
    val_rows, sh_rows = [], []
    for i, (s, (ind, rg, pg, n, drift)) in enumerate(syms.items()):
        d = cfg.RAW_FILINGS / s
        d.mkdir()
        dates = fy[:n]
        rev0, pat0 = 1000e7, 100e7 if s != "LOSS" else -50e7
        revs = [rev0 / (1 + rg) ** k for k in range(n)]
        pats = [pat0 / (1 + pg) ** k if s != "LOSS" else pat0 for k in range(n)]
        _statement(d / "income_stmt.csv", {"Total Revenue": revs, "Operating Income": [r * .18 for r in revs],
                   "EBIT": [r * .17 for r in revs], "Net Income": pats, "Diluted EPS": [5.0] * n}, dates)
        _statement(d / "balance_sheet.csv", {"Total Assets": [800e7] * n, "Current Liabilities": [200e7] * n,
                   "Total Debt": [100e7] * n, "Stockholders Equity": [500e7] * n}, dates)
        _statement(d / "cashflow.csv", {"Operating Cash Flow": [p * 0.9 for p in pats], "Free Cash Flow": [50e7] * n}, dates)
        qrev = [250e7 * (1 + rg) ** (-k / 4) for k in range(5)]
        _statement(d / "quarterly_income_stmt.csv", {"Total Revenue": qrev, "Net Income": [r * .1 for r in qrev]}, qs)
        (d / "meta.json").write_text('{"source":"synthetic","fetched_at_utc":"2026-11-20T00:00:00+00:00"}')
        end = date.today() - timedelta(days=30 if s == "STALE" else 0)
        _prices(120 if s == 'NEWLIST' else 300, drift, i, end).to_csv(cfg.PRICE_HISTORY / f"{s}.csv")
        val_rows.append({"SYMBOL": s, "PRICE": 100, "MARKET_CAP": (2e6 if s == "BIGCAP" else 5000) * 1e7,
                         "PE_TTM": {"LOSS": -5, "LOWBASE": 100}.get(s, 20),
                         "PE_FORWARD": 18, "PB": 3, "EV_EBITDA": 12, "FETCHED_AT_UTC": "2026-11-20T00:00:00+00:00"})
        if s != "NEWCO":
            sh_rows.append({"SYMBOL": s, "AS_ON_DATE": "2026-09-30", "PROMOTER_PCT": 55.0, "PUBLIC_PCT": 45.0,
                            "PLEDGE_PCT": 0.0})
    _prices(300, 0.001, 99).to_csv(cfg.PRICE_HISTORY / f"{cfg.BENCHMARK_FILE_NAME}.csv")
    pd.DataFrame(val_rows).to_csv(cfg.VALUATION_FILE, index=False)
    pd.DataFrame(sh_rows).to_csv(cfg.SHAREHOLDING_FILE, index=False)

    from utils import Ctx, load_universe
    return Ctx(load_universe())
