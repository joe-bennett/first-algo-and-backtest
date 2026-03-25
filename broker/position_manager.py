"""
Daily position monitor — detects stopped-out positions and replaces them
with the next-highest ranked stock not already in the portfolio.

Flow:
  1. Load last saved signals (written at each monthly rebalance)
  2. Compare expected long positions to actual Alpaca positions
  3. Any expected long that is missing = was stopped out
  4. Score all S&P 500 stocks, find the next best candidate not already held
  5. Buy the replacement at the same portfolio weight
  6. Send email notification
"""

import json
import yaml
import numpy as np
from datetime import datetime
from pathlib import Path

from broker.alpaca import get_account, get_positions, place_order
from alerts.notifier import send_alert

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
SIGNALS_FILE = DATA_DIR / "last_signals.json"
CONFIG_PATH = Path(__file__).parent.parent / "config" / "portfolio.yaml"


def save_signals(signals) -> None:
    """Persist signals DataFrame after each monthly rebalance."""
    records = signals[signals["action"] == "BUY"][["ticker", "weight", "composite_score"]].to_dict(orient="records")
    with open(SIGNALS_FILE, "w") as f:
        json.dump({"saved_at": datetime.today().isoformat(), "longs": records}, f, indent=2)


def load_signals() -> list[dict]:
    """Load last saved long signals. Returns empty list if none saved yet."""
    if not SIGNALS_FILE.exists():
        return []
    with open(SIGNALS_FILE) as f:
        return json.load(f).get("longs", [])


def _load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_and_replace_stopped_positions(dry_run: bool = False) -> None:
    """
    Detect stopped-out long positions and replace with next-best ranked stock.
    Called daily by run_alerts.py.
    """
    expected_longs = load_signals()
    if not expected_longs:
        print("No saved signals found — skipping replacement check.")
        return

    current_positions = get_positions()
    current_tickers = set(current_positions.keys())
    expected_tickers = {r["ticker"] for r in expected_longs}

    # Stopped out = expected long is no longer in positions
    stopped = expected_tickers - current_tickers
    if not stopped:
        print("No stopped positions detected.")
        return

    print(f"Stopped-out positions detected: {', '.join(stopped)}")

    acct = get_account()
    portfolio_value = acct["portfolio_value"]
    cfg = _load_config()

    # Re-rank universe to find replacements
    from utils.openbb_client import get_sp500_tickers, get_price_history, get_fundamentals
    from strategies.value_momentum_120_20 import ValueMomentum12020

    print("Re-ranking universe for replacements...")
    tickers = get_sp500_tickers()
    prices = get_price_history(tickers, start="2022-01-01")
    fundamentals = get_fundamentals(list(prices.columns))

    strategy = ValueMomentum12020(cfg)
    all_signals = strategy.generate_signals({"prices": prices, "fundamentals": fundamentals})
    ranked_longs = all_signals[all_signals["action"] == "BUY"].sort_values("composite_score", ascending=False)

    # Exclude tickers already held or already in expected signals
    already_held = current_tickers | expected_tickers
    candidates = ranked_longs[~ranked_longs["ticker"].isin(already_held)]

    replacements_made = []

    for stopped_ticker in stopped:
        # Find the weight this position should have had
        original = next((r for r in expected_longs if r["ticker"] == stopped_ticker), None)
        weight = original["weight"] if original else cfg["strategy"]["long_weight"] / max(1, int(len(ranked_longs)))

        if candidates.empty:
            print(f"  No replacement candidate available for {stopped_ticker}.")
            continue

        replacement = candidates.iloc[0]
        candidates = candidates.iloc[1:]  # consume this candidate

        target_dollars = portfolio_value * abs(weight)

        try:
            import yfinance as yf
            price = yf.Ticker(replacement["ticker"]).fast_info["last_price"]
        except Exception:
            print(f"  Could not fetch price for {replacement['ticker']}, skipping.")
            continue

        qty = target_dollars / price
        stop_loss_pct = cfg["risk"].get("stop_loss_pct")
        stop_price = round(price * (1 - stop_loss_pct), 2) if stop_loss_pct else None
        stop_note = f" | stop @ ${stop_price:.2f}" if stop_price else ""

        if dry_run:
            print(f"  [DRY RUN] {stopped_ticker} stopped out -> Replace with {replacement['ticker']} "
                  f"BUY {qty:.4f} @ ~${price:.2f}{stop_note}")
        else:
            place_order(replacement["ticker"], qty, "buy", price=price, reason=f"replacement for {stopped_ticker}")
            replacements_made.append({
                "stopped": stopped_ticker,
                "replacement": replacement["ticker"],
                "qty": qty,
                "price": price,
                "stop_price": stop_price,
            })

            # Update saved signals to reflect replacement
            for r in expected_longs:
                if r["ticker"] == stopped_ticker:
                    r["ticker"] = replacement["ticker"]
                    r["composite_score"] = float(replacement["composite_score"])
            with open(SIGNALS_FILE, "w") as f:
                saved = {"saved_at": datetime.today().isoformat(), "longs": expected_longs}
                json.dump(saved, f, indent=2)

    if replacements_made:
        date_str = datetime.today().strftime("%Y-%m-%d")
        lines = [f"=== STOP-LOSS REPLACEMENTS: {date_str} ===\n"]
        for r in replacements_made:
            stop_note = f" | stop-loss @ ${r['stop_price']:.2f}" if r["stop_price"] else ""
            lines.append(f"{r['stopped']} stopped out -> {r['replacement']}")
            lines.append(f"  BUY {r['qty']:.4f} shares @ ~${r['price']:.2f}{stop_note}")
            lines.append("")
        send_alert(f"Stop-Loss Replacements: {date_str}", "\n".join(lines))

        from broker.ledger import save_ledger
        save_ledger()
