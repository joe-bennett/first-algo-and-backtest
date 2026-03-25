"""
Local portfolio ledger — keeps a CSV and JSON snapshot of current holdings.

Updates automatically after:
  - Every monthly rebalance
  - Every stop-loss replacement
  - Every daily run (refreshes current prices and P&L)

Files written:
  data/ledger.csv   — open in Excel to view holdings at a glance
  data/ledger.json  — used by dashboard and other code

Columns:
  ticker, side, qty, entry_price, current_price, current_value,
  unrealized_pl, unrealized_pl_pct, portfolio_weight, stop_loss_price, last_updated
"""

import json
import csv
import yaml
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
LEDGER_CSV = DATA_DIR / "ledger.csv"
LEDGER_JSON = DATA_DIR / "ledger.json"
CONFIG_PATH = Path(__file__).parent.parent / "config" / "portfolio.yaml"


def _get_stop_loss_pct() -> float | None:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    val = cfg.get("risk", {}).get("stop_loss_pct")
    return float(val) if val is not None else None


def save_ledger() -> list[dict]:
    """
    Pull current positions from Alpaca, enrich with account totals,
    and write ledger.csv + ledger.json.

    Returns the list of position dicts written.
    """
    from broker.alpaca import get_account, get_positions

    acct = get_account()
    portfolio_value = acct["portfolio_value"]
    positions = get_positions()
    stop_loss_pct = _get_stop_loss_pct()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = []
    for ticker, pos in positions.items():
        entry_price = pos["avg_entry"]
        current_price = pos["market_value"] / pos["qty"] if pos["qty"] != 0 else 0.0
        unrealized_pl = pos["unrealized_pl"]
        unrealized_pl_pct = (unrealized_pl / (entry_price * abs(pos["qty"])) * 100) if entry_price else 0.0
        portfolio_weight = pos["market_value"] / portfolio_value * 100 if portfolio_value else 0.0
        stop_loss_price = round(entry_price * (1 - stop_loss_pct), 2) if (stop_loss_pct and pos["side"] == "long") else None

        rows.append({
            "ticker": ticker,
            "side": pos["side"],
            "qty": round(pos["qty"], 4),
            "entry_price": round(entry_price, 2),
            "current_price": round(current_price, 2),
            "current_value": round(pos["market_value"], 2),
            "unrealized_pl": round(unrealized_pl, 2),
            "unrealized_pl_pct": round(unrealized_pl_pct, 2),
            "portfolio_weight_pct": round(portfolio_weight, 2),
            "stop_loss_price": stop_loss_price,
            "last_updated": now,
        })

    # Sort: longs first by value descending, then shorts
    rows.sort(key=lambda r: (0 if r["side"] == "long" else 1, -abs(r["current_value"])))

    # Add summary row
    total_pl = sum(r["unrealized_pl"] for r in rows)
    total_pl_pct = total_pl / (portfolio_value - total_pl) * 100 if (portfolio_value - total_pl) else 0.0

    summary = {
        "portfolio_value": round(portfolio_value, 2),
        "cash": round(acct["cash"], 2),
        "total_unrealized_pl": round(total_pl, 2),
        "total_unrealized_pl_pct": round(total_pl_pct, 2),
        "position_count": len(rows),
        "last_updated": now,
    }

    # Write CSV
    if rows:
        fieldnames = list(rows[0].keys())
        with open(LEDGER_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    # Write JSON (positions + summary)
    with open(LEDGER_JSON, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "positions": rows}, f, indent=2)

    print(f"Ledger saved: {len(rows)} positions | "
          f"Portfolio value: ${portfolio_value:,.2f} | "
          f"Unrealized P&L: ${total_pl:+,.2f} ({total_pl_pct:+.2f}%)")
    return rows


def print_ledger() -> None:
    """Print a formatted ledger table to the console."""
    if not LEDGER_JSON.exists():
        print("No ledger found. Run save_ledger() first.")
        return

    with open(LEDGER_JSON, encoding="utf-8") as f:
        data = json.load(f)

    s = data["summary"]
    print(f"\n{'='*70}")
    print(f"  PORTFOLIO LEDGER — {s['last_updated']}")
    print(f"{'='*70}")
    print(f"  Portfolio value:   ${s['portfolio_value']:>12,.2f}")
    print(f"  Cash:              ${s['cash']:>12,.2f}")
    print(f"  Unrealized P&L:    ${s['total_unrealized_pl']:>+12,.2f}  ({s['total_unrealized_pl_pct']:+.2f}%)")
    print(f"  Positions:         {s['position_count']}")
    print(f"{'='*70}")
    print(f"  {'TICKER':<8} {'SIDE':<6} {'QTY':>8} {'ENTRY':>8} {'NOW':>8} {'VALUE':>10} {'P&L':>10} {'P&L%':>7} {'STOP':>8}")
    print(f"  {'-'*8} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*10} {'-'*10} {'-'*7} {'-'*8}")

    for p in data["positions"]:
        stop = f"${p['stop_loss_price']:.2f}" if p["stop_loss_price"] else "  —"
        print(
            f"  {p['ticker']:<8} {p['side']:<6} {p['qty']:>8.2f} "
            f"${p['entry_price']:>7.2f} ${p['current_price']:>7.2f} "
            f"${p['current_value']:>9,.2f} ${p['unrealized_pl']:>+9,.2f} "
            f"{p['unrealized_pl_pct']:>+6.2f}% {stop:>8}"
        )
    print(f"{'='*70}\n")
