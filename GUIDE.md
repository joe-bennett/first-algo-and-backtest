# User Guide — Algo Trading Portfolio

This guide explains everything in plain English: what each piece does, how to get started,
and how to make common changes without needing to touch code.

---

## Table of Contents

0. [Where Securities Are Held — Brokerages Explained](#0-where-securities-are-held)
1. [First-Time Setup](#1-first-time-setup)
2. [Daily Use — How to Run Things](#2-daily-use)
3. [The Dashboard](#3-the-dashboard)
4. [How the Strategy Scores Stocks](#4-how-the-strategy-scores-stocks)
   - Raw factors, percentile ranking, composite score assembly, sector neutralization
4b. [Changing Strategy Parameters](#4b-changing-strategy-parameters)
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

For this strategy you need up to three account features depending on what you run:

| Feature | Why you need it | Without it |
|---|---|---|
| **Margin account** | Required to short stocks (the 20% short side of 120/20) | Long book only; disable `enable_short_book` |
| **Options approval Level 1** | Required to buy put contracts (`short_book_puts`) | Cannot use puts on the short book; use regular shorts instead |
| **Options approval Level 2** | Required for multi-leg spreads like iron condors | Cannot trade condors |

Most brokers approve Level 1 (buying options) and Level 2 (spreads) without difficulty —
you answer questions about your experience and income when applying. Margin requires a
minimum account balance (usually $2,000, but $25,000+ is practical — see below).

You can run this strategy without options at all: set `enable_short_book: true` with
`short_book_puts.enabled: false` and skip the iron condor scanner. The equity strategy
is fully functional without any options approval.

---

### Do I need a brokerage account at all?

**No — most of the system works without one:**

| Works without any brokerage | Requires Alpaca |
|---|---|
| Backtesting (full historical simulation) | Portfolio Overview page (live positions) |
| Research Sandbox | Automated rebalancing |
| Signal scanning — today's ranked stocks | Automated stop-loss replacement |
| Email alerts | Placing live or paper trades |
| All dashboard charts | Put option order placement |

If you skip Alpaca for now, leave those three lines blank in `.env`. The Portfolio
Overview page will show your config instead of live positions; everything else works.

---

### What is Alpaca?

Alpaca (alpaca.markets) is a **free brokerage with an open API** — meaning you can write
code that places real trades automatically. It also offers **paper trading**: a simulated
account pre-loaded with $100,000 of fake money so you can test automated strategies
without risking anything real. That's what this system uses by default.

Paper trading is completely free, requires no credit card, and takes about 5 minutes to
set up. You do not need to fund the account or go through a full brokerage application.

### How to set up Alpaca (5 minutes)

1. Go to **alpaca.markets** → click "Get Started Free"
2. Create an account with your email and a password — no credit card required
3. You land in the paper trading dashboard with $100,000 simulated balance
4. Click your name in the top-right corner → **API Keys** → **Generate New Key**
5. Copy both the **API Key** (starts with `PK...`) and the **Secret Key**
   — you only see the secret once, copy it somewhere safe immediately
6. Open your `.env` file and add:
```
ALPACA_API_KEY=PKXXXXXXXXXXXXXXXX
ALPACA_SECRET_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ALPACA_BASE_URL=https://paper-api.alpaca.markets
```

The system will now connect to your paper account, place simulated trades on rebalance
dates, track positions, and show live P&L in the Portfolio Overview dashboard.

> **When you're ready for real money:** Fund a live Alpaca account and change
> `ALPACA_BASE_URL` to `https://api.alpaca.markets`. Everything else stays the same.
> Only do this after running paper trading long enough to trust the system.

---

### Which broker to use

| Broker | Best for | Notes |
|---|---|---|
| **Alpaca** | Paper trading now, automation later | Free, no credit card, $100k simulated balance, commission-free. Best path to Phase 3 automation. |
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

With quarterly rebalancing this is not a significant issue — you're not day trading.
But it's worth knowing. If you plan to start with less than $25,000, use quarterly
rebalancing (already the default) and avoid same-day round trips.

---

### How much capital do you need?

There is no hard minimum, but here is the practical reality:

| Capital | What's feasible |
|---|---|
| **$5,000 – $10,000** | Longs only. Use concentration mode (`top_n_longs: 10`) for manageable position count. |
| **$25,000 – $50,000** | Full long book + short book. Above PDT threshold. Consider concentration (top 15–20 longs). |
| **$50,000+** | Full 120/20 strategy — long and short book with reasonable position sizing. |
| **$100,000+** | Full strategy including condors and/or puts on short book with meaningful sizes. |

The strategy works at any size. Smaller accounts benefit from concentration mode —
fewer positions, each one large enough to matter, without needing $100k to build
100 equally-sized positions.

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
rebalance date (quarterly by default — 1st of January, April, July, October).

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

### Step 0 — Get the code
```bash
git clone https://github.com/joe-bennett/first-algo-and-backtest.git
cd first-algo-and-backtest
```
Requires **Python 3.10 or later**. Check your version with `python --version`.
If you need to install Python, download from python.org — make sure to check
"Add Python to PATH" during installation on Windows.

### Step 1 — Install Python packages
Open a terminal in the project folder and run:
```
pip install -r requirements.txt
```
This installs everything the system needs (yfinance for data, VectorBT for backtesting,
Streamlit for the dashboard, alpaca-py for paper trading, etc.).

### Step 2 — Set up Gmail for alerts
1. Use a Gmail account to send alerts from
2. Enable 2-Step Verification on the account (Google Account → Security)
3. Generate an App Password (Google Account → Security → 2-Step Verification → App passwords)
4. The App Password is a 16-character code — treat it like a password

### Step 3 — Set up your credentials
1. Copy `.env.example` and rename the copy to `.env`
2. Open `.env` and fill in your values:
```
GMAIL_ADDRESS=you@gmail.com             ← the Gmail account sending alerts
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx  ← your 16-character App Password
ALERT_TO_EMAIL=you@gmail.com            ← where to send the alerts (can be the same address)
ALPACA_API_KEY=your_key                 ← from alpaca.markets (free paper trading account)
ALPACA_SECRET_KEY=your_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets
SIMFIN_API_KEY=your_simfin_key          ← from simfin.com → Free Plan → Get API Key
```
**Never share or commit the `.env` file. It contains your private keys.**

The SimFin key is required for backtesting with accurate historical fundamentals. The first backtest run downloads ~450MB of data to `data/simfin/` — this takes a few minutes once, then loads from cache in seconds.

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
Windows Task Scheduler is already configured to run `run_alerts.py` every weekday
at 4:30 PM ET (task name: `TradingAlerts`). This handles both the daily condor scan
and the quarterly rebalance (fires on the 1st of January, April, July, October).

---

## 3. The Dashboard

The dashboard has four pages (left sidebar):

### Portfolio Overview
Shows current strategy settings and config. In Phase 2, this will show your live
paper trading positions and P&L.

### Backtest
Run a historical test of the strategy. Every parameter below is adjustable without
touching any files — changes only affect that backtest run, not the live system.

**Factor weights**
- Value / momentum / quality blend (sliders; quality auto-fills to keep sum at 100%)

**Universe and book size**
- Long book: top X% of universe (how many stocks, not how much capital)
- Short book: bottom X% of universe (same idea)
- Rebalance frequency: monthly or quarterly

**Exposure — the X/Y in 120/20**
- Long-side capital deployed: how much of the portfolio is invested long (default 120%)
- Short-side capital deployed: how much is short (default 20%)
- A live label shows the current strategy name ("130/30 — net 100%, gross 160%") and
  updates as you move the sliders so you always know what structure you're testing

**Concentration and conviction**
- Concentration mode: fix the long/short book to a specific stock count instead of a
  percentage (e.g., top 15 longs at 8% each instead of top 20% at 1.2% each)
- Weight by conviction: score-proportional sizing within the book so rank #1 gets more
  capital than rank #15 (most impactful combined with concentration mode)

**Other**
- Sector neutralization toggle
- Run label (auto-filled with the key settings so the comparison table is self-labeling)

Each run shows an equity curve, drawdown chart, rolling Sharpe, and a metrics table
vs. the S&P 500 benchmark. Multiple runs stack in a comparison table at the bottom.

> **Note on puts in backtests:** Put signals are simulated as short positions (same
> directional exposure, 1:1 payoff). The convex upside of real options cannot be
> reproduced without implied volatility history.

### Signals
Shows what the strategy recommends right now. Includes:
- Top long candidates with factor scores and WHY explanations
- Short book — regular short shares
- Short book — conviction puts (separate section when `short_book_puts` is enabled)
- Iron condor opportunities
- "Dry run" checkbox: preview the full email text without sending anything

### Research Sandbox
Quickly change factor weights, concentration, and conviction settings to see how the
top-ranked stocks change — without running a full backtest. Results appear in seconds.
Good for fast "what if" questions before committing to a full backtest run.

---

## 4. How the Strategy Scores Stocks

Before changing parameters, it helps to understand exactly how a stock gets its score.
Everything below is a plain-English description of `strategies/value_momentum_120_20.py`.

### Step 1 — Gather raw data for every stock in the universe

For each stock in the S&P 500 the system collects:

| Data point | Source | What it measures |
|---|---|---|
| P/E ratio | SimFin / yfinance | Price paid per $1 of earnings |
| P/B ratio | SimFin / yfinance | Price paid per $1 of book value (assets minus liabilities) |
| FCF yield | SimFin / yfinance | Free cash flow generated per $1 of market cap |
| EV/EBITDA | SimFin / yfinance | Total firm cost (debt + equity) vs. operating earnings |
| ROE | SimFin / yfinance | Net income earned per $1 of shareholders' equity |
| Net profit margin | SimFin / yfinance | Fraction of each dollar of revenue that becomes profit |
| Debt/equity ratio | SimFin / yfinance | Total debt relative to equity — a leverage measure |
| 12-1 month price return | yfinance | Price 1 month ago ÷ price 12 months ago minus 1 |

The momentum calculation uses a **5-day average** around each reference point (±2 trading
days) rather than a single day's price. This prevents one unusually volatile day from
distorting a full year of price history.

---

### Step 2 — Convert every raw number to a percentile rank (0–1)

Raw numbers can't be meaningfully compared across factors or across time. A P/E of 20
might be cheap in 2022 and expensive in 2015. A tech stock at P/E 25 is cheap for tech;
an oil stock at P/E 25 is expensive for energy.

**Percentile ranking solves this** by asking: *how does this stock rank compared to every
other stock in the universe right now?*

Line up all 500 stocks by P/E from lowest to highest:
```
Cheapest P/E  → rank 0.01  (1st percentile)
Median P/E    → rank 0.50
Most expensive → rank 0.99  (99th percentile)
```

For factors where **lower is better** (P/E, P/B, EV/EBITDA, debt/equity), the rank is
**inverted** — the cheapest stock gets a score of 1.0, the most expensive gets 0.0.

For factors where **higher is better** (FCF yield, ROE, net margin, momentum), higher values
get higher scores directly.

**Example:**

| Stock | Raw P/E | Position in universe | Raw rank | Inverted (value score) |
|---|---|---|---|---|
| XOM | 11 | 8th cheapest of 500 | 0.016 | **0.984** |
| AAPL | 28 | 350th cheapest | 0.700 | **0.300** |
| MSFT | 35 | 420th cheapest | 0.840 | **0.160** |

XOM gets a near-perfect value sub-score not because P/E 11 is a magic threshold — it's
because XOM is cheaper than 98% of the universe today. If P/Es compress market-wide next
year, XOM's raw P/E might be 9 and AAPL might be 22, but their relative scores would be
similar because the ranking is always relative to the current universe.

---

### Step 3 — Build composite scores within each factor category

Each of the three categories blends its ranked sub-factors into a single score:

**Value score** (four sub-factors, weights from `value_factors` in portfolio.yaml):
```
value_score = 0.30 × pe_rank  +  0.25 × pb_rank  +  0.25 × fcf_rank  +  0.20 × ev_rank
```

**Momentum score** (single factor — no blending needed):
```
momentum_score = rank of 12-1 month return
```

**Quality score** (three sub-factors, weights from `quality_factors`):
```
quality_score = 0.40 × roe_rank  +  0.40 × margin_rank  +  0.20 × debt_equity_rank
```

All three composite scores end up on the same 0–1 scale. A score of 0.85 means the
stock ranks in the top 15% on that factor across the entire universe.

---

### Step 4 — Blend into one final composite score

```
composite = 0.40 × value_score  +  0.40 × momentum_score  +  0.20 × quality_score
```

(weights from `score_blend` in portfolio.yaml — you can change them)

The top 20% of composite scores become the **long book**. The bottom 20% become the
**short book** (or put candidates if `short_book_puts` is enabled).

---

### Step 5 — Sector neutralization (optional)

When `sector_neutral: true`, Steps 2 and 3 happen **within each GICS sector** rather than
across the whole universe. A tech stock's P/E is ranked against other tech stocks only.

This prevents the entire long book from loading up in one sector. If energy is universally
cheap on P/E right now, global ranking might put 30 energy stocks in the top 20%. Sector
neutralization ensures no one sector dominates by forcing each sector to contribute
roughly proportionally to the long and short books.

Default is `false` because sector neutralization removes the ability to bet on cheap
sectors vs. expensive sectors — a legitimate source of return.

---

### What this means practically

- **Composite score of 0.85** → ranks in the top 15% of the universe on the blended signal
- **Composite score of 0.50** → median; doesn't have a strong signal either way
- **Composite score of 0.10** → ranks in the bottom 10%; strong short/put candidate
- The score is always relative to today's universe, not an absolute threshold
- Changing factor weights in `portfolio.yaml` shifts which kind of stocks rank highly —
  run a backtest after any change to see the historical impact

---

## 4b. Changing Strategy Parameters

**All strategy parameters live in one file: `config/portfolio.yaml`**
Open it in any text editor. The key sections:

### Rebalance frequency
```yaml
strategy:
  rebalance_frequency: "quarterly"  ← change to "monthly" to rebalance more often (higher cost)
```

### Long/short book size
```yaml
strategy:
  long_pct: 0.20     ← long the top 20% of ranked stocks
  short_pct: 0.20    ← short the bottom 20% of ranked stocks
```
Increasing `long_pct` to 0.30 means you hold more stocks in the long book (more diversified,
lower individual stock risk, but potentially weaker returns).

### Value / momentum / quality blend
```yaml
score_blend:
  value_weight:    0.34   ← 34% of the final score comes from value factors
  momentum_weight: 0.33   ← 33% comes from momentum
  quality_weight:  0.33   ← 33% comes from quality factors (ROE, margin, debt)
```
The three weights must add up to 1.0. If you want a pure momentum strategy, set
`value_weight: 0.0`, `quality_weight: 0.0`, and `momentum_weight: 1.0`.
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

### Quality factor weights
```yaml
quality_factors:
  roe: 0.40           ← Return on Equity gets 40% of the quality score
  net_margin: 0.40    ← Net profit margin gets 40%
  debt_equity: 0.20   ← Debt/Equity gets 20% (lower D/E = higher quality)
```
Quality data comes from SimFin (same point-in-time source as value factors).
Stocks with negative equity or missing data fall back to the median quality score.

### Sector neutralization
```yaml
sector_neutral: true   ← rank stocks within their GICS sector (recommended)
# sector_neutral: false ← rank all stocks globally (may concentrate in one sector)
```
When enabled (default), each factor is ranked relative to sector peers. A cheap tech
stock is ranked against other tech stocks, not against cheap energy stocks. This prevents
the entire long book from filling up with one sector when it happens to be out of favor.

### Short book toggle
```yaml
enable_short_book: true   ← 120% long / 20% short (full strategy)
# enable_short_book: false ← 100% long, no shorting (long-only version)
```
Turn off shorting if your broker doesn't support short selling or if you want to
reduce risk. The long book is identical either way — only the short positions change.

### Concentration mode
```yaml
concentration:
  top_n_longs: null            ← null = use long_pct percentage (default: top 20%)
  top_n_shorts: null           ← null = use short_pct percentage (default: bottom 20%)
  weight_by_conviction: false  ← true = score-proportional sizing within the book
```
By default the portfolio spreads across the top 20% of ranked stocks (~100 names at 1.2% each).
Concentration mode overrides this with a fixed count so more capital goes to your
highest-conviction picks.

| Setting | Long count | Position size | Character |
|---|---|---|---|
| `top_n_longs: null` | ~100 names | ~1.2% each | Diversified (default) |
| `top_n_longs: 15` | 15 names | ~8% each | Aggressive |
| `top_n_longs: 10` | 10 names | ~12% each | Very aggressive |

**The tradeoff:** Your ranking signal is strongest at the extremes — the top 15 stocks
rank higher than the average of the top 100. Concentration lets that signal actually matter.
But a single bad pick has much larger impact. Run a backtest before going live with
concentrated sizing to see how it affects drawdowns.

You can control longs and shorts independently:
```yaml
concentration:
  top_n_longs: 15    ← concentrate longs to top 15
  top_n_shorts: null ← keep shorts diversified (percentage-based)
```

The dashboard Backtest page has a "Concentration mode" toggle that lets you backtest
different counts without editing the YAML file.

### Weight by conviction (score-proportional sizing)
```yaml
concentration:
  weight_by_conviction: false   ← true = higher-ranked stocks get more capital
```

By default, equal weight is applied within the long and short books — every stock in
the top 15 gets the same 8% regardless of whether it scored 0.94 or 0.79. Conviction
weighting breaks that equal split: **position size becomes proportional to composite score**.

**How the math works for longs:**
```
position_weight = (stock's composite score / sum of all selected scores) × total long exposure

Example with top 5 longs, long exposure = 120%:
  Stock A  score 0.94  →  0.94 / 4.25  × 120% = 26.5%  ← gets most capital
  Stock B  score 0.88  →  0.88 / 4.25  × 120% = 24.8%
  Stock C  score 0.83  →  0.83 / 4.25  × 120% = 23.4%
  Stock D  score 0.79  →  0.79 / 4.25  × 120% = 22.3%
  Stock E  score 0.81  →  0.81 / 4.25  × 120% = 22.9%  ← gets least capital
  Total: 120% ✓
```

**How the math works for shorts (and puts):**
For short positions, a *lower* composite score means *stronger bearish conviction* — the
stock ranks at the very bottom of the universe. So the weighting is inverted:
```
short_conviction = (highest score in short book) − (stock's score)
position_weight  = short_conviction / sum(all short convictions) × total short exposure

Example with bottom 3 shorts, short exposure = 20%:
  Stock X  score 0.09  →  conviction = 0.21 − 0.09 = 0.12  →  largest short
  Stock Y  score 0.14  →  conviction = 0.21 − 0.14 = 0.07  →  mid short
  Stock Z  score 0.21  →  conviction = 0.21 − 0.21 = 0.00 + floor →  smallest short
```

**When to use it:**
- Most impactful **combined with concentration mode** (`top_n_longs: 15`). When each position
  averages 8%, a spread from 6% to 10% between the weakest and strongest pick is meaningful
  ($4,000 difference on a $100k portfolio per stock).
- At default diversification (~100 longs at 1.2% each), conviction weighting only spreads
  positions across a ~0.8%–1.6% range — meaningful but subtle.
- **Off by default** because equal weighting is more stable and still captures the full alpha
  of stock selection. Conviction weighting adds a layer of concentration within an already
  concentrated book.

**Dashboard:** The Backtest page and Research Sandbox both have a "Weight by conviction"
checkbox. Check it alongside "Concentration mode" to see the combined effect in backtests.

### Puts on the short book
```yaml
short_book_puts:
  enabled: false        ← true = buy put contracts on conviction shorts
  conviction_n: 10      ← number of most-extreme shorts to buy puts on
  target_delta: 0.30    ← target option delta (~30 delta = moderately OTM)
  dte: 90               ← days to expiration (3 months)
  premium_pct: 0.003    ← spend 0.3% of portfolio per put position
```
When `enabled: true`, the bottom `conviction_n` stocks by composite score get **OTM
put options** instead of short shares. Any additional short candidates (beyond
conviction_n) still use regular short selling.

**Why puts instead of shorting shares:**
- A 40% stock drop on a short position returns 40%. The same drop on a put can return 3–5x.
- No short squeeze risk — your max loss is the premium paid, not unlimited.
- No borrow fees on hard-to-borrow or expensive-to-borrow names.

**The tradeoff:** Puts decay every day (theta). If a stock drifts sideways for 3 months,
the put expires worthless. A short position has no such time pressure — you can hold it for
a year waiting to be right. Use puts on your *most extreme* conviction shorts where you
expect a real move, not just gradual underperformance.

**Managing put positions:**
- Set a GTC limit order to close at 2x the premium paid (profit target).
- Always close by 21 DTE regardless — time decay accelerates in the final weeks.
- The system does NOT automatically close puts during rebalance — you must manage them.

**Backtesting note:** In backtests, PUT signals are treated as regular short positions
(same directional exposure, 1:1 payoff). The convex upside of real put options cannot be
reproduced without implied volatility history. The backtest tells you the directional edge
of the signal; use the live system to evaluate the actual options payoff.

**Requirements:** Alpaca options trading must be enabled on your account.

### Iron condor thresholds and sizing
```yaml
iron_condor:
  min_iv_rank: 50         ← only consider trades when IV Rank is >= 50
  min_dte: 30             ← minimum days to expiration
  max_dte: 45             ← maximum days to expiration
  target_delta: 0.16      ← how far OTM to sell (~1 standard deviation)
  profit_target_pct: 0.50 ← close the trade at 50% of max profit
  stop_loss_multiplier: 2.0  ← close if loss reaches 2x the credit received
  exit_dte: 21            ← always close at 21 days to expiration
  per_condor_pct: 0.05    ← reserve 5% of portfolio as margin per condor
  max_total_pct: 0.15     ← max 15% across all open condors (3 at once)
  default_portfolio_value: 100000  ← fallback if Alpaca is not connected
```
Raising `min_iv_rank` to 60 makes the scanner more selective (only the highest premium
environments trigger an alert).

**How condor sizing works:** The alert email tells you exactly how many contracts to trade — no math needed. The system reserves `per_condor_pct` (5%) of your portfolio as the margin budget for each condor, then divides by the max loss per contract to arrive at a contract count. The 15% total cap means no more than 3 condors open at once before the scanner stops recommending new ones.

**Condor and 120/20 conflict avoidance:** The condor scanner automatically skips any ticker already held in the 120/20 equity book. A condor profits when a stock stays range-bound — that conflicts with holding it as a directional long or short. When the scanner runs, it reads live positions from Alpaca (or falls back to `data/last_signals.json`) and removes those tickers from consideration before screening.

### Long/short exposure — the X/Y in 120/20
```yaml
strategy:
  long_weight: 1.20    ← deploy 120% of portfolio value long (the "120" in 120/20)
  short_weight: 0.20   ← deploy 20% of portfolio value short (the "20" in 120/20)
```
This controls **how much total capital** is deployed on each side — not how many stocks.
The extra long-side capital (beyond 100%) is funded by the proceeds from short selling.

| long_weight | short_weight | Net exposure | Gross exposure | Name |
|---|---|---|---|---|
| 1.00 | 0.00 | 100% | 100% | Long-only |
| 1.20 | 0.20 | 100% | 140% | 120/20 (default) |
| 1.30 | 0.30 | 100% | 160% | 130/30 |
| 1.50 | 0.50 | 100% | 200% | 150/50 |

You can also test these directly on the **Backtest page** using the "Long-side capital
deployed" and "Short-side capital deployed" sliders — no file editing needed. A live
label shows the resulting strategy name and gross/net exposure as you move the sliders.

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
preset: "sp500"        ← S&P 500 only (~500 stocks) — default, fully point-in-time accurate
# preset: "sp1500"     ← S&P 500 + MidCap + SmallCap (~1,500 stocks, modest survivorship bias on mid/small)
# preset: "all_us"     ← all US-listed stocks (4,000–5,000 after filters)
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

### How backtests handle historical fundamentals

Backtests use **point-in-time fundamentals** via SimFin. This matters because value factors (P/E, P/B, FCF Yield, EV/EBITDA) depend on financial statement data — if you used today's numbers for a 2018 backtest, you'd be feeding the model information that didn't exist yet. That's look-ahead bias and it inflates backtest returns.

SimFin stores both the fiscal period end date and the date the filing was made public. The backtest only uses the filing once it was actually public — so a March 31 quarter-end that was filed on May 10 isn't available to the model until May 10.

The first backtest session builds the fundamentals panel from SimFin (~450MB of quarterly data for 3,600 US stocks back to 2007). It caches to `data/simfin/pit_fundamentals.pkl` and auto-refreshes every 7 days.

### How backtests handle survivorship bias

**Survivorship bias** is a common backtest problem: if you use today's S&P 500 list for a historical test, you're only including companies that survived to today. Companies that went bankrupt, were acquired, or were removed from the index are excluded — making historical returns look better than they actually were.

The backtest fixes this using a historical membership dataset (downloaded once to `data/sp500_historical_members.csv`). This gives accurate daily S&P 500 snapshots back to 1996. At each quarterly rebalance date, only stocks that were **actually in the S&P 500 on that specific date** are eligible for ranking — companies that were later removed, went bankrupt, or were acquired are properly excluded from future dates but included in the periods when they were members.

This produces more realistic — and typically lower — backtest returns than naive approaches.

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
    config_override={"score_blend": {"value_weight": 0.1, "momentum_weight": 0.8, "quality_weight": 0.1}},
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

Long book: 15 positions | Short book: 5 short shares + 10 put contracts

--- TOP 5 LONGS ---
LONG AAPL @ 8.0% of portfolio
  Composite score: 0.82 (value: 0.71, momentum: 0.93, quality: 0.77)
  P/E 24.1 | P/B 3.2 | FCF yield 4.1% | ROE 28.1% | Margin 24.2%
  WHY: AAPL ranks highly because it is cheap on fundamentals and high-quality.
  HOW: Buy market order at open

--- TOP 5 SHORTS (short shares) ---
SHORT XYZ @ 0.2% of portfolio
  ...
  HOW: Sell short at market open

--- TOP 5 CONVICTION SHORTS (via put options) ---
  These are the most extreme bottom-ranked names. Put contracts give convex downside
  exposure without short squeeze risk.

PUT ABC @ 0.2% of portfolio
  Composite score: 0.08 (value: 0.12, momentum: 0.09, quality: 0.11)
  ...
  WHY: ABC ranks poorly because it is expensive on fundamentals and weak momentum.
  HOW: Buy 1 put contract (~30-delta, ~90 DTE) via your options broker.
       Cost ≈ 0.3% of portfolio per position.
       Manage: close at 2x premium paid (profit) or at 21 DTE (time stop).
```
- **Composite score**: 0–1 scale. Higher = stronger combined signal.
- **Value/momentum/quality sub-scores**: also 0–1. Shows which factor is driving the ranking.
- **HOW for longs**: market order at open.
- **HOW for shorts**: sell short at market open.
- **HOW for puts**: buy an OTM put contract; the system shows you exactly what to look for.
  The automated system (Alpaca) finds the contract and places the order for you.

### Iron condor alert example
```
IRON CONDOR OPPORTUNITY: SPY
  Current price: $512.00 | IV Rank: 67
  Expiry: 2026-04-18 (38 DTE)
  Structure:
    Buy  470P / Sell 480P — Sell 530C / Buy 540C
  Credit: $2.45/share | Max loss: $7.55/share
  SIZE: 6 contracts | Margin reserved: $4,530.00 | Max profit: $1,470.00 | Max loss: $4,530.00
  WHY: IV Rank 67 (>=50) means elevated premium — good time to sell volatility.
  HOW: Sell 6 condors as a single 4-leg order at midpoint ($2.45 credit target per contract).
  MANAGE: Close at 50% profit (~$735.00 gain) or at 21 DTE.
```
- **IV Rank 67**: Implied volatility is in the 67th percentile of its past year — above average, good for selling premium.
- **Buy 470P / Sell 480P**: Your put spread (defines max loss on the downside).
- **Sell 530C / Buy 540C**: Your call spread (defines max loss on the upside).
- **Credit $2.45/share**: You collect $245 per contract (100 shares × $2.45). With 6 contracts = $1,470 collected.
- **Max loss $7.55/share**: Worst case per contract = $755. With 6 contracts = $4,530 total.
- **SIZE line**: The system calculated 6 contracts because 5% of a $100k portfolio ($5,000) ÷ $755 max loss per contract ≈ 6.
- **MANAGE line**: This tells you exactly when to close the trade and what your profit target is in dollars.

---

## 9. File Map

```
config/
  portfolio.yaml     ← MAIN CONTROL FILE — strategy parameters, factor weights, risk limits
  universe.yaml      ← Which stocks to include and filters
  alerts.yaml        ← When and how to send emails

strategies/
  value_momentum_120_20.py   ← Core equity strategy logic (scoring, ranking, signal generation)
                               Supports: concentration mode (top_n_longs/shorts), puts on short
                               book (action="PUT" for most-extreme conviction shorts)
  iron_condor.py             ← Options condor screener

backtesting/
  runner.py          ← Run historical backtests; compare configs
  results/           ← Saved HTML backtest charts (open in browser)

alerts/
  engine.py          ← Runs the scan, decides when to fire alerts; emails PUT signals
                       separately from regular shorts with options-specific instructions
  notifier.py        ← Sends alert emails via Gmail

broker/
  alpaca.py          ← Alpaca paper trading integration (orders, rebalance, stop-loss)
                       find_put_contract(): locates best matching OTM put via yfinance
                       place_put_order(): buys put contracts sized to premium_pct of portfolio
                       rebalance(): routes PUT signals to put orders, equity signals to shares
  position_manager.py ← Daily stop-loss replacement for equity positions
  ledger.py          ← Local portfolio ledger; saves data/ledger.csv + data/ledger.json

dashboard/
  app.py             ← Launch this with "streamlit run dashboard/app.py"
                       Backtest page: concentration mode toggle + top_n sliders
                       Signals page: PUT signals shown in dedicated section with explanations
                       Research Sandbox: concentration controls for live signal preview
  charts.py          ← Chart templates (equity curve, drawdown, etc.)

utils/
  openbb_client.py   ← All live data fetching (prices, fundamentals, options) — used by alerts
  simfin_client.py   ← Point-in-time historical fundamentals — used only by backtesting
  metrics.py         ← Performance calculations (Sharpe, drawdown, etc.)

data/
  cache/             ← Auto-generated cache files — safe to delete if data seems stale
  simfin/            ← SimFin datasets (~450MB); auto-refreshes every 7 days
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
- Quarterly rebalance (Jan/Apr/Jul/Oct) + daily stop-loss replacement run on schedule
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
performing poorly recently. A pure value investor might still buy it. With our blended
approach (34% value / 33% momentum / 33% quality), it may or may not rank highly enough
to make the long book depending on how it scores on quality.

**Q: How do I change the blend to be all value or all momentum?**
In `config/portfolio.yaml`:
```yaml
score_blend:
  value_weight:    1.0   ← pure value
  momentum_weight: 0.0
  quality_weight:  0.0
```
Then run a backtest to compare vs. the blended version.

**Q: How do I run the system on a smaller universe while experimenting?**
Change `preset: "sp500"` in `config/universe.yaml`. This is much faster for iteration.
Switch back to `all_us` when you're ready for production runs.

**Q: When should I use concentration mode vs. the default diversified approach?**
Use concentration when you have high confidence in the ranking signal and want to
maximize returns. Use diversified (default) when you want smoother returns and lower
single-stock risk. A good test: run a backtest with `top_n_longs: 15` and compare the
Sharpe ratio and max drawdown to the default. If the concentrated version has a better
Sharpe, the signal has genuine edge at the extremes. If the Sharpe drops, the signal
is noisier and diversification is doing real work.

**Q: How do I enable puts on the short book without enabling concentration?**
They're independent toggles. Set `short_book_puts.enabled: true` while leaving
`concentration.top_n_longs: null`. The strategy will still spread across the top 20%
of ranked stocks for longs, but the bottom `conviction_n` shorts will get put contracts
instead of shares.

**Q: My put orders are failing. What do I check?**
1. Confirm your Alpaca account has options trading enabled (paper accounts need this enabled in settings).
2. Make sure you have enough buying power — options are paid upfront, not on margin.
3. Check the terminal output for the specific error message from Alpaca.
4. For paper trading, some option symbols may not be available — try with a more liquid name (SPY, AAPL, MSFT).

**Q: Where do I make changes that require code?**
Ask Claude in this folder. Claude reads CLAUDE.md at the start of every session
and knows the full project context. Describe what you want in plain English.
