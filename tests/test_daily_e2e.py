"""Runs the whole daily job on fake data: setup at a close -> hourly trigger -> trade -> exit."""

from datetime import datetime

import numpy as np
import pandas as pd

import run_daily
from lab import calendar, data, screen, store
from lab.data import ET


def _daily(end, n=330, seed=3):
    days = pd.DatetimeIndex([d for d in pd.bdate_range(end=end, periods=n + 40)
                             if calendar.is_trading_day(d)][-n:])
    rng = np.random.default_rng(seed)
    c = 20 * np.cumprod(1 + 0.003 + rng.normal(0, 0.005, len(days)))
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c,
                         "volume": 1e6}, index=days)


def _hourly(daily):
    rows = []
    for d, r in daily.iterrows():
        for hhmm in ["09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30"]:
            ts = pd.Timestamp(f"{d.date()} {hhmm}", tz="America/New_York")
            rows.append((ts, r["close"], r["close"] * 1.002, r["close"] * 0.998, r["close"], 1e5))
    return pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).set_index("ts")


def test_daily_pipeline(tmp_path, monkeypatch):
    # isolated data folder
    monkeypatch.setattr(store, "DATA", tmp_path)
    monkeypatch.setattr(store, "COHORTS", tmp_path / "cohorts")
    monkeypatch.setattr(store, "FILES", {k: tmp_path / v.name for k, v in store.FILES.items()})
    monkeypatch.setattr(run_daily, "STATE", tmp_path / "state.json")

    sym = "NASDAQ:TEST"
    stock = _daily("2026-10-16")
    # pullback: 4 lower closes ending Fri 10/09 (stays above the 200-day)
    pb = ["2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"]
    base = stock.loc["2026-10-05", "close"]
    for k, d in enumerate(pb):
        c = base * (1 - 0.015 * (k + 1))
        stock.loc[d, ["open", "high", "low", "close"]] = [c * 1.005, c * 1.01, c * 0.995, c]
    # Mon 10/12 bounce then run-up to the target
    for k, d in enumerate(["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16"]):
        c = stock.loc["2026-10-09", "close"] * (1.01 + 0.03 * k)
        stock.loc[d, ["open", "high", "low", "close"]] = [c * 0.995, c * 1.02, c * 0.99, c]
    hourly = _hourly(stock)
    trig = hourly.index[(hourly.index.date == pd.Timestamp("2026-10-12").date())
                        & (hourly.index.strftime("%H:%M") == "10:30")]
    lo = stock.loc["2026-10-09", "close"]
    hourly.loc[trig, ["close", "high"]] = [lo * 1.02, lo * 1.021]
    hourly.loc[trig, "volume"] = 4e5

    spy = _daily("2026-10-16", seed=9)
    vix = spy.assign(close=15.0)

    def fake_bars(symbols, interval="1d", period="2y", max_backup=8):
        src = {sym: stock, "AMEX:SPY": spy, "CBOE:VIX": vix} if interval == "1d" else {sym: hourly}
        return {s: src[s] for s in symbols if s in src}

    monkeypatch.setattr(data, "get_bars", fake_bars)
    monkeypatch.setattr(screen, "fetch_universe", lambda: pd.DataFrame(
        {"symbol": [sym], "close": [30.0], "SMA50": [25.0], "average_volume_30d_calc": [1e6]}))
    monkeypatch.setattr(data, "tv_details", lambda s, *a, **k: pd.DataFrame(
        {"symbol": [sym], "earnings_release_next_date": [None]}))

    store.COHORTS.mkdir(parents=True)
    pd.DataFrame([{"cohort_date": "2026-10-04", "group": "cohort", "rank": 1, "symbol": sym,
                   "sector": "Tech", "rs_pct": 95.0}]).to_csv(store.cohort_path("2026-10-04"), index=False)

    clock = {"t": datetime(2026, 10, 9, 16, 30, tzinfo=ET)}
    monkeypatch.setattr(data, "now_et", lambda: clock["t"])

    run_daily.main.__globals__["sys"].argv = ["run_daily.py"]
    assert run_daily.main() == 0                       # Fri close: setup found
    setups = store.load("setups")
    assert len(setups) == 1 and setups.iloc[0]["status"] == "pending"

    clock["t"] = datetime(2026, 10, 16, 17, 0, tzinfo=ET)
    assert run_daily.main() == 0                       # catch up Mon-Fri
    sig = store.load("signals")
    trd = store.load("trades")
    assert len(sig) == 1 and sig.iloc[0]["trigger_hour"] == "10:30"
    assert sig.iloc[0]["entry_time"].startswith("2026-10-12T11:30")
    assert sig.iloc[0]["action"] == "take"
    t = trd.iloc[0]
    assert t["status"] == "closed" and t["exit_reason"] in ("target", "rsi2_strength")
    assert t["r_multiple"] > 0 and not pd.isna(t["spy_ret_pct"])
    assert (tmp_path / "latest.md").exists()
    m = store.load("macro")
    assert m["date"].iloc[-1] == "2026-10-16"
