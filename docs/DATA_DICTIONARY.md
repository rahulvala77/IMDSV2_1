# Data dictionary — initial schema plan

Retain the user's existing CSV headers where possible. For each imported financial
fact, preserve reporting period, reporting basis, units, source URL, filing date,
collection timestamp and verification status.

Core input files:
- `stock_universe.csv`: SYMBOL, NAME OF COMPANY, YAHOO_TICKER, SECTOR, INDUSTRY, UNIVERSE, ...
- `annual_finantial.csv`: SYMBOL, FINANCIAL_YEAR, STATEMENT_TYPE, SALES, OPERATING_PROFIT, NET_PROFIT, EQUITY, DEBT, CASH_FROM_OPERATIONS, CAPITAL_EMPLOYED, RECEIVABLES, INVENTORY
- `quarterly_results.csv`: SYMBOL, QUARTER_END, SALES, OPERATING_PROFIT, NET_PROFIT, EPS, RESULT_TYPE, SOURCE_DATE
- `shareholding.csv`: SYMBOL, QUARTER_END, PROMOTER_HOLDING_PCT, PROMOTER_PLEDGE_PCT, FII_HOLDING_PCT, DII_HOLDING_PCT, PUBLIC_HOLDING_PCT, SOURCE
- `valuation.csv`: SYMBOL, AS_OF_DATE, SHARE_PRICE, MARKET_CAP_CR, PE_TTM, PB_RATIO, PS_RATIO, EV_EBITDA, PEG_RATIO, INDUSTRY_PE, DIVIDEND_YIELD_PCT, SOURCE
- `technicals.csv`: to be finalized alongside the technical collector.

Do not assume OPERATING_PROFIT means EBITDA. For ROCE, consistently use EBIT or
derive it from reported components with a traceable formula. A true 3-year CAGR
requires four annual observations (base year plus three subsequent years).
