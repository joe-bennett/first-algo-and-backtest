"""
Performance metrics used across backtesting and dashboard.
"""

import numpy as np
import pandas as pd


def sharpe_ratio(returns: pd.Series, risk_free: float = 0.05) -> float:
    """Annualized Sharpe ratio."""
    excess = returns - risk_free / 252
    if excess.std() == 0:
        return 0.0
    return float((excess.mean() / excess.std()) * np.sqrt(252))


def sortino_ratio(returns: pd.Series, risk_free: float = 0.05) -> float:
    """Annualized Sortino ratio (penalizes downside volatility only)."""
    excess = returns - risk_free / 252
    downside = excess[excess < 0].std()
    if downside == 0:
        return 0.0
    return float((excess.mean() / downside) * np.sqrt(252))


def max_drawdown(returns: pd.Series) -> float:
    """Maximum peak-to-trough drawdown as a decimal (e.g., -0.25 = -25%)."""
    cum = (1 + returns).cumprod()
    rolling_max = cum.cummax()
    drawdown = (cum - rolling_max) / rolling_max
    return float(drawdown.min())


def calmar_ratio(returns: pd.Series) -> float:
    """Annualized return divided by max drawdown magnitude."""
    ann_return = (1 + returns.mean()) ** 252 - 1
    mdd = abs(max_drawdown(returns))
    if mdd == 0:
        return 0.0
    return float(ann_return / mdd)


def win_rate(returns: pd.Series) -> float:
    """Fraction of positive return days."""
    return float((returns > 0).mean())


def annualized_return(returns: pd.Series) -> float:
    """Compound annualized growth rate."""
    n = len(returns)
    if n == 0:
        return 0.0
    total = (1 + returns).prod()
    return float(total ** (252 / n) - 1)


def annualized_volatility(returns: pd.Series) -> float:
    return float(returns.std() * np.sqrt(252))


def summary(returns: pd.Series, risk_free: float = 0.05) -> dict:
    """Full performance summary as a dict."""
    return {
        "annualized_return": annualized_return(returns),
        "annualized_volatility": annualized_volatility(returns),
        "sharpe_ratio": sharpe_ratio(returns, risk_free),
        "sortino_ratio": sortino_ratio(returns, risk_free),
        "calmar_ratio": calmar_ratio(returns),
        "max_drawdown": max_drawdown(returns),
        "win_rate": win_rate(returns),
    }
