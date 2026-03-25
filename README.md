# Algo Trading Portfolio

An automated trading system built around two strategies:

- **120/20 Value-Momentum** — ranks S&P 500 stocks by a blend of value and momentum factors, goes long the top-ranked and short the bottom-ranked, rebalances monthly
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
```
To generate a Gmail App Password: Google Account → Security → 2-Step Verification → App passwords.

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

---

## How to Change the Portfolio

All tunable parameters live in **`config/portfolio.yaml`** — open it in any text editor. No code changes needed.

### Change value vs. momentum blend
```yaml
score_blend:
  value_weight: 0.50      # increase for more value tilt
  momentum_weight: 0.50   # increase for more momentum tilt
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
broker/              ← Alpaca paper trading integration
dashboard/           ← Streamlit app
utils/               ← data fetching and performance metrics
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
