"""Plain pandas indicators. Each one only looks backward, so values are point-in-time."""

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(s: pd.Series, n: int) -> pd.Series:
    """Wilder's RSI, same as TradingView's ta.rsi."""
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn
    out = 100 - 100 / (1 + rs)
    out[dn == 0] = 100.0
    return out


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder's ATR, same as TradingView's ta.atr."""
    prev = df["close"].shift()
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def down_streak(close: pd.Series) -> pd.Series:
    """How many lower closes in a row, ending at each bar."""
    lower = close < close.shift()
    groups = (~lower).cumsum()
    return lower.groupby(groups).cumsum().astype(int)


def session_vwap(h: pd.DataFrame) -> pd.Series:
    """Cumulative VWAP inside each session, from hourly bars (typical price x volume)."""
    tp = (h["high"] + h["low"] + h["close"]) / 3
    day = h.index.date
    pv = (tp * h["volume"]).groupby(day).cumsum()
    v = h["volume"].groupby(day).cumsum()
    return (pv / v.replace(0, np.nan)).rename("vwap")
