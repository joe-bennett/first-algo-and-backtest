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
            df = df[~df["Symbol"].str.startswith("$", na=False)]      # remove any remaining $ prefixes

            # Remove test issues
            if "Test Issue" in df.columns:
                df = df[df["Test Issue"] != "Y"]

            # Drop ETFs if not wanted
            if not include_etfs and "ETF" in df.columns:
                df = df[df["ETF"] != "Y"]

            # Drop warrants, units, and rights by security name
            if "Security Name" in df.columns:
                junk_pattern = r"\b(warrant|unit|right)s?\b"
                mask = df["Security Name"].str.lower().str.contains(junk_pattern, regex=True, na=False)
                df = df[~mask]

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
# Point-in-time S&P 500 membership (survivorship-bias-free backtesting)
# =============================================================================

_SP500_MEMBERS_CSV = ROOT / "data" / "sp500_historical_members.csv"
_SP500_MEMBERS_URL = (
    "https://raw.githubusercontent.com/fja05680/sp500/master/"
    "S%26P%20500%20Historical%20Components%20%26%20Changes.csv"
)


def _ensure_sp500_members_downloaded() -> None:
    """Download the historical S&P 500 membership CSV if not already on disk."""
    if _SP500_MEMBERS_CSV.exists():
        return
    print("Downloading historical S&P 500 membership data (one-time, ~2MB)...")
    resp = requests.get(_SP500_MEMBERS_URL, timeout=30)
    resp.raise_for_status()
    _SP500_MEMBERS_CSV.parent.mkdir(parents=True, exist_ok=True)
    _SP500_MEMBERS_CSV.write_bytes(resp.content)
    print(f"Saved to {_SP500_MEMBERS_CSV}")


def get_sp500_members_at(date: pd.Timestamp) -> list[str]:
    """
    Return the list of S&P 500 tickers that were members on a given date.
    Uses the fja05680/sp500 dataset (daily snapshots from 1996 to present).

    Tickers are normalised to yfinance format (dots → dashes, e.g. BRK.B → BRK-B).
    If the exact date is not in the dataset, the most recent prior date is used.
    """
    _ensure_sp500_members_downloaded()

    # Cache the parsed DataFrame in memory across calls within one process
    if not hasattr(get_sp500_members_at, "_df"):
        df = pd.read_csv(_SP500_MEMBERS_CSV)
        df.columns = df.columns.str.strip().str.lower()
        # Column names: 'date', 'tickers'
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        get_sp500_members_at._df = df

    df = get_sp500_members_at._df

    # Find the latest snapshot on or before the requested date
    available = df[df["date"] <= date]
    if available.empty:
        logger.warning(f"No S&P 500 membership data before {date.date()} — using earliest available.")
        available = df.head(1)

    tickers_str = available.iloc[-1]["tickers"]
    tickers = []
    for t in tickers_str.split(","):
        t = t.strip()
        if not t:
            continue
        # Strip removal-date annotations like "GGP-201808" → "GGP"
        # A valid removal annotation is a dash followed by exactly 6 digits at the end
        import re
        t = re.sub(r"-\d{6}$", "", t)
        t = t.replace(".", "-")  # normalise to yfinance format
        if t:
            tickers.append(t)
    return tickers


_SP_MIDSMALL_CACHE_KEY = "sp_midsmall_current"


def _get_midsmall_tickers() -> set[str]:
    """
    Return current S&P MidCap 400 + SmallCap 600 tickers from Wikipedia.
    Cached for 24 hours. Used as the mid/small component for sp1500 backtesting.

    NOTE: This is today's membership list. No free point-in-time dataset exists for
    S&P 400/600, so mid/small components carry modest survivorship bias in backtests.
    The S&P 500 component uses the accurate historical dataset.
    """
    cached = _load_cache(_SP_MIDSMALL_CACHE_KEY, ttl_hours=24.0)
    if cached is not None:
        return set(cached)

    tickers = []
    # S&P 400 and S&P 600 Wikipedia tables use "Symbol" column (not "Ticker symbol")
    for url in [
        "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
    ]:
        try:
            tables = _read_wiki_html(url)
            for t in tables:
                if "Symbol" in t.columns:
                    tickers += t["Symbol"].str.replace(".", "-", regex=False).tolist()
                    break
        except Exception as e:
            logger.warning(f"Could not fetch mid/small tickers from {url}: {e}")

    _save_cache(_SP_MIDSMALL_CACHE_KEY, tickers)
    return set(tickers)


def get_sp1500_members_at(date: pd.Timestamp) -> list[str]:
    """
    Return S&P 1500 tickers (S&P 500 + MidCap 400 + SmallCap 600) for a given date.

    S&P 500 component:    point-in-time historical dataset — no survivorship bias.
    S&P 400/600 component: current Wikipedia list — modest survivorship bias
                           (no free historical dataset available for these indices).
    """
    sp500 = set(get_sp500_members_at(date))
    midsmall = _get_midsmall_tickers()
    return list(sp500 | midsmall)


def get_index_members_at(date: pd.Timestamp, universe: str = "sp500") -> list[str]:
    """
    Dispatcher: return index members at a given date for the configured universe.

    universe: "sp500" | "sp1500"  (other presets fall back to sp500)
    """
    if universe == "sp1500":
        return get_sp1500_members_at(date)
    return get_sp500_members_at(date)


_SECTOR_CACHE_KEY = "sp500_sectors"


def get_sector_map() -> dict[str, str]:
    """
    Return {ticker: GICS sector} for all S&P 1500 members from Wikipedia.
    Covers S&P 500, S&P MidCap 400, and S&P SmallCap 600.
    Used for sector neutralization in the strategy (ranking within sector).

    Cached for 24 hours. Returns an empty dict on failure (strategy falls back to
    global ranking gracefully).
    """
    cached = _load_cache(_SECTOR_CACHE_KEY, ttl_hours=24.0)
    if cached is not None:
        return cached

    # Each Wikipedia table has "Symbol" and "GICS Sector" columns
    sources = [
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
    ]
    headers = {"User-Agent": "Mozilla/5.0 (compatible; algo-trading-bot/1.0)"}
    sector_map: dict[str, str] = {}
    for url in sources:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            tables = pd.read_html(io.StringIO(resp.text))
            for table in tables:
                if "Symbol" in table.columns and "GICS Sector" in table.columns:
                    chunk = dict(zip(
                        table["Symbol"].str.replace(".", "-", regex=False),
                        table["GICS Sector"],
                    ))
                    sector_map.update(chunk)
                    break
        except Exception as e:
            logger.warning(f"Could not fetch sector map from {url}: {e}")

    if sector_map:
        _save_cache(_SECTOR_CACHE_KEY, sector_map)
    return sector_map


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
    import yfinance as yf

    def _fetch_one(ticker: str) -> tuple[str, pd.DataFrame | None]:
        try:
            # auto_adjust=True returns dividend and split-adjusted close prices
            df = yf.download(
                ticker,
                start=start,
                end=end,
                interval=interval,
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            if df.empty:
                return ticker, None
            close = df["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close = close.rename(ticker)
            return ticker, close.to_frame()
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

    result = pd.concat(frames.values(), axis=1)
    result.index = pd.to_datetime(result.index)
    result = result.sort_index()
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
    Returns key valuation and quality metrics for each ticker via yfinance.
    Columns: pe_ratio, pb_ratio, fcf_yield, ev_ebitda, market_cap,
             roe, net_margin, debt_equity

    Parallelized — large universes still take several minutes on first run,
    but results are cached for 24 hours.
    """
    cache_key = f"fundamentals_v2_{len(tickers)}"
    cached = _load_cache(cache_key, cache_ttl_hours)
    if cached is not None:
        return cached

    import yfinance as yf

    def _fetch_one(ticker: str) -> dict | None:
        try:
            info = yf.Ticker(ticker).info

            mktcap = info.get("marketCap") or np.nan

            # Value factors
            pe_ratio  = info.get("trailingPE")        or np.nan
            pb_ratio  = info.get("priceToBook")        or np.nan
            ev_ebitda = info.get("enterpriseToEbitda") or np.nan

            # FCF yield = freeCashflow / marketCap
            fcf = info.get("freeCashflow")
            fcf_yield = (float(fcf) / float(mktcap)
                         if fcf and mktcap and np.isfinite(mktcap)
                         else np.nan)

            # Quality factors (yfinance returns these as ratios: 0.15 = 15%)
            roe        = info.get("returnOnEquity") or np.nan
            net_margin = info.get("profitMargins")  or np.nan
            # debtToEquity from yfinance is D/E × 100 (e.g. 150 = 1.5× D/E)
            de_raw     = info.get("debtToEquity")
            debt_equity = float(de_raw) / 100.0 if de_raw is not None else np.nan

            return {
                "ticker":      ticker,
                "pe_ratio":    pe_ratio,
                "pb_ratio":    pb_ratio,
                "fcf_yield":   fcf_yield,
                "ev_ebitda":   ev_ebitda,
                "market_cap":  mktcap,
                "roe":         roe,
                "net_margin":  net_margin,
                "debt_equity": debt_equity,
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

def get_options_chain(ticker: str, expiry: str | None = None, retries: int = 3) -> pd.DataFrame:
    """
    Returns options chain for a ticker.
    Retries up to `retries` times on rate-limit errors, with increasing delays.
    """
    for attempt in range(retries):
        try:
            result = obb.derivatives.options.chains(
                symbol=ticker,
                provider="yfinance",
                expiration=expiry,
            )
            return result.to_df()
        except Exception as e:
            err = str(e).lower()
            if any(kw in err for kw in ("rate", "too many", "429", "limit")):
                wait = 10 * (attempt + 1)  # 10s, 20s, 30s
                logger.warning(f"Rate limited fetching options for {ticker} — waiting {wait}s (attempt {attempt+1}/{retries})")
                time.sleep(wait)
            else:
                logger.warning(f"Could not fetch options for {ticker}: {e}")
                return pd.DataFrame()
    logger.warning(f"Could not fetch options for {ticker} after {retries} attempts.")
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
