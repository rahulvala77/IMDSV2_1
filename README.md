# IMDS v2.1 — Indian Multibagger Discovery System

Working pipeline built on the v2.0 scaffold. It downloads data, computes metrics, validates,
scores and writes an Excel report. **It is a rules-based screen on third-party data, not investment advice.**

## Run (Windows / PowerShell)

```powershell
cd D:\IMDS_v2.0
py -m venv .venv                      # skip if .venv already works
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m pytest -q                       # offline tests, should all pass
py IMDS_auto_update.py --limit 10     # SMOKE TEST on 10 symbols first
py IMDS_auto_update.py                # full run (~30-60 min for 752 symbols)
```
Output: `reports\IMDS_report_<date>.xlsx` plus CSVs in `data\output\`. Re-running reuses statements fetched
in the last 7 days (`--force` to refetch). `py IMDS_auto_update.py --offline` recomputes from downloaded data.

Useful: `--stages a,b`, `--skip shareholding_extraction`, `--workers 2`.

## Where each dataset comes from

| Data | Source | Reliability |
|---|---|---|
| Prices / volume | Yahoo Finance (yfinance) | good; unofficial |
| Annual + quarterly statements | Yahoo Finance (yfinance) | ~4 FYs, ~5 quarters; basis (standalone/consolidated) not disclosed |
| PE, PB, EV/EBITDA, market cap | Yahoo Finance `info` | fields can be missing/stale; blanks stay blank |
| Promoter %, pledge % | NSE website JSON endpoints | **unofficial, may block or change** — raw JSON archived in `data\raw_filings\<SYMBOL>\` |

For official-grade numbers, the upgrade path is NSE/BSE XBRL filings; the extractors' output schema
(`annual_financials.csv`, `quarterly_results.csv`) was designed so a XBRL source can replace Yahoo later.

## Method
Scoring components, weights and thresholds: `engine/calculate_scores.py` (also on the Methodology sheet).
Missing inputs are dropped from the denominator (never scored as 0); stocks with <70% coverage, stale prices,
<3 annual periods or no valuation are `NOT RANKED`. Banks/NBFCs skip ROCE and debt/equity.
