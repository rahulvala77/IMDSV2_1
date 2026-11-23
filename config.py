from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
INPUT = DATA / "input"
RAW_FILINGS = DATA / "raw_filings"
PRICE_HISTORY = DATA / "price_history"
OUTPUT = DATA / "output"
REPORTS = ROOT / "reports"
LOGS = ROOT / "logs"

# ---- input / collected datasets (data/input) ----
UNIVERSE_FILE = INPUT / "stock_universe.csv"
TECHNICALS_FILE = INPUT / "technicals.csv"
ANNUAL_FINANCIAL_FILE = INPUT / "annual_financials.csv"   # (v2.0 scaffold had a typo: annual_finantial.csv)
QUARTERLY_RESULTS_FILE = INPUT / "quarterly_results.csv"
SHAREHOLDING_FILE = INPUT / "shareholding.csv"
VALUATION_FILE = INPUT / "valuation.csv"                  # raw market data collected from the provider

# ---- computed outputs (data/output) ----
FUNDAMENTALS_FILE = OUTPUT / "fundamentals.csv"
VALUATION_METRICS_FILE = OUTPUT / "valuation_metrics.csv"
VALIDATION_FILE = OUTPUT / "validation_report.csv"
SCORES_FILE = OUTPUT / "multibagger_scores.csv"
STATUS_FILE = OUTPUT / "pipeline_status.csv"

# ---- collection settings ----
PRICE_PERIOD = "2y"            # enough for a 200-DMA and 12-month returns
BENCHMARK_TICKER = "^NSEI"     # Nifty 50, used for relative strength
BENCHMARK_FILE_NAME = "_NIFTY50"
PRICE_BATCH_SIZE = 50
RAW_MAX_AGE_DAYS = 7           # re-use cached statements newer than this unless --force
DEFAULT_WORKERS = 3            # keep low: Yahoo rate-limits aggressive scraping
REQUEST_SLEEP = (0.3, 0.9)     # random sleep range (seconds) between requests
CRORE = 1e7

# ---- validation / scoring thresholds ----
MAX_PRICE_AGE_DAYS = 6
MIN_ANNUAL_YEARS = 3           # annual rows needed for a 2-interval CAGR
MIN_SCORE_COVERAGE = 0.70      # share of the 100 points that must be scoreable to be ranked
MIN_PRICE_BARS = 200           # need a full 200-day average (and ~12m return) to be ranked
REQUIRED_PILLARS = ("Growth", "Quality", "Valuation", "Technical")
MIN_PILLAR_COVERAGE = 0.50     # each required pillar needs >= this share of its points scoreable
PEG_GROWTH_CAP = 0.40          # profit growth above this is capped when computing PEG (low-base distortion)
MCAP_BAND_CR = (500, 50000)    # market-cap band (INR crore) in which a 'multibagger' screen is meaningful
MCAP_BAND_ENFORCED = True      # True: out-of-band stocks are scored but not ranked
FINANCIAL_INDUSTRIES = {"Financial Services"}   # leverage / ROCE not comparable for banks & NBFCs

for _folder in (INPUT, RAW_FILINGS, PRICE_HISTORY, OUTPUT, REPORTS, LOGS):
    _folder.mkdir(parents=True, exist_ok=True)
