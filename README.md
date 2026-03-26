# Algo Trading Portfolio

An automated trading system built around two strategies:

- **120/20 Value-Momentum** — ranks S&P 500 stocks by a blend of value and momentum factors, goes long the top-ranked and short the bottom-ranked, rebalances monthly or quarterly (changable)
- **Iron Condor (opportunistic)** — scans for elevated implied volatility and alerts when conditions are right to sell premium

The system sends email alerts, runs historical backtests, trades automatically on Alpaca paper, and has a Streamlit dashboard for analysis.

---

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set up credentials
Copy `.env.example` to `.env` and fill in your values:
```
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
ALERT_TO_EMAIL=you@gmail.com
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets
SIMFIN_API_KEY=your_simfin_key
```
To generate a Gmail App Password: Google Account → Security → 2-Step Verification → App passwords.

To get a SimFin API key: simfin.com → Free Plan → Get API Key (free, no credit card).

### 3. Verify the install
```bash
python quickstart.py
```
If it completes without errors, the data pipeline is working.

### 4. Launch the dashboard
```bash
streamlit run dashboard/app.py
```

---

## How to Analyze Performance

### Run a backtest
Open the dashboard and go to the **Backtest** page. Set a date range, click **Run Backtest**, and the system will show:
- Equity curve vs. S&P 500 benchmark
- Drawdown chart
- Rolling Sharpe ratio
- Summary metrics table (annualized return, max drawdown, Sharpe, Sortino)

Run multiple configurations back to back — results stack up in a comparison table at the bottom so you can see them side by side.

Backtests use **point-in-time fundamentals** via SimFin — P/E, P/B, FCF Yield, EV/EBITDA, ROE, net margin, and debt/equity are pulled from the actual quarterly filing available on each rebalance date, not today's snapshot. This eliminates look-ahead bias in the value and quality scores.

Backtests also use **point-in-time index membership** — at each rebalance date, only stocks that were actually in the S&P 500 on that date are eligible. This eliminates survivorship bias (the distortion from only including companies that survived to today).

The strategy scores each stock on three factors:
- **Value** (34%): P/E, P/B, FCF yield, EV/EBITDA — cheaper is better
- **Momentum** (33%): 12-month price return skipping the last month — uses 5-day averages at reference points to reduce single-day noise
- **Quality** (33%): ROE, net profit margin, debt/equity — profitable, low-leverage companies score higher

With **sector neutralization** enabled (default), each factor is ranked within GICS sector. This prevents the portfolio from concentrating in a single sector (e.g., buying only cheap energy stocks when energy is out of favor).

You can also run backtests directly from Python for more control:
```python
from backtesting.runner import run_backtest, compare_backtests

r1 = run_backtest(start="2018-01-01", end="2024-01-01", label="baseline")
r2 = run_backtest(
    start="2018-01-01",
    end="2024-01-01",
    config_override={"score_blend": {"value_weight": 0.2, "momentum_weight": 0.8}},
    label="high_momentum",
)
print(compare_backtests([r1, r2]))
```

### View current signals
Go to the **Signals** page in the dashboard. Check **Dry run** to preview what the system would recommend today — tickers, factor scores, and the full email text — without sending anything.

### Explore factor weights
The **Research Sandbox** page lets you adjust value vs. momentum weights with a slider and instantly see how the top-ranked stocks change, without running a full backtest. Good for quick "what if" questions.

### View current holdings
A local ledger is saved to `data/ledger.csv` and `data/ledger.json` after every rebalance, stop-loss replacement, and daily run. Open `ledger.csv` in Excel any time to see:

| Column | Description |
|---|---|
| ticker / side | What you hold and whether it's long or short |
| qty / entry_price | Shares held and average cost basis |
| current_price / current_value | Live price and position value |
| unrealized_pl / unrealized_pl_pct | Dollar and percent gain/loss |
| portfolio_weight_pct | What percentage of the portfolio this position represents |
| stop_loss_price | The price at which the stop order will trigger |

You can also print it from Python:
```python
from broker.ledger import save_ledger, print_ledger
save_ledger()   # pull latest from Alpaca and write files
print_ledger()  # formatted table in the terminal
```

---

## How to Change the Portfolio

All tunable parameters live in **`config/portfolio.yaml`** — open it in any text editor. No code changes needed.

### Change value / momentum / quality blend
```yaml
score_blend:
  value_weight:    0.34   # increase for more value tilt
  momentum_weight: 0.33   # increase for more momentum tilt
  quality_weight:  0.33   # increase for more quality tilt (must sum to 1.0)
```

### Disable sector neutralization (rank globally instead of within sector)
```yaml
sector_neutral: false
```

### Run long-only (no short book)
```yaml
enable_short_book: false  # runs 100% long, 0% short
```

### Change rebalance frequency
```yaml
strategy:
  rebalance_frequency: "monthly"   # or "quarterly"
```

### Change how many stocks are in the long/short books
```yaml
strategy:
  long_pct: 0.20    # long the top 20% of ranked stocks
  short_pct: 0.20   # short the bottom 20% of ranked stocks
```

### Adjust the stop-loss
```yaml
risk:
  stop_loss_pct: 0.15    # close position if down 15% from entry
```

### Adjust iron condor selectivity
```yaml
iron_condor:
  min_iv_rank: 50    # raise to 60+ to only trade in the highest IV environments
```

**Note:** The condor scanner automatically excludes any ticker currently held in the 120/20 equity book. A condor bets on range-bound price action, which contradicts holding the same stock as a directional long or short position.

### Change which stocks are in the universe
Edit **`config/universe.yaml`**:
```yaml
preset: "sp500"      # sp500 | sp1500 | nasdaq100 | all_us | custom
```
Always run a backtest after changing parameters to see the historical impact before trading it live.

---

## How to Change Alert Settings

Edit **`config/alerts.yaml`** to control when and what gets emailed:
```yaml
triggers:
  rebalance_signal: true      # set false to disable rebalance emails
  condor_opportunity: true    # set false to disable condor alerts

quiet_hours:
  enabled: true
  start: "22:00"
  end: "07:00"
```

---

## Project Structure

```
config/
  portfolio.yaml     ← strategy parameters, factor weights, risk limits  ← START HERE
  universe.yaml      ← which stocks to include
  alerts.yaml        ← when and what to email

strategies/          ← strategy logic (scoring, ranking, signal generation)
backtesting/         ← backtest engine; results saved as HTML charts
alerts/              ← signal scanner and email sender
broker/
  alpaca.py          ← Alpaca paper trading (orders, rebalance, stop-loss)
  position_manager.py ← daily stop-loss replacement logic
  ledger.py          ← local portfolio ledger (writes data/ledger.csv + data/ledger.json)
dashboard/           ← Streamlit app
utils/
  openbb_client.py   ← price, fundamentals, and options data (live signals)
  simfin_client.py   ← point-in-time fundamentals for backtesting (SimFin)
  metrics.py         ← performance calculations

data/                ← runtime files (gitignored)
  ledger.csv         ← current holdings — open in Excel
  ledger.json        ← same data in JSON for dashboard/code use
  last_signals.json  ← last rebalance signals, used for stop-loss detection
  simfin/            ← cached SimFin datasets (~450MB, auto-refreshes every 7 days)
```

---

## Phases

| Phase | Status | Description |
|---|---|---|
| 1 | Complete | Data pipeline, backtesting, email alerts. Manual trade execution. |
| 2 | Current | Alpaca paper trading. Automated monthly rebalance + daily stop-loss replacement. |
| 3 | Planned | Live trading with real money and additional risk controls. |

---

## Full Documentation

See **[GUIDE.md](GUIDE.md)** for plain-English explanations of every feature, all config options, and common questions.
