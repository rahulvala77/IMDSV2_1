"""Excel report -> reports/IMDS_report_<date>.xlsx (openpyxl). Built only from pipeline CSV outputs."""
from datetime import datetime

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import config as cfg
from engine.calculate_scores import COMPONENTS
from utils import read_csv_safe

FONT = "Arial"
HDR_FILL = PatternFill("solid", fgColor="1F3864")
PCT_COLS = {"REV_CAGR", "PAT_CAGR", "QTR_REV_YOY", "QTR_PAT_YOY", "ROE", "ROCE", "OPM", "NPM", "RET_1M", "RET_3M", "RET_6M",
            "RET_12M", "PCT_FROM_52W_HIGH", "RS_12M_VS_NIFTY", "EARNINGS_YIELD", "COVERAGE"}
SHOW = ["RANK", "SYMBOL", "NAME OF COMPANY", "INDUSTRY", "SCORE", "TIER", "COVERAGE", "SIZE_BAND", "RANK_NOTE", "MARKET_CAP_CR", "PE_TTM", "PEG",
        "REV_CAGR", "PAT_CAGR", "QTR_REV_YOY", "QTR_PAT_YOY", "ROE", "ROCE", "DEBT_EQUITY", "RET_12M", "RS_12M_VS_NIFTY",
        "PCT_FROM_52W_HIGH", "PROMOTER_PCT", "PLEDGE_PCT"]


def _write_df(ws, df, start_row=1):
    for j, col in enumerate(df.columns, 1):
        c = ws.cell(row=start_row, column=j, value=col)
        c.font = Font(name=FONT, bold=True, color="FFFFFF")
        c.fill = HDR_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, row in enumerate(df.itertuples(index=False), start_row + 1):
        for j, v in enumerate(row, 1):
            if pd.isna(v):
                v = None  # keep missing blank, never 0
            elif hasattr(v, "item"):
                v = v.item()
            c = ws.cell(row=i, column=j, value=v)
            c.font = Font(name=FONT)
            name = df.columns[j - 1]
            if name in PCT_COLS:
                c.number_format = "0.0%"
            elif isinstance(v, float):
                c.number_format = "#,##0.00"
    for j, col in enumerate(df.columns, 1):
        width = max([len(str(col))] + [len(str(x)) for x in df[col].head(200)]) + 2
        ws.column_dimensions[get_column_letter(j)].width = min(max(width, 9), 45)
    ws.freeze_panes = ws.cell(row=start_row + 1, column=3)
    ws.auto_filter.ref = f"A{start_row}:{get_column_letter(len(df.columns))}{start_row + len(df)}"


def run(ctx):
    scores = read_csv_safe(cfg.SCORES_FILE)
    if scores.empty:
        return "FAILED", "multibagger_scores.csv missing - run scoring first"
    valid, status = read_csv_safe(cfg.VALIDATION_FILE), read_csv_safe(cfg.STATUS_FILE)
    wb = Workbook()

    ws = wb.active
    ws.title = "Summary"
    n_total = len(scores)
    ws["A1"] = "IMDS v2.0 - Indian Multibagger Discovery System"
    ws["A1"].font = Font(name=FONT, bold=True, size=14)
    ws["A2"] = f"Generated {datetime.now():%Y-%m-%d %H:%M}. Rules-based screen using third-party data - not investment advice."
    ws["A2"].font = Font(name=FONT, italic=True)
    scs = wb.create_sheet("All Scores")
    _write_df(scs, scores[[c for c in SHOW if c in scores.columns]].assign(**{}), 1)
    last = n_total + 1
    cols = {n: get_column_letter(i + 1) for i, n in enumerate([c for c in SHOW if c in scores.columns])}
    items = [("Symbols in universe", f"=COUNTA('All Scores'!{cols['SYMBOL']}2:{cols['SYMBOL']}{last})"),
             ("Ranked (eligible)", f"=COUNT('All Scores'!{cols['RANK']}2:{cols['RANK']}{last})"),
             ("Tier A (score >= 70)", f"=COUNTIF('All Scores'!{cols['TIER']}2:{cols['TIER']}{last},\"A*\")"),
             ("Tier B (55-70)", f"=COUNTIF('All Scores'!{cols['TIER']}2:{cols['TIER']}{last},\"B*\")"),
             ("Out of size band",  f"=COUNTIF('All Scores'!{cols['TIER']}2:{cols['TIER']}{last},\"OUT OF*\")"),
             ("Not ranked (data gaps)", f"=COUNTIF('All Scores'!{cols['TIER']}2:{cols['TIER']}{last},\"NOT RANKED\")")]
    for i, (label, f) in enumerate(items, 4):
        ws.cell(row=i, column=1, value=label).font = Font(name=FONT, bold=True)
        ws.cell(row=i, column=2, value=f).font = Font(name=FONT)
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 14
    r = len(items) + 6
    ws.cell(row=r, column=1, value="Pipeline stages").font = Font(name=FONT, bold=True)
    if not status.empty:
        _write_df(ws, status, r + 1)
        ws.freeze_panes = None
        ws.auto_filter.ref = None
        for col, w in zip("ABCD", (28, 22, 18, 70)):
            ws.column_dimensions[col].width = w

    top = scores[scores["RANKED"]].head(50)
    ts = wb.create_sheet("Top 50", 1)
    _write_df(ts, top[[c for c in SHOW if c in top.columns]], 1)

    meth = wb.create_sheet("Methodology")
    meth.append(["Component", "Pillar", "Max points", "Rule"])
    for c in COMPONENTS:
        meth.append([c[0], c[1], c[3], c[6]])
    meth.append(["TOTAL", "", "=SUM(C2:C%d)" % (len(COMPONENTS) + 1), ""])
    meth.append([])
    for t in ("Missing inputs are excluded from earned AND available points (not scored as zero); COVERAGE = available/100.",
              f"Ranked only if: data ready (>= {cfg.MIN_PRICE_BARS} price bars), coverage >= {cfg.MIN_SCORE_COVERAGE:.0%}, each of growth/quality/valuation/technical >= {cfg.MIN_PILLAR_COVERAGE:.0%} scoreable, market cap Rs{cfg.MCAP_BAND_CR[0]:,}-{cfg.MCAP_BAND_CR[1]:,} cr.",
              f"PEG uses profit growth capped at {cfg.PEG_GROWTH_CAP:.0%} so low-base growth does not make expensive stocks look cheap.",
              "Financial-sector stocks skip ROCE and debt/equity (not comparable).",
              "Data: Yahoo Finance (prices, statements, ratios) and NSE website (shareholding) - unofficial; verify before acting."):
        meth.append([t])
    for c in meth[1]:
        c.font = Font(name=FONT, bold=True, color="FFFFFF")
        c.fill = HDR_FILL
    for row in meth.iter_rows(min_row=2):
        for c in row:
            c.font = Font(name=FONT)
    meth.column_dimensions["A"].width = 16
    meth.column_dimensions["D"].width = 80

    if not valid.empty:
        _write_df(wb.create_sheet("Data Quality"), valid, 1)
    out = cfg.REPORTS / f"IMDS_report_{datetime.now():%Y%m%d}.xlsx"
    wb.save(out)
    return "SUCCESS", str(out.name)
