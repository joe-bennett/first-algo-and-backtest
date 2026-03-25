"""
Centralized data fetching via OpenBB (yfinance provider — no API key needed).
All other modules should import from here rather than calling yfinance directly.

Supports universe presets: all_us | sp500 | sp1500 | nasdaq100 | custom
All universe/filter parameters are read from config/universe.yaml.
"""

import io
import json
import time
import pickle
import logging
import requests
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from openbb import obb

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
CACHE_DIR = ROOT / "data" / "cache"
RAW_DIR = ROOT / "data" / "raw"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# Cache helpers
# =============================================================================

def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.pkl"


def _load_cache(key: str, ttl_hours: float) -> object | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    age_hours = (time.time() - path.stat().st_mtime) / 3600
    if age_hours > ttl_hours:
        return None
    with open(path, "rb") as f:
        return pickle.load(f)


def _save_cache(key: str, obj: object) -> None:
    with open(_cache_path(key), "wb") as f:
        pickle.dump(obj, f)


# =============================================================================
# Universe — ticker list fetching
# =============================================================================

def get_universe_tickers(universe_cfg: dict | None = None) -> list[str]:
    """
    Return a filtered list of tickers based on universe.yaml config.
    Caches the raw ticker list to avoid repeated downloads.

    Parameters
    ----------
    universe_cfg : dict, optional
        Pass a loaded universe config dict. If None, reads from config/universe.yaml.
    """
    import yaml
    if universe_cfg is None:
        with open(ROOT / "config" / "universe.yaml", encoding="utf-8") as f:
            universe_cfg = yaml.safe_load(f)

    preset_name = universe_cfg.get("preset", "sp500")
    preset = universe_cfg["presets"][preset_name]
    cache_ttl = universe_cfg["cache"]["ticker_list_ttl_hours"]
    cache_key = f"universe_{preset_name}"

    cached = _load_cache(cache_key, cache_ttl)
    if cached is not None:
        logger.info(f"Universe '{preset_name}' loaded from cache ({len(cached)} tickers).")
        return cached

    source = preset["source"]
    raw_tickers = _fetch_raw_tickers(source, preset, universe_cfg)

    filtered = _apply_filters(raw_tickers, universe_cfg)

    _save_cache(cache_key, filtered)
    logger.info(f"Universe '{preset_name}': {len(raw_tickers)} raw → {len(filtered)} after filters.")
    return filtered


def _fetch_raw_tickers(source: str, preset: dict, cfg: dict) -> list[str]:
    """Fetch raw ticker list from the appropriate source."""
    if source == "nasdaq_ftp":
        return _fetch_nasdaq_ftp(cfg)
    elif source == "wikipedia":
        return _fetch_sp500_wikipedia()
    elif source == "sp1500_wikipedia":
        return _fetch_sp1500_wikipedia()
    elif source == "wikipedia_nasdaq100":
        return _fetch_nasdaq100_wikipedia()
    elif source == "custom":
        return preset.get("tickers", [])
    else:
        raise ValueError(f"Unknown universe source: {source}")


def _fetch_nasdaq_ftp(cfg: dict) -> list[str]:
    """
    Fetch all exchange-listed US equities from NASDAQ's public FTP.
    Covers NASDAQ, NYSE, and AMEX. Free, no authentication.
    Returns a deduplicated, cleaned ticker list.
    """
    base_url = "https://www.nasdaqtrader.com/dynamic/SymDir"
    files = {
        "NASDAQ": f"{base_url}/nasdaqlisted.txt",
        "NYSE/AMEX": f"{base_url}/otherlisted.txt",
    }
    tickers = []
    filters = cfg.get("filters", {})
    include_etfs = filters.get("include_etfs", False)
    include_spacs = filters.get("include_spacs", False)
    include_adrs = filters.get("include_adrs", True)

    for exchange, url in files.items():
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text), sep="|")
            df = df[df["Symbol"].notna()]
            df = df[~df["Symbol"].str.contains(r"[$^]", regex=True)]  # remove test symbols

            # Drop ETFs if not wanted
            if not include_etfs and "ETF" in df.columns:
                df = df[df["ETF"] != "Y"]

            # Drop SPACs (common patterns in name)
            if not include_spacs and "Security Name" in df.columns:
                spac_pattern = r"(acquisition|blank check|special purpose)"
                mask = df["Security Name"].str.lower().str.contains(spac_pattern, regex=True, na=False)
                df = df[~mask]

            # Normalize ticker format (yfinance uses - not .)
            syms = df["Symbol"].str.strip().str.replace(r"\.", "-", regex=True).tolist()
            tickers.extend(syms)
        except Exception as e:
            logger.warning(f"Failed to fetch {exchange} from NASDAQ FTP: {e}")

    return list(dict.fromkeys(tickers))  # deduplicate, preserve order


_WIKI_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; trading-research-bot/1.0)"}


def _read_wiki_html(url: str) -> list:
    import io, urllib.request
    req = urllib.request.Request(url, headers=_WIKI_HEADERS)
    with urllib.request.urlopen(req) as resp:
        html = resp.read()
    return pd.read_html(io.BytesIO(html))


def _fetch_sp500_wikipedia() -> list[str]:
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    df = _read_wiki_html(url)[0]
    return df["Symbol"].str.replace(".", "-", regex=False).tolist()


def _fetch_sp1500_wikipedia() -> list[str]:
    """S&P 500 + S&P MidCap 400 + S&P SmallCap 600."""
    tickers = _fetch_sp500_wikipedia()
    for url, col in [
        ("https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", "Ticker symbol"),
        ("https://en.wikipedia.org/wiki/List_of_S%26P_600_companies", "Ticker symbol"),
    ]:
        try:
            tables = _read_wiki_html(url)
            for t in tables:
                if col in t.columns:
                    tickers += t[col].str.replace(".", "-", regex=False).tolist()
                    break
        except Exception as e:
            logger.warning(f"Could not fetch from {url}: {e}")
    return list(dict.fromkeys(tickers))


def _fetch_nasdaq100_wikipedia() -> list[str]:
    url = "https://en.wikipedia.org/wiki/Nasdaq-100"
    tables = _read_wiki_html(url)
    for t in tables:
        if "Ticker" in t.columns:
            return t["Ticker"].str.replace(".", "-", regex=False).tolist()
    raise RuntimeError("Could not parse NASDAQ 100 from Wikipedia.")


def _apply_filters(tickers: list[str], cfg: dict) -> list[str]:
    """
    Apply price/volume/market-cap filters using yfinance batch info.
    Processes in chunks to avoid rate limits. Shows a progress counter.
    """
    filters = cfg.get("filters", {})
    min_price = filters.get("min_price", 1.0)
    min_mktcap = filters.get("min_market_cap_M", 0) * 1e6
    min_volume = filters.get("min_avg_daily_volume", 0)
    min_dollar_vol = filters.get("min_avg_daily_dollar_volume_M", 0) * 1e6
    exclusions = cfg.get("exclusions", {}).get("tickers", [])
    inclusions = cfg.get("inclusions", {}).get("tickers", [])

    # Remove explicit exclusions
    tickers = [t for t in tickers if t not in exclusions]

    # If no filters are active, return as-is plus inclusions
    if min_price <= 0 and min_mktcap <= 0 and min_volume <= 0:
        return list(dict.fromkeys(tickers + inclusions))

    import yfinance as yf

    passed = []
    chunk_size = 100
    chunks = [tickers[i:i+chunk_size] for i in range(0, len(tickers), chunk_size)]
    total = len(tickers)
    processed = 0

    print(f"Filtering {total} tickers (price >= ${min_price}, "
          f"mktcap >= ${min_mktcap/1e6:.0f}M, volume >= {min_volume:,})...")

    for chunk in chunks:
        try:
            data = yf.Tickers(" ".join(chunk))
            for ticker in chunk:
                try:
                    info = data.tickers[ticker].fast_info
                    price = getattr(info, "last_price", 0) or 0
                    mktcap = getattr(info, "market_cap", 0) or 0
                    volume = getattr(info, "three_month_average_volume", 0) or 0
                    dollar_vol = price * volume

                    if price < min_price:
                        continue
                    if mktcap < min_mktcap:
                        continue
                    if volume < min_volume:
                        continue
                    if dollar_vol < min_dollar_vol:
                        continue
                    passed.append(ticker)
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"Batch filter chunk failed: {e}")

        processed += len(chunk)
        print(f"  {processed}/{total} checked — {len(passed)} passing so far", end="\r")

    print(f"\nFiltering complete: {len(passed)} tickers passed.")

    # Force-include any explicit inclusions
    for t in inclusions:
        if t not in passed:
            passed.append(t)

    return passed


# Backwards-compatible alias
def get_sp500_tickers() -> list[str]:
    return _fetch_sp500_wikipedia()


# =============================================================================
# Price data — batched with caching
# =============================================================================

def get_price_history(
    tickers: list[str],
    start: str,
    end: str | None = None,
    interval: str = "1d",
    max_workers: int = 10,
    cache_ttl_hours: float = 4.0,
) -> pd.DataFrame:
    """
    Returns a DataFrame of adjusted closing prices.
    Columns = tickers, index = date.

    Fetches in parallel batches; caches results to disk.
    Large universes (1000+ tickers) will take several minutes on first run.
    """
    end = end or datetime.today().strftime("%Y-%m-%d")
    cache_key = f"prices_{start}_{end}_{len(tickers)}_{interval}"
    cached = _load_cache(cache_key, cache_ttl_hours)
    if cached is not None:
        return cached

    frames = {}

    def _fetch_one(ticker: str) -> tuple[str, pd.DataFrame | None]:
        try:
            result = obb.equity.price.historical(
                symbol=ticker,
                start_date=start,
                end_date=end,
                interval=interval,
                provider="yfinance",
            )
            df = result.to_df()[["close"]].rename(columns={"close": ticker})
            return ticker, df
        except Exception:
            return ticker, None

    print(f"Fetching price history for {len(tickers)} tickers ({start} to {end})...")
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one, t): t for t in tickers}
        done = 0
        for future in as_completed(futures):
            ticker, df = future.result()
            if df is not None:
                frames[ticker] = df
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(tickers)} fetched", end="\r")

    print(f"\nPrice fetch complete: {len(frames)}/{len(tickers)} tickers returned data.")

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames.values(), axis=1).sort_index()
    _save_cache(cache_key, result)
    return result


# =============================================================================
# Fundamental data — batched with caching
# =============================================================================

def get_fundamentals(
    tickers: list[str],
    max_workers: int = 10,
    cache_ttl_hours: float = 24.0,
) -> pd.DataFrame:
    """
    Returns key valuation metrics for each ticker.
    Columns: pe_ratio, pb_ratio, fcf_yield, ev_ebitda, market_cap

    Parallelized — large universes still take several minutes on first run,
    but results are cached for 24 hours.
    """
    cache_key = f"fundamentals_{len(tickers)}"
    cached = _load_cache(cache_key, cache_ttl_hours)
    if cached is not None:
        return cached

    def _fetch_one(ticker: str) -> dict | None:
        try:
            result = obb.equity.fundamental.metrics(
                symbol=ticker,
                provider="yfinance",
            )
            df = result.to_df()
            if df.empty:
                return None
            row = df.iloc[-1]
            return {
                "ticker": ticker,
                "pe_ratio": row.get("pe_ratio", np.nan),
                "pb_ratio": row.get("pb_ratio", np.nan),
                "fcf_yield": row.get("fcf_yield", np.nan),
                "ev_ebitda": row.get("ev_ebitda", np.nan),
                "market_cap": row.get("market_cap", np.nan),
            }
        except Exception:
            return None

    print(f"Fetching fundamentals for {len(tickers)} tickers...")
    records = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one, t): t for t in tickers}
        done = 0
        for future in as_completed(futures):
            rec = future.result()
            if rec is not None:
                records.append(rec)
            done += 1
            if done % 50 == 0:
                print(f"  {done}/{len(tickers)} fetched", end="\r")

    print(f"\nFundamentals complete: {len(records)}/{len(tickers)} tickers returned data.")

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records).set_index("ticker")
    _save_cache(cache_key, df)
    return df


# =============================================================================
# Options data (for iron condor screening)
# =============================================================================

def get_options_chain(ticker: str, expiry: str | None = None) -> pd.DataFrame:
    """Returns options chain for a ticker."""
    try:
        result = obb.derivatives.options.chains(
            symbol=ticker,
            provider="yfinance",
            expiration=expiry,
        )
        return result.to_df()
    except Exception as e:
        logger.warning(f"Could not fetch options for {ticker}: {e}")
        return pd.DataFrame()


def get_iv_rank(ticker: str, lookback_days: int = 252) -> float | None:
    """
    Approximate IV Rank: where is current IV vs its 52-week range?
    IV Rank = (current IV - 52w low) / (52w high - 52w low) * 100
    Uses ATM implied vol from options chain as proxy.
    """
    try:
        chain = get_options_chain(ticker)
        if chain.empty:
            return None

        price_result = obb.equity.price.quote(symbol=ticker, provider="yfinance")
        current_price = price_result.to_df()["last_price"].iloc[0]

        atm = chain[abs(chain["strike"] - current_price) < current_price * 0.02]
        if atm.empty:
            return None
        current_iv = atm["implied_volatility"].mean()

        end = datetime.today().strftime("%Y-%m-%d")
        start = (datetime.today() - timedelta(days=lookback_days + 30)).strftime("%Y-%m-%d")
        prices = get_price_history([ticker], start=start, end=end)
        if prices.empty:
            return None

        returns = prices[ticker].pct_change().dropna()
        rolling_iv = returns.rolling(30).std() * np.sqrt(252)
        iv_52w_low = rolling_iv.min()
        iv_52w_high = rolling_iv.max()

        if iv_52w_high == iv_52w_low:
            return None

        return round(float((current_iv - iv_52w_low) / (iv_52w_high - iv_52w_low) * 100), 1)
    except Exception:
        return None
