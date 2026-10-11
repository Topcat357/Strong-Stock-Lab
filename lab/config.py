"""
Every rule in the Strong-Stock Lab lives here.

Change a number -> bump RULE_VERSION. Each logged signal records the version
it was produced under, so results from different rule sets never get mixed.
"""

RULE_VERSION = "v1"

# ---------------------------------------------------------------- Layer 1: macro
MACRO = {
    "vix_green_max": 20.0,         # VIX under this = green input
    "vix_red_min": 28.0,           # VIX above this = red input
    "breadth_green_min": 50.0,     # % of liquid US stocks above their 50-day; below = yellow
    "yellow_rank_max": 20,         # yellow light: only cohort rank 1-20 are "take"
}

# ---------------------------------------------------------- Layer 2: weekly screen
SCREEN = {
    "price_min": 5.0,
    "price_max": 100.0,
    "dollar_vol_min": 10_000_000,   # 50-day average daily dollar volume
    "rs_top_pct": 20.0,             # 6-month return in top 20% of the liquid universe
    "max_off_high_pct": 25.0,       # within 25% of the 52-week high
    "sma200_rising_days": 20,       # 200-day SMA higher than 20 sessions ago
    "cohort_max": 60,
    "control_size": 60,             # random liquid stocks that FAILED the screen
    "exchanges": ["NASDAQ", "NYSE", "AMEX"],
}

# ------------------------------------------------------- Layer 3: setup + trigger
SETUP = {
    "rsi2_max": 15.0,              # daily RSI(2) below this
    "ema20_atr_band": 1.0,         # close within 1 ATR(14) of the 20-day EMA
    "down_closes_min": 3,          # or 3+ lower closes in a row
    "valid_sessions": 3,           # trigger must come within the next 3 sessions
    "earnings_blackout_days": 3,   # no entries within 3 trading days before earnings
}

TRIGGER = {
    "rvol_min": 1.5,               # hourly volume vs 20-day average for that hour
    "rvol_lookback_days": 20,
    "first_bar_start": "09:30",    # the 9:30-10:30 bar may trigger at its 10:30 close
}

# ---------------------------------------------------------------------- exits
EXITS = {
    "stop_buffer_atr": 0.25,       # stop = pullback low - 0.25 ATR
    "stop_max_atr": 2.0,           # ...but never more than 2 ATR below entry
    "stop_min_atr": 0.5,           # ...and never less than 0.5 ATR (entry gapped near the low)
    "target_r": 2.0,               # target = entry + 2R
    "rsi2_exit": 70.0,             # daily close with RSI(2) above 70
    "time_stop_days": 10,          # close of the 10th trading day
}

POSITION_USD = 1000.0
