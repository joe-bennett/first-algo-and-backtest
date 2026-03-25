# User Guide — Algo Trading Portfolio

This guide explains everything in plain English: what each piece does, how to get started,
and how to make common changes without needing to touch code.

---

## Table of Contents

0. [Where Securities Are Held — Brokerages Explained](#0-where-securities-are-held)
1. [First-Time Setup](#1-first-time-setup)
2. [Daily Use — How to Run Things](#2-daily-use)
3. [The Dashboard](#3-the-dashboard)
4. [Changing Strategy Parameters](#4-changing-strategy-parameters)
5. [Changing Your Universe](#5-changing-your-universe)
6. [Changing Your Alert Settings](#6-changing-your-alert-settings)
7. [Running a Backtest](#7-running-a-backtest)
8. [Understanding the Email Alerts](#8-understanding-the-email-alerts)
9. [File Map — What Every File Does](#9-file-map)
10. [Phases — Where We Are and What's Next](#10-phases)
11. [Common Questions](#11-common-questions)

---

## 0. Where Securities Are Held

### The short answer
**This software holds nothing.** It is purely an analysis and alert engine.
Securities (stocks, options) live at a brokerage. The software tells you what to
trade and why — you (or eventually the automation) execute it at the broker.

You need two separate things running in parallel:
- **This system** — generates signals, runs backtests, sends email alerts
- **A brokerage account** — actually holds your positions and executes trades

---

### What kind of brokerage account you need

For this strategy you need two specific account features:

| Feature | Why you need it | Without it |
|---|---|---|
| **Margin account** | Required to short stocks (the 20% short side of 120/20) | You can only trade the long book |
| **Options approval Level 2** | Required for spreads like iron condors | You cannot trade condors |

Most brokers approve Level 2 options without difficulty — you just need to answer
questions about your experience and income when applying. Margin requires a minimum
account balance (usually $2,000, but $25,000+ is practical — see below).

---

### Which broker to use

| Broker | Best for | Notes |
|---|---|---|
| **Alpaca** | Paper trading now, automation later | Free account, commission-free trades, built-in paper trading with $100k simulated money. Best path to Phase 3 automation. Sign up at alpaca.markets |
| **Interactive Brokers (IBKR)** | Live trading, especially options | Best long-term for condors — best short-locate inventory, lowest margin rates, institutional quality. More complex interface. |
| **Tastytrade** | Options-focused live trading | Excellent for condors specifically. Low per-contract fees. Not ideal for automation later. |

**Recommended path:**
1. Open **Alpaca** now (free) for paper trading and to prepare for automation
2. Open **IBKR or Tastytrade** when you go live with real money

You can run both simultaneously — paper trade on Alpaca to validate the system,
while manually executing the same trades on your live broker to get comfortable.

---

### The Pattern Day Trader rule

If your account is under **$25,000**, US brokers restrict you to 3 "day trades"
(buy and sell the same stock same day) within a 5-day rolling window.

With monthly rebalancing this is not a significant issue — you're not day trading.
But it's worth knowing. If you plan to start with less than $25,000, use monthly
rebalancing (already the default) and avoid same-day round trips.

---

### How much capital do you need?

There is no hard minimum, but here is the practical reality:

| Capital | What's feasible |
|---|---|
| **$5,000 – $10,000** | Longs only, top 10–15 positions. Skip the short book for now. |
| **$25,000 – $50,000** | Full long book, partial short book. Above PDT threshold. |
| **$50,000+** | Full 120/20 strategy as designed — long and short book with reasonable position sizing. |
| **$100,000+** | Full strategy including condors with meaningful position sizes. |

The strategy works at any size — smaller just means fewer positions and
higher concentration risk per stock.

---

### How to actually start building the portfolio — step by step

**Step 1 — Get the system working**
```
pip install -r requirements.txt
python quickstart.py
```
If quickstart completes without errors, the data pipeline works.

**Step 2 — Run a backtest before risking a dollar**
```
streamlit run dashboard/app.py
```
Go to the Backtest page. Run 2018–2024 with default settings. Look at:
- Annualized return vs. S&P 500 — is the strategy adding value?
- Max drawdown — could you stomach a loss that large?
- Sharpe ratio — is the return worth the volatility?

Only move forward if you're comfortable with what you see.

**Step 3 — Open an Alpaca paper trading account**
1. Go to alpaca.markets and create a free account
2. You start with $100,000 in simulated money
3. Come back and ask Claude to connect it to this system (Phase 2)

**Step 4 — Preview today's signals (no email yet)**
In the dashboard → Signals page → check "Dry run" → Run Equity Scan.
You'll see exactly what the system would recommend today — tickers, scores, weights,
and the full email text it would send.

**Step 5 — Set up Gmail and receive your first real alert email**
1. Use a Gmail account (the system sends from joe.d.bennett01@gmail.com by default)
2. Generate a Gmail App Password (Google Account → Security → 2-Step Verification → App passwords)
3. Fill in your `.env` file (see Section 1 below)
4. In the dashboard → Signals → uncheck "Dry run" → Run Equity Scan
5. You'll receive an email with the full signal list

**Step 6 — Decide how much of the strategy to execute**
When you get your first signal email, you have options for how to act on it:

| Approach | What to do | Trade-off |
|---|---|---|
| **Full strategy** | Execute every long and short signal | Closest to backtest results. Requires more capital and a margin account. |
| **Longs only** | Only buy the long book, skip shorting | Easier to start. Loses the hedge and some return edge, but simpler. |
| **Top N longs only** | Execute only the top 10 or 20 ranked longs | Good starting point. Higher concentration risk but manageable. |
| **Paper trade first** | Do nothing live, watch Alpaca paper account | Best if you want to validate before committing real money. Recommended. |

The short side (shorting the bottom-ranked stocks) is what distinguishes 120/20
from a plain momentum strategy. It's worth including eventually, but starting
with longs only is a perfectly reasonable Phase 1 approach.

**Step 7 — Execute the trades at your broker**
The email gives you everything you need. Example:
```
LONG MSFT @ 1.2% of portfolio
  HOW: Buy market order at open
```
If your portfolio is $50,000 → buy $600 worth of MSFT at market open next morning.
Do this for each position in the signal list. Set a calendar reminder for the next
rebalance date (monthly or quarterly depending on your config).

**Step 8 — On rebalance day**
The system sends you a new signal list. Compare it to what you currently hold:
- Stocks that dropped off the long book → sell
- New entries to the long book → buy
- Stocks that dropped off the short book → cover (buy back)
- New entries to the short book → short sell

The email will eventually include a "current vs. target" comparison to make this easy.

---

---

## 1. First-Time Setup

### Step 1 — Install Python packages
Open a terminal in this folder and run:
```
pip install -r requirements.txt
```
This installs everything the system needs (OpenBB for data, VectorBT for backtesting,
Streamlit for the dashboard, etc.).

### Step 2 — Set up Gmail for alerts
1. Use a Gmail account to send alerts from
2. Enable 2-Step Verification on the account (Google Account → Security)
3. Generate an App Password (Google Account → Security → 2-Step Verification → App passwords)
4. The App Password is a 16-character code — treat it like a password

### Step 3 — Set up your credentials
1. Copy `.env.example` and rename the copy to `.env`
2. Open `.env` and fill in your Gmail values:
```
GMAIL_ADDRESS=you@gmail.com           ← the Gmail account sending alerts
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx  ← your 16-character App Password
ALERT_TO_EMAIL=you@gmail.com          ← where to send the alerts (can be the same address)
```
**Never share or commit the `.env` file. It contains your private keys.**

### Step 4 — Verify everything works
```
python quickstart.py
```
This runs through data fetching and signal generation without sending any email.
If it completes without errors, you're ready.

---

## 2. Daily Use

### Launch the dashboard
```
streamlit run dashboard/app.py
```
A browser window opens automatically. This is your main control panel.

### Run a signal scan (and send email if conditions are met)
```
python alerts/engine.py
```
Or use the **Signals** page in the dashboard — check "Dry run" first to preview
without actually sending a message.

### Schedule it to run automatically
You can use Windows Task Scheduler to run `python alerts/engine.py` every weekday
after market close (e.g., 4:30 PM ET). Ask Claude to help set this up when ready.

---

## 3. The Dashboard

The dashboard has four pages (left sidebar):

### Portfolio Overview
Shows current strategy settings and config. In Phase 2, this will show your live
paper trading positions and P&L.

### Backtest
Run a historical test of the strategy. You can:
- Set the date range (e.g., 2018–2024)
- Adjust value vs. momentum weighting with a slider
- Change rebalance frequency (monthly vs. quarterly)
- Change how many stocks are in the long/short books
- Compare multiple runs side by side in a table

Each run shows an equity curve, drawdown chart, rolling Sharpe, and a metrics table
vs. the S&P 500 benchmark.

### Signals
Shows what the strategy recommends right now. Includes:
- Top long candidates with their factor scores
- Top short candidates
- Any iron condor opportunities
- Check "Dry run" to preview the email text before actually sending it

### Research Sandbox
Quickly change factor weights and see how the top-ranked stocks change —
without running a full backtest. Good for fast "what if" exploration.

---

## 4. Changing Strategy Parameters

**All strategy parameters live in one file: `config/portfolio.yaml`**
Open it in any text editor. The key sections:

### Rebalance frequency
```yaml
strategy:
  rebalance_frequency: "monthly"    ← change to "quarterly" to rebalance less often
```

### Long/short book size
```yaml
strategy:
  long_pct: 0.20     ← long the top 20% of ranked stocks
  short_pct: 0.20    ← short the bottom 20% of ranked stocks
```
Increasing `long_pct` to 0.30 means you hold more stocks in the long book (more diversified,
lower individual stock risk, but potentially weaker returns).

### Value vs. momentum blend
```yaml
score_blend:
  value_weight: 0.50      ← 50% of final score comes from value factors
  momentum_weight: 0.50   ← 50% comes from momentum
```
If you want a pure momentum strategy, set `value_weight: 0.0` and `momentum_weight: 1.0`.
Always run a backtest after changing this to see the impact.

### Value factor weights
```yaml
value_factors:
  pe_ratio: 0.30      ← P/E ratio gets 30% of the value score
  pb_ratio: 0.25      ← Price/Book gets 25%
  fcf_yield: 0.25     ← Free Cash Flow yield gets 25%
  ev_ebitda: 0.20     ← EV/EBITDA gets 20%
```
These must add up to 1.0. If you don't trust EV/EBITDA data quality, you could
set it to 0.0 and redistribute weight to the others.

### Iron condor thresholds
```yaml
iron_condor:
  min_iv_rank: 50         ← only consider trades when IV Rank is >= 50
  min_dte: 30             ← minimum days to expiration
  max_dte: 45             ← maximum days to expiration
  target_delta: 0.16      ← how far OTM to sell (~1 standard deviation)
  profit_target_pct: 0.50 ← close the trade at 50% of max profit
  stop_loss_multiplier: 2.0  ← close if loss reaches 2x the credit received
  exit_dte: 21            ← always close at 21 days to expiration
```
Raising `min_iv_rank` to 60 makes the scanner more selective (only the highest premium
environments trigger an alert).

### Position size limits
```yaml
risk:
  max_single_position: 0.05    ← no single stock can exceed 5% of portfolio
  max_sector_exposure: 0.30    ← no sector can exceed 30%
```

**After any change to portfolio.yaml:**
Go to the Backtest page in the dashboard and run a test to see how it would have performed.

---

## 5. Changing Your Universe

**Universe settings live in: `config/universe.yaml`**

### Switch universe with one line
```yaml
preset: "all_us"       ← all US-listed stocks (4,000–5,000 after filters)
# preset: "sp500"      ← S&P 500 only (~500 stocks)
# preset: "sp1500"     ← S&P 500 + MidCap + SmallCap (~1,500 stocks)
# preset: "nasdaq100"  ← NASDAQ 100 only
# preset: "custom"     ← your own list (fill in tickers below)
```
Just uncomment the line you want and comment out the others.

### Custom ticker list
```yaml
preset: "custom"

presets:
  custom:
    tickers: ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
```

### Adjust filters to control universe size
```yaml
filters:
  min_market_cap_M: 300      ← raise to 1000 to cut universe roughly in half
  min_avg_daily_volume: 100000
  min_price: 5.00
  include_adrs: true         ← set false to exclude foreign companies listed in US
  include_etfs: false
  include_spacs: false
```

### Always exclude specific stocks
```yaml
exclusions:
  tickers: ["GME", "AMC"]    ← these will never appear in signals regardless of score
```

### Force-include specific stocks
```yaml
inclusions:
  tickers: ["BRK-B"]         ← these always pass filters even if they wouldn't normally
```

**Note on speed:** The first time you run with a large universe (all_us), fetching
data for 4,000+ stocks takes 15–30 minutes. After that it loads from cache in seconds.
The cache refreshes automatically every 4–24 hours depending on the data type.

---

## 6. Changing Your Alert Settings

**Alert settings live in: `config/alerts.yaml`**

### Turn off a type of alert
```yaml
triggers:
  rebalance_signal: true      ← set false to stop getting rebalance emails
  condor_opportunity: true    ← set false to stop condor alerts
  risk_breach: true
```

### Set quiet hours (no emails during these times)
```yaml
quiet_hours:
  enabled: true
  start: "22:00"    ← no emails after 10 PM
  end: "07:00"      ← no emails before 7 AM
```

### Change what's included in the email
```yaml
detail:
  include_why: true           ← explains why the trade makes sense
  include_how: true           ← step-by-step execution instructions
  include_current_vs_target: true
```

---

## 7. Running a Backtest

### From the dashboard (easiest)
1. Open the dashboard: `streamlit run dashboard/app.py`
2. Go to the **Backtest** page
3. Set your date range, adjust sliders, give the run a label
4. Click **Run Backtest**
5. Charts appear automatically — equity curve, drawdown, rolling Sharpe
6. Run again with different settings; both runs appear in the comparison table at the bottom

### From Python (for more control)
```python
from backtesting.runner import run_backtest, compare_backtests

# Baseline run
r1 = run_backtest(start="2018-01-01", end="2024-01-01", label="baseline")

# Same period, more momentum weight
r2 = run_backtest(
    start="2018-01-01",
    end="2024-01-01",
    config_override={"score_blend": {"value_weight": 0.2, "momentum_weight": 0.8}},
    label="high_momentum",
)

# Side-by-side comparison
print(compare_backtests([r1, r2]))
```

### Backtest results are saved automatically
Each run saves an interactive HTML chart to `backtesting/results/`.
Open any `.html` file in your browser to view it later.

---

## 8. Understanding the Email Alerts

### Equity rebalance alert example
```
=== PORTFOLIO SIGNAL: 2026-03-24 ===

--- TOP 5 LONGS ---
LONG AAPL @ 1.2% of portfolio
  Composite score: 0.82 (value: 0.71, momentum: 0.93)
  P/E 24.1 | P/B 3.2 | FCF yield 4.1%
  HOW: Buy market order at open
```
- **Composite score**: 0–1 scale. Higher = stronger combined value+momentum signal.
- **Value/momentum sub-scores**: also 0–1. Shows which factor is driving the ranking.
- **HOW**: tells you exactly what to do — market order at open, or short sale, etc.

### Iron condor alert example
```
IRON CONDOR OPPORTUNITY: SPY
  Current price: $512.00 | IV Rank: 67
  Expiry: 2026-04-18 (38 DTE)
  Structure:
    Buy 470P / Sell 480P — Sell 530C / Buy 540C
  Est. credit: $2.45 | Max loss: $7.55
  WHY: IV Rank 67 means elevated premium — good time to sell volatility.
  HOW: Sell the condor as a single 4-leg order at midpoint ($2.45 credit target).
  MANAGE: Close at 50% profit ($1.23 credit remaining) or at 21 DTE.
```
- **IV Rank 67**: Implied volatility is in the 67th percentile of its past year — above average, good for selling premium.
- **Buy 470P / Sell 480P**: Your put spread (defines max loss on the downside).
- **Sell 530C / Buy 540C**: Your call spread (defines max loss on the upside).
- **Est. credit $2.45**: You collect $245 per contract (100 shares × $2.45).
- **Max loss $7.55**: Worst case you lose $755 per contract.
- **MANAGE line**: This tells you exactly when to close the trade.

---

## 9. File Map

```
config/
  portfolio.yaml     ← MAIN CONTROL FILE — strategy parameters, factor weights, risk limits
  universe.yaml      ← Which stocks to include and filters
  alerts.yaml        ← When and how to send emails

strategies/
  value_momentum_120_20.py   ← Core equity strategy logic (scoring, ranking, signal generation)
  iron_condor.py             ← Options condor screener

backtesting/
  runner.py          ← Run historical backtests; compare configs
  results/           ← Saved HTML backtest charts (open in browser)

alerts/
  engine.py          ← Runs the scan, decides when to fire alerts
  notifier.py        ← Sends alert emails via Gmail

dashboard/
  app.py             ← Launch this with "streamlit run dashboard/app.py"
  charts.py          ← Chart templates (equity curve, drawdown, etc.)

utils/
  openbb_client.py   ← All data fetching (prices, fundamentals, options)
  metrics.py         ← Performance calculations (Sharpe, drawdown, etc.)

data/
  cache/             ← Auto-generated cache files — safe to delete if data seems stale
  raw/               ← Downloaded data snapshots

research/
  notebooks/         ← Jupyter notebooks for free-form exploration

.env                 ← YOUR PRIVATE CREDENTIALS — never share this file
.env.example         ← Template showing what goes in .env
requirements.txt     ← Python package list
quickstart.py        ← Sanity check — run this after first install
```

---

## 10. Phases

### Phase 1 — Complete (alerts, no automation)
- Strategy scans run manually or on a schedule
- Email alerts tell you what to trade and why
- You place the trades yourself in your brokerage
- Backtesting fully functional

### Phase 2 — Current (paper trading)
- Alpaca paper trading account connected (free at alpaca.markets)
- System places simulated trades automatically
- Monthly rebalance + daily stop-loss replacement run on schedule
- Validate the system works before going live

### Phase 3 — Live trading
- Flip Alpaca from paper to live account
- Real money trades execute automatically
- Additional risk controls and circuit breakers added first

---

## 11. Common Questions

**Q: How do I clear the cache if data looks stale?**
Delete everything in the `data/cache/` folder. The next run will re-fetch fresh data.

**Q: How do I add a new stock to always watch (even if it doesn't rank well)?**
Add it to `inclusions.tickers` in `config/universe.yaml`.

**Q: How do I stop getting alerts for a strategy I don't want?**
Set the relevant trigger to `false` in `config/alerts.yaml`.

**Q: How do I test what an alert email will look like without sending it?**
In the dashboard, go to Signals page and check "Dry run" before clicking scan.
Or run `python alerts/engine.py` — it defaults to dry run when run directly.

**Q: What does it mean when a stock has a high value score but low momentum?**
It means the stock looks cheap on fundamentals (low P/E, low P/B etc.) but has been
performing poorly recently. A pure value investor might still buy it. With our 50/50 blend,
it may or may not rank highly enough to make the long book.

**Q: How do I change the blend to be all value or all momentum?**
In `config/portfolio.yaml`:
```yaml
score_blend:
  value_weight: 1.0      ← pure value
  momentum_weight: 0.0
```
Then run a backtest to compare vs. the blended version.

**Q: How do I run the system on a smaller universe while experimenting?**
Change `preset: "sp500"` in `config/universe.yaml`. This is much faster for iteration.
Switch back to `all_us` when you're ready for production runs.

**Q: Where do I make changes that require code?**
Ask Claude in this folder. Claude reads CLAUDE.md at the start of every session
and knows the full project context. Describe what you want in plain English.
