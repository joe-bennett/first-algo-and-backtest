# Project: First Algo and Backtest

## Purpose
Automated trading portfolio with email alerts, backtesting, and a Streamlit dashboard.
Start with manual execution on alerts, evolve toward live automated trading.

## Strategies
- **120/20 Value-Momentum**: Long top-ranked S&P 500 stocks (value + momentum composite), short bottom-ranked. Rebalances monthly/quarterly.
- **Iron Condor (opportunistic)**: Triggered when IV Rank >= 50 on liquid underlyings, 30-45 DTE.

## Key files
- `config/portfolio.yaml` — all tunable strategy parameters (tweak here first)
- `backtesting/runner.py` — run `run_backtest()` to test any config change
- `dashboard/app.py` — Streamlit dashboard (`streamlit run dashboard/app.py`)
- `alerts/engine.py` — signal scanner; run with `dry_run=True` to preview alerts
- `alerts/notifier.py` — email sender via Gmail/smtplib
- `broker/alpaca.py` — Alpaca paper trading integration (orders, rebalance, stop-loss)
- `broker/position_manager.py` — daily stop-loss replacement logic
- `broker/ledger.py` — local portfolio ledger; saves `data/ledger.csv` + `data/ledger.json`
- `run_alerts.py` — scheduled runner (called by Windows Task Scheduler)
- `quickstart.py` — sanity check after install

## Phase roadmap
1. **Phase 1 (complete)**: Data pipeline + alerts + backtesting. Manual trade execution.
2. **Phase 2 (current)**: Alpaca paper trading. Automated rebalance + stop-loss replacement.
3. **Phase 3**: Live trading with real money + risk controls.

## Data
- Provider: `yfinance` via OpenBB (free, no API key needed)
- Universe: S&P 500 (fetched from Wikipedia with browser User-Agent header)
- Limitations: fundamentals are current snapshot only (not point-in-time historical)

## Alerts
- Delivery: Email via Gmail (smtplib — no extra package needed)
- Credentials: `.env` file (copy from `.env.example`)
- Sending from: joe.d.bennett01@gmail.com
- Each alert includes WHY the trade is flagged (value/momentum driver explanation)

## Broker (Phase 2)
- Platform: Alpaca Paper Trading (free, $100k simulated starting balance)
- Credentials: `.env` file (ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_BASE_URL)
- Stop loss: 15% below entry, attached as Alpaca server-side stop order (GTC)
- Rebalance: monthly on the 1st, triggered by Windows Task Scheduler at 4:30 PM
- Stop replacement: daily check at 4:30 PM — stopped positions auto-replaced with next-best ranked stock
- Signals persisted to `data/last_signals.json` after each rebalance for daily comparison

## Scheduling
- Windows Task Scheduler task: `TradingAlerts`
- Runs: Monday–Friday at 4:30 PM
- Settings: WakeToRun (wakes PC from sleep), StartWhenAvailable (catches up if missed), RunOnlyIfNetworkAvailable

---

## Activity Log

### 2026-03-24
- Initialized project folder
- Created CLAUDE.md to track work and context
- Built full initial project structure:
  - Folder layout, requirements.txt, .env.example
  - config/: portfolio.yaml, alerts.yaml, universe.yaml
  - utils/: openbb_client.py (data fetching), metrics.py (performance metrics)
  - strategies/: base.py, value_momentum_120_20.py, iron_condor.py
  - backtesting/: runner.py (VectorBT-based)
  - alerts/: engine.py, notifier.py (Gmail email via smtplib)
  - dashboard/: app.py (Streamlit, 4 pages), charts.py (Plotly)
  - quickstart.py (sanity check script)
  - GUIDE.md (plain English user guide)
- Expanded universe from S&P 500 to all US-listed equities
  - config/universe.yaml now has 5 presets: all_us | sp500 | sp1500 | nasdaq100 | custom
  - Filters: min price, market cap, avg volume, dollar volume — all adjustable in yaml
  - openbb_client.py: get_universe_tickers() reads preset + applies filters; parallel fetch + disk cache
  - Source for all_us: NASDAQ public FTP (free, covers NASDAQ + NYSE + AMEX)

### 2026-03-25
- Switched alerts from Twilio SMS to Gmail email (smtplib, no extra package)
  - notifier.py rewritten to use GMAIL_ADDRESS, GMAIL_APP_PASSWORD, ALERT_TO_EMAIL
  - .env.example updated, Twilio vars removed
  - engine.py print statements updated to say "email" not "SMS"
- Added WHY explanation to each signal in describe_signal() for both strategies
  - 120/20: identifies value-driven, momentum-driven, or both
  - Iron condor: explains IV Rank logic (already had this)
- Fixed Wikipedia 403 error in openbb_client.py (added browser User-Agent header)
- Fixed Unicode arrow character crashing on Windows terminal
- Configured Windows Task Scheduler task (TradingAlerts) — weekdays 4:30 PM
  - WakeToRun, StartWhenAvailable, RunOnlyIfNetworkAvailable
- Built Phase 2 Alpaca paper trading integration
  - broker/alpaca.py: account info, positions, market orders, rebalance logic
  - Connected to Alpaca paper account ($100k starting balance)
  - Monthly rebalance on 1st of month — auto-places orders after signal scan
  - Sends confirmation email with all orders placed
- Implemented 15% stop-loss on all long positions
  - Attached as Alpaca server-side OTO stop order (GTC) at order placement
  - Configurable via risk.stop_loss_pct in config/portfolio.yaml
- Built daily stop-loss replacement logic (broker/position_manager.py)
  - Detects stopped-out positions by comparing expected vs actual holdings
  - Re-ranks S&P 500, buys next-best candidate not already held
  - Attaches new 15% stop to replacement position
  - Sends email notification with replacement details
  - Signals persisted to data/last_signals.json after each rebalance
- Added .gitignore (excludes .env, __pycache__, data/, logs/)
- requirements.txt: removed twilio, added alpaca-py
- Pushed project to GitHub: https://github.com/joe-bennett/first-algo-and-backtest
- Added README.md with quick start, analysis guide, and portfolio configuration instructions
- Updated GUIDE.md: replaced all SMS/Twilio references with Gmail email throughout

### 2026-03-25 (continued, session 3)
- Connected Portfolio Overview dashboard page to live Alpaca data
  - dashboard/app.py: replaced placeholder with live account metrics, position tables, weight/P&L charts
  - dashboard/charts.py: added holdings_weight_bar() and holdings_pl_bar() chart functions
  - Refresh button pulls latest positions from Alpaca on demand; auto-fetches on first load
  - Graceful fallback to config display if Alpaca is unreachable
- Fixed multiple backtesting bugs in runner.py:
  - prices.index not cast to DatetimeIndex → resample("MS") crashed with TypeError
  - size_matrix initialized to 0.0 instead of NaN → VectorBT sold all positions every non-rebalance day, causing -115 Sharpe
  - portfolio.returns() returns per-asset DataFrame for multi-asset portfolio → switched to portfolio.value().pct_change()
  - portfolio.plot() fails on multi-asset portfolio → replaced with manual Plotly equity curve
  - VectorBT running N independent $100k portfolios instead of one shared portfolio → added group_by=True, cash_sharing=True
  - SPY not in strategy universe → benchmark fell back to random ticker; fixed to always fetch SPY separately
  - Momentum calculation inverted (prices.iloc[-252]/prices.iloc[-21] instead of iloc[-21]/iloc[-252]) → was buying losers, shorting winners
- Fixed survivorship bias in backtesting
  - Previously used today's S&P 500 list for all historical dates — only included companies that survived to 2024
  - Added get_sp500_members_at(date) to openbb_client.py using fja05680/sp500 GitHub dataset
  - Dataset: daily S&P 500 snapshots from 1996 to present, downloaded once to data/sp500_historical_members.csv
  - runner.py now builds union of all members over the backtest window, fetches prices for all of them
  - At each rebalance date, only stocks actually in the S&P 500 on that date are eligible for ranking
  - Added `start-dashboard` PowerShell shortcut for launching dashboard from any terminal

### 2026-03-25 (continued, session 2)
- Fixed look-ahead bias in backtesting: replaced current-snapshot fundamentals with point-in-time data
  - Built utils/simfin_client.py: downloads SimFin quarterly financials, computes TTM P/E, P/B, FCF Yield, EV/EBITDA using each filing's Publish Date as the availability cutoff
  - Panel covers 3,600 US tickers, 49,000+ quarterly data points, 2007–present
  - Cached to data/simfin/pit_fundamentals.pkl; auto-refreshes every 7 days
  - backtesting/runner.py updated: calls build_fundamentals_panel() once per session, then get_pit_fundamentals(panel, rdate, tickers) on each rebalance date
  - Removed stale get_fundamentals import from runner.py
  - Added simfin>=0.9.0 to requirements.txt; SIMFIN_API_KEY to .env.example
- Fixed iron condor / 120/20 strategy conflict
  - Condor scanner now excludes tickers currently held in the 120/20 equity book
  - alerts/engine.py: added _get_held_tickers() — reads live Alpaca positions, falls back to data/last_signals.json
  - Prevents selling volatility on stocks held as directional longs or shorts
- Updated README.md and GUIDE.md with SimFin setup, PIT fundamentals explanation, condor exclusion logic, and revised file maps

### 2026-03-25 (continued)
- Added iron condor contract sizing based on portfolio value
  - portfolio.yaml: per_condor_pct (5%), max_total_pct (15%), default_portfolio_value
  - iron_condor.py: calculates contracts, margin reserved, max profit/loss per alert
  - engine.py: fetches live portfolio value from Alpaca, passes to condor scanner
  - Alert email now tells you exactly how many contracts to trade and dollar amounts
- Cleaned up alerts/notifier.py: removed leftover send_sms alias, all callers use send_alert
- Fixed Windows UTF-8 encoding error: added encoding="utf-8" to all yaml file opens
- Added local portfolio ledger (broker/ledger.py)
  - Saves data/ledger.csv (open in Excel) and data/ledger.json after every event
  - Columns: ticker, side, qty, entry price, current price, value, P&L, weight, stop-loss
  - Auto-updates: daily price refresh, post-rebalance, post-stop-loss replacement
- Fixed all stale SMS/Twilio references in code comments and docstrings

### 2026-03-25 (continued, session 3)
- Implemented four strategy improvements for better backtest accuracy and realism:
  1. **Quality factor** — added ROE, net margin, debt/equity to SimFin panel
     - simfin_client.py: added ttm_revenue, roe, net_margin, debt_equity columns
     - Cache version bumped to pit_fundamentals_v2.pkl (forces one-time rebuild)
     - portfolio.yaml: added quality_factors section (ROE 40%, net margin 40%, D/E 20%)
     - Score blend updated to 34% value / 33% momentum / 33% quality
  2. **Sector neutralization** — ranks stocks within GICS sector rather than globally
     - openbb_client.py: added get_sector_map() from Wikipedia, cached 24 hours
     - Prevents portfolio from concentrating in a single cheap sector
     - Controlled by sector_neutral: true in portfolio.yaml (default on)
  3. **Short book toggle** — enable_short_book: true in portfolio.yaml
     - When false, runs 100% long with no shorting
     - Portfolio exposure changes from 120/20 to 100/0 when disabled
  4. **Momentum robustness** — replaced single-day price lookups with 5-day averages
     - Uses average of days -23 to -18 (recent) and -254 to -249 (year-ago)
     - Prevents a single volatile day from distorting the 12-month signal
- Updated all callers (runner.py, engine.py, dashboard/app.py, sandbox) to pass sectors dict
- Dashboard Backtest page now has separate value/momentum/quality weight sliders plus short book
  and sector neutralization toggles
- Dashboard Research Sandbox shows quality_score, roe, net_margin, sector columns in results

### 2026-03-25 (continued, session 4)
- Expanded universe to S&P 1500 (was S&P 500)
  - universe.yaml: preset changed from "all_us" to "sp1500"
  - openbb_client.py: added get_sp1500_members_at(date), _get_midsmall_tickers(), get_index_members_at(date, universe)
  - S&P 500 component: accurate point-in-time via fja05680 dataset
  - S&P 400/600 component: current Wikipedia list (no free historical dataset — modest survivorship bias)
  - runner.py reads universe.yaml at runtime, passes preset to get_index_members_at()
- Switched rebalance frequency from monthly to quarterly
  - portfolio.yaml: rebalance_frequency changed to "quarterly"
  - Reduces transaction costs ~75% — largest single drag on backtest performance
  - Dashboard Backtest page defaults still allow override via dropdown

### 2026-03-26
- Reverted universe from S&P 1500 back to S&P 500
  - universe.yaml: preset changed from "sp1500" back to "sp500"
  - Rationale: S&P 400/600 uses current-membership Wikipedia list (no free historical dataset),
    introducing survivorship bias on mid/small caps; S&P 500 uses fully accurate fja05680 point-in-time data
  - Practical benefit: large-cap shorts are more shortable (better borrow availability, lower fees);
    S&P 1500 backtest returns overstated because borrow costs on small caps are not modeled
  - Short book still has ~100 candidates (bottom 20% of ~500 stocks) — sufficient for the strategy
  - sp1500 preset remains available in code if needed in future
  - Updated: quickstart.py comment, GUIDE.md universe section and survivorship bias section
- Fixed quality factors missing from live signal scanner
  - Root cause: get_fundamentals() used obb.equity.fundamental.metrics() which doesn't expose
    ROE, net_margin, or debt_equity — quality score was 0.00 for all stocks
  - Fix: switched to yf.Ticker(ticker).info directly, pulling all 8 fields in one call:
    pe_ratio (trailingPE), pb_ratio (priceToBook), fcf_yield (freeCashflow/marketCap),
    ev_ebitda (enterpriseToEbitda), roe (returnOnEquity), net_margin (profitMargins),
    debt_equity (debtToEquity/100)
  - Cache key bumped to fundamentals_v2_ to force one-time rebuild
- Fixed Alpaca order placement for fractional shares and shorts
  - Root cause 1: OTO stop-loss with GTC fails for fractional buys ("fractional orders must be DAY")
  - Root cause 2: Fractional short sells not supported ("fractional orders cannot be sold short")
  - Fix: long buys use DAY (fractional OK); stop-loss placed as separate GTC StopOrderRequest
    using math.floor(qty) whole shares so stop never exceeds actual position size
  - Fix: short sells round to max(1, round(qty)) whole shares, DAY
  - Added StopOrderRequest to alpaca.py imports
- Placed initial paper portfolio in Alpaca
  - 100 long positions (fractional, 1.2% each = 120% long exposure)
  - 100 GTC stop-loss orders on all longs (15% below entry, whole shares)
  - 100 short positions (whole shares, 0.2% each = 20% short exposure)
  - Portfolio value at open: $99,911.78 (-0.09% from $100k cash)
