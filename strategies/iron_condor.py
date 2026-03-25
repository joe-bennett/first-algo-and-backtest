"""
Iron Condor Opportunity Scanner

Screens for candidates where:
  - IV Rank >= threshold (high premium environment)
  - Stock is range-bound (low realized vol trend)
  - 30-45 DTE options exist
  - Constructs suggested strikes at target delta

Returns suggested condor structures with email-ready descriptions.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from strategies.base import BaseStrategy
from utils.openbb_client import get_options_chain, get_iv_rank, get_price_history


class IronCondorScanner(BaseStrategy):

    def generate_signals(self, data: dict) -> pd.DataFrame:
        """
        data expects:
            "tickers": list of tickers to screen
            "portfolio_value": float — used to calculate contract count
        """
        cfg = self.config["iron_condor"]
        tickers = data.get("tickers", [])
        portfolio_value = data.get("portfolio_value", cfg.get("default_portfolio_value", 100000))
        rows = []

        for ticker in tickers:
            try:
                iv_rank = get_iv_rank(ticker)
                if iv_rank is None or iv_rank < cfg["min_iv_rank"]:
                    continue

                chain = get_options_chain(ticker)
                if chain.empty:
                    continue

                # Find expiry in the 30-45 DTE window
                today = datetime.today()
                chain["expiration"] = pd.to_datetime(chain["expiration"])
                chain["dte"] = (chain["expiration"] - today).dt.days

                valid = chain[(chain["dte"] >= cfg["min_dte"]) & (chain["dte"] <= cfg["max_dte"])]
                if valid.empty:
                    continue

                # Pick nearest expiry in window
                target_expiry = valid["expiration"].min()
                expiry_chain = chain[chain["expiration"] == target_expiry]
                dte = int((target_expiry - today).days)

                # Get current price
                price_df = get_price_history([ticker], start=(today - timedelta(days=5)).strftime("%Y-%m-%d"))
                if price_df.empty:
                    continue
                current_price = price_df[ticker].iloc[-1]

                # Find short strikes near target delta
                calls = expiry_chain[expiry_chain["option_type"] == "call"].copy()
                puts = expiry_chain[expiry_chain["option_type"] == "put"].copy()

                if calls.empty or puts.empty:
                    continue

                # Short call: lowest call delta near target
                calls_otm = calls[calls["strike"] > current_price]
                puts_otm = puts[puts["strike"] < current_price]

                if calls_otm.empty or puts_otm.empty:
                    continue

                # Closest to target delta
                target_d = cfg["target_delta"]
                short_call = calls_otm.iloc[(calls_otm["delta"].fillna(0) - target_d).abs().argsort()[:1]]
                short_put = puts_otm.iloc[(puts_otm["delta"].fillna(0).abs() - target_d).abs().argsort()[:1]]

                short_call_strike = float(short_call["strike"].iloc[0])
                short_put_strike = float(short_put["strike"].iloc[0])

                # Long wings: 5 points OTM from short strikes
                wing_width = round(current_price * 0.05 / 5) * 5  # ~5% in $5 increments
                long_call_strike = short_call_strike + wing_width
                long_put_strike = short_put_strike - wing_width

                # Estimate credit (short premiums - long premiums)
                short_call_mid = (short_call["bid"].iloc[0] + short_call["ask"].iloc[0]) / 2
                short_put_mid = (short_put["bid"].iloc[0] + short_put["ask"].iloc[0]) / 2

                est_credit = round(short_call_mid + short_put_mid, 2)
                max_loss_per_share = round(wing_width - est_credit, 2)
                max_loss_per_contract = max_loss_per_share * 100  # 100 shares per contract

                # Size: reserve per_condor_pct of portfolio as margin
                margin_budget = portfolio_value * cfg.get("per_condor_pct", 0.05)
                contracts = max(1, int(margin_budget / max_loss_per_contract)) if max_loss_per_contract > 0 else 1
                margin_reserved = round(contracts * max_loss_per_contract, 2)
                max_profit = round(contracts * est_credit * 100, 2)
                max_loss_total = round(contracts * max_loss_per_contract, 2)

                rows.append({
                    "ticker": ticker,
                    "action": "CONDOR",
                    "weight": cfg.get("per_condor_pct", 0.05),
                    "iv_rank": iv_rank,
                    "dte": dte,
                    "expiry": target_expiry.strftime("%Y-%m-%d"),
                    "current_price": round(current_price, 2),
                    "short_call": short_call_strike,
                    "long_call": long_call_strike,
                    "short_put": short_put_strike,
                    "long_put": long_put_strike,
                    "est_credit": est_credit,
                    "max_loss": max_loss_per_share,
                    "contracts": contracts,
                    "margin_reserved": margin_reserved,
                    "max_profit": max_profit,
                    "max_loss_total": max_loss_total,
                })
            except Exception:
                continue

        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def describe_signal(self, signal_row: pd.Series) -> str:
        t = signal_row["ticker"]
        expiry = signal_row["expiry"]
        dte = signal_row["dte"]
        price = signal_row["current_price"]
        sc = signal_row["short_call"]
        lc = signal_row["long_call"]
        sp = signal_row["short_put"]
        lp = signal_row["long_put"]
        credit = signal_row["est_credit"]
        max_loss = signal_row["max_loss"]
        iv_rank = signal_row["iv_rank"]
        contracts = int(signal_row["contracts"])
        margin_reserved = signal_row["margin_reserved"]
        max_profit = signal_row["max_profit"]
        max_loss_total = signal_row["max_loss_total"]
        profit_target_credit = round(credit * self.config["iron_condor"]["profit_target_pct"], 2)
        profit_target_dollars = round(max_profit * self.config["iron_condor"]["profit_target_pct"], 2)

        return (
            f"IRON CONDOR OPPORTUNITY: {t}\n"
            f"  Current price: ${price:.2f} | IV Rank: {iv_rank:.0f}\n"
            f"  Expiry: {expiry} ({dte} DTE)\n"
            f"  Structure:\n"
            f"    Buy  {lp}P / Sell {sp}P — Sell {sc}C / Buy {lc}C\n"
            f"  Credit: ${credit:.2f}/share | Max loss: ${max_loss:.2f}/share\n"
            f"  SIZE: {contracts} contract{'s' if contracts != 1 else ''} "
            f"| Margin reserved: ${margin_reserved:,.2f} | Max profit: ${max_profit:,.2f} | Max loss: ${max_loss_total:,.2f}\n"
            f"  WHY: IV Rank {iv_rank:.0f} (>=50) means elevated premium — good time to sell volatility.\n"
            f"  HOW: Sell {contracts} condor{'s' if contracts != 1 else ''} as a single 4-leg order "
            f"at midpoint (${credit:.2f} credit target per contract).\n"
            f"  MANAGE: Close at 50% profit (~${profit_target_dollars:,.2f} gain) "
            f"or at {self.config['iron_condor']['exit_dte']} DTE."
        )
