"""
Alert engine — orchestrates signal generation and fires SMS when conditions are met.

Run this on a schedule (e.g., daily after market close) or manually.
"""

import yaml
import pandas as pd
from datetime import datetime
from pathlib import Path

from strategies.value_momentum_120_20 import ValueMomentum12020
from strategies.iron_condor import IronCondorScanner
from alerts.notifier import send_alert
from utils.openbb_client import get_universe_tickers, get_price_history, get_fundamentals

CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_config() -> dict:
    with open(CONFIG_DIR / "portfolio.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_alerts_config() -> dict:
    with open(CONFIG_DIR / "alerts.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _is_quiet_hours(alerts_cfg: dict) -> bool:
    """Return True if current time falls in the configured quiet window."""
    qh = alerts_cfg.get("quiet_hours", {})
    if not qh.get("enabled", False):
        return False
    now = datetime.now().strftime("%H:%M")
    start = qh["start"]
    end = qh["end"]
    if start <= end:
        return start <= now <= end
    else:  # wraps midnight
        return now >= start or now <= end


def run_equity_scan(dry_run: bool = False) -> pd.DataFrame:
    """
    Run the 120/20 value-momentum scan and send SMS for the top/bottom signals.
    dry_run=True prints the messages without sending SMS.
    """
    cfg = load_config()
    alerts_cfg = load_alerts_config()

    print("Fetching universe...")
    tickers = get_universe_tickers()

    print(f"Fetching price history for {len(tickers)} tickers...")
    prices = get_price_history(tickers, start="2022-01-01")

    print("Fetching fundamentals...")
    fundamentals = get_fundamentals(tickers)

    strategy = ValueMomentum12020(cfg)
    signals = strategy.generate_signals({"prices": prices, "fundamentals": fundamentals})

    if signals.empty:
        print("No signals generated.")
        return signals

    # Build SMS message
    date_str = datetime.today().strftime("%Y-%m-%d")
    lines = [f"=== PORTFOLIO SIGNAL: {date_str} ===\n"]

    longs = signals[signals["action"] == "BUY"].head(5)
    shorts = signals[signals["action"] == "SHORT"].head(5)

    lines.append("--- TOP 5 LONGS ---")
    for _, row in longs.iterrows():
        lines.append(strategy.describe_signal(row))
        lines.append("")

    lines.append("--- TOP 5 SHORTS ---")
    for _, row in shorts.iterrows():
        lines.append(strategy.describe_signal(row))
        lines.append("")

    message = "\n".join(lines)

    if dry_run:
        print("\n[DRY RUN — email not sent]\n")
        print(message)
    elif _is_quiet_hours(alerts_cfg):
        print("Quiet hours active — email suppressed.")
    else:
        send_alert(f"Portfolio Signal: {date_str}", message)
        print("Email alert sent.")

    return signals


def run_condor_scan(tickers: list[str] | None = None, dry_run: bool = False) -> pd.DataFrame:
    """
    Screen for iron condor opportunities and send email if found.
    Contract count is sized to 5% of portfolio per condor (configurable in portfolio.yaml).
    """
    cfg = load_config()
    alerts_cfg = load_alerts_config()

    # Fetch live portfolio value from Alpaca; fall back to config default
    try:
        from broker.alpaca import get_account
        portfolio_value = get_account()["portfolio_value"]
        print(f"Portfolio value (Alpaca): ${portfolio_value:,.2f}")
    except Exception:
        portfolio_value = cfg["iron_condor"].get("default_portfolio_value", 100000)
        print(f"Alpaca unavailable — using default portfolio value: ${portfolio_value:,.2f}")

    if tickers is None:
        # Screen liquid large-caps only for condors (options liquidity matters)
        tickers = ["SPY", "QQQ", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]

    scanner = IronCondorScanner(cfg)
    signals = scanner.generate_signals({"tickers": tickers, "portfolio_value": portfolio_value})

    if signals.empty:
        print("No condor opportunities found.")
        return signals

    date_str = datetime.today().strftime("%Y-%m-%d")
    max_total_pct = cfg["iron_condor"].get("max_total_pct", 0.15)
    total_margin = signals["margin_reserved"].sum()
    lines = [
        f"=== CONDOR OPPORTUNITIES: {date_str} ===\n",
        f"Portfolio value: ${portfolio_value:,.2f} | "
        f"Total margin reserved: ${total_margin:,.2f} ({total_margin/portfolio_value*100:.1f}% of portfolio) | "
        f"Max allowed: {max_total_pct*100:.0f}%\n",
    ]
    for _, row in signals.iterrows():
        lines.append(scanner.describe_signal(row))
        lines.append("")

    message = "\n".join(lines)

    if dry_run:
        print("\n[DRY RUN — email not sent]\n")
        print(message)
    elif _is_quiet_hours(alerts_cfg):
        print("Quiet hours active — email suppressed.")
    else:
        send_alert(f"Condor Opportunities: {date_str}", message)
        print("Condor email alert sent.")

    return signals


if __name__ == "__main__":
    # Quick test — prints signals without sending SMS
    run_equity_scan(dry_run=True)
    run_condor_scan(dry_run=True)
