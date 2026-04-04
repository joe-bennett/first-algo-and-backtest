"""
Alpaca Paper Trading broker integration.

Handles:
  - Connecting to Alpaca paper account
  - Fetching current positions and portfolio value
  - Placing and canceling orders
  - Rebalancing based on signal output from strategies

Put option orders (for short_book_puts mode):
  find_put_contract() uses yfinance to locate the best matching put contract
  (closest to target DTE and ~10% OTM as a proxy for ~30-delta).
  place_put_order() buys that contract on Alpaca, sized by premium_pct of portfolio value.
  Requires options trading enabled on your Alpaca account.
  Option positions are NOT automatically closed during rebalance — manage them manually
  or set a GTC limit order at 2x premium (profit target) when entering.
"""

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, StopOrderRequest, GetOrdersRequest, TakeProfitRequest, StopLossRequest
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
    Place a market order. For long buys, attaches a GTC stop-loss using whole shares.
    side: 'buy' or 'sell'
    qty: number of shares (fractional for longs, rounded to whole shares for shorts)
    price: current price — required to calculate stop price for longs
    """
    import math
    client = get_client()
    order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
    stop_loss_pct = _get_stop_loss_pct()

    if side == "buy":
        # Long buys: fractional OK, DAY required; attach separate GTC stop using whole shares
        req = MarketOrderRequest(
            symbol=ticker,
            qty=round(qty, 4),
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        order = client.submit_order(req)

        if price and stop_loss_pct:
            stop_price = round(price * (1 - stop_loss_pct), 2)
            whole_qty = max(1, math.floor(qty))  # floor so stop never exceeds position size
            try:
                stop_req = StopOrderRequest(
                    symbol=ticker,
                    qty=whole_qty,
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.GTC,
                    stop_price=stop_price,
                )
                client.submit_order(stop_req)
                print(f"  Order placed: BUY {qty:.4f} {ticker} | stop-loss @ ${stop_price:.2f} ({stop_loss_pct*100:.0f}%) | {reason}")
            except Exception as e:
                print(f"  Order placed: BUY {qty:.4f} {ticker} | stop-loss failed ({e}) | {reason}")
        else:
            print(f"  Order placed: BUY {qty:.4f} {ticker} | {reason}")
    else:
        # Short sells: Alpaca does not support fractional shorts — round up to whole shares
        whole_qty = max(1, round(qty))
        req = MarketOrderRequest(
            symbol=ticker,
            qty=whole_qty,
            side=order_side,
            time_in_force=TimeInForce.DAY,
        )
        order = client.submit_order(req)
        print(f"  Order placed: SHORT {whole_qty} {ticker} | {reason}")

    return {"id": str(order.id), "ticker": ticker, "side": side, "qty": qty}


def cancel_all_orders() -> None:
    get_client().cancel_orders()


def find_put_contract(ticker: str, target_dte: int = 90, otm_pct: float = 0.10) -> dict | None:
    """
    Find the best matching put contract for a given ticker using yfinance option chains.

    Selects the expiry date closest to target_dte days out, then finds the put strike
    closest to (current_price * (1 - otm_pct)).  otm_pct=0.10 gives ~10% OTM, which is
    a reasonable proxy for a ~30-delta put on an average S&P 500 stock.

    Returns a dict with: symbol (OCC format), strike, expiry, ask_price
    Returns None if no suitable contract is found.
    """
    import yfinance as yf
    from datetime import date, timedelta

    try:
        yf_ticker = yf.Ticker(ticker)
        expiries = yf_ticker.options
        if not expiries:
            print(f"  {ticker}: no option expiries available")
            return None

        # Find expiry date closest to target_dte
        today = date.today()
        target_date = today + timedelta(days=target_dte)
        best_expiry = min(expiries, key=lambda e: abs((date.fromisoformat(e) - target_date).days))

        chain = yf_ticker.option_chain(best_expiry)
        puts = chain.puts.copy()
        if puts.empty:
            print(f"  {ticker}: no put contracts for expiry {best_expiry}")
            return None

        current_price = yf_ticker.fast_info["last_price"]
        target_strike = current_price * (1 - otm_pct)

        puts["strike_diff"] = (puts["strike"] - target_strike).abs()
        best = puts.nsmallest(1, "strike_diff").iloc[0]

        ask = float(best["ask"]) if float(best["ask"]) > 0 else float(best["lastPrice"])
        if ask <= 0:
            print(f"  {ticker}: could not determine put ask price")
            return None

        return {
            "symbol": best["contractSymbol"],
            "strike": float(best["strike"]),
            "expiry": best_expiry,
            "ask":    ask,
        }

    except Exception as e:
        print(f"  {ticker}: error finding put contract — {e}")
        return None


def place_put_order(ticker: str, portfolio_value: float, puts_cfg: dict) -> dict | None:
    """
    Buy a put option contract on the given ticker, sized to puts_cfg["premium_pct"] of portfolio.

    puts_cfg keys used:
        dte         : target days to expiration (default 90)
        target_delta: used to derive OTM % (0.30 delta ≈ 10% OTM, default)
        premium_pct : fraction of portfolio to spend per position (default 0.003 = 0.3%)

    Requires Alpaca options trading enabled on the account.
    Returns order metadata dict, or None if the contract could not be found or order failed.
    """
    target_dte  = int(puts_cfg.get("dte", 90))
    premium_pct = float(puts_cfg.get("premium_pct", 0.003))

    contract = find_put_contract(ticker, target_dte=target_dte, otm_pct=0.10)
    if not contract:
        return None

    budget    = portfolio_value * premium_pct
    contracts = max(1, int(budget / (contract["ask"] * 100)))  # 100 shares per contract

    try:
        client = get_client()
        req = MarketOrderRequest(
            symbol=contract["symbol"],
            qty=contracts,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        order = client.submit_order(req)
        print(
            f"  Put order placed: BUY {contracts}x {contract['symbol']} "
            f"(strike ${contract['strike']:.2f}, exp {contract['expiry']}, "
            f"ask ~${contract['ask']:.2f}/share, budget ${budget:.0f})"
        )
        return {
            "id":        str(order.id),
            "ticker":    ticker,
            "side":      "buy_put",
            "symbol":    contract["symbol"],
            "contracts": contracts,
            "strike":    contract["strike"],
            "expiry":    contract["expiry"],
        }
    except Exception as e:
        print(f"  Put order FAILED for {ticker}: {e}")
        return None


def rebalance(signals, dry_run: bool = False) -> list[dict]:
    """
    Rebalance the paper portfolio to match strategy signals.

    signals: DataFrame with columns [ticker, action, weight]
      action: 'BUY' (long), 'SHORT' (short shares), or 'PUT' (buy put options)
      weight: positive for longs, negative for shorts/puts (e.g. 0.012 = 1.2%)

    PUT signals:
      Calls place_put_order() to buy OTM put contracts instead of short-selling shares.
      Put positions are NOT automatically closed during subsequent rebalances — manage
      them manually (close at 2x premium profit or at 21 DTE).

    Returns list of orders placed.
    """
    import yaml
    with open(_CONFIG_PATH, encoding="utf-8") as _f:
        cfg = yaml.safe_load(_f)
    puts_cfg = cfg.get("short_book_puts", {})

    acct = get_account()
    portfolio_value = acct["portfolio_value"]
    current_positions = get_positions()

    print(f"\nPortfolio value: ${portfolio_value:,.2f}")
    print(f"Current positions: {len(current_positions)}")

    # Separate PUT signals from equity signals
    put_signals    = signals[signals["action"] == "PUT"]
    equity_signals = signals[signals["action"].isin(["BUY", "SHORT"])]

    # Build target position map for equity only: ticker -> dollar value (negative = short)
    target = {}
    for _, row in equity_signals.iterrows():
        dollar_value = portfolio_value * abs(row["weight"])
        target[row["ticker"]] = dollar_value if row["action"] == "BUY" else -dollar_value

    orders = []

    # Close equity positions no longer in signals
    # Note: option positions (OCC symbols) are not tracked here — close puts manually
    for ticker, pos in current_positions.items():
        if ticker not in target:
            qty = abs(pos["qty"])
            close_side = "sell" if pos["side"] == "long" else "buy"
            reason = "no longer in signals"
            if dry_run:
                print(f"  [DRY RUN] Would {close_side.upper()} {qty:.4f} {ticker} — {reason}")
            else:
                orders.append(place_order(ticker, qty, close_side, reason))

    # Open or adjust equity positions
    for ticker, target_dollars in target.items():
        is_long = target_dollars > 0

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

        # Close existing equity position if on wrong side
        if current and current_side != ("long" if is_long else "short"):
            close_side = "sell" if current_side == "long" else "buy"
            if dry_run:
                print(f"  [DRY RUN] Would {close_side.upper()} {current_qty:.4f} {ticker} — flip side")
            else:
                orders.append(place_order(ticker, current_qty, close_side, "flip side"))

        # Place equity order
        side = "buy" if is_long else "sell"
        reason = f"target weight {target_dollars/portfolio_value*100:.1f}%"
        stop_loss_pct = _get_stop_loss_pct()
        stop_note = f" | stop @ ${price*(1-stop_loss_pct):.2f}" if (side == "buy" and stop_loss_pct) else ""
        if dry_run:
            print(f"  [DRY RUN] Would {side.upper()} {target_qty:.4f} {ticker} @ ~${price:.2f}{stop_note} — {reason}")
        else:
            orders.append(place_order(ticker, target_qty, side, price=price, reason=reason))

    # Place put option orders for PUT signals
    if not put_signals.empty:
        print(f"\nPlacing put orders for {len(put_signals)} conviction short(s)...")
        for _, row in put_signals.iterrows():
            ticker = row["ticker"]
            if dry_run:
                contract = find_put_contract(ticker, target_dte=puts_cfg.get("dte", 90))
                budget = portfolio_value * puts_cfg.get("premium_pct", 0.003)
                if contract:
                    contracts = max(1, int(budget / (contract["ask"] * 100)))
                    print(
                        f"  [DRY RUN] Would BUY {contracts}x {contract['symbol']} "
                        f"(strike ${contract['strike']:.2f}, exp {contract['expiry']}, "
                        f"ask ~${contract['ask']:.2f}, budget ${budget:.0f})"
                    )
                else:
                    print(f"  [DRY RUN] Could not find put contract for {ticker}")
            else:
                result = place_put_order(ticker, portfolio_value, puts_cfg)
                if result:
                    orders.append(result)

    return orders
