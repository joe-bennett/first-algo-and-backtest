"""
120/20 Value-Momentum Strategy

Long book:  120% exposure in top-ranked stocks (value + momentum + quality composite)
Short book:  20% exposure in bottom-ranked stocks (toggled by enable_short_book in config)

Ranking factors:
  - Value score:    composite of P/E, P/B, FCF yield, EV/EBITDA (lower multiples = higher score)
  - Momentum score: 12-1 month price return (skip last month to avoid short-term reversal)
                    Uses 5-day average around reference points to reduce single-day noise.
  - Quality score:  composite of ROE, net margin, debt/equity (high ROE/margin, low debt = quality)
  - Final score:    blend of value + momentum + quality (weights in config/portfolio.yaml)

Sector neutralization (enabled by sector_neutral in config):
  When enabled, each factor is ranked within GICS sector rather than globally. This prevents
  the portfolio from concentrating in a single sector (e.g., buying only cheap energy stocks).
  Requires get_sector_map() from openbb_client — falls back to global ranking if unavailable.
"""

import numpy as np
import pandas as pd

from strategies.base import BaseStrategy


def _rank_within_sector(
    series: pd.Series,
    sector_series: pd.Series,
    ascending: bool = True,
) -> pd.Series:
    """
    Rank a series within GICS sector groups, returning percentile ranks 0–1.

    Parameters
    ----------
    series        : raw factor values, indexed by ticker
    sector_series : GICS sector label per ticker (same index)
    ascending     : True → low values get low rank; False → high values get low rank
    """
    result = pd.Series(np.nan, index=series.index)
    for _sec, group_idx in series.groupby(sector_series).groups.items():
        grp = series.loc[group_idx].dropna()
        if grp.empty:
            continue
        if ascending:
            ranked = grp.rank(pct=True)
        else:
            ranked = (-grp).rank(pct=True)
        result.loc[ranked.index] = ranked
    return result


class ValueMomentum12020(BaseStrategy):

    def generate_signals(self, data: dict) -> pd.DataFrame:
        """
        Generate long and short signals ranked by composite score.

        data expects:
            "prices"      : pd.DataFrame — daily adj close, cols=tickers, index=date
            "fundamentals": pd.DataFrame — index=ticker; cols include pe_ratio, pb_ratio,
                            fcf_yield, ev_ebitda, roe, net_margin, debt_equity
            "sectors"     : dict[str, str] — optional {ticker: GICS sector}; used when
                            sector_neutral=True is set in config
        """
        prices: pd.DataFrame = data["prices"]
        fundamentals: pd.DataFrame = data["fundamentals"]
        sector_map: dict = data.get("sectors", {})

        cfg = self.config["strategy"]
        vf = self.config["value_factors"]
        mf = self.config["momentum_factors"]
        blend = self.config["score_blend"]
        qf = self.config.get("quality_factors", {"roe": 0.40, "net_margin": 0.40, "debt_equity": 0.20})
        enable_short = self.config.get("enable_short_book", True)
        sector_neutral = self.config.get("sector_neutral", False) and bool(sector_map)

        tickers = list(set(prices.columns) & set(fundamentals.index))
        if not tickers:
            return pd.DataFrame()

        # --- Momentum score: 12-1 month return, 5-day average at reference points ---
        # Using a 5-day window (±2 days) around each reference point reduces single-day
        # price noise that can distort the return calculation.
        if len(prices) < 252:
            raise ValueError("Need at least 252 days of price history for momentum calc.")

        # ~1 month ago: days -23 to -18; ~12 months ago: days -254 to -249
        recent_avg  = prices.iloc[-23:-18].mean()
        year_ago_avg = prices.iloc[-254:-249].mean() if len(prices) >= 254 else prices.iloc[-252]
        ret_12_1 = recent_avg / year_ago_avg.replace(0, np.nan) - 1
        momentum_raw = ret_12_1.reindex(tickers)

        # --- Factor rankings (global or within sector) ---
        f = fundamentals.reindex(tickers)
        sectors_s = pd.Series(sector_map).reindex(tickers).fillna("Unknown") if sector_neutral else None

        def _rank(series: pd.Series, ascending: bool = True) -> pd.Series:
            """Rank globally or within sector based on config."""
            if sector_neutral and sectors_s is not None:
                return _rank_within_sector(series, sectors_s, ascending=ascending)
            if ascending:
                return series.rank(pct=True)
            return (-series).rank(pct=True)

        # Momentum rank: higher return = higher score
        momentum_score = _rank(momentum_raw, ascending=True)

        # --- Value score ---
        value_score = pd.Series(0.0, index=tickers)

        pe_mask = f["pe_ratio"].notna() & (f["pe_ratio"] > 0) if "pe_ratio" in f.columns else pd.Series(False, index=tickers)
        if pe_mask.any():
            value_score += vf["pe_ratio"] * _rank(f.loc[pe_mask, "pe_ratio"], ascending=False).reindex(tickers).fillna(0.5)

        pb_mask = f["pb_ratio"].notna() & (f["pb_ratio"] > 0) if "pb_ratio" in f.columns else pd.Series(False, index=tickers)
        if pb_mask.any():
            value_score += vf["pb_ratio"] * _rank(f.loc[pb_mask, "pb_ratio"], ascending=False).reindex(tickers).fillna(0.5)

        fcf_mask = f["fcf_yield"].notna() if "fcf_yield" in f.columns else pd.Series(False, index=tickers)
        if fcf_mask.any():
            value_score += vf["fcf_yield"] * _rank(f.loc[fcf_mask, "fcf_yield"], ascending=True).reindex(tickers).fillna(0.5)

        ev_mask = f["ev_ebitda"].notna() & (f["ev_ebitda"] > 0) if "ev_ebitda" in f.columns else pd.Series(False, index=tickers)
        if ev_mask.any():
            value_score += vf["ev_ebitda"] * _rank(f.loc[ev_mask, "ev_ebitda"], ascending=False).reindex(tickers).fillna(0.5)

        # --- Quality score ---
        quality_score = pd.Series(0.0, index=tickers)

        roe_mask = f["roe"].notna() if "roe" in f.columns else pd.Series(False, index=tickers)
        if roe_mask.any():
            quality_score += qf["roe"] * _rank(f.loc[roe_mask, "roe"], ascending=True).reindex(tickers).fillna(0.5)

        nm_mask = f["net_margin"].notna() if "net_margin" in f.columns else pd.Series(False, index=tickers)
        if nm_mask.any():
            quality_score += qf["net_margin"] * _rank(f.loc[nm_mask, "net_margin"], ascending=True).reindex(tickers).fillna(0.5)

        de_mask = f["debt_equity"].notna() if "debt_equity" in f.columns else pd.Series(False, index=tickers)
        if de_mask.any():
            quality_score += qf["debt_equity"] * _rank(f.loc[de_mask, "debt_equity"], ascending=False).reindex(tickers).fillna(0.5)

        # --- Composite score ---
        quality_weight = blend.get("quality_weight", 0.0)
        composite = (
            blend["value_weight"]    * value_score
            + blend["momentum_weight"] * momentum_score
            + quality_weight           * quality_score
        )
        composite = composite.dropna()

        n_long = max(1, int(len(composite) * cfg["long_pct"]))
        n_short = max(1, int(len(composite) * cfg["short_pct"])) if enable_short else 0

        sorted_scores = composite.sort_values(ascending=False)
        long_tickers  = sorted_scores.head(n_long).index.tolist()
        short_tickers = sorted_scores.tail(n_short).index.tolist() if enable_short else []

        # Weight allocation: 120/20 when short book on, 100/0 when off
        long_weight  = cfg["long_weight"] / n_long
        short_weight = (cfg["short_weight"] / n_short) if (enable_short and n_short > 0) else 0.0

        rows = []
        for t in long_tickers:
            rows.append({
                "ticker":          t,
                "action":          "BUY",
                "weight":          round(long_weight, 4),
                "composite_score": round(composite[t], 4),
                "momentum_score":  round(float(momentum_score.get(t, np.nan)), 4),
                "value_score":     round(float(value_score.get(t, np.nan)), 4),
                "quality_score":   round(float(quality_score.get(t, np.nan)), 4),
                "pe_ratio":   f.loc[t, "pe_ratio"]   if "pe_ratio"   in f.columns and t in f.index else np.nan,
                "pb_ratio":   f.loc[t, "pb_ratio"]   if "pb_ratio"   in f.columns and t in f.index else np.nan,
                "fcf_yield":  f.loc[t, "fcf_yield"]  if "fcf_yield"  in f.columns and t in f.index else np.nan,
                "roe":        f.loc[t, "roe"]         if "roe"         in f.columns and t in f.index else np.nan,
                "net_margin": f.loc[t, "net_margin"]  if "net_margin" in f.columns and t in f.index else np.nan,
                "sector":     sector_map.get(t, ""),
            })
        for t in short_tickers:
            rows.append({
                "ticker":          t,
                "action":          "SHORT",
                "weight":          round(-short_weight, 4),
                "composite_score": round(composite[t], 4),
                "momentum_score":  round(float(momentum_score.get(t, np.nan)), 4),
                "value_score":     round(float(value_score.get(t, np.nan)), 4),
                "quality_score":   round(float(quality_score.get(t, np.nan)), 4),
                "pe_ratio":   f.loc[t, "pe_ratio"]   if "pe_ratio"   in f.columns and t in f.index else np.nan,
                "pb_ratio":   f.loc[t, "pb_ratio"]   if "pb_ratio"   in f.columns and t in f.index else np.nan,
                "fcf_yield":  f.loc[t, "fcf_yield"]  if "fcf_yield"  in f.columns and t in f.index else np.nan,
                "roe":        f.loc[t, "roe"]         if "roe"         in f.columns and t in f.index else np.nan,
                "net_margin": f.loc[t, "net_margin"]  if "net_margin" in f.columns and t in f.index else np.nan,
                "sector":     sector_map.get(t, ""),
            })

        return pd.DataFrame(rows)

    def describe_signal(self, signal_row: pd.Series) -> str:
        t = signal_row["ticker"]
        action = signal_row["action"]
        weight = abs(signal_row["weight"]) * 100
        comp = signal_row["composite_score"]
        mom  = signal_row["momentum_score"]
        val  = signal_row["value_score"]
        qual = signal_row.get("quality_score", float("nan"))
        pe   = signal_row.get("pe_ratio",   float("nan"))
        pb   = signal_row.get("pb_ratio",   float("nan"))
        fcf  = signal_row.get("fcf_yield",  float("nan"))
        roe  = signal_row.get("roe",         float("nan"))
        nm   = signal_row.get("net_margin",  float("nan"))
        sec  = signal_row.get("sector", "")

        direction = "LONG" if action == "BUY" else "SHORT"
        pe_str  = f"P/E {pe:.1f}"        if not (isinstance(pe, float) and np.isnan(pe))  else "P/E N/A"
        pb_str  = f"P/B {pb:.1f}"        if not (isinstance(pb, float) and np.isnan(pb))  else "P/B N/A"
        fcf_str = f"FCF {fcf*100:.1f}%"  if not (isinstance(fcf, float) and np.isnan(fcf)) else "FCF N/A"
        roe_str = f"ROE {roe*100:.1f}%"  if not (isinstance(roe, float) and np.isnan(roe)) else "ROE N/A"
        nm_str  = f"Margin {nm*100:.1f}%" if not (isinstance(nm, float) and np.isnan(nm))  else "Margin N/A"
        sec_str = f" [{sec}]" if sec else ""

        # Build WHY explanation from dominant drivers
        why_parts = []
        if action == "BUY":
            if val  >= 0.75: why_parts.append(f"cheap on fundamentals (value score {val:.2f})")
            if mom  >= 0.75: why_parts.append(f"strong 12-month price trend (momentum score {mom:.2f})")
            if not (isinstance(qual, float) and np.isnan(qual)) and qual >= 0.75:
                why_parts.append(f"high-quality business (quality score {qual:.2f})")
            if not why_parts:
                why_parts.append(f"top composite ranking across value + momentum + quality (score {comp:.2f})")
        else:
            if val  <= 0.25: why_parts.append(f"expensive on fundamentals (value score {val:.2f})")
            if mom  <= 0.25: why_parts.append(f"weak 12-month price trend (momentum score {mom:.2f})")
            if not (isinstance(qual, float) and np.isnan(qual)) and qual <= 0.25:
                why_parts.append(f"low-quality business (quality score {qual:.2f})")
            if not why_parts:
                why_parts.append(f"bottom composite ranking across value + momentum + quality (score {comp:.2f})")

        why = " and ".join(why_parts)

        return (
            f"{direction} {t}{sec_str} @ {weight:.1f}% of portfolio\n"
            f"  Composite score: {comp:.2f}  (value: {val:.2f}, momentum: {mom:.2f}, quality: {qual:.2f})\n"
            f"  {pe_str} | {pb_str} | {fcf_str} | {roe_str} | {nm_str}\n"
            f"  WHY: {t} ranks {'highly' if action == 'BUY' else 'poorly'} because it is {why}.\n"
            f"  HOW: {'Buy market order at open' if action == 'BUY' else 'Sell short at market open'}"
        )
