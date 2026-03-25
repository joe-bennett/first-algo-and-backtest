"""
Main Streamlit dashboard.

Run with:
    streamlit run dashboard/app.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Algo Portfolio",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Sidebar navigation ----
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", [
    "Portfolio Overview",
    "Backtest",
    "Signals",
    "Research Sandbox",
])

CONFIG_DIR = Path(__file__).parent.parent / "config"


# ============================================================
# PAGE: Portfolio Overview
# ============================================================
if page == "Portfolio Overview":
    st.title("Portfolio Overview")
    st.info("Connect to Alpaca paper trading in Phase 2 to see live positions here.")

    col1, col2, col3 = st.columns(3)
    col1.metric("Strategy", "120/20 Value Momentum")
    col2.metric("Universe", "S&P 500")
    col3.metric("Status", "Paper Trading (Phase 1)")

    st.markdown("---")
    st.subheader("Current Config")
    with open(CONFIG_DIR / "portfolio.yaml") as f:
        cfg = yaml.safe_load(f)
    st.json(cfg)


# ============================================================
# PAGE: Backtest
# ============================================================
elif page == "Backtest":
    st.title("Backtest Runner")
    st.markdown("Adjust parameters, run backtest, compare results.")

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start date", value=pd.Timestamp("2018-01-01"))
        end_date = st.date_input("End date", value=pd.Timestamp("2024-01-01"))
        initial_capital = st.number_input("Initial capital ($)", value=100_000, step=10_000)

    with col2:
        value_weight = st.slider("Value factor weight", 0.0, 1.0, 0.50, 0.05)
        momentum_weight = round(1.0 - value_weight, 2)
        st.write(f"Momentum weight: **{momentum_weight:.0%}**")
        rebalance_freq = st.selectbox("Rebalance frequency", ["monthly", "quarterly"])
        long_pct = st.slider("Long book: top X% of universe", 0.05, 0.40, 0.20, 0.05)
        short_pct = st.slider("Short book: bottom X% of universe", 0.05, 0.40, 0.20, 0.05)

    run_label = st.text_input("Run label (for comparison)", value=f"run_{start_date.year}_{value_weight:.0%}val")

    if st.button("Run Backtest"):
        config_override = {
            "score_blend": {"value_weight": value_weight, "momentum_weight": momentum_weight},
            "strategy": {
                "rebalance_frequency": rebalance_freq,
                "long_pct": long_pct,
                "short_pct": short_pct,
            },
        }

        with st.spinner("Running backtest... (this takes 2-5 minutes on first run)"):
            from backtesting.runner import run_backtest
            from dashboard.charts import equity_curve, drawdown_chart, rolling_sharpe, metrics_table

            results = run_backtest(
                start=str(start_date),
                end=str(end_date),
                initial_capital=initial_capital,
                config_override=config_override,
                label=run_label,
            )

        st.success("Backtest complete!")

        pf = results["portfolio"]
        bench = results["benchmark"]

        st.plotly_chart(
            equity_curve(pf.value(), bench.value(), title=f"Equity Curve — {run_label}"),
            use_container_width=True,
        )

        col_a, col_b = st.columns(2)
        with col_a:
            st.plotly_chart(drawdown_chart(pf.returns()), use_container_width=True)
        with col_b:
            st.plotly_chart(rolling_sharpe(pf.returns()), use_container_width=True)

        st.subheader("Performance Metrics")
        st.plotly_chart(metrics_table(results["metrics"]), use_container_width=True)

        st.session_state.setdefault("backtest_runs", []).append(results)

    if st.session_state.get("backtest_runs"):
        st.markdown("---")
        st.subheader("Run Comparison")
        from backtesting.runner import compare_backtests
        comparison = compare_backtests(st.session_state["backtest_runs"])
        st.dataframe(comparison)


# ============================================================
# PAGE: Signals
# ============================================================
elif page == "Signals":
    st.title("Current Signals")
    st.markdown("Run the scanner to see today's suggested trades.")

    col1, col2 = st.columns(2)
    run_equity = col1.button("Run Equity Scan (120/20)")
    run_condor = col2.button("Run Condor Scan")
    dry_run = st.checkbox("Dry run (don't send SMS)", value=True)

    if run_equity:
        with st.spinner("Scanning S&P 500..."):
            from alerts.engine import run_equity_scan
            signals = run_equity_scan(dry_run=dry_run)

        if not signals.empty:
            from dashboard.charts import factor_scores_bar, exposure_pie
            st.plotly_chart(factor_scores_bar(signals), use_container_width=True)
            st.plotly_chart(exposure_pie(signals), use_container_width=True)

            st.subheader("Long Book")
            longs = signals[signals["action"] == "BUY"].sort_values("composite_score", ascending=False)
            st.dataframe(longs, use_container_width=True)

            st.subheader("Short Book")
            shorts = signals[signals["action"] == "SHORT"].sort_values("composite_score")
            st.dataframe(shorts, use_container_width=True)

    if run_condor:
        with st.spinner("Scanning for condor opportunities..."):
            from alerts.engine import run_condor_scan
            condors = run_condor_scan(dry_run=dry_run)
        if not condors.empty:
            st.subheader("Condor Opportunities")
            st.dataframe(condors, use_container_width=True)
        else:
            st.info("No condor opportunities found today.")


# ============================================================
# PAGE: Research Sandbox
# ============================================================
elif page == "Research Sandbox":
    st.title("Research Sandbox")
    st.markdown(
        "Use this page to tweak strategy parameters and immediately see how signals "
        "would change — **without running a full backtest**. Great for rapid iteration."
    )

    st.subheader("Factor Weight Experiment")
    val_w = st.slider("Value weight", 0.0, 1.0, 0.50, 0.05, key="sandbox_val")
    mom_w = round(1.0 - val_w, 2)
    st.write(f"Momentum weight: **{mom_w:.0%}**")

    n_show = st.slider("Show top N long candidates", 5, 30, 10)

    if st.button("Preview Signals"):
        with st.spinner("Generating signals..."):
            import yaml
            from strategies.value_momentum_120_20 import ValueMomentum12020
            from utils.openbb_client import get_sp500_tickers, get_price_history, get_fundamentals

            with open(CONFIG_DIR / "portfolio.yaml") as f:
                cfg = yaml.safe_load(f)
            cfg["score_blend"]["value_weight"] = val_w
            cfg["score_blend"]["momentum_weight"] = mom_w

            tickers = get_sp500_tickers()
            prices = get_price_history(tickers, start="2022-01-01")
            fundamentals = get_fundamentals(list(prices.columns))

            strategy = ValueMomentum12020(cfg)
            signals = strategy.generate_signals({"prices": prices, "fundamentals": fundamentals})

        if not signals.empty:
            longs = signals[signals["action"] == "BUY"].nlargest(n_show, "composite_score")
            st.dataframe(longs[["ticker", "composite_score", "value_score", "momentum_score",
                                 "pe_ratio", "pb_ratio", "fcf_yield", "weight"]],
                         use_container_width=True)
