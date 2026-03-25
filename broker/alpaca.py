"""
Alpaca Paper Trading broker integration.

Handles:
  - Connecting to Alpaca paper account
  - Fetching current positions and portfolio value
  - Placing and canceling orders
  - Rebalancing based on signal output from strategies
"""

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus, OrderClass

load_dotenv(Path(__file__).parent.parent / ".env")

_client = None
_CONFIG_PATH = Path(__file__).parent.parent / "config" / "portfolio.yaml"


def _get_stop_loss_pct() -> float | None:
    """Read stop_loss_pct from portfolio.yaml. Returns None if disabled."""
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    val = cfg.get("risk", {}).get("stop_loss_pct")
    return float(val) if val is not None else None


def get_client() -> TradingClient:
    global _client
    if _client is None:
        _client = TradingClient(
            api_key=os.getenv("ALPACA_API_KEY"),
            secret_key=os.getenv("ALPACA_SECRET_KEY"),
            paper=True,
        )
    return _client


def get_account() -> dict:
    """Return key account metrics."""
    acct = get_client().get_account()
    return {
        "portfolio_value": float(acct.portfolio_value),
        "cash": float(acct.cash),
        "buying_power": float(acct.buying_power),
        "equity": float(acct.equity),
    }


def get_positions() -> dict[str, dict]:
    """Return current positions keyed by ticker."""
    positions = get_client().get_all_positions()
    return {
        p.symbol: {
            "qty": float(p.qty),
            "side": p.side.value,
            "market_value": float(p.market_value),
            "avg_entry": float(p.avg_entry_price),
            "unrealized_pl": float(p.unrealized_pl),
        }
        for p in positions
    }


def place_order(ticker: str, qty: float, side: str, price: float | None = None, reason: str = "") -> dict:
    """
    Place a market order. For long buys, attaches a stop-loss if configured in portfolio.yaml.
    side: 'buy' or 'sell'
    qty: number of shares (fractional supported on paper)
    price: current price — required to calculate stop price for longs
    """
    client = get_client()
    order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
    stop_loss_pct = _get_stop_loss_pct()

    # Attach stop-loss to long buys when price and stop_loss_pct are available
    if side == "buy" and price and stop_loss_pct:
        stop_price = round(price * (1 - stop_loss_pct), 2)
        req = MarketOrderRequest(
            symbol=ticker,
            qty=round(qty, 4),
            side=order_side,
            time_in_force=TimeInForce.GTC,
            order_class=OrderClass.OTO,
            stop_loss=StopLossRequest(stop_price=stop_price),
        )
        print(f"  Order placed: BUY {qty:.4f} {ticker} | stop-loss @ ${stop_price:.2f} ({stop_loss_pct*100:.0f}%) | {reason}")
    else:
        req = MarketOrderRequest(
            symbol=ticker,
            qty=round(qty, 4),
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        print(f"  Order placed: {side.upper()} {qty:.4f} {ticker} | {reason}")

    order = client.submit_order(req)
    return {"id": str(order.id), "ticker": ticker, "side": side, "qty": qty}


def cancel_all_orders() -> None:
    get_client().cancel_orders()


def rebalance(signals, dry_run: bool = False) -> list[dict]:
    """
    Rebalance the paper portfolio to match strategy signals.

    signals: DataFrame with columns [ticker, action, weight]
      action: 'BUY' (long) or 'SHORT' (short)
      weight: positive for longs, negative for shorts (e.g. 0.012 = 1.2%)

    Returns list of orders placed.
    """
    acct = get_account()
    portfolio_value = acct["portfolio_value"]
    current_positions = get_positions()

    print(f"\nPortfolio value: ${portfolio_value:,.2f}")
    print(f"Current positions: {len(current_positions)}")

    # Build target position map: ticker -> dollar value (negative = short)
    target = {}
    for _, row in signals.iterrows():
        dollar_value = portfolio_value * abs(row["weight"])
        target[row["ticker"]] = dollar_value if row["action"] == "BUY" else -dollar_value

    orders = []

    # Close positions no longer in signals
    for ticker, pos in current_positions.items():
        if ticker not in target:
            qty = abs(pos["qty"])
            close_side = "sell" if pos["side"] == "long" else "buy"
            reason = "no longer in signals"
            if dry_run:
                print(f"  [DRY RUN] Would {close_side.upper()} {qty:.4f} {ticker} — {reason}")
            else:
                orders.append(place_order(ticker, qty, close_side, reason))

    # Open or adjust positions in signals
    for ticker, target_dollars in target.items():
        is_long = target_dollars > 0

        # Fetch current price via yfinance for share qty calculation
        try:
            import yfinance as yf
            price = yf.Ticker(ticker).fast_info["last_price"]
        except Exception:
            print(f"  Could not fetch price for {ticker}, skipping.")
            continue

        target_qty = abs(target_dollars) / price

        current = current_positions.get(ticker)
        current_qty = float(current["qty"]) if current else 0.0
        current_side = current["side"] if current else None

        # Already in the right direction with roughly right size (within 10%)?
        if current and current_side == ("long" if is_long else "short"):
            diff_pct = abs(target_qty - current_qty) / max(current_qty, 0.0001)
            if diff_pct < 0.10:
                print(f"  {ticker}: already sized correctly, skipping.")
                continue

        # Close existing position if on wrong side
        if current and current_side != ("long" if is_long else "short"):
            close_side = "sell" if current_side == "long" else "buy"
            if dry_run:
                print(f"  [DRY RUN] Would {close_side.upper()} {current_qty:.4f} {ticker} — flip side")
            else:
                orders.append(place_order(ticker, current_qty, close_side, "flip side"))

        # Place new order
        side = "buy" if is_long else "sell"
        reason = f"target weight {target_dollars/portfolio_value*100:.1f}%"
        stop_loss_pct = _get_stop_loss_pct()
        stop_note = f" | stop @ ${price*(1-stop_loss_pct):.2f}" if (side == "buy" and stop_loss_pct) else ""
        if dry_run:
            print(f"  [DRY RUN] Would {side.upper()} {target_qty:.4f} {ticker} @ ~${price:.2f}{stop_note} — {reason}")
        else:
            orders.append(place_order(ticker, target_qty, side, price=price, reason=reason))

    return orders
