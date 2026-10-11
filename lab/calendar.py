"""NYSE trading days."""

from functools import lru_cache

import pandas as pd
import pandas_market_calendars as mcal


@lru_cache(maxsize=1)
def _days():
    cal = mcal.get_calendar("XNYS")
    d = cal.valid_days("2023-01-01", "2028-12-31")
    return pd.DatetimeIndex(d.tz_localize(None).normalize())


def is_trading_day(d) -> bool:
    return pd.Timestamp(d).normalize() in _days()


def next_day(d, n=1) -> pd.Timestamp:
    days = _days()
    i = days.searchsorted(pd.Timestamp(d).normalize(), side="right")
    return days[i + n - 1]


def prev_day(d) -> pd.Timestamp:
    days = _days()
    i = days.searchsorted(pd.Timestamp(d).normalize(), side="left")
    return days[i - 1]


def sessions_between(a, b) -> int:
    """Trading days after a, up to and including b (0 if b <= a)."""
    days = _days()
    a, b = pd.Timestamp(a).normalize(), pd.Timestamp(b).normalize()
    if b <= a:
        return 0
    return int(days.searchsorted(b, side="right") - days.searchsorted(a, side="right"))
