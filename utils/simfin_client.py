"""
Point-in-time fundamental data via SimFin.

Used exclusively by backtesting/runner.py to avoid look-ahead bias in value factors.
Live signal scanning continues to use current yfinance data via openbb_client.py.

Setup:
  1. Get a free API key at simfin.com (click "Free Plan" → "Get API Key")
  2. Add SIMFIN_API_KEY=your_key to your .env file
  3. First run downloads ~100MB of data to data/simfin/ — takes a few minutes once

How it works:
  SimFin quarterly filings have two dates:
    - Report Date: the fiscal period end (e.g. March 31)
    - Publish Date: when the filing was actually made public (e.g. May 10)
  We use Publish Date as the "available" date so no data is used before it
  was actually public — this is true point-in-time, no look-ahead bias.

Coverage: 2,000+ US stocks with quarterly financials back to ~2009.
Refresh: panel is rebuilt from SimFin servers every 7 days.

Columns in the panel:
  Value factors  : pe_ratio, pb_ratio, fcf_yield, ev_ebitda
  Quality factors: roe (Return on Equity), net_margin, debt_equity
"""

import os
import time
import pickle
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
logger = logging.getLogger(__name__)

SIMFIN_DIR = Path(__file__).parent.parent / "data" / "simfin"
SIMFIN_DIR.mkdir(parents=True, exist_ok=True)
PANEL_CACHE = SIMFIN_DIR / "pit_fundamentals_v3.pkl"   # v3 fixes FCF, EBITDA, Total Debt column names
PANEL_TTL_DAYS = 7


def _api_key() -> str:
    key = os.getenv("SIMFIN_API_KEY")
    if not key:
        raise EnvironmentError(
            "SIMFIN_API_KEY not found in .env. "
            "Get a free key at simfin.com and add SIMFIN_API_KEY=your_key to your .env file."
        )
    return key


def _cache_valid() -> bool:
    if not PANEL_CACHE.exists():
        return False
    age_days = (time.time() - PANEL_CACHE.stat().st_mtime) / 86400
    return age_days < PANEL_TTL_DAYS


def build_fundamentals_panel() -> pd.DataFrame:
    """
    Download SimFin quarterly financials + daily prices for all US stocks.
    Compute value and quality factors at each quarterly publish date.

    Returns DataFrame with MultiIndex (date, ticker) where date = Publish Date.
    Columns:
      Value:   pe_ratio, pb_ratio, fcf_yield, ev_ebitda
      Quality: roe, net_margin, debt_equity

    Cached to data/simfin/pit_fundamentals_v2.pkl for PANEL_TTL_DAYS days.
    Call build_fundamentals_panel() once per backtest session — it's fast from cache.
    """
    if _cache_valid():
        logger.info("Loading SimFin panel from cache.")
        with open(PANEL_CACHE, "rb") as f:
            return pickle.load(f)

    import simfin as sf

    print("Downloading SimFin data (first run only — ~100MB, a few minutes)...")
    sf.set_api_key(_api_key())
    sf.set_data_dir(str(SIMFIN_DIR))

    print("  Loading income statements...")
    income = sf.load_income(variant="quarterly", market="us").reset_index()
    print("  Loading balance sheets...")
    balance = sf.load_balance(variant="quarterly", market="us").reset_index()
    print("  Loading cash flow statements...")
    cashflow = sf.load_cashflow(variant="quarterly", market="us").reset_index()
    print("  Loading daily share prices...")
    prices = sf.load_shareprices(variant="daily", market="us").reset_index()

    # SimFin column name constants (verified against actual downloaded datasets)
    TICKER      = "Ticker"
    REPORT_DATE = "Report Date"
    PUB_DATE    = "Publish Date"
    SHARES      = "Shares (Diluted)"
    NET_INCOME  = "Net Income"
    REVENUE     = "Revenue"
    OP_INCOME   = "Operating Income (Loss)"    # used to compute EBITDA
    DA_INCOME   = "Depreciation & Amortization"  # D&A on income statement
    TOTAL_EQ    = "Total Equity"
    SHORT_DEBT  = "Short Term Debt"
    LONG_DEBT   = "Long Term Debt"
    # Correct exact name from SimFin balance sheet:
    CASH        = "Cash, Cash Equivalents & Short Term Investments"
    OCF         = "Net Cash from Operating Activities"   # operating cash flow
    CAPEX       = "Change in Fixed Assets & Intangibles" # negative = capex outflow
    ADJ_CLOSE   = "Adj. Close"
    PRICE_DATE  = "Date"

    # --- TTM metrics (rolling sum of last 4 quarters per ticker) ---
    for df in [income, cashflow]:
        df.sort_values([TICKER, REPORT_DATE], inplace=True)

    def ttm(df, col):
        if col not in df.columns:
            return pd.Series(np.nan, index=df.index)
        return df.groupby(TICKER)[col].transform(lambda x: x.rolling(4, min_periods=4).sum())

    income["ttm_net_income"] = ttm(income, NET_INCOME)
    income["ttm_revenue"]    = ttm(income, REVENUE)

    # EBITDA = Operating Income + D&A  (SimFin has no pre-built EBITDA column)
    if OP_INCOME in income.columns and DA_INCOME in income.columns:
        income["ebitda_qtr"] = income[OP_INCOME].fillna(0) + income[DA_INCOME].fillna(0)
        income["ttm_ebitda"] = income.groupby(TICKER)["ebitda_qtr"].transform(
            lambda x: x.rolling(4, min_periods=4).sum()
        )
    else:
        income["ttm_ebitda"] = np.nan

    # FCF = Operating Cash Flow + CapEx (CapEx is negative in SimFin, so adding works)
    # SimFin has no pre-built "Free Cash Flow" column
    if OCF in cashflow.columns:
        capex_series = cashflow[CAPEX].fillna(0) if CAPEX in cashflow.columns else 0
        cashflow["fcf_qtr"] = cashflow[OCF].fillna(0) + capex_series
        cashflow["ttm_fcf"] = cashflow.groupby(TICKER)["fcf_qtr"].transform(
            lambda x: x.rolling(4, min_periods=4).sum()
        )
    else:
        cashflow["ttm_fcf"] = np.nan

    # Total Debt = Short Term Debt + Long Term Debt (SimFin has no single "Total Debt" column)
    for col in [SHORT_DEBT, LONG_DEBT]:
        if col not in balance.columns:
            balance[col] = np.nan
    balance["total_debt"] = balance[SHORT_DEBT].fillna(0) + balance[LONG_DEBT].fillna(0)

    # --- Merge income + balance + cashflow on Ticker + Report Date ---
    inc_keep = [c for c in [TICKER, REPORT_DATE, PUB_DATE, SHARES,
                             "ttm_net_income", "ttm_revenue", "ttm_ebitda"] if c in income.columns]
    bal_keep = [c for c in [TICKER, REPORT_DATE, TOTAL_EQ, "total_debt", CASH] if c in balance.columns]
    cf_keep  = [c for c in [TICKER, REPORT_DATE, "ttm_fcf"] if c in cashflow.columns]

    merged = (
        income[inc_keep]
        .merge(balance[bal_keep], on=[TICKER, REPORT_DATE], how="left")
        .merge(cashflow[cf_keep], on=[TICKER, REPORT_DATE], how="left")
    )

    # Use Publish Date as the point-in-time availability date
    merged[PUB_DATE] = pd.to_datetime(merged[PUB_DATE])
    merged = merged.dropna(subset=[PUB_DATE])
    merged = merged.rename(columns={TICKER: "ticker", PUB_DATE: "date"})
    merged = merged.sort_values("date").reset_index(drop=True)

    # --- Align stock price to each publish date (vectorized via merge_asof) ---
    px = prices[[TICKER, PRICE_DATE, ADJ_CLOSE]].copy()
    px.columns = ["ticker", "price_date", "price"]
    px["price_date"] = pd.to_datetime(px["price_date"])
    px = px.sort_values("price_date").reset_index(drop=True)

    price_at_publish = pd.merge_asof(
        merged[["ticker", "date"]],
        px,
        left_on="date",
        right_on="price_date",
        by="ticker",
        direction="backward",
    )
    merged["price"] = price_at_publish["price"].values

    # --- Compute ratios ---
    shares = merged[SHARES].astype(float).replace(0, np.nan) if SHARES in merged.columns else pd.Series(np.nan, index=merged.index)
    price  = merged["price"].astype(float).replace(0, np.nan)

    # P/E (TTM): only valid when earnings are positive
    eps_ttm = merged["ttm_net_income"].astype(float) / shares
    pe = (price / eps_ttm).where(eps_ttm > 0)

    # P/B: only valid when equity is positive
    bv_per_share = merged[TOTAL_EQ].astype(float) / shares if TOTAL_EQ in merged.columns else pd.Series(np.nan, index=merged.index)
    pb = (price / bv_per_share).where(bv_per_share > 0)

    # FCF Yield: can be negative (not filtered — let strategy handle)
    fcf_per_share = merged["ttm_fcf"].astype(float) / shares
    fcf_yield = fcf_per_share / price

    # EV/EBITDA: Enterprise Value / TTM EBITDA
    ev_ebitda = pd.Series(np.nan, index=merged.index)
    if "total_debt" in merged.columns and CASH in merged.columns:
        mktcap = price * shares
        ev = mktcap + merged["total_debt"].astype(float).fillna(0) - merged[CASH].astype(float).fillna(0)
        ebitda = merged["ttm_ebitda"].astype(float)
        ev_ebitda = (ev / ebitda).where(ebitda > 0)

    # --- Quality factors ---
    # ROE: TTM net income / total equity (higher = better quality)
    roe = pd.Series(np.nan, index=merged.index)
    if TOTAL_EQ in merged.columns:
        eq = merged[TOTAL_EQ].astype(float).replace(0, np.nan)
        roe = (merged["ttm_net_income"].astype(float) / eq)
        roe = roe.where(np.isfinite(roe))

    # Net margin: TTM net income / TTM revenue (higher = better quality)
    net_margin = pd.Series(np.nan, index=merged.index)
    if "ttm_revenue" in merged.columns:
        rev = merged["ttm_revenue"].astype(float).replace(0, np.nan)
        net_margin = (merged["ttm_net_income"].astype(float) / rev)
        net_margin = net_margin.where(np.isfinite(net_margin))

    # Debt/Equity: total debt / total equity (lower = better quality)
    debt_equity = pd.Series(np.nan, index=merged.index)
    if "total_debt" in merged.columns and TOTAL_EQ in merged.columns:
        eq = merged[TOTAL_EQ].astype(float).replace(0, np.nan)
        debt_equity = (merged["total_debt"].astype(float).fillna(0) / eq)
        debt_equity = debt_equity.where(np.isfinite(debt_equity) & (debt_equity >= 0))

    panel = pd.DataFrame({
        "date":        merged["date"],
        "ticker":      merged["ticker"],
        # Value
        "pe_ratio":    pe.where(np.isfinite(pe)),
        "pb_ratio":    pb.where(np.isfinite(pb)),
        "fcf_yield":   fcf_yield.where(np.isfinite(fcf_yield)),
        "ev_ebitda":   ev_ebitda.where(np.isfinite(ev_ebitda)),
        # Quality
        "roe":         roe,
        "net_margin":  net_margin,
        "debt_equity": debt_equity,
    }).dropna(subset=["date", "ticker"])

    panel = panel.set_index(["date", "ticker"]).sort_index()

    n_tickers = panel.index.get_level_values("ticker").nunique()
    print(f"SimFin panel built: {len(panel):,} quarterly data points across {n_tickers:,} tickers.")
    print(f"Columns: {list(panel.columns)}")

    with open(PANEL_CACHE, "wb") as f:
        pickle.dump(panel, f)
    print(f"Panel cached to {PANEL_CACHE}")

    return panel


def get_pit_fundamentals(
    panel: pd.DataFrame,
    as_of_date: pd.Timestamp,
    tickers: list[str],
) -> pd.DataFrame:
    """
    Return point-in-time fundamentals for `tickers` as of `as_of_date`.

    For each ticker, finds the most recently published quarterly filing
    available on or before as_of_date. Tickers not covered by SimFin
    return NaN — the strategy handles this gracefully.

    Parameters
    ----------
    panel       : full panel from build_fundamentals_panel()
    as_of_date  : the backtest rebalance date to look up
    tickers     : list of tickers to return data for

    Returns
    -------
    DataFrame indexed by ticker with columns:
      pe_ratio, pb_ratio, fcf_yield, ev_ebitda, roe, net_margin, debt_equity
    """
    cols = ["pe_ratio", "pb_ratio", "fcf_yield", "ev_ebitda", "roe", "net_margin", "debt_equity"]

    min_date = panel.index.get_level_values("date").min()
    if as_of_date < min_date:
        return pd.DataFrame(np.nan, index=tickers, columns=cols)

    # All filings published on or before as_of_date
    available = panel.loc[:as_of_date]
    if available.empty:
        return pd.DataFrame(np.nan, index=tickers, columns=cols)

    # Most recent filing per ticker
    latest = available.groupby(level="ticker")[cols].last()

    return latest.reindex(tickers)
