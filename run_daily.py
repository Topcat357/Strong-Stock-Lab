#!/usr/bin/env python3
"""
Daily job, run after the close. For each session not yet processed:

  1. Macro light at the close (applies to the next session).
  2. Fill entries that triggered on the previous session's last hourly bar.
  3. Replay the day's hourly bars for live setups -> signals + shadow trades.
  4. Walk open trades through the day (stops, targets, RSI(2) exit, time stop, MFE/MAE).
  5. Find new pullback setups at the close.

    python run_daily.py                  # catch up to the latest completed session
    python run_daily.py --date 2026-10-09  # process one session (testing)

Nothing here uses bars after the session being processed.
"""

import argparse
import json
import sys
from datetime import time as dtime

import numpy as np
import pandas as pd

from lab import calendar, config, data, macro, news, signals, store, trades
from lab.indicators import rsi

STATE = store.DATA / "state.json"
SPY, VIX = "AMEX:SPY", "CBOE:VIX"


def latest_complete_session():
    now = data.now_et()
    today = pd.Timestamp(now.date())
    if calendar.is_trading_day(today) and now.time() >= dtime(16, 10):
        return today
    return calendar.prev_day(today)


def sessions_to_process(last_done, latest, explicit):
    if explicit:
        return [pd.Timestamp(explicit)]
    if not last_done:
        return [latest]
    out, d = [], pd.Timestamp(last_done)
    while True:
        d = calendar.next_day(d)
        if d > latest:
            break
        out.append(d)
    return out[-10:]


def action_for(group, light, rank):
    if group == "control":
        return "control"
    if light == "red":
        return "log_only"
    if light == "yellow":
        return "take_half" if pd.notna(rank) and rank <= config.MACRO["yellow_rank_max"] else "skip"
    return "take"


def earnings_days(earn_ts, day):
    if earn_ts is None or pd.isna(earn_ts):
        return np.nan
    e = pd.Timestamp(int(earn_ts), unit="s").normalize()
    return calendar.sessions_between(day, e) if e > day else (0 if e == day else np.nan)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="process just this session (YYYY-MM-DD)")
    args = ap.parse_args()

    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    days = sessions_to_process(state.get("last_processed"), latest_complete_session(), args.date)
    if not days:
        data.log("Nothing new to process.")
        return 0
    data.log(f"Processing: {[d.date().isoformat() for d in days]}")

    macro_df = store.load("macro")
    setups = store.load("setups")
    sigs = store.load("signals")
    trd = store.load("trades")
    events = store.load("events")

    open_trades = [] if trd.empty else trd[trd["status"] == "open"].to_dict("records")
    closed = [] if trd.empty else trd[trd["status"] != "open"].to_dict("records")
    setup_rows = [] if setups.empty else setups.to_dict("records")
    new_signals = []

    # ---- symbols we need bars for
    cohorts = {}
    for d in days:
        cd, c = store.latest_cohort(d.date().isoformat())
        if cd:
            cohorts[cd] = c
    syms = set()
    for c in cohorts.values():
        syms |= set(c["symbol"])
    syms |= {t["symbol"] for t in open_trades}
    syms |= {s["symbol"] for s in setup_rows if s.get("status") in ("pending", "waiting_entry")}
    daily = data.get_bars(sorted(syms | {SPY, VIX}), "1d", "2y")
    hourly = data.get_bars(sorted(syms), "60m", "3mo") if syms else {}
    data.log(f"Bars: {len(daily)} daily, {len(hourly)} hourly")

    # ---- live extras for the latest session: breadth and earnings dates
    breadth, earn = None, {}
    try:
        breadth = data.sp500_breadth()
        if breadth is None:  # fall back to the liquid US universe
            from lab import screen
            liq = screen.liquid(screen.fetch_universe())
            breadth = float((liq["close"] > liq["SMA50"]).mean() * 100)
        det = data.tv_details(sorted(syms - {SPY, VIX}))
        earn = dict(zip(det["symbol"], det["earnings_release_next_date"]))
        if VIX not in daily:  # Yahoo missed VIX: today's close from TradingView
            v = data.tv_details([VIX], columns=("close",))
            if len(v) and pd.notna(v["close"].iloc[0]):
                day = days[-1]
                daily[VIX] = pd.DataFrame({"open": v["close"], "high": v["close"], "low": v["close"],
                                           "close": v["close"], "volume": 0.0},
                                          index=pd.DatetimeIndex([day]))
    except Exception as e:
        data.log(f"TradingView extras unavailable ({e}); continuing without breadth/earnings")

    if SPY not in daily:
        data.log("No SPY bars from any source; try again later.")
        return 1
    spy = daily[SPY]
    vix = daily.get(VIX)
    spy_close = spy["close"]

    def macro_for(day, with_breadth):
        nonlocal macro_df
        ds = day.date().isoformat()
        if not macro_df.empty and ds in set(macro_df["date"]):
            return macro_df[macro_df["date"] == ds].iloc[-1].to_dict()
        row = macro.macro_row(day, spy, vix, breadth if with_breadth else None, events)
        macro_df = pd.concat([macro_df, pd.DataFrame([row])], ignore_index=True)
        return row

    for D in days:
        ds = D.date().isoformat()
        if spy.index[-1] < D:
            data.log(f"No bars yet for {ds}; stopping here.")
            break
        today_macro = macro_for(D, D == days[-1])
        prev_macro = macro_for(calendar.prev_day(D), False)
        cd, cohort = store.latest_cohort(ds)
        rank_of = {} if cohort.empty else dict(zip(cohort["symbol"], cohort["rank"]))
        open_syms = {t["symbol"] for t in open_trades}

        def make_signal(s, trig, entry_time, entry_price):
            sym = s["symbol"]
            sid = f"{ds}-{sym.split(':')[-1]}-{s['group'][0]}"
            row = {
                "signal_id": sid, "rule_version": config.RULE_VERSION, "cohort_date": s["cohort_date"],
                "group": s["group"], "symbol": sym, "cohort_rank": s.get("cohort_rank"),
                "setup_date": s["setup_date"], "setup_reasons": s["reasons"],
                "trigger_time": trig["trigger_time"], "entry_time": entry_time, "entry_price": entry_price,
                "light": prev_macro["light"], "light_reason": prev_macro["reason"],
                "spy_above_50": prev_macro["spy_close"] > prev_macro["spy_sma50"],
                "spy_above_200": prev_macro["spy_close"] > prev_macro["spy_sma200"],
                "vix": prev_macro["vix"], "breadth_pct": prev_macro["breadth_pct"],
                "rs_pct": s.get("rs_pct"), "off_high_pct": s["off_high_pct"],
                "ret_6m_pct": s["ret_6m_pct"], "atr_pct": s["atr_pct"], "sector": s.get("sector"),
                "rsi2": s["rsi2"], "pullback_depth_atr": s["pullback_depth_atr"],
                "down_closes": s["down_closes"], "pullback_vol_ratio": s["pullback_vol_ratio"],
                "hourly_rvol": trig["hourly_rvol"], "vwap_dist_pct": trig["vwap_dist_pct"],
                "trigger_hour": trig["trigger_time"][11:16],
                "sessions_to_earnings": earnings_days(earn.get(sym), D),
                "action": action_for(s["group"], prev_macro["light"], s.get("cohort_rank")),
            }
            new_signals.append(row)
            t = trades.open_trade(sid, sym, s["group"], entry_time, entry_price,
                                  s["atr14"], s["pullback_low"])
            prev_spy = spy_close[spy_close.index < D]
            t["spy_entry"] = float(prev_spy.iloc[-1])
            open_trades.append(t)
            return sid

        # 2. entries waiting from yesterday's last-bar trigger
        for s in setup_rows:
            if s.get("status") != "waiting_entry" or s["symbol"] not in hourly:
                continue
            h = hourly[s["symbol"]]
            todays = h[h.index.date == D.date()]
            if todays.empty:
                continue
            trig = json.loads(s["trigger_json"])
            sid = make_signal(s, trig, todays.index[0].isoformat(), float(todays["open"].iloc[0]))
            s.update(status="triggered", signal_id=sid)

        # 3. hourly replay for live setups
        for s in setup_rows:
            if s.get("status") != "pending":
                continue
            age = calendar.sessions_between(s["setup_date"], D)
            if age < 1:
                continue
            if age > config.SETUP["valid_sessions"]:
                s["status"] = "expired"
                continue
            sym = s["symbol"]
            if sym not in hourly or sym in open_syms:
                continue
            trig = signals.find_trigger(hourly[sym], D)
            if not trig:
                if age == config.SETUP["valid_sessions"]:
                    s["status"] = "expired"
                continue
            ed = earnings_days(earn.get(sym), D)
            if pd.notna(ed) and ed <= config.SETUP["earnings_blackout_days"]:
                s["status"] = "skipped_earnings"
                continue
            if trig["entry_time"]:
                sid = make_signal(s, trig, trig["entry_time"], trig["entry_price"])
                s.update(status="triggered", signal_id=sid)
            else:
                s.update(status="waiting_entry", trigger_json=json.dumps(trig))
            open_syms.add(sym)

        # 4. walk open trades through the day
        still_open = []
        for t in open_trades:
            df = daily.get(t["symbol"])
            if df is None or D not in df.index:
                still_open.append(t)
                continue
            r2 = float(rsi(df[df.index <= D]["close"], 2).iloc[-1])
            trades.update_day(t, D, hourly.get(t["symbol"]), df.loc[D], r2)
            if t["status"] == "open":
                still_open.append(t)
            else:
                t["spy_exit"] = float(spy_close.loc[D])
                t["spy_ret_pct"] = (t["spy_exit"] / t["spy_entry"] - 1) * 100
                closed.append(t)
        open_trades = still_open

        # 5. new setups at the close
        if not cohort.empty:
            busy = {t["symbol"] for t in open_trades} | {
                s["symbol"] for s in setup_rows if s.get("status") in ("pending", "waiting_entry")}
            found = 0
            for _, c in cohort.iterrows():
                sym = c["symbol"]
                if sym in busy or sym not in daily:
                    continue
                f = signals.daily_features(daily[sym], D)
                why = signals.is_setup(f)
                if not why:
                    continue
                setup_rows.append({
                    "setup_date": ds, "symbol": sym, "group": c["group"], "cohort_date": cd,
                    "cohort_rank": c["rank"], "rs_pct": c["rs_pct"], "sector": c["sector"],
                    "reasons": "+".join(why), "status": "pending", "signal_id": "",
                    "trigger_json": "", **f,
                })
                found += 1
            data.log(f"{ds}: light {today_macro['light']}, {found} new setups, "
                     f"{len(open_trades)} open trades")
        if ds > state.get("last_processed", ""):
            state["last_processed"] = ds

    # ---- news from Massive for each new signal (headlines before the trigger only)
    tags = []
    for sg in new_signals:
        t = news.tag_signal(sg["signal_id"], sg["symbol"], sg["trigger_time"])
        if t:
            tags.append(t)
    if new_signals:
        data.log(f"News tags: {len(tags)} of {len(new_signals)} signals from Massive")
    if tags:
        old = store.load("news")
        merged = pd.concat([old, pd.DataFrame(tags)], ignore_index=True) if len(old) else pd.DataFrame(tags)
        store.save("news", merged.reindex(columns=news.COLUMNS))

    # ---- save
    store.save("macro", macro_df.drop_duplicates("date", keep="last").sort_values("date"))
    if setup_rows:
        store.save("setups", pd.DataFrame(setup_rows))
    store.append("signals", new_signals)
    all_trades = closed + open_trades
    if all_trades:
        store.save("trades", pd.DataFrame(all_trades))
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    write_summary(macro_df, setup_rows, new_signals, open_trades, closed, state)
    return 0


def write_summary(macro_df, setup_rows, new_signals, open_trades, closed, state):
    m = macro_df.sort_values("date").iloc[-1]
    pend = [s for s in setup_rows if s.get("status") in ("pending", "waiting_entry")]
    lines = [
        f"# Strong-Stock Lab: {state.get('last_processed')}",
        "",
        f"Light for {m['next_session']}: **{m['light'].upper()}** ({m['reason']}).",
        "",
        f"New signals: {len(new_signals)} · Open shadow trades: {len(open_trades)} · "
        f"Closed so far: {len(closed)} · Setups waiting: {len(pend)}",
        "",
    ]
    if new_signals:
        lines += ["## New signals", "", "| Symbol | Group | Entry | Action |", "|---|---|---|---|"]
        for s in new_signals:
            lines.append(f"| {s['symbol'].split(':')[-1]} | {s['group']} | "
                         f"{s['entry_price']:.2f} | {s['action']} |")
        lines.append("")
    if pend:
        lines += ["## Setups waiting for an hourly trigger", "",
                  "| Symbol | Group | Since | Why |", "|---|---|---|---|"]
        for s in pend:
            lines.append(f"| {s['symbol'].split(':')[-1]} | {s['group']} | {s['setup_date']} | {s['reasons']} |")
        lines.append("")
    (store.DATA / "latest.md").write_text("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
