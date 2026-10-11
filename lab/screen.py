"""Layer 2: the weekly cohort of strong long-term stocks, plus a random control group."""

import numpy as np
import pandas as pd

from . import config, data
from .indicators import sma

UNIVERSE_COLUMNS = [
    "description", "close", "SMA50", "SMA200", "Perf.6M", "Perf.Y", "price_52_week_high",
    "average_volume_30d_calc", "market_cap_basic", "sector",
    "earnings_release_next_date", "total_revenue_yoy_growth_fq",
]


def fetch_universe():
    """Every active US common stock priced $5-$100 that trades at least 100K shares a day."""
    c = config.SCREEN
    filters = data.base_filters(c["exchanges"]) + [
        data.tv_filter("close", "in_range", [c["price_min"], c["price_max"]]),
        data.tv_filter("average_volume_30d_calc", "greater", 100_000),
    ]
    return data.tv_scan(UNIVERSE_COLUMNS, filters, sort=("market_cap_basic", "desc"), limit=6000)


def liquid(universe: pd.DataFrame) -> pd.DataFrame:
    u = universe.copy()
    u["dollar_vol_est"] = u["close"] * u["average_volume_30d_calc"]
    return u[u["dollar_vol_est"] >= config.SCREEN["dollar_vol_min"]].reset_index(drop=True)


def first_pass(liq: pd.DataFrame) -> pd.DataFrame:
    """Everything the screener alone can decide. Adds rs_pct (0-100) to every row."""
    c = config.SCREEN
    u = liq.copy()
    u["rs_pct"] = u["Perf.6M"].rank(pct=True) * 100
    u["off_high_pct"] = (1 - u["close"] / u["price_52_week_high"]) * 100
    ok = (
        (u["rs_pct"] >= 100 - c["rs_top_pct"])
        & (u["Perf.Y"] > 0)
        & (u["close"] > u["SMA200"])
        & (u["SMA50"] > u["SMA200"])
        & (u["off_high_pct"] <= c["max_off_high_pct"])
        & (u["total_revenue_yoy_growth_fq"] > 0)
    )
    u["pass_first"] = ok.fillna(False)
    return u


def confirm_with_bars(cands: pd.DataFrame, bars: dict) -> pd.DataFrame:
    """Checks that need real bars: rising 200-day and true 50-day dollar volume."""
    c = config.SCREEN
    keep = []
    for _, r in cands.iterrows():
        df = bars.get(r["symbol"])
        if df is None or len(df) < 200 + c["sma200_rising_days"]:
            continue
        s200 = sma(df["close"], 200)
        rising = s200.iloc[-1] > s200.iloc[-1 - c["sma200_rising_days"]]
        dv50 = (df["close"] * df["volume"]).tail(50).mean()
        if rising and dv50 >= c["dollar_vol_min"]:
            row = r.to_dict()
            row["dollar_vol_50d"] = dv50
            row["sma200_slope_pct"] = (s200.iloc[-1] / s200.iloc[-1 - c["sma200_rising_days"]] - 1) * 100
            keep.append(row)
    return pd.DataFrame(keep)


def pick_control(liq_ranked: pd.DataFrame, exclude: set, cohort_date: str) -> pd.DataFrame:
    """Random liquid stocks that failed the screen. Seeded by the date, so reruns pick the same names."""
    pool = liq_ranked[~liq_ranked["pass_first"] & ~liq_ranked["symbol"].isin(exclude)]
    n = min(config.SCREEN["control_size"], len(pool))
    seed = int(cohort_date.replace("-", ""))
    return pool.sample(n=n, random_state=seed)


def build(cohort_date: str):
    """Returns (cohort_df, liquid_universe_df). cohort_df has group = cohort | control."""
    uni = fetch_universe()
    data.log(f"Universe: {len(uni)} stocks")
    liq = first_pass(liquid(uni))
    data.log(f"Liquid: {len(liq)}; first pass: {int(liq['pass_first'].sum())}")
    cands = liq[liq["pass_first"]].sort_values("rs_pct", ascending=False)
    bars = data.get_bars(cands["symbol"].tolist(), "1d", "2y")
    strong = confirm_with_bars(cands, bars)
    if strong.empty:
        raise RuntimeError("No stock passed the screen; check the data source")
    strong = strong.sort_values("rs_pct", ascending=False).head(config.SCREEN["cohort_max"])
    strong["group"] = "cohort"
    strong["rank"] = np.arange(1, len(strong) + 1)
    control = pick_control(liq, set(strong["symbol"]), cohort_date)
    control = control.assign(group="control", rank=np.nan)
    out = pd.concat([strong, control], ignore_index=True).rename(columns={"description": "name"})
    out.insert(0, "cohort_date", cohort_date)
    out["rule_version"] = config.RULE_VERSION
    cols = ["cohort_date", "group", "rank", "symbol", "name", "sector", "close", "rs_pct",
            "Perf.6M", "Perf.Y", "off_high_pct", "sma200_slope_pct", "dollar_vol_50d",
            "market_cap_basic", "total_revenue_yoy_growth_fq", "earnings_release_next_date",
            "rule_version"]
    return out.reindex(columns=cols), liq
