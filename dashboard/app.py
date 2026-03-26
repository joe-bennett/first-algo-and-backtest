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

    # --- Connect to Alpaca ---
    try:
        from broker.alpaca import get_account
        from broker.ledger import save_ledger
        import json
        from pathlib import Path

        col_refresh, _ = st.columns([1, 5])
        if col_refresh.button("Refresh from Alpaca"):
            with st.spinner("Pulling latest positions from Alpaca..."):
                save_ledger()
            st.success("Ledger updated.")

        # Load ledger (saved by save_ledger or from last run)
        ledger_path = Path(__file__).parent.parent / "data" / "ledger.json"
        if not ledger_path.exists():
            with st.spinner("Loading positions from Alpaca..."):
                save_ledger()

        with open(ledger_path, encoding="utf-8") as f:
            ledger = json.load(f)

        summary = ledger["summary"]
        positions = ledger["positions"]

        # --- Account summary metrics ---
        st.markdown("---")
        acct = get_account()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Portfolio Value",  f"${summary['portfolio_value']:,.2f}")
        c2.metric("Cash",             f"${summary['cash']:,.2f}")
        c3.metric("Buying Power",     f"${acct['buying_power']:,.2f}")
        pl = summary["total_unrealized_pl"]
        pl_pct = summary["total_unrealized_pl_pct"]
        c4.metric("Unrealized P&L",   f"${pl:+,.2f}", delta=f"{pl_pct:+.2f}%")

        c5, c6, c7 = st.columns(3)
        longs  = [p for p in positions if p["side"] == "long"]
        shorts = [p for p in positions if p["side"] == "short"]
        c5.metric("Total Positions", summary["position_count"])
        c6.metric("Longs",  len(longs))
        c7.metric("Shorts", len(shorts))
        st.caption(f"Last updated: {summary['last_updated']}")

        # --- Charts ---
        if positions:
            from dashboard.charts import holdings_weight_bar, holdings_pl_bar
            st.markdown("---")
            ch1, ch2 = st.columns(2)
            with ch1:
                st.plotly_chart(holdings_weight_bar(positions), use_container_width=True)
            with ch2:
                st.plotly_chart(holdings_pl_bar(positions), use_container_width=True)

        # --- Positions tables ---
        st.markdown("---")
        display_cols = ["ticker", "side", "qty", "entry_price", "current_price",
                        "current_value", "unrealized_pl", "unrealized_pl_pct",
                        "portfolio_weight_pct", "stop_loss_price"]

        if longs:
            st.subheader(f"Long Book ({len(longs)} positions)")
            df_longs = pd.DataFrame(longs)[display_cols].set_index("ticker")
            df_longs["unrealized_pl_pct"] = df_longs["unrealized_pl_pct"].map("{:+.2f}%".format)
            df_longs["portfolio_weight_pct"] = df_longs["portfolio_weight_pct"].map("{:.2f}%".format)
            st.dataframe(df_longs, use_container_width=True)

        if shorts:
            st.subheader(f"Short Book ({len(shorts)} positions)")
            df_shorts = pd.DataFrame(shorts)[display_cols].set_index("ticker")
            df_shorts["unrealized_pl_pct"] = df_shorts["unrealized_pl_pct"].map("{:+.2f}%".format)
            df_shorts["portfolio_weight_pct"] = df_shorts["portfolio_weight_pct"].map("{:.2f}%".format)
            st.dataframe(df_shorts, use_container_width=True)

        if not positions:
            st.info("No open positions in Alpaca account.")

    except Exception as e:
        st.error(f"Could not connect to Alpaca: {e}")
        st.markdown("Check that `ALPACA_API_KEY` and `ALPACA_SECRET_KEY` are set in your `.env` file.")

        st.markdown("---")
        st.subheader("Current Config")
        with open(CONFIG_DIR / "portfolio.yaml", encoding="utf-8") as f:
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
        start_date = st.date_input("Start date", value=pd.Timestamp("2020-01-01"))
        end_date = st.date_input("End date", value=pd.Timestamp.today().normalize())
        initial_capital = st.number_input("Initial capital ($)", value=100_000, step=10_000)

    with col2:
        value_weight    = st.slider("Value factor weight",    0.0, 1.0, 0.34, 0.01)
        momentum_weight = st.slider("Momentum factor weight", 0.0, 1.0, 0.33, 0.01)
        quality_weight  = round(max(0.0, 1.0 - value_weight - momentum_weight), 2)
        st.write(f"Quality weight (auto): **{quality_weight:.0%}**")
        rebalance_freq  = st.selectbox("Rebalance frequency", ["monthly", "quarterly"])
        long_pct  = st.slider("Long book: top X% of universe",   0.05, 0.40, 0.20, 0.05)
        short_pct = st.slider("Short book: bottom X% of universe", 0.05, 0.40, 0.20, 0.05)
        enable_short   = st.checkbox("Enable short book", value=True)
        sector_neutral = st.checkbox("Sector neutralization", value=True)

    run_label = st.text_input(
        "Run label (for comparison)",
        value=f"run_{start_date.year}_{value_weight:.0%}val_{'sn' if sector_neutral else 'global'}",
    )

    if start_date < pd.Timestamp("2020-01-01").date():
        st.warning(
            "SimFin free plan provides quarterly fundamentals from **2020 onward**. "
            "Before 2020 the value and quality factors have no data — the strategy runs as "
            "pure momentum for those years, skewing results. Recommend starting from 2020-01-01."
        )

    if st.button("Run Backtest"):
        config_override = {
            "score_blend": {
                "value_weight":    value_weight,
                "momentum_weight": momentum_weight,
                "quality_weight":  quality_weight,
            },
            "strategy": {
                "rebalance_frequency": rebalance_freq,
                "long_pct":  long_pct,
                "short_pct": short_pct,
            },
            "enable_short_book": enable_short,
            "sector_neutral":    sector_neutral,
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

        def _portfolio_value(p):
            v = p.value()
            return v.iloc[:, 0] if isinstance(v, pd.DataFrame) else v

        pf_value = _portfolio_value(pf)
        bench_value = _portfolio_value(bench)
        pf_returns = pf_value.pct_change().dropna()

        st.plotly_chart(
            equity_curve(pf_value, bench_value, title=f"Equity Curve — {run_label}"),
            use_container_width=True,
        )

        col_a, col_b = st.columns(2)
        with col_a:
            st.plotly_chart(drawdown_chart(pf_returns), use_container_width=True)
        with col_b:
            st.plotly_chart(rolling_sharpe(pf_returns), use_container_width=True)

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
    dry_run = st.checkbox("Dry run (don't send email)", value=True)

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
    sb_col1, sb_col2, sb_col3 = st.columns(3)
    val_w = sb_col1.slider("Value weight",    0.0, 1.0, 0.34, 0.01, key="sandbox_val")
    mom_w = sb_col2.slider("Momentum weight", 0.0, 1.0, 0.33, 0.01, key="sandbox_mom")
    qual_w = round(max(0.0, 1.0 - val_w - mom_w), 2)
    sb_col3.metric("Quality weight (auto)", f"{qual_w:.0%}")

    sb_col4, sb_col5, sb_col6 = st.columns(3)
    n_show         = sb_col4.slider("Show top N candidates", 5, 30, 10)
    enable_short   = sb_col5.checkbox("Enable short book", value=True, key="sandbox_short")
    sector_neutral = sb_col6.checkbox("Sector neutralization", value=True, key="sandbox_sn")

    if st.button("Preview Signals"):
        with st.spinner("Generating signals..."):
            import yaml
            from strategies.value_momentum_120_20 import ValueMomentum12020
            from utils.openbb_client import get_price_history, get_sp500_members_at, get_sector_map
            from utils.simfin_client import build_fundamentals_panel, get_pit_fundamentals

            with open(CONFIG_DIR / "portfolio.yaml", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            cfg["score_blend"]["value_weight"]    = val_w
            cfg["score_blend"]["momentum_weight"] = mom_w
            cfg["score_blend"]["quality_weight"]  = qual_w
            cfg["enable_short_book"] = enable_short
            cfg["sector_neutral"]    = sector_neutral

            # Use today's S&P 500 members for current signal preview
            today = pd.Timestamp.today().normalize()
            tickers = get_sp500_members_at(today)
            prices = get_price_history(tickers, start="2022-01-01")
            idx = pd.to_datetime(prices.index)
            if idx.tz is not None:
                idx = idx.tz_convert(None)
            prices.index = idx
            tickers = list(prices.columns)

            # SimFin for fundamentals — same source as backtester, point-in-time accurate
            pit_panel   = build_fundamentals_panel()
            fundamentals = get_pit_fundamentals(pit_panel, today, tickers)

            # Sector map for sector neutralization
            sectors = get_sector_map() if sector_neutral else {}

            strategy = ValueMomentum12020(cfg)
            signals  = strategy.generate_signals({
                "prices": prices,
                "fundamentals": fundamentals,
                "sectors": sectors,
            })

        if not signals.empty:
            display_cols = ["ticker", "sector", "composite_score", "value_score",
                            "momentum_score", "quality_score",
                            "pe_ratio", "pb_ratio", "fcf_yield", "roe", "net_margin", "weight"]
            # Only show columns that actually exist
            display_cols = [c for c in display_cols if c in signals.columns]

            longs  = signals[signals["action"] == "BUY"].nlargest(n_show, "composite_score")
            shorts = signals[signals["action"] == "SHORT"].nsmallest(n_show, "composite_score")

            st.subheader(f"Top {n_show} Long Candidates")
            st.dataframe(longs[display_cols], use_container_width=True)

            if enable_short:
                st.subheader(f"Top {n_show} Short Candidates")
                st.dataframe(shorts[display_cols], use_container_width=True)

            st.caption(
                "Fundamentals sourced from SimFin (most recent quarterly filing per ticker). "
                "Sector data from Wikipedia GICS classifications."
            )
