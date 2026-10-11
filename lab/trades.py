"""Shadow trades: fixed exits, plus best/worst price while open (MFE/MAE)."""

import pandas as pd

from . import calendar, config


def open_trade(signal_id, symbol, group, entry_time, entry_price, atr14, pullback_low) -> dict:
    e = config.EXITS
    raw = entry_price - (pullback_low - e["stop_buffer_atr"] * atr14)
    dist = min(max(raw, e["stop_min_atr"] * atr14), e["stop_max_atr"] * atr14)
    stop = entry_price - dist
    return {
        "signal_id": signal_id,
        "symbol": symbol,
        "group": group,
        "entry_time": entry_time,
        "entry_date": entry_time[:10],
        "entry": entry_price,
        "stop": stop,
        "target": entry_price + e["target_r"] * dist,
        "risk_per_share": dist,
        "shares": config.POSITION_USD / entry_price,
        "status": "open",
        "high_since": entry_price,
        "low_since": entry_price,
        "last_date": "",
        "days_held": 0,
        "exit_time": "",
        "exit": None,
        "exit_reason": "",
        "r_multiple": None,
        "ret_pct": None,
        "mfe_r": 0.0,
        "mae_r": 0.0,
        "spy_entry": None,
        "spy_exit": None,
        "spy_ret_pct": None,
    }


def _close(t, when, price, reason):
    t.update(status="closed", exit_time=when, exit=price, exit_reason=reason)
    t["r_multiple"] = (price - t["entry"]) / t["risk_per_share"]
    t["ret_pct"] = (price / t["entry"] - 1) * 100


def _bar(t, when, o, h, l):
    """Apply one bar's range. Gaps fill at the open; stop wins if both are touched."""
    t["high_since"] = max(t["high_since"], h)
    t["low_since"] = min(t["low_since"], l)
    t["mfe_r"] = (t["high_since"] - t["entry"]) / t["risk_per_share"]
    t["mae_r"] = (t["low_since"] - t["entry"]) / t["risk_per_share"]
    if l <= t["stop"]:
        _close(t, when, min(o, t["stop"]), "stop")
    elif h >= t["target"]:
        _close(t, when, max(o, t["target"]), "target")


def update_day(t: dict, day, hourly: pd.DataFrame | None, daily_row, rsi2_close: float) -> dict:
    """Walk a trade through one session.
    Entry day: hourly bars from the entry bar onward. Later days: the daily bar.
    Then the close checks: RSI(2) strength exit and the 10-day time stop."""
    if t["status"] != "open":
        return t
    day = pd.Timestamp(day).normalize()
    ds = day.date().isoformat()
    if t["last_date"] and ds <= t["last_date"]:
        return t
    if ds == t["entry_date"] and hourly is not None:
        bars = hourly[(hourly.index.date == day.date())
                      & (hourly.index >= pd.Timestamp(t["entry_time"]))]
        for when, b in bars.iterrows():
            _bar(t, when.isoformat(), b["open"], b["high"], b["low"])
            if t["status"] != "open":
                break
    elif ds > t["entry_date"] and daily_row is not None:
        _bar(t, ds, daily_row["open"], daily_row["high"], daily_row["low"])
    t["last_date"] = ds
    t["days_held"] = calendar.sessions_between(calendar.prev_day(t["entry_date"]), day)
    if t["status"] == "open" and daily_row is not None:
        e = config.EXITS
        if rsi2_close > e["rsi2_exit"]:
            _close(t, ds + " close", float(daily_row["close"]), "rsi2_strength")
        elif t["days_held"] >= e["time_stop_days"]:
            _close(t, ds + " close", float(daily_row["close"]), "time_stop")
    return t
