import numpy as np
import pandas as pd
import pytest

from lab import calendar, config, macro, signals, trades
from lab.indicators import down_streak, rsi


# ------------------------------------------------------------------ helpers
def daily_trend(end="2026-10-09", n=320, drift=0.003, seed=1):
    days = pd.DatetimeIndex([d for d in pd.bdate_range(end=end, periods=n + 40)
                             if calendar.is_trading_day(d)][-n:])
    rng = np.random.default_rng(seed)
    c = 20 * np.cumprod(1 + drift + rng.normal(0, 0.01, len(days)))
    return pd.DataFrame({"open": c * 0.998, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": 1_000_000.0}, index=days)


def hourly_bars(days, base=50.0, vol=100_000.0):
    rows = []
    for d in days:
        for hhmm in ["09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30"]:
            ts = pd.Timestamp(f"{d.date()} {hhmm}", tz="America/New_York")
            rows.append((ts, base, base + 0.2, base - 0.2, base, vol))
    return pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")


# --------------------------------------------------------------- indicators
def test_rsi_extremes():
    up = pd.Series(np.arange(1, 30, dtype=float))
    assert rsi(up, 2).iloc[-1] == 100
    down = pd.Series(np.arange(30, 1, -1, dtype=float))
    assert rsi(down, 2).iloc[-1] < 1


def test_down_streak():
    s = pd.Series([5, 4, 3, 4, 3, 2, 1.0])
    assert down_streak(s).tolist() == [0, 1, 2, 0, 1, 2, 3]


# ----------------------------------------------------------------- calendar
def test_calendar_skips_holiday():
    assert calendar.next_day("2026-11-25") == pd.Timestamp("2026-11-27")  # Thanksgiving
    assert calendar.sessions_between("2026-10-09", "2026-10-14") == 3
    assert calendar.prev_day("2026-10-12") == pd.Timestamp("2026-10-09")


# -------------------------------------------------------------------- macro
def test_light_worst_input_wins():
    assert macro.light(110, 105, 100, 15, 60, "")[0] == "green"
    assert macro.light(110, 105, 100, 22, 60, "")[0] == "yellow"
    assert macro.light(103, 105, 100, 15, 60, "")[0] == "yellow"
    assert macro.light(110, 105, 100, 15, 40, "")[0] == "yellow"
    assert macro.light(95, 105, 100, 15, 60, "")[0] == "red"
    assert macro.light(110, 105, 100, 30, 60, "")[0] == "red"
    assert macro.light(110, 105, 100, 15, 60, "CPI")[0] == "red"


# ------------------------------------------------------------------- setups
def test_setup_on_pullback_only():
    df = daily_trend()
    f = signals.daily_features(df, df.index[-1])
    assert f is not None
    # force a 4-day pullback
    d2 = df.copy()
    for k, i in enumerate(range(-4, 0)):
        d2.iloc[i, d2.columns.get_loc("close")] = df["close"].iloc[-5] * (1 - 0.02 * (k + 1))
        d2.iloc[i, d2.columns.get_loc("low")] = d2["close"].iloc[i] * 0.99
    f2 = signals.daily_features(d2, d2.index[-1])
    why = signals.is_setup(f2)
    assert "rsi2" in why and "down_streak" in why


def test_features_ignore_future_bars():
    df = daily_trend()
    day = df.index[-5]
    a = signals.daily_features(df, day)
    b = signals.daily_features(df[df.index <= day], day)
    assert a == b


# ------------------------------------------------------------------ trigger
def _trigger_frame(trigger_slot):
    days = [d for d in pd.bdate_range("2026-08-20", "2026-10-09") if calendar.is_trading_day(d)]
    h = hourly_bars(days)
    day = pd.Timestamp("2026-10-09").date()
    mask = (h.index.date == day) & (h.index.strftime("%H:%M") == trigger_slot)
    h.loc[mask, ["close", "high"]] = [51.0, 51.1]
    h.loc[mask, "volume"] = 300_000
    return h


def test_trigger_enters_next_bar_open():
    h = _trigger_frame("11:30")
    t = signals.find_trigger(h, "2026-10-09")
    assert t and t["trigger_time"].startswith("2026-10-09T11:30")
    assert t["entry_time"].startswith("2026-10-09T12:30") and t["entry_price"] == 50.0


def test_last_bar_trigger_waits_for_next_session():
    h = _trigger_frame("15:30")
    t = signals.find_trigger(h, "2026-10-09")
    assert t and t["entry_time"] == "" and np.isnan(t["entry_price"])


def test_no_trigger_without_volume():
    h = _trigger_frame("11:30")
    h.loc[h["volume"] == 300_000, "volume"] = 100_000
    assert signals.find_trigger(h, "2026-10-09") is None


# ------------------------------------------------------------------- trades
def _t():
    return trades.open_trade("x", "NYSE:X", "cohort", "2026-10-09T10:30:00-04:00", 50.0, 2.0, 49.0)


def test_stop_clamped_to_atr_limits():
    t = _t()  # raw distance 1.5, between 0.5 and 2 ATR
    assert t["stop"] == pytest.approx(48.5) and t["target"] == pytest.approx(53.0)
    far = trades.open_trade("y", "S", "cohort", "2026-10-09T10:30", 50.0, 1.0, 40.0)
    assert far["stop"] == pytest.approx(48.0)          # capped at 2 ATR
    near = trades.open_trade("z", "S", "cohort", "2026-10-09T10:30", 50.0, 2.0, 51.0)
    assert near["stop"] == pytest.approx(49.0)         # floored at 0.5 ATR


def _row(o, h, l, c):
    return pd.Series({"open": o, "high": h, "low": l, "close": c})


def test_gap_down_fills_at_open_and_both_touched_is_stop():
    t = _t()
    trades.update_day(t, "2026-10-12", None, _row(47, 47.5, 46, 47), 30)
    assert t["exit_reason"] == "stop" and t["exit"] == 47 and t["r_multiple"] == pytest.approx(-2)
    t = _t()
    trades.update_day(t, "2026-10-12", None, _row(50, 54, 48, 50), 30)
    assert t["exit_reason"] == "stop"


def test_target_rsi_and_time_stop():
    t = _t()
    trades.update_day(t, "2026-10-12", None, _row(50, 53.5, 49.5, 53), 30)
    assert t["exit_reason"] == "target" and t["r_multiple"] == pytest.approx(2)
    t = _t()
    trades.update_day(t, "2026-10-12", None, _row(50, 51, 49.5, 51), 85)
    assert t["exit_reason"] == "rsi2_strength" and t["exit"] == 51
    t = _t()
    days = [d for d in pd.bdate_range("2026-10-12", "2026-10-30") if calendar.is_trading_day(d)]
    for d in days:
        trades.update_day(t, d, None, _row(50, 50.5, 49.5, 50.2), 50)
        if t["status"] != "open":
            break
    assert t["exit_reason"] == "time_stop" and t["days_held"] == config.EXITS["time_stop_days"]
    assert t["exit_time"].startswith("2026-10-22")  # 10th session counting entry day 10/09


def test_mfe_mae_tracked():
    t = _t()
    trades.update_day(t, "2026-10-12", None, _row(50, 52, 49, 51), 30)
    assert t["mfe_r"] == pytest.approx(4 / 3) and t["mae_r"] == pytest.approx(-2 / 3)


# --------------------------------------------------------------------- news
def test_news_tone():
    from lab.news import tone_from
    assert tone_from([], "X")["news_tone"] == "none"
    arts = [{"title": "a", "insights": [{"ticker": "X", "sentiment": "positive"},
                                        {"ticker": "Y", "sentiment": "negative"}]},
            {"title": "b", "insights": [{"ticker": "X", "sentiment": "positive"}]},
            {"title": "c", "insights": [{"ticker": "X", "sentiment": "negative"}]}]
    r = tone_from(arts, "X")
    assert r["news_tone"] == "positive" and r["headlines_48h"] == 3 and r["negative"] == 1
    assert tone_from(arts[2:] + arts[:1], "X")["news_tone"] == "neutral"
    assert tone_from([{"title": "z"}], "X")["news_tone"] == "neutral"
