"""
News in the 48 hours BEFORE a signal fired (never after), from Massive's news API.

Each article Massive returns can carry per-ticker sentiment ("insights"). The signal's
tone is the majority of those labels for its own ticker; ties and no labels = neutral.
The Sunday review adds a second opinion from TradingView's news (source = tradingview).
"""

import os
import time
from collections import Counter

import pandas as pd
import requests

URL = "https://api.massive.com/v2/reference/news"
COLUMNS = ["signal_id", "symbol", "trigger_time", "source", "headlines_48h", "news_tone",
           "positive", "negative", "neutral", "top_headline"]


def tone_from(articles: list, ticker: str) -> dict:
    """Count headlines and sentiment labels for one ticker. Pure function (tested)."""
    labels = []
    for a in articles:
        for ins in a.get("insights") or []:
            if ins.get("ticker") == ticker and ins.get("sentiment") in ("positive", "negative", "neutral"):
                labels.append(ins["sentiment"])
    c = Counter(labels)
    if not articles:
        tone = "none"
    elif c["positive"] > c["negative"]:
        tone = "positive"
    elif c["negative"] > c["positive"]:
        tone = "negative"
    else:
        tone = "neutral"
    top = ""
    if articles:
        top = str(articles[0].get("title", ""))[:80]
    return {"headlines_48h": len(articles), "news_tone": tone, "positive": c["positive"],
            "negative": c["negative"], "neutral": c["neutral"], "top_headline": top}


def massive_news(tv_symbol: str, trigger_time: str, hours: int = 48) -> dict | None:
    """Headlines about the stock published in the `hours` before trigger_time. None if unavailable."""
    key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if not key:
        return None
    end = pd.Timestamp(trigger_time).tz_convert("UTC")
    start = end - pd.Timedelta(hours=hours)
    ticker = tv_symbol.split(":")[-1]
    params = {
        "ticker": ticker,
        "published_utc.gte": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "published_utc.lt": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "order": "desc",
        "sort": "published_utc",
        "limit": 100,
    }
    time.sleep(13)  # free tier: 5 calls a minute, shared with the daily-bar backup
    try:
        r = requests.get(URL, params=params, headers={"Authorization": f"Bearer {key}"}, timeout=30)
        if r.status_code == 429:
            time.sleep(60)
            r = requests.get(URL, params=params, headers={"Authorization": f"Bearer {key}"}, timeout=30)
        if r.status_code != 200:
            return None
        articles = r.json().get("results") or []
    except Exception:
        return None
    # belt and braces: drop anything not strictly before the trigger
    articles = [a for a in articles if pd.Timestamp(a.get("published_utc", "2100-01-01")) < end]
    return tone_from(articles, ticker)


def tag_signal(signal_id: str, tv_symbol: str, trigger_time: str) -> dict | None:
    res = massive_news(tv_symbol, trigger_time)
    if res is None:
        return None
    return {"signal_id": signal_id, "symbol": tv_symbol, "trigger_time": trigger_time,
            "source": "massive", **res}
