"""
120/20 Value-Momentum Strategy

Long book:  120% exposure in top-ranked stocks (value + momentum composite)
Short book:  20% exposure in bottom-ranked stocks

Ranking:
  - Value score:    composite of P/E, P/B, FCF yield, EV/EBITDA (lower multiples = higher score)
  - Momentum score: 12-1 month price return (skip last month to avoid short-term reversal)
  - Final score:    blend of value + momentum (weights in config/portfolio.yaml)
"""

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy


class ValueMomentum12020(BaseStrategy):

    def generate_signals(self, data: dict) -> pd.DataFrame:
        """
        data expects:
            "prices"      : pd.DataFrame — daily adj close, cols=tickers, index=date
            "fundamentals": pd.DataFrame — index=ticker, cols=pe_ratio, pb_ratio, fcf_yield, ev_ebitda
        """
        prices: pd.DataFrame = data["prices"]
        fundamentals: pd.DataFrame = data["fundamentals"]

        cfg = self.config["strategy"]
        vf = self.config["value_factors"]
        mf = self.config["momentum_factors"]
        blend = self.config["score_blend"]

        tickers = list(set(prices.columns) & set(fundamentals.index))
        if not tickers:
            return pd.DataFrame()

        # --- Momentum score: 12-month return, skip last month ---
        if len(prices) < 252:
            raise ValueError("Need at least 252 days of price history for momentum calc.")

        ret_12_1 = (
            prices.iloc[-252] / prices.iloc[-21] - 1  # ~11 months ending 1 month ago
            if len(prices) >= 252
            else prices.pct_change(periods=len(prices) - 21).iloc[-1]
        )
        momentum_raw = ret_12_1.reindex(tickers)

        # Rank 0-1 (higher = stronger momentum)
        momentum_score = momentum_raw.rank(pct=True)

        # --- Value score: composite of factors ---
        f = fundamentals.reindex(tickers)

        # Invert ratios so lower multiple = higher score, then rank
        def invert_rank(series):
            return (-series).rank(pct=True)

        value_score = pd.Series(0.0, index=tickers)

        pe_mask = f["pe_ratio"].notna() & (f["pe_ratio"] > 0)
        if pe_mask.any():
            value_score += vf["pe_ratio"] * invert_rank(f.loc[pe_mask, "pe_ratio"]).reindex(tickers).fillna(0.5)

        pb_mask = f["pb_ratio"].notna() & (f["pb_ratio"] > 0)
        if pb_mask.any():
            value_score += vf["pb_ratio"] * invert_rank(f.loc[pb_mask, "pb_ratio"]).reindex(tickers).fillna(0.5)

        fcf_mask = f["fcf_yield"].notna()
        if fcf_mask.any():
            value_score += vf["fcf_yield"] * f.loc[fcf_mask, "fcf_yield"].rank(pct=True).reindex(tickers).fillna(0.5)

        ev_mask = f["ev_ebitda"].notna() & (f["ev_ebitda"] > 0)
        if ev_mask.any():
            value_score += vf["ev_ebitda"] * invert_rank(f.loc[ev_mask, "ev_ebitda"]).reindex(tickers).fillna(0.5)

        # --- Composite score ---
        composite = (
            blend["value_weight"] * value_score
            + blend["momentum_weight"] * momentum_score
        )
        composite = composite.dropna()

        n_long = max(1, int(len(composite) * cfg["long_pct"]))
        n_short = max(1, int(len(composite) * cfg["short_pct"]))

        sorted_scores = composite.sort_values(ascending=False)
        long_tickers = sorted_scores.head(n_long).index.tolist()
        short_tickers = sorted_scores.tail(n_short).index.tolist()

        # Equal weight within each book
        long_weight = cfg["long_weight"] / n_long
        short_weight = cfg["short_weight"] / n_short

        rows = []
        for t in long_tickers:
            rows.append({
                "ticker": t,
                "action": "BUY",
                "weight": round(long_weight, 4),
                "composite_score": round(composite[t], 4),
                "momentum_score": round(float(momentum_score.get(t, np.nan)), 4),
                "value_score": round(float(value_score.get(t, np.nan)), 4),
                "pe_ratio": f.loc[t, "pe_ratio"] if t in f.index else np.nan,
                "pb_ratio": f.loc[t, "pb_ratio"] if t in f.index else np.nan,
                "fcf_yield": f.loc[t, "fcf_yield"] if t in f.index else np.nan,
            })
        for t in short_tickers:
            rows.append({
                "ticker": t,
                "action": "SHORT",
                "weight": round(-short_weight, 4),
                "composite_score": round(composite[t], 4),
                "momentum_score": round(float(momentum_score.get(t, np.nan)), 4),
                "value_score": round(float(value_score.get(t, np.nan)), 4),
                "pe_ratio": f.loc[t, "pe_ratio"] if t in f.index else np.nan,
                "pb_ratio": f.loc[t, "pb_ratio"] if t in f.index else np.nan,
                "fcf_yield": f.loc[t, "fcf_yield"] if t in f.index else np.nan,
            })

        return pd.DataFrame(rows)

    def describe_signal(self, signal_row: pd.Series) -> str:
        t = signal_row["ticker"]
        action = signal_row["action"]
        weight = abs(signal_row["weight"]) * 100
        comp = signal_row["composite_score"]
        mom = signal_row["momentum_score"]
        val = signal_row["value_score"]
        pe = signal_row.get("pe_ratio", float("nan"))
        pb = signal_row.get("pb_ratio", float("nan"))
        fcf = signal_row.get("fcf_yield", float("nan"))

        direction = "LONG" if action == "BUY" else "SHORT"
        pe_str = f"P/E {pe:.1f}" if not np.isnan(pe) else "P/E N/A"
        pb_str = f"P/B {pb:.1f}" if not np.isnan(pb) else "P/B N/A"
        fcf_str = f"FCF yield {fcf*100:.1f}%" if not np.isnan(fcf) else "FCF N/A"

        # Build WHY explanation from the dominant driver
        why_parts = []
        if action == "BUY":
            if val >= 0.75:
                why_parts.append(f"cheap on fundamentals (value score {val:.2f})")
            if mom >= 0.75:
                why_parts.append(f"strong 12-month price trend (momentum score {mom:.2f})")
            if not why_parts:
                why_parts.append(f"top composite ranking across value + momentum (score {comp:.2f})")
        else:
            if val <= 0.25:
                why_parts.append(f"expensive on fundamentals (value score {val:.2f})")
            if mom <= 0.25:
                why_parts.append(f"weak 12-month price trend (momentum score {mom:.2f})")
            if not why_parts:
                why_parts.append(f"bottom composite ranking across value + momentum (score {comp:.2f})")

        why = " and ".join(why_parts)

        return (
            f"{direction} {t} @ {weight:.1f}% of portfolio\n"
            f"  Composite score: {comp:.2f} (value: {val:.2f}, momentum: {mom:.2f})\n"
            f"  {pe_str} | {pb_str} | {fcf_str}\n"
            f"  WHY: {t} ranks {'highly' if action == 'BUY' else 'poorly'} because it is {why}.\n"
            f"  HOW: {'Buy market order at open' if action == 'BUY' else 'Sell short at market open'}"
        )
