"""
Quick sanity check — run this first after installing dependencies.
Tests data fetching and signal generation without sending any SMS.

Run: python quickstart.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

def check_step(name):
    print(f"\n{'='*50}")
    print(f"  {name}")
    print('='*50)

check_step("1. Fetching universe (uses preset in config/universe.yaml)")
from utils.openbb_client import get_universe_tickers, get_sp500_tickers
# Use S&P 500 for the quick sanity check (fast); real runs use whatever preset is configured
tickers = get_sp500_tickers()
print(f"  Found {len(tickers)} tickers. First 5: {tickers[:5]}")
print(f"  (Full universe via get_universe_tickers() uses the preset in config/universe.yaml)")

check_step("2. Fetching price history (10 tickers, 1 year)")
from utils.openbb_client import get_price_history
sample = tickers[:10]
prices = get_price_history(sample, start="2023-01-01")
print(f"  Price data shape: {prices.shape}")
print(f"  Date range: {prices.index[0]} to {prices.index[-1]}")

check_step("3. Fetching fundamentals (10 tickers)")
from utils.openbb_client import get_fundamentals
fundamentals = get_fundamentals(sample)
print(f"  Fundamentals shape: {fundamentals.shape}")
print(f"  Columns: {list(fundamentals.columns)}")

check_step("4. Generating 120/20 signals (sample universe)")
import yaml
from strategies.value_momentum_120_20 import ValueMomentum12020

# Use larger sample for signal generation
prices_full = get_price_history(tickers[:50], start="2022-01-01")
fundamentals_full = get_fundamentals(list(prices_full.columns))

with open("config/portfolio.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

strategy = ValueMomentum12020(cfg)
signals = strategy.generate_signals({"prices": prices_full, "fundamentals": fundamentals_full})
print(f"  Signals generated: {len(signals)} ({len(signals[signals.action=='BUY'])} long, {len(signals[signals.action=='SHORT'])} short)")

print("\n" + "="*50)
print("  Sample signal description:")
print("="*50)
if not signals.empty:
    row = signals[signals["action"] == "BUY"].iloc[0]
    print(strategy.describe_signal(row))

check_step("5. Performance metrics")
import pandas as pd
import numpy as np
from utils.metrics import summary
fake_returns = pd.Series(np.random.normal(0.0005, 0.01, 500))
m = summary(fake_returns)
for k, v in m.items():
    print(f"  {k}: {v:.3f}")

print("\n" + "="*50)
print("  ALL CHECKS PASSED")
print("  Next step: run the dashboard with:")
print("    streamlit run dashboard/app.py")
print("="*50 + "\n")
