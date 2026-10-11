#!/usr/bin/env python3
"""
Weekly numbers for the review: results by group, action, light and rule version,
plus each cohort's buy-and-hold return against SPY.

    python report.py     # writes data/report_latest.md and data/report_latest.json
"""

import json
import sys

import numpy as np
import pandas as pd

from lab import data, store


def stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"trades": 0}
    r = df["r_multiple"].astype(float)
    win = r > 0
    return {
        "trades": int(len(df)),
        "win_rate_pct": round(float(win.mean() * 100), 1),
        "avg_r": round(float(r.mean()), 2),
        "avg_win_r": round(float(r[win].mean()), 2) if win.any() else None,
        "avg_loss_r": round(float(r[~win].mean()), 2) if (~win).any() else None,
        "avg_ret_pct": round(float(df["ret_pct"].astype(float).mean()), 2),
        "avg_spy_ret_pct": round(float(df["spy_ret_pct"].astype(float).mean()), 2),
        "avg_days": round(float(df["days_held"].astype(float).mean()), 1),
        "avg_mfe_r": round(float(df["mfe_r"].astype(float).mean()), 2),
        "avg_mae_r": round(float(df["mae_r"].astype(float).mean()), 2),
    }


def table(title, groups: dict) -> list[str]:
    out = [f"## {title}", "", "| | Trades | Win % | Avg R | Avg % | SPY % | Days |",
           "|---|---|---|---|---|---|---|"]
    for name, s in groups.items():
        if not s.get("trades"):
            out.append(f"| {name} | 0 | | | | | |")
            continue
        out.append(f"| {name} | {s['trades']} | {s['win_rate_pct']} | {s['avg_r']} | "
                   f"{s['avg_ret_pct']} | {s['avg_spy_ret_pct']} | {s['avg_days']} |")
    return out + [""]


def cohort_buy_hold():
    """Equal-weight return of each cohort from its date's close to the next cohort (or today)."""
    files = sorted(store.COHORTS.glob("cohort_*.csv"))
    if not files:
        return []
    rows, all_syms = [], set()
    cohorts = []
    for i, f in enumerate(files):
        c = pd.read_csv(f)
        start = f.stem.split("_")[1]
        end = files[i + 1].stem.split("_")[1] if i + 1 < len(files) else None
        cohorts.append((start, end, c))
        all_syms |= set(c["symbol"])
    bars = data.get_bars(sorted(all_syms | {"AMEX:SPY"}), "1d", "1y")
    spy = bars["AMEX:SPY"]["close"]
    for start, end, c in cohorts:
        def ret(sym):
            s = bars.get(sym)
            if s is None:
                return np.nan
            s = s["close"]
            a = s[s.index <= start]
            b = s[s.index <= end] if end else s
            return (b.iloc[-1] / a.iloc[-1] - 1) * 100 if len(a) and len(b) else np.nan
        row = {"cohort": start, "through": end or "today"}
        for g in ("cohort", "control"):
            row[f"{g}_ret_pct"] = round(float(np.nanmean([ret(s) for s in c[c["group"] == g]["symbol"]])), 2)
        row["spy_ret_pct"] = round(float(ret("AMEX:SPY")), 2)
        rows.append(row)
    return rows


def main():
    trd = store.load("trades")
    sig = store.load("signals")
    out = {"as_of": data.now_et().isoformat(timespec="minutes")}
    lines = [f"# Strong-Stock Lab report, {data.now_et():%Y-%m-%d}", ""]
    closed = pd.DataFrame()
    if not trd.empty:
        closed = trd[trd["status"] == "closed"].merge(
            sig[["signal_id", "action", "light", "rule_version", "cohort_rank", "setup_reasons"]],
            on="signal_id", how="left")
        news = store.load("news")
        if not news.empty:
            closed = closed.merge(news[["signal_id", "news_tone"]], on="signal_id", how="left")
        else:
            closed["news_tone"] = np.nan
        lines.append(f"{len(closed)} closed and {int((trd['status'] == 'open').sum())} open shadow trades.")
    else:
        lines.append("No shadow trades yet.")
    lines.append("")

    if not closed.empty:
        by = {}
        by["Screen vs control"] = {g: stats(closed[closed["group"] == g]) for g in ("cohort", "control")}
        coh = closed[closed["group"] == "cohort"]
        by["Cohort by light"] = {l: stats(coh[coh["light"] == l]) for l in ("green", "yellow", "red")}
        by["Cohort by action"] = {a: stats(coh[coh["action"] == a])
                                  for a in ("take", "take_half", "skip", "log_only")}
        by["Cohort by exit"] = {e: stats(coh[coh["exit_reason"] == e])
                                for e in ("target", "stop", "rsi2_strength", "time_stop")}
        by["Cohort by setup type"] = {r: stats(coh[coh["setup_reasons"].fillna("").str.contains(r)])
                                      for r in ("rsi2", "ema20", "down_streak")}
        by["Cohort by news (48h before trigger)"] = {
            t: stats(coh[coh["news_tone"].fillna("none") == t])
            for t in ("positive", "negative", "neutral", "none")}
        by["By rule version"] = {v: stats(coh[coh["rule_version"] == v])
                                 for v in sorted(coh["rule_version"].dropna().unique())}
        for title, groups in by.items():
            lines += table(title, groups)
        out["breakdowns"] = by

    bh = cohort_buy_hold()
    out["cohort_buy_hold"] = bh
    if bh:
        lines += ["## Buy-and-hold by cohort", "", "| Cohort | Through | Cohort % | Control % | SPY % |",
                  "|---|---|---|---|---|"]
        for r in bh:
            lines.append(f"| {r['cohort']} | {r['through']} | {r['cohort_ret_pct']} | "
                         f"{r['control_ret_pct']} | {r['spy_ret_pct']} |")
        lines.append("")
    (store.DATA / "report_latest.md").write_text("\n".join(lines))
    (store.DATA / "report_latest.json").write_text(json.dumps(out, indent=2, default=str) + "\n")
    data.log("Wrote data/report_latest.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
