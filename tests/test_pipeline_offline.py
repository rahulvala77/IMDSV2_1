"""End-to-end test of every offline stage on synthetic yfinance-shaped data (no network needed)."""
import numpy as np
import pandas as pd

import config as cfg
from collectors import extract_annual_financials as ann, extract_quarterly_results as qtr
from engine import (build_report, calculate_fundamentals as fund, calculate_scores as scr, calculate_technicals as tech,
                    calculate_valuations as val, validate_data as vd)
from engine.calculate_technicals import rsi


def run_all(ctx):
    for m in (ann, qtr, tech, fund, val, vd, scr):
        status, details = m.run(ctx)
        assert status in ("SUCCESS", "PARTIAL"), (m.__name__, status, details)


def test_rsi_bounds():
    up = pd.Series(np.arange(1, 60, dtype=float))
    assert rsi(up) == 100.0
    assert 0 <= rsi(pd.Series(np.sin(np.arange(100)) + 5)) <= 100


def test_annual_extraction_units_and_missing(sandbox):
    ann.run(sandbox)
    a = pd.read_csv(cfg.ANNUAL_FINANCIAL_FILE)
    g = a[(a.SYMBOL == "GROW") & (a.FY_END == "2025-03-31")].iloc[0]
    assert abs(g.REVENUE_CR - 1000) < 1e-6          # 1000e7 INR -> 1000 crore
    assert pd.isna(g.CASH_CR)                         # not supplied -> stays blank, not 0
    assert (a.BASIS == "NOT_DISCLOSED_BY_SOURCE").all()


def test_fundamentals(sandbox):
    run_all(sandbox)
    f = pd.read_csv(cfg.FUNDAMENTALS_FILE).set_index("SYMBOL")
    assert abs(f.at["GROW", "REV_CAGR"] - 0.25) < 0.01
    assert abs(f.at["GROW", "PAT_CAGR"] - 0.35) < 0.01
    assert pd.isna(f.at["LOSS", "PAT_CAGR"])                      # negative base -> no CAGR
    assert pd.isna(f.at["BANKX", "ROCE"]) and pd.isna(f.at["BANKX", "DEBT_EQUITY"])   # financials skip
    assert not pd.isna(f.at["GROW", "ROCE"])
    assert f.at["GROW", "QTR_REV_YOY"] > 0.2


def test_valuation_peg_and_losses(sandbox):
    run_all(sandbox)
    v = pd.read_csv(cfg.VALUATION_METRICS_FILE).set_index("SYMBOL")
    assert abs(v.at["GROW", "PEG"] - 20 / 35) < 0.05
    assert pd.isna(v.at["LOSS", "PE_TTM"]) and pd.isna(v.at["LOSS", "PEG"])


def test_validation_flags(sandbox):
    run_all(sandbox)
    r = pd.read_csv(cfg.VALIDATION_FILE).set_index("SYMBOL")
    assert r.at["GROW", "READY_FOR_SCORING"]
    assert not r.at["STALE", "READY_FOR_SCORING"] and "stale" in r.at["STALE", "ISSUES"]
    assert not r.at["NEWCO", "READY_FOR_SCORING"] and "annual" in r.at["NEWCO", "ISSUES"]
    assert "no shareholding" in r.at["NEWCO", "ISSUES"]


def test_scoring_behaviour(sandbox):
    run_all(sandbox)
    s = pd.read_csv(cfg.SCORES_FILE).set_index("SYMBOL")
    assert s.at["GROW", "SCORE"] > s.at["SLOW", "SCORE"]
    assert not s.at["SLOW", "RANKED"] and "valuation" in s.at["SLOW", "RANK_NOTE"]  # no PEG -> valuation pillar empty
    assert s.at["GROW", "ELIGIBLE"] and s.at["GROW", "RANK"] == 1
    assert not s.at["STALE", "ELIGIBLE"] and s.at["STALE", "TIER"] == "NOT RANKED"
    assert s.at["BANKX", "COVERAGE"] < s.at["GROW", "COVERAGE"]   # ROCE + D/E drop out for the bank
    assert 0 <= s["SCORE"].max() <= 100


def test_report_builds(sandbox):
    run_all(sandbox)
    status, det = build_report.run(sandbox)
    assert status == "SUCCESS", det
    assert list(cfg.REPORTS.glob("IMDS_report_*.xlsx"))


def test_nse_parsers():
    from collectors.extract_shareholding import parse_pledge, parse_shareholding
    rows = parse_shareholding("X", [{"date": "30-SEP-2026", "pr_and_prgrp": "54.1", "public_val": "45.9"},
                                    {"date": "30-JUN-2026", "pr_and_prgrp": "-", "public_val": "46"}])
    assert rows[0]["PROMOTER_PCT"] == 54.1 and np.isnan(rows[1]["PROMOTER_PCT"])
    assert parse_pledge({"data": [{"percSharesPledged": "2.5"}]}) == 2.5
    assert np.isnan(parse_pledge({"data": []}))


def test_orchestrator_offline_end_to_end(sandbox):
    import IMDS_auto_update as app
    assert app.main(["--offline"]) == 0
    st = pd.read_csv(cfg.STATUS_FILE).set_index("STAGE")["STATUS"]
    assert st["technical_data_collection"] == "SKIPPED"
    assert st["multibagger_scoring"] in ("SUCCESS", "PARTIAL") and st["excel_report"] == "SUCCESS"


def test_short_history_not_ranked(sandbox):
    run_all(sandbox)
    s = pd.read_csv(cfg.SCORES_FILE).set_index("SYMBOL")
    assert not s.at["NEWLIST", "RANKED"] and s.at["NEWLIST", "TIER"] == "NOT RANKED"
    r = pd.read_csv(cfg.VALIDATION_FILE).set_index("SYMBOL")
    assert "price bars" in r.at["NEWLIST", "ISSUES"]


def test_peg_growth_cap(sandbox):
    run_all(sandbox)
    v = pd.read_csv(cfg.VALUATION_METRICS_FILE).set_index("SYMBOL")
    assert v.at["LOWBASE", "PEG_GROWTH_USED"] == cfg.PEG_GROWTH_CAP
    assert abs(v.at["LOWBASE", "PEG"] - 100 / 40) < 0.01          # uncapped would be ~0.77
    s = pd.read_csv(cfg.SCORES_FILE).set_index("SYMBOL")
    assert s.at["LOWBASE", "PTS_PEG"] == 0                         # expensive despite huge growth
    assert s.at["GROW", "PTS_PEG"] > 10                            # PE 20 / 35% growth still rewarded


def test_size_band(sandbox):
    run_all(sandbox)
    s = pd.read_csv(cfg.SCORES_FILE).set_index("SYMBOL")
    assert s.at["BIGCAP", "TIER"] == "OUT OF SIZE BAND" and pd.isna(s.at["BIGCAP", "RANK"])
    assert s.at["BIGCAP", "ELIGIBLE"] and not s.at["BIGCAP", "RANKED"]
    assert s.at["BIGCAP", "SCORE"] > 0                             # still scored, just not ranked
    assert s.at["GROW", "SIZE_BAND"] == "in band"


def test_pillar_coverage_blocks_strengths_only_ranking(sandbox):
    """A stock whose technical data is blank must not be ranked on growth/quality alone."""
    import numpy as np
    run_all(sandbox)
    t = pd.read_csv(cfg.TECHNICALS_FILE)
    for c in ("ABOVE_SMA200", "SMA50_ABOVE_SMA200", "RS_12M_VS_NIFTY", "PCT_FROM_52W_HIGH"):
        t.loc[t.SYMBOL == "GROW", c] = np.nan
    t.to_csv(cfg.TECHNICALS_FILE, index=False)
    scr.run(sandbox)
    s = pd.read_csv(cfg.SCORES_FILE).set_index("SYMBOL")
    assert s.at["GROW", "COV_TECHNICAL"] == 0 and not s.at["GROW", "ELIGIBLE"]
    assert "technical" in s.at["GROW", "RANK_NOTE"]
