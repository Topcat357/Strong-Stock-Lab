"""Layer 3: the daily pullback setup and the hourly turn that triggers an entry."""

import numpy as np
import pandas as pd

from . import config
from .indicators import atr, down_streak, ema, rsi, session_vwap, sma


def daily_features(df: pd.DataFrame, day) -> dict | None:
    """Indicator snapshot at the close of `day`, using only bars up to that day."""
    day = pd.Timestamp(day).normalize()
    d = df[df.index <= day]
    if len(d) < 252 or d.index[-1] != day:
        return None
    c = d["close"]
    a = atr(d, 14)
    e20 = ema(c, 20)
    r2 = rsi(c, 2)
    streak = down_streak(c)
    vol50 = d["volume"].tail(51).iloc[:-1].mean()
    n = max(int(streak.iloc[-1]), 1)
    return {
        "close": float(c.iloc[-1]),
        "atr14": float(a.iloc[-1]),
        "atr_pct": float(a.iloc[-1] / c.iloc[-1] * 100),
        "ema20": float(e20.iloc[-1]),
        "sma50": float(sma(c, 50).iloc[-1]),
        "sma200": float(sma(c, 200).iloc[-1]),
        "rsi2": float(r2.iloc[-1]),
        "down_closes": int(streak.iloc[-1]),
        "pullback_low": float(d["low"].tail(max(n, 3)).min()),
        "pullback_depth_atr": float((d["high"].tail(10).max() - c.iloc[-1]) / a.iloc[-1]),
        "pullback_vol_ratio": float(d["volume"].tail(n).mean() / vol50) if vol50 else np.nan,
        "off_high_pct": float((1 - c.iloc[-1] / d["high"].tail(252).max()) * 100),
        "ret_6m_pct": float((c.iloc[-1] / c.iloc[-127] - 1) * 100),
    }


def is_setup(f: dict) -> list[str]:
    """Which pullback conditions are met (empty list = no setup). The stock must still be above its 200-day."""
    s = config.SETUP
    if f is None or f["close"] <= f["sma200"]:
        return []
    why = []
    if f["rsi2"] < s["rsi2_max"]:
        why.append("rsi2")
    if abs(f["close"] - f["ema20"]) <= s["ema20_atr_band"] * f["atr14"]:
        why.append("ema20")
    if f["down_closes"] >= s["down_closes_min"]:
        why.append("down_streak")
    return why


def hourly_rvol(h: pd.DataFrame) -> pd.Series:
    """Each bar's volume / average volume of the same hour over the prior 20 sessions."""
    slot = h.index.strftime("%H:%M")
    n = config.TRIGGER["rvol_lookback_days"]
    avg = h["volume"].groupby(slot).transform(lambda v: v.shift(1).rolling(n, min_periods=10).mean())
    return h["volume"] / avg


def find_trigger(h: pd.DataFrame, day) -> dict | None:
    """First hourly bar on `day` that closes above the prior bar's high and session VWAP on 1.5x+ volume.
    Entry is the NEXT bar's open; if the trigger is the day's last bar, entry waits for the next session."""
    day = pd.Timestamp(day).date()
    h = h.sort_index()
    rv = hourly_rvol(h)
    vw = session_vwap(h)
    prev_high = h["high"].shift(1)
    idx = np.where(h.index.date == day)[0]
    start = config.TRIGGER["first_bar_start"]
    for i in idx:
        if i == 0 or h.index[i].strftime("%H:%M") < start:
            continue
        bar = h.iloc[i]
        if (bar["close"] > prev_high.iloc[i] and bar["close"] > vw.iloc[i]
                and rv.iloc[i] >= config.TRIGGER["rvol_min"]):
            nxt = i + 1 if i + 1 < len(h) and h.index[i + 1].date() == day else None
            return {
                "trigger_time": h.index[i].isoformat(),
                "trigger_close": float(bar["close"]),
                "hourly_rvol": float(rv.iloc[i]),
                "vwap_dist_pct": float((bar["close"] / vw.iloc[i] - 1) * 100),
                "entry_time": h.index[nxt].isoformat() if nxt is not None else "",
                "entry_price": float(h["open"].iloc[nxt]) if nxt is not None else np.nan,
            }
    return None
