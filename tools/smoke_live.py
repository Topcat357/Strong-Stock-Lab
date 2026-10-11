#!/usr/bin/env python3
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
"""Live data check (writes nothing): hourly bar times, setups and triggers on the current cohort
over the last 5 sessions. Run from the Tests workflow by hand."""

import pandas as pd

from lab import calendar, data, signals, store

import os
if os.environ.get("MASSIVE_API_KEY", "").strip():
    m = data.massive_daily("AMEX:SPY", days=30)
    print("Massive backup:", f"OK, {len(m)} SPY daily bars, last {m.index[-1].date()}" if m is not None
          else "key set but the request failed")
    from lab import news
    for sym in ("NYSE:HPE", "NASDAQ:GTLB"):
        r = news.massive_news(sym, "2026-10-09T15:30:00-04:00")
        print(f"Massive news {sym} (48h before Fri 3:30 pm):",
              "unavailable" if r is None else
              f"{r['headlines_48h']} headlines, tone {r['news_tone']} "
              f"(+{r['positive']} / -{r['negative']} / ={r['neutral']})")
else:
    print("Massive backup: no key")

cd, cohort = store.latest_cohort("2100-01-01")
syms = cohort[cohort["group"] == "cohort"]["symbol"].tolist()[:25]
daily = data.get_bars(syms, "1d", "2y")
hourly = data.get_bars(syms, "60m", "3mo")
print(f"cohort {cd}: {len(daily)} daily, {len(hourly)} hourly of {len(syms)}")
h0 = next(iter(hourly.values()))
last_day = h0.index[-1].date()
print("hourly bar times on", last_day, ":", [t.strftime("%H:%M") for t in h0.index if t.date() == last_day])
day = pd.Timestamp(last_day)
days = [day]
for _ in range(4):
    days.insert(0, calendar.prev_day(days[0]))
setups = trig = 0
for s in syms:
    if s not in daily or s not in hourly:
        continue
    for d in days[:-1]:
        f = signals.daily_features(daily[s], d)
        why = signals.is_setup(f)
        if why:
            setups += 1
            nxt = calendar.next_day(d)
            t = signals.find_trigger(hourly[s], nxt)
            if t:
                trig += 1
                print(f"  {s} setup {d.date()} ({'+'.join(why)}) -> trigger {t['trigger_time'][:16]} "
                      f"rvol {t['hourly_rvol']:.1f} entry {t['entry_price']:.2f}")
print(f"setups: {setups}, next-day triggers: {trig}")
