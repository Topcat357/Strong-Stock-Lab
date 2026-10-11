"""Layer 1: the traffic light. Computed at each close; it applies to the NEXT session."""

import pandas as pd

from . import calendar, config
from .indicators import sma


def event_on(events: pd.DataFrame, day) -> str:
    if events is None or events.empty:
        return ""
    hits = events[pd.to_datetime(events["date"]).dt.normalize() == pd.Timestamp(day).normalize()]
    return "; ".join(hits["event"].astype(str)) if len(hits) else ""


def light(spy_close, spy50, spy200, vix, breadth, event_next) -> tuple[str, str]:
    """Returns (light, reason). The worst input wins."""
    m = config.MACRO
    reds, yellows = [], []
    if spy_close < spy200:
        reds.append("SPY below 200-day")
    if vix is not None and vix > m["vix_red_min"]:
        reds.append(f"VIX {vix:.1f}")
    if event_next:
        reds.append(f"event: {event_next}")
    if reds:
        return "red", "; ".join(reds)
    if not (spy_close > spy50 and spy50 > spy200):
        yellows.append("SPY not above a rising 50/200 stack")
    if vix is not None and vix >= m["vix_green_max"]:
        yellows.append(f"VIX {vix:.1f}")
    if breadth is not None and breadth < m["breadth_green_min"]:
        yellows.append(f"breadth {breadth:.0f}%")
    if yellows:
        return "yellow", "; ".join(yellows)
    return "green", "all clear"


def macro_row(day, spy: pd.DataFrame, vix: pd.DataFrame, breadth, events) -> dict:
    """spy / vix are daily bars; only bars up to and including `day` are used."""
    day = pd.Timestamp(day).normalize()
    s = spy[spy.index <= day]["close"]
    v = vix[vix.index <= day]["close"] if vix is not None and len(vix) else pd.Series(dtype=float)
    s50, s200 = sma(s, 50).iloc[-1], sma(s, 200).iloc[-1]
    vix_close = float(v.iloc[-1]) if len(v) else None
    nxt = calendar.next_day(day)
    ev = event_on(events, nxt)
    lt, why = light(float(s.iloc[-1]), s50, s200, vix_close, breadth, ev)
    return {
        "date": day.date().isoformat(),
        "spy_close": float(s.iloc[-1]),
        "spy_sma50": s50,
        "spy_sma200": s200,
        "vix": vix_close,
        "breadth_pct": breadth,
        "next_session": nxt.date().isoformat(),
        "event_next": ev,
        "light": lt,
        "reason": why,
        "rule_version": config.RULE_VERSION,
    }
