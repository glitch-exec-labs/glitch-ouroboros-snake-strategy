"""
news_guard.py
Two-layer news filter:
  1. Static time-window blackout (no API call, instant) — conservative: blocks
     all recurring high-impact windows every week.
  2. Brave Search live news check — symbol-specific queries, cached 5 min,
     fail-open (returns False on any API error so trading is never stuck).
"""
import time
import requests
from datetime import datetime, timezone, timedelta

BRAVE_API_KEY = "BSA6fJYRU5hT2r55TvOgAxmvMfmcbbP"
BRAVE_URL = "https://api.search.brave.com/res/v1/news/search"

# Cache: {symbol: (unix_ts_fetched, result_bool)}
_news_cache: dict[str, tuple[float, bool]] = {}
CACHE_TTL = 300  # 5 minutes

# Symbol-specific search queries — more precise than a generic query
_SYMBOL_QUERIES: dict[str, str] = {
    "XAUUSD":    "gold price federal reserve interest rate inflation news high impact",
    "XAUUSD.s":  "gold price federal reserve interest rate inflation news high impact",
    "WTIcash-1": "crude oil OPEC EIA inventory production cut price news",
    "USOUSD":    "crude oil OPEC EIA inventory production cut price news",
    "USOUSD.s":  "crude oil OPEC EIA inventory production cut price news",
    "EURUSD":    "EUR euro ECB european central bank rate decision inflation",
    "EURUSD.s":  "EUR euro ECB european central bank rate decision inflation",
    "USDJPY":    "USD JPY yen BOJ bank of japan fed rate decision",
    "USDJPY.s":  "USD JPY yen BOJ bank of japan fed rate decision",
    "BTCUSD":    "bitcoin crypto SEC regulation crash liquidity market impact",
    "ETHUSD":    "ethereum crypto regulation market crash impact",
    "SOLUSD":    "solana crypto market crash regulation impact",
}
_DEFAULT_QUERY = "forex high impact economic news {symbol} next 30 minutes"

HIGH_IMPACT_KEYWORDS = [
    "nfp", "non-farm", "payroll",
    "cpi", "inflation", "ppi", "core price",
    "fomc", "fed rate", "federal reserve", "interest rate", "rate decision",
    "rate hike", "rate cut",
    "boe", "bank of england",
    "ecb", "european central bank",
    "boj", "bank of japan",
    "rba", "reserve bank",
    "gdp", "gross domestic product",
    "ism", "pmI", "purchasing managers",
    "retail sales", "jobless claims", "unemployment",
    "adp payroll", "adp employment",
    "opec", "eia crude", "oil inventory",
    "central bank",
]


def is_news_blackout(now_utc: datetime | None = None) -> bool:
    """
    Returns True if current time falls inside a high-impact news window.
    Conservative: blocks the window every week even if the event
    doesn't occur that specific week.

    UTC windows:
      Wednesday  13:15–14:00  US CPI / ADP payroll
      Wednesday  18:45–19:30  FOMC statement
      Thursday   11:50–13:10  BOE rate decision
      Thursday   13:15–14:15  ECB / US jobless claims / PPI
      Friday     13:15–14:00  NFP
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    wd = now_utc.weekday()   # 0=Mon … 6=Sun
    hm = now_utc.hour * 60 + now_utc.minute

    if wd == 2:  # Wednesday
        if 795 <= hm <= 840:    # 13:15–14:00  US CPI / ADP
            return True
        if 1125 <= hm <= 1170:  # 18:45–19:30  FOMC
            return True

    if wd == 3:  # Thursday
        if 710 <= hm <= 790:    # 11:50–13:10  BOE
            return True
        if 795 <= hm <= 855:    # 13:15–14:15  ECB / jobless claims / PPI
            return True

    if wd == 4:  # Friday
        if 795 <= hm <= 840:    # 13:15–14:00  NFP
            return True

    return False


def is_live_news_risk(symbol: str) -> bool:
    """
    Returns True if Brave news search detects a high-impact event for symbol.
    Cached per symbol for 5 minutes. Fails open on any error.
    """
    now = time.monotonic()
    cached = _news_cache.get(symbol)
    if cached:
        ts, result = cached
        if now - ts < CACHE_TTL:
            return result

    try:
        query = _SYMBOL_QUERIES.get(symbol, _DEFAULT_QUERY.format(symbol=symbol))
        resp = requests.get(
            BRAVE_URL,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": BRAVE_API_KEY,
            },
            params={"q": query, "count": 5, "freshness": "ph"},  # past hour
            timeout=4.0,
        )
        if resp.status_code != 200:
            _news_cache[symbol] = (now, False)
            return False

        results = resp.json().get("results", [])
        cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
        fresh_results = []
        for r in results:
            page_age = r.get("page_age", "")
            try:
                pub = datetime.fromisoformat(page_age).replace(tzinfo=timezone.utc)
                if pub >= cutoff:
                    fresh_results.append(r)
            except Exception:
                fresh_results.append(r)  # no date → include to be safe

        title_blob = " ".join(
            (r.get("title", "") + " " + r.get("description", "")).lower()
            for r in fresh_results
        )
        hit = any(kw in title_blob for kw in HIGH_IMPACT_KEYWORDS)
        _news_cache[symbol] = (now, hit)
        return hit

    except Exception:
        # Fail open — don't block trading if API is unreachable
        _news_cache[symbol] = (now, False)
        return False


def should_skip_trade(symbol: str, now_utc: datetime | None = None) -> bool:
    """
    Master check. Returns True if trade entry should be skipped due to news.
    Call this before every entry signal.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    if is_news_blackout(now_utc):
        return True
    if is_live_news_risk(symbol):
        return True
    return False
