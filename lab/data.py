"""
Where prices come from.

- TradingView's screener service: the whole US market in one request (screen, breadth, earnings dates).
- Yahoo Finance (yfinance): daily and hourly bars, free, no key.
- Massive (formerly Polygon): backup for any symbol Yahoo misses. Free tier = 5 calls a minute,
  so it is only used for a handful of symbols. Needs the MASSIVE_API_KEY secret.
"""

import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

ET = ZoneInfo("America/New_York")
SCAN_URL = "https://scanner.tradingview.com/america/scan"


def now_et() -> datetime:
    return datetime.now(ET)


# --------------------------------------------------------------------- TradingView
def tv_filter(left, op, right):
    return {"left": left, "operation": op, "right": right}


def tv_scan(columns, filters=None, tickers=None, sort=None, limit=5000):
    """One POST to TradingView's screener. Returns a DataFrame with one row per symbol."""
    payload = {
        "markets": ["america"],
        "symbols": {"query": {"types": []}, "tickers": tickers or []},
        "options": {"lang": "en"},
        "columns": columns,
        "range": [0, limit],
    }
    if filters:
        payload["filter"] = filters
    if sort:
        payload["sort"] = {"sortBy": sort[0], "sortOrder": sort[1]}
    headers = {
        "Content-Type": "text/plain;charset=UTF-8",
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/",
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    }
    cookies = {}
    sid = os.environ.get("TV_SESSIONID", "").strip()
    if sid:
        cookies["sessionid"] = sid
    for attempt in range(1, 4):
        r = requests.post(SCAN_URL, data=json.dumps(payload), headers=headers,
                          cookies=cookies, timeout=30)
        if r.status_code == 429:
            print(f"TradingView rate limit (attempt {attempt}/3), waiting 30s")
            time.sleep(30)
            continue
        if r.status_code != 200:
            raise RuntimeError(f"TradingView HTTP {r.status_code}: {r.text[:300]}")
        rows = []
        for row in r.json().get("data", []):
            d = dict(zip(columns, row.get("d", [])))
            d["symbol"] = row.get("s", "")
            rows.append(d)
        return pd.DataFrame(rows, columns=["symbol"] + columns)
    raise RuntimeError("TradingView still rate-limited after 3 attempts")


def base_filters(exchanges):
    return [
        tv_filter("type", "equal", "stock"),
        tv_filter("typespecs", "has", ["common"]),
        tv_filter("is_primary", "equal", True),
        tv_filter("active_symbol", "equal", True),
        tv_filter("exchange", "in_range", exchanges),
    ]


def tv_details(tv_symbols, columns=("earnings_release_next_date", "sector", "market_cap_basic")):
    """Current earnings date, sector, etc. for a list like ['NASDAQ:AAPL', ...]."""
    if not tv_symbols:
        return pd.DataFrame(columns=["symbol", *columns])
    return tv_scan(list(columns), tickers=list(tv_symbols), limit=len(tv_symbols))


# ------------------------------------------------------------------------- Yahoo
YAHOO_SPECIAL = {"CBOE:VIX": "^VIX", "TVC:VIX": "^VIX"}


def yahoo_symbol(tv_symbol: str) -> str:
    if tv_symbol in YAHOO_SPECIAL:
        return YAHOO_SPECIAL[tv_symbol]
    return tv_symbol.split(":")[-1].replace(".", "-")


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
    return df.dropna(subset=["open", "high", "low", "close"]).astype(float)


def yahoo_bars(tv_symbols, interval="1d", period="2y"):
    """{tv_symbol: DataFrame(open, high, low, close, volume)}. Unadjusted for dividends."""
    import yfinance as yf

    out = {}
    syms = list(dict.fromkeys(tv_symbols))
    for i in range(0, len(syms), 100):
        chunk = syms[i:i + 100]
        tick = [yahoo_symbol(s) for s in chunk]
        data = None
        for attempt in range(3):
            try:
                data = yf.download(tick, period=period, interval=interval, group_by="ticker",
                                   auto_adjust=False, progress=False, threads=True)
                break
            except Exception as e:  # Yahoo hiccups now and then
                print(f"Yahoo download failed ({e}); retry {attempt + 1}/3")
                time.sleep(15)
        if data is None or data.empty:
            continue
        for s, t in zip(chunk, tick):
            try:
                df = data[t] if isinstance(data.columns, pd.MultiIndex) else data
                df = _normalize(df)
            except Exception:
                continue
            if len(df):
                if interval != "1d":
                    df.index = df.index.tz_convert(ET)
                else:
                    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
                out[s] = df
    return out


# ----------------------------------------------------------------------- Massive
def massive_daily(tv_symbol, days=730):
    """Backup source for daily bars. Returns a DataFrame or None.
    Waits 13s per call to respect the free tier's 5 calls a minute.
    (Hourly bars are Yahoo-only: Massive's hourly bars start on the hour, not at 9:30.)"""
    key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if not key:
        return None
    end = date.today()
    start = end - timedelta(days=days)
    url = (f"https://api.massive.com/v2/aggs/ticker/{tv_symbol.split(':')[-1]}/range/"
           f"1/day/{start}/{end}")
    time.sleep(13)
    try:
        r = requests.get(url, params={"adjusted": "false", "sort": "asc", "limit": 50000},
                         headers={"Authorization": f"Bearer {key}"}, timeout=30)
        res = r.json().get("results") if r.status_code == 200 else None
    except Exception:
        res = None
    if not res:
        return None
    df = pd.DataFrame(res).rename(columns={"o": "open", "h": "high", "l": "low",
                                           "c": "close", "v": "volume"})
    idx = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert(ET)
    df.index = pd.DatetimeIndex(idx.dt.tz_localize(None).dt.normalize())
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def get_bars(tv_symbols, interval="1d", period="2y", max_backup=8):
    bars = yahoo_bars(tv_symbols, interval, period)
    missing = [s for s in tv_symbols if s not in bars]
    if missing:
        print(f"Yahoo missed {len(missing)} {interval} symbols: {missing[:10]}")
    if missing and interval == "1d":
        for s in missing[:max_backup]:
            df = massive_daily(s)
            if df is not None and len(df):
                bars[s] = df
    return bars


def log(msg):
    print(f"[{now_et():%H:%M:%S}] {msg}", file=sys.stdout, flush=True)
