# Strong-Stock Lab

A forward test of buying pullbacks in strong long-term stocks. Every signal is shadow-traded
with fixed rules and logged at the moment it fires, so the data can show which conditions
actually pay. No orders are ever placed.

```
Macro light (daily close) ──┐
Weekly cohort (Sunday) → Daily setup (close) → Hourly trigger → Shadow trade → data/*.csv
                                     ▲                                           │
                                     └──────── new rule version ◄── Weekly review┘
```

## What runs when

| Workflow | When (New York time) | Does |
|---|---|---|
| Weekly screen | Sunday 6 pm | `report.py` on last week, then `run_weekly.py` freezes this week's cohort + control |
| Daily after close | Weekdays 4:30 pm | `run_daily.py`: macro light, hourly replay for setups, trade exits, new setups |
| Tests | On every code push | `pytest` |

Both data workflows can be started by hand: Actions tab → pick the workflow → Run workflow.
The daily job catches up on any sessions it missed and skips ones already done.

## Files in `data/`

| File | What it holds |
|---|---|
| `cohorts/cohort_YYYY-MM-DD.csv` | Each week's frozen cohort (`group = cohort`) and random control (`group = control`). Never edited. |
| `cohort_latest.md`, `cohort_latest_tv.txt` | Readable cohort list; comma list to import into a TradingView watchlist |
| `macro.csv` | The light at each close and why. It applies to the next session. |
| `setups.csv` | Pullback setups and what became of them (triggered, expired, skipped for earnings) |
| `signals.csv` | Append-only: everything known when each signal fired |
| `trades.csv` | Each signal's shadow trade: entry, stop, target, exit, R, MFE/MAE, SPY over the same window |
| `latest.md` | Today's summary |
| `report_latest.md` / `.json` | Weekly results by group, light, action, exit and rule version |
| `news_tags.csv` | Headlines in the 48h before each signal: `massive` rows at the moment it fires, `tradingview` rows added by the Sunday review |
| `events.csv` | FOMC / CPI / jobs days (red light). Kept current by the weekly review. |

## Rules

All thresholds live in [`lab/config.py`](lab/config.py). Changing any of them means bumping
`RULE_VERSION`, so results from different rule sets never get mixed.

## Data sources

- TradingView screener service: the market-wide screen, breadth and earnings dates.
  Optional secret `TV_SESSIONID` (same as Gap-Scan).
- Yahoo Finance (`yfinance`): daily and hourly bars.
- Massive: news and sentiment for each new signal, and backup daily bars when Yahoo misses a
  symbol. Secret `MASSIVE_API_KEY` (free tier, 5 calls a minute).

## Run locally

```
pip install -r requirements.txt
python run_weekly.py
python run_daily.py
python report.py
python -m pytest -q
```
