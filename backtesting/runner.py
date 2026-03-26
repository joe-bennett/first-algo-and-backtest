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
from utils.openbb_client import get_universe_tickers, get_price_history, get_index_members_at, get_sector_map
from utils.simfin_client import build_fundamentals_panel, get_pit_fundamentals
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

    print(f"Running backtest: {start} to {end}")
    blend = cfg["score_blend"]
    print(f"Config: rebalance={cfg['strategy']['rebalance_frequency']}, "
          f"value/momentum/quality blend="
          f"{blend['value_weight']:.0%}/{blend['momentum_weight']:.0%}/{blend.get('quality_weight', 0):.0%}, "
          f"short_book={'on' if cfg.get('enable_short_book', True) else 'off'}, "
          f"sector_neutral={'on' if cfg.get('sector_neutral', False) else 'off'}")

    # --- Determine universe preset from config ---
    with open(CONFIG_DIR / "universe.yaml", encoding="utf-8") as _f:
        _ucfg = yaml.safe_load(_f)
    universe_preset = _ucfg.get("preset", "sp500")
    # Only sp500 and sp1500 are supported for point-in-time backtesting
    if universe_preset not in ("sp500", "sp1500"):
        print(f"Warning: universe preset '{universe_preset}' is not supported for backtesting. "
              f"Falling back to 'sp500'.")
        universe_preset = "sp500"

    # --- Fetch data ---
    # Build the union of all index members across the backtest window so we have
    # price history for every stock that was ever in the index during this period.
    print(f"Building point-in-time {universe_preset.upper()} member universe...")
    if universe_preset == "sp1500":
        print("  Note: S&P 500 component uses accurate historical data; "
              "MidCap 400 + SmallCap 600 use current membership (modest survivorship bias).")
    start_ts = pd.Timestamp(start)
    end_ts   = pd.Timestamp(end)
    # Sample membership quarterly across the window to build the full union
    sample_dates = pd.date_range(start=start_ts, end=end_ts, freq="QS")
    all_members: set[str] = set()
    for d in sample_dates:
        all_members.update(get_index_members_at(d, universe_preset))
    tickers = sorted(all_members)
    print(f"Union of {universe_preset.upper()} members over backtest window: {len(tickers)} tickers")

    print(f"Fetching prices for {len(tickers)} tickers...")
    prices = get_price_history(tickers, start=start, end=end)
    # Normalise index to tz-naive DatetimeIndex and drop any duplicate dates
    idx = pd.to_datetime(prices.index)
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    prices.index = idx
    prices = prices[~prices.index.duplicated(keep="last")]
    prices = prices.dropna(axis=1, thresh=int(len(prices) * 0.8))  # drop tickers with >20% gaps
    tickers = list(prices.columns)

    # --- Build point-in-time fundamentals panel (SimFin) ---
    print("Building point-in-time fundamentals panel (SimFin)...")
    pit_panel = build_fundamentals_panel()

    # --- Sector map for sector neutralization ---
    sector_neutral = cfg.get("sector_neutral", False)
    sectors: dict = {}
    if sector_neutral:
        print("Fetching sector map for sector neutralization...")
        sectors = get_sector_map()
        print(f"  Sectors loaded for {len(sectors)} tickers.")

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
    # NaN = hold (don't trade). 0 = close position. Non-zero = target weight.
    size_matrix = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    strategy = ValueMomentum12020(cfg)

    for rdate in rebalance_dates:
        hist = prices.loc[:rdate]
        if len(hist) < 252:
            continue
        try:
            # Only allow stocks that were actually in the index on this date
            pit_members = set(get_index_members_at(rdate, universe_preset))
            eligible = [t for t in tickers if t in pit_members]
            if not eligible:
                continue

            pit_fundamentals = get_pit_fundamentals(pit_panel, rdate, eligible)
            signals = strategy.generate_signals({
                "prices": hist[eligible],
                "fundamentals": pit_fundamentals,
                "sectors": sectors,
            })
            size_matrix.loc[rdate] = 0.0
            for _, row in signals.iterrows():
                if row["ticker"] in size_matrix.columns:
                    # weight as fraction of portfolio (positive = long, negative = short)
                    size_matrix.loc[rdate, row["ticker"]] = row["weight"]
        except Exception as e:
            print(f"  Skipped {rdate.date()}: {e}")

    # --- VectorBT Portfolio ---
    # Reindex size_matrix to exactly match prices (guards against any row insertion during loop)
    size_matrix = size_matrix.reindex(index=prices.index, columns=prices.columns, fill_value=np.nan)

    # group_by=True + cash_sharing=True treats all columns as one shared portfolio,
    # not N independent $100k portfolios. This is required for correct multi-asset simulation.
    portfolio = vbt.Portfolio.from_orders(
        close=prices,
        size=size_matrix,
        size_type="targetpercent",
        init_cash=initial_capital,
        fees=0.001,          # 10 bps per trade
        slippage=0.0005,     # 5 bps slippage
        freq="D",
        group_by=True,
        cash_sharing=True,
    )

    # --- Benchmark: SPY buy-and-hold ---
    # Fetch SPY separately — it may not be in the strategy universe
    if "SPY" in prices.columns:
        spy_prices = prices["SPY"]
    else:
        spy_raw = get_price_history(["SPY"], start=start, end=end)
        spy_raw.index = pd.to_datetime(spy_raw.index)
        if spy_raw.index.tz is not None:
            spy_raw.index = spy_raw.index.tz_convert(None)
        spy_prices = spy_raw["SPY"].reindex(prices.index).ffill()
    benchmark = vbt.Portfolio.from_holding(spy_prices, init_cash=initial_capital)

    # --- Metrics ---
    # With group_by+cash_sharing, value() returns a single Series for the whole portfolio
    strat_value = portfolio.value()
    if isinstance(strat_value, pd.DataFrame):
        strat_value = strat_value.iloc[:, 0]
    strat_returns = strat_value.pct_change().dropna()

    bench_value = benchmark.value()
    if isinstance(bench_value, pd.DataFrame):
        bench_value = bench_value.iloc[:, 0]
    bench_returns = bench_value.pct_change().dropna()

    metrics = {
        "strategy": perf.summary(strat_returns),
        "benchmark": perf.summary(bench_returns),
    }

    # --- Save HTML report ---
    if save:
        import plotly.graph_objects as go
        html_path = RESULTS_DIR / f"{label}.html"
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=strat_value.index, y=strat_value.values,
                                 name="Strategy", line=dict(color="#2196F3")))
        fig.add_trace(go.Scatter(x=bench_value.index, y=bench_value.values,
                                 name="Benchmark (SPY)", line=dict(color="#9E9E9E", dash="dash")))
        fig.update_layout(title=f"Equity Curve — {label}", xaxis_title="Date",
                          yaxis_title="Portfolio Value ($)", template="plotly_dark")
        fig.write_html(str(html_path))
        print(f"Report saved: {html_path}")

    print("\n=== RESULTS ===")
    print(f"Strategy  — Return: {metrics['strategy']['annualized_return']:.1%}  "
          f"Sharpe: {metrics['strategy']['sharpe_ratio']:.2f}  "
          f"MaxDD: {metrics['strategy']['max_drawdown']:.1%}")
    print(f"Benchmark — Return: {metrics['benchmark']['annualized_return']:.1%}  "
          f"Sharpe: {metrics['benchmark']['sharpe_ratio']:.2f}  "
          f"MaxDD: {metrics['benchmark']['max_drawdown']:.1%}")

    # Get final signals for reference (use most recent PIT fundamentals available)
    final_fundamentals = get_pit_fundamentals(pit_panel, prices.index[-1], tickers)
    final_signals = strategy.generate_signals({
        "prices": prices,
        "fundamentals": final_fundamentals,
        "sectors": sectors,
    })

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
