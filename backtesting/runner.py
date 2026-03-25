"""
Backtest runner using VectorBT.

Usage:
    from backtesting.runner import run_backtest
    results = run_backtest(start="2018-01-01", end="2024-01-01")
    results["portfolio"].plot()  # interactive Plotly chart
"""

import yaml
import numpy as np
import pandas as pd
import vectorbt as vbt
from pathlib import Path
from datetime import datetime

from strategies.value_momentum_120_20 import ValueMomentum12020
from utils.openbb_client import get_universe_tickers, get_price_history, get_fundamentals
from utils import metrics as perf

CONFIG_DIR = Path(__file__).parent.parent / "config"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def load_config(config_override: dict | None = None) -> dict:
    with open(CONFIG_DIR / "portfolio.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if config_override:
        cfg = _deep_merge(cfg, config_override)
    return cfg


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for k, v in override.items():
        if isinstance(v, dict) and k in result:
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def run_backtest(
    start: str = "2018-01-01",
    end: str | None = None,
    initial_capital: float = 100_000,
    config_override: dict | None = None,
    save: bool = True,
    label: str | None = None,
) -> dict:
    """
    Run a full backtest of the 120/20 value-momentum strategy.

    Parameters
    ----------
    start           : backtest start date (YYYY-MM-DD)
    end             : backtest end date (defaults to today)
    initial_capital : starting portfolio value
    config_override : dict of config values to override (for experimentation)
    save            : save HTML report to backtesting/results/
    label           : name for this backtest run (used in saved filename)

    Returns
    -------
    dict with keys:
        "portfolio"  : vbt.Portfolio object (has .plot(), .stats(), etc.)
        "signals"    : pd.DataFrame of final period signals
        "metrics"    : dict of performance metrics
        "config"     : the config used for this run
    """
    end = end or datetime.today().strftime("%Y-%m-%d")
    cfg = load_config(config_override)
    label = label or f"backtest_{start[:4]}_{end[:4]}"

    print(f"Running backtest: {start} → {end}")
    print(f"Config: rebalance={cfg['strategy']['rebalance_frequency']}, "
          f"value/momentum blend={cfg['score_blend']['value_weight']:.0%}/{cfg['score_blend']['momentum_weight']:.0%}")

    # --- Fetch data ---
    tickers = get_universe_tickers()
    print(f"Fetching prices for {len(tickers)} tickers...")
    prices = get_price_history(tickers, start=start, end=end)
    prices = prices.dropna(axis=1, thresh=int(len(prices) * 0.8))  # drop tickers with >20% gaps
    tickers = list(prices.columns)

    print("Fetching fundamentals (current snapshot — limitation of free data)...")
    fundamentals = get_fundamentals(tickers)

    # --- Generate rebalance dates ---
    freq = cfg["strategy"]["rebalance_frequency"]
    if freq == "monthly":
        rebalance_dates = prices.resample("MS").first().index
    elif freq == "quarterly":
        rebalance_dates = prices.resample("QS").first().index
    else:
        raise ValueError(f"Unknown rebalance_frequency: {freq}")

    rebalance_dates = [d for d in rebalance_dates if d >= prices.index[252]]

    # --- Build signal matrices ---
    # VectorBT uses size matrices: positive = long, negative = short, 0 = flat
    size_matrix = pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    strategy = ValueMomentum12020(cfg)

    for rdate in rebalance_dates:
        hist = prices.loc[:rdate]
        if len(hist) < 252:
            continue
        try:
            signals = strategy.generate_signals({
                "prices": hist,
                "fundamentals": fundamentals,
            })
            size_matrix.loc[rdate] = 0.0
            for _, row in signals.iterrows():
                if row["ticker"] in size_matrix.columns:
                    # weight as fraction of portfolio (positive = long, negative = short)
                    size_matrix.loc[rdate, row["ticker"]] = row["weight"]
        except Exception as e:
            print(f"  Skipped {rdate.date()}: {e}")

    # --- VectorBT Portfolio ---
    # Use from_orders with target percent sizing
    portfolio = vbt.Portfolio.from_orders(
        close=prices,
        size=size_matrix,
        size_type="targetpercent",
        init_cash=initial_capital,
        fees=0.001,          # 10 bps per trade
        slippage=0.0005,     # 5 bps slippage
        freq="D",
    )

    # --- Benchmark: SPY buy-and-hold ---
    spy_prices = prices["SPY"] if "SPY" in prices.columns else prices.iloc[:, 0]
    benchmark = vbt.Portfolio.from_holding(spy_prices, init_cash=initial_capital)

    # --- Metrics ---
    strat_returns = portfolio.returns()
    bench_returns = benchmark.returns()

    metrics = {
        "strategy": perf.summary(strat_returns),
        "benchmark": perf.summary(bench_returns),
    }

    # --- Save HTML report ---
    if save:
        html_path = RESULTS_DIR / f"{label}.html"
        portfolio.plot().write_html(str(html_path))
        print(f"Report saved: {html_path}")

    print("\n=== RESULTS ===")
    print(f"Strategy  — Return: {metrics['strategy']['annualized_return']:.1%}  "
          f"Sharpe: {metrics['strategy']['sharpe_ratio']:.2f}  "
          f"MaxDD: {metrics['strategy']['max_drawdown']:.1%}")
    print(f"Benchmark — Return: {metrics['benchmark']['annualized_return']:.1%}  "
          f"Sharpe: {metrics['benchmark']['sharpe_ratio']:.2f}  "
          f"MaxDD: {metrics['benchmark']['max_drawdown']:.1%}")

    # Get final signals for reference
    final_signals = strategy.generate_signals({"prices": prices, "fundamentals": fundamentals})

    return {
        "portfolio": portfolio,
        "benchmark": benchmark,
        "signals": final_signals,
        "metrics": metrics,
        "config": cfg,
        "label": label,
    }


def compare_backtests(runs: list[dict]) -> pd.DataFrame:
    """
    Side-by-side comparison of multiple backtest runs.
    Pass a list of result dicts from run_backtest().
    """
    rows = []
    for r in runs:
        row = {"label": r["label"]}
        row.update({f"strat_{k}": v for k, v in r["metrics"]["strategy"].items()})
        rows.append(row)
    df = pd.DataFrame(rows).set_index("label")
    pct_cols = ["strat_annualized_return", "strat_annualized_volatility",
                "strat_max_drawdown", "strat_win_rate"]
    for col in pct_cols:
        if col in df.columns:
            df[col] = df[col].map("{:.1%}".format)
    return df
