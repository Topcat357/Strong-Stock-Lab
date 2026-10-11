#!/usr/bin/env python3
"""
Weekly screen: builds and freezes this week's cohort (plus the random control group).

    python run_weekly.py            # cohort dated today (New York time)
    python run_weekly.py --force    # rebuild even if today's cohort file exists

Writes data/cohorts/cohort_YYYY-MM-DD.csv, data/cohort_latest.md and
data/cohort_latest_tv.txt (import into a TradingView watchlist).
"""

import argparse
import sys

from lab import config, data, screen, store


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    d = data.now_et().date().isoformat()
    path = store.cohort_path(d)
    if path.exists() and not args.force:
        print(f"{path.name} already exists; past cohorts are never rebuilt (use --force today only).")
        return 0

    cohort, liq = screen.build(d)
    path.parent.mkdir(parents=True, exist_ok=True)
    cohort.to_csv(path, index=False, float_format="%.6g")

    strong = cohort[cohort["group"] == "cohort"]
    lines = [
        f"# Cohort {d}",
        "",
        f"{len(strong)} strong stocks out of {len(liq)} liquid US stocks "
        f"(rules {config.RULE_VERSION}). {int((cohort['group'] == 'control').sum())} control stocks.",
        "",
        "| # | Symbol | Name | Sector | Close | 6M % | Off high % |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, r in strong.iterrows():
        lines.append(f"| {int(r['rank'])} | {r['symbol'].split(':')[-1]} | {r['name']} | {r['sector']} "
                     f"| {r['close']:.2f} | {r['Perf.6M']:.0f} | {r['off_high_pct']:.1f} |")
    (store.DATA / "cohort_latest.md").write_text("\n".join(lines) + "\n")
    (store.DATA / "cohort_latest_tv.txt").write_text(",".join(strong["symbol"]) + "\n")
    data.log(f"Saved {path.name}: {len(strong)} cohort + {len(cohort) - len(strong)} control")
    return 0


if __name__ == "__main__":
    sys.exit(main())
