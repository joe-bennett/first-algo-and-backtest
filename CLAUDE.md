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
  - alerts/: engine.py, notifier.py (Twilio SMS)
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
