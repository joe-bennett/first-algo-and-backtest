"""
Scheduled alert runner — called by Windows Task Scheduler.
  - Daily (weekdays 4:30 PM):    Iron Condor scan + stop-loss replacement check
  - Quarterly (1st of Jan/Apr/Jul/Oct): 120/20 Value-Momentum equity scan + portfolio rebalance

Logs output to logs/alerts.log
"""

import sys
import logging
from datetime import datetime
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).parent))

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / "alerts.log",
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)

from alerts.engine import run_equity_scan, run_condor_scan
from alerts.notifier import send_alert
from broker.alpaca import rebalance, get_account
from broker.position_manager import check_and_replace_stopped_positions, save_signals
from broker.ledger import save_ledger


def main():
    today = datetime.today()
    logging.info("=== Alert runner started ===")

    # --- Daily: refresh local ledger with current prices and P&L ---
    try:
        logging.info("Refreshing portfolio ledger...")
        save_ledger()
        logging.info("Ledger updated.")
    except Exception as e:
        logging.error(f"Ledger update failed: {e}")

    # --- Daily: check for stopped-out positions and replace them ---
    try:
        logging.info("Checking for stopped-out positions...")
        check_and_replace_stopped_positions(dry_run=False)
        logging.info("Position check complete.")
    except Exception as e:
        logging.error(f"Position check failed: {e}")

    # --- Iron Condor scan: runs every weekday ---
    try:
        logging.info("Running condor scan...")
        run_condor_scan(dry_run=False)
        logging.info("Condor scan complete.")
    except Exception as e:
        logging.error(f"Condor scan failed: {e}")

    # --- Equity scan + rebalance: runs quarterly (1st of Jan, Apr, Jul, Oct) ---
    if today.day == 1 and today.month in (1, 4, 7, 10):
        try:
            logging.info("Running equity scan (quarterly)...")
            signals = run_equity_scan(dry_run=False)
            logging.info("Equity scan complete.")

            if not signals.empty:
                logging.info("Rebalancing paper portfolio via Alpaca...")
                acct = get_account()
                orders = rebalance(signals, dry_run=False)
                save_signals(signals)
                save_ledger()
                logging.info(f"Quarterly rebalance complete: {len(orders)} orders placed.")

                # Send summary email
                date_str = today.strftime("%Y-%m-%d")
                lines = [f"=== REBALANCE COMPLETE: {date_str} ===\n"]
                lines.append(f"Portfolio value: ${acct['portfolio_value']:,.2f}")
                lines.append(f"Cash available: ${acct['cash']:,.2f}\n")
                lines.append(f"Orders placed: {len(orders)}")
                for o in orders:
                    lines.append(f"  {o['side'].upper()} {o['qty']:.4f} {o['ticker']}")
                send_alert(f"Rebalance Complete: {date_str}", "\n".join(lines))

        except Exception as e:
            logging.error(f"Equity scan/rebalance failed: {e}")
    else:
        logging.info(f"Equity scan skipped (runs quarterly on day 1 of Jan/Apr/Jul/Oct, today is {today.strftime('%Y-%m-%d')}).")

    logging.info("=== Alert runner finished ===")


if __name__ == "__main__":
    main()
