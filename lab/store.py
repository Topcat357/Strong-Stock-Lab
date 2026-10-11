"""CSV files under data/. Everything the system knows lives here, in the repo."""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
COHORTS = DATA / "cohorts"
FILES = {
    "macro": DATA / "macro.csv",
    "setups": DATA / "setups.csv",
    "signals": DATA / "signals.csv",    # append-only: what was known when the signal fired
    "trades": DATA / "trades.csv",      # outcome of each signal, updated until closed
    "events": DATA / "events.csv",      # FOMC / CPI / jobs days, kept by the weekly review
}


def load(name, parse_dates=()):
    p = FILES[name]
    if not p.exists() or p.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(p, parse_dates=list(parse_dates), dtype={"symbol": str})


def save(name, df):
    FILES[name].parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(FILES[name], index=False, float_format="%.6g")


def append(name, rows):
    if not rows:
        return
    new = pd.DataFrame(rows)
    old = load(name)
    save(name, pd.concat([old, new], ignore_index=True) if len(old) else new)


def cohort_path(d):
    return COHORTS / f"cohort_{d}.csv"


def latest_cohort(on_or_before):
    """The newest cohort dated on or before the given date (YYYY-MM-DD string)."""
    files = sorted(COHORTS.glob("cohort_*.csv"))
    files = [f for f in files if f.stem.split("_")[1] <= str(on_or_before)]
    if not files:
        return None, pd.DataFrame()
    f = files[-1]
    return f.stem.split("_")[1], pd.read_csv(f)
