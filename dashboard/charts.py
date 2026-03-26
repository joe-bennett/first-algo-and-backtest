"""
Reusable chart components for the Streamlit dashboard.
All charts return Plotly figures.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots


def equity_curve(portfolio_values: pd.Series, benchmark_values: pd.Series | None = None,
                 title: str = "Portfolio Equity Curve") -> go.Figure:
    """Normalized equity curve (starts at 1.0). Optionally overlays benchmark."""
    fig = go.Figure()

    norm = portfolio_values / portfolio_values.iloc[0]
    fig.add_trace(go.Scatter(x=norm.index, y=norm.values, name="Strategy",
                             line=dict(color="#2196F3", width=2)))

    if benchmark_values is not None:
        bnorm = benchmark_values / benchmark_values.iloc[0]
        fig.add_trace(go.Scatter(x=bnorm.index, y=bnorm.values, name="S&P 500 (benchmark)",
                                 line=dict(color="#9E9E9E", width=1.5, dash="dash")))

    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Growth of $1",
                      hovermode="x unified", template="plotly_dark")
    return fig


def drawdown_chart(returns: pd.Series, title: str = "Drawdown") -> go.Figure:
    cum = (1 + returns).cumprod()
    rolling_max = cum.cummax()
    drawdown = (cum - rolling_max) / rolling_max

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=drawdown.index, y=drawdown.values * 100,
                             fill="tozeroy", fillcolor="rgba(244,67,54,0.3)",
                             line=dict(color="#F44336"), name="Drawdown"))
    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Drawdown (%)",
                      template="plotly_dark")
    return fig


def rolling_sharpe(returns: pd.Series, window: int = 63,
                   title: str = "Rolling Sharpe Ratio (63-day)") -> go.Figure:
    roll_mean = returns.rolling(window).mean()
    roll_std = returns.rolling(window).std()
    roll_sharpe = (roll_mean / roll_std) * np.sqrt(252)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=roll_sharpe.index, y=roll_sharpe.values,
                             line=dict(color="#4CAF50"), name="Rolling Sharpe"))
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.add_hline(y=1, line_dash="dot", line_color="#2196F3", annotation_text="Sharpe=1")
    fig.update_layout(title=title, xaxis_title="Date", yaxis_title="Sharpe",
                      template="plotly_dark")
    return fig


def factor_scores_bar(signals: pd.DataFrame, top_n: int = 20,
                      title: str = "Top Long Positions — Composite Score") -> go.Figure:
    longs = signals[signals["action"] == "BUY"].nlargest(top_n, "composite_score")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=longs["ticker"], y=longs["value_score"],
                         name="Value", marker_color="#2196F3"))
    fig.add_trace(go.Bar(x=longs["ticker"], y=longs["momentum_score"],
                         name="Momentum", marker_color="#4CAF50"))
    fig.update_layout(title=title, barmode="group", xaxis_title="Ticker",
                      yaxis_title="Percentile Rank (0-1)", template="plotly_dark")
    return fig


def exposure_pie(signals: pd.DataFrame) -> go.Figure:
    """Long vs short vs cash exposure breakdown."""
    long_exp = signals[signals["action"] == "BUY"]["weight"].sum() * 100
    short_exp = abs(signals[signals["action"] == "SHORT"]["weight"].sum()) * 100
    cash = max(0, 100 - long_exp + short_exp)

    fig = go.Figure(go.Pie(
        labels=["Long", "Short", "Net Cash"],
        values=[long_exp, short_exp, cash],
        hole=0.4,
        marker_colors=["#4CAF50", "#F44336", "#9E9E9E"],
    ))
    fig.update_layout(title="Portfolio Exposure", template="plotly_dark")
    return fig


def holdings_weight_bar(positions: list[dict]) -> go.Figure:
    """Horizontal bar chart of portfolio weight by position."""
    df = pd.DataFrame(positions)
    if df.empty:
        return go.Figure()
    df = df.sort_values("portfolio_weight_pct", ascending=True)
    colors = ["#F44336" if s == "short" else "#4CAF50" for s in df["side"]]
    fig = go.Figure(go.Bar(
        x=df["portfolio_weight_pct"],
        y=df["ticker"],
        orientation="h",
        marker_color=colors,
        text=df["portfolio_weight_pct"].map("{:.1f}%".format),
        textposition="outside",
    ))
    fig.update_layout(
        title="Portfolio Weight by Position",
        xaxis_title="Weight (%)",
        template="plotly_dark",
        height=max(300, len(df) * 22),
        margin=dict(l=60, r=60, t=40, b=40),
    )
    return fig


def holdings_pl_bar(positions: list[dict]) -> go.Figure:
    """Bar chart of unrealized P&L by position."""
    df = pd.DataFrame(positions)
    if df.empty:
        return go.Figure()
    df = df.sort_values("unrealized_pl", ascending=True)
    colors = ["#F44336" if v < 0 else "#4CAF50" for v in df["unrealized_pl"]]
    fig = go.Figure(go.Bar(
        x=df["unrealized_pl"],
        y=df["ticker"],
        orientation="h",
        marker_color=colors,
        text=df["unrealized_pl"].map("${:+,.0f}".format),
        textposition="outside",
    ))
    fig.update_layout(
        title="Unrealized P&L by Position",
        xaxis_title="Unrealized P&L ($)",
        template="plotly_dark",
        height=max(300, len(df) * 22),
        margin=dict(l=60, r=60, t=40, b=40),
    )
    return fig


def metrics_table(metrics_dict: dict) -> go.Figure:
    """Render a clean metrics comparison table."""
    strat = metrics_dict.get("strategy", {})
    bench = metrics_dict.get("benchmark", {})

    labels = {
        "annualized_return": "Ann. Return",
        "annualized_volatility": "Ann. Volatility",
        "sharpe_ratio": "Sharpe Ratio",
        "sortino_ratio": "Sortino Ratio",
        "calmar_ratio": "Calmar Ratio",
        "max_drawdown": "Max Drawdown",
        "win_rate": "Win Rate",
    }
    pct_keys = {"annualized_return", "annualized_volatility", "max_drawdown", "win_rate"}

    rows = []
    for k, label in labels.items():
        sv = strat.get(k, 0)
        bv = bench.get(k, 0)
        fmt = "{:.1%}" if k in pct_keys else "{:.2f}"
        rows.append([label, fmt.format(sv), fmt.format(bv)])

    fig = go.Figure(go.Table(
        header=dict(values=["Metric", "Strategy", "Benchmark (SPY)"],
                    fill_color="#1E1E1E", font=dict(color="white")),
        cells=dict(values=list(zip(*rows)),
                   fill_color=[["#2C2C2C"] * len(rows)],
                   font=dict(color="white")),
    ))
    fig.update_layout(template="plotly_dark", margin=dict(l=0, r=0, t=0, b=0))
    return fig
