# Strong-Stock Lab report, 2026-11-15

News sources agree on 71 of 158 signals tagged by both.

204 closed and 8 open shadow trades.

## Screen vs control

| | Trades | Win % | Avg R | Avg % | SPY % | Days |
|---|---|---|---|---|---|---|
| cohort | 143 | 51.0 | -0.02 | -0.01 | -0.04 | 1.8 |
| control | 61 | 62.3 | 0.15 | 0.48 | 0.04 | 1.6 |

## Cohort by light

| | Trades | Win % | Avg R | Avg % | SPY % | Days |
|---|---|---|---|---|---|---|
| green | 19 | 57.9 | 0.12 | 0.57 | -0.78 | 2.0 |
| yellow | 101 | 44.6 | -0.1 | -0.39 | -0.13 | 1.7 |
| red | 23 | 73.9 | 0.21 | 1.22 | 0.97 | 1.8 |

## Cohort by action

| | Trades | Win % | Avg R | Avg % | SPY % | Days |
|---|---|---|---|---|---|---|
| take | 19 | 57.9 | 0.12 | 0.57 | -0.78 | 2.0 |
| take_half | 33 | 36.4 | -0.28 | -1.09 | -0.44 | 1.6 |
| skip | 68 | 48.5 | -0.02 | -0.05 | 0.02 | 1.8 |
| log_only | 23 | 73.9 | 0.21 | 1.22 | 0.97 | 1.8 |

## Cohort by exit

| | Trades | Win % | Avg R | Avg % | SPY % | Days |
|---|---|---|---|---|---|---|
| target | 11 | 100.0 | 2.18 | 5.03 | 0.12 | 2.1 |
| stop | 48 | 0.0 | -1.07 | -3.95 | -0.97 | 2.2 |
| rsi2_strength | 84 | 73.8 | 0.29 | 1.59 | 0.47 | 1.5 |
| time_stop | 0 | | | | | |

## Cohort by setup type

| | Trades | Win % | Avg R | Avg % | SPY % | Days |
|---|---|---|---|---|---|---|
| rsi2 | 47 | 51.1 | 0.06 | 0.41 | 0.15 | 2.0 |
| ema20 | 119 | 47.9 | -0.07 | -0.25 | -0.14 | 1.7 |
| down_streak | 19 | 42.1 | -0.12 | 0.51 | -0.18 | 1.9 |

## Cohort by news (48h before trigger)

| | Trades | Win % | Avg R | Avg % | SPY % | Days |
|---|---|---|---|---|---|---|
| positive | 38 | 31.6 | -0.39 | -1.28 | -0.43 | 1.7 |
| negative | 2 | 0.0 | -0.63 | -2.49 | 0.63 | 3.0 |
| neutral | 13 | 76.9 | 0.66 | 3.84 | 0.16 | 2.5 |
| none | 90 | 56.7 | 0.05 | 0.03 | 0.08 | 1.7 |

## By rule version

| | Trades | Win % | Avg R | Avg % | SPY % | Days |
|---|---|---|---|---|---|---|
| v1 | 143 | 51.0 | -0.02 | -0.01 | -0.04 | 1.8 |

## Buy-and-hold by cohort

| Cohort | Through | Cohort % | Control % | SPY % |
|---|---|---|---|---|
| 2026-10-11 | 2026-10-18 | -5.68 | -1.89 | -1.97 |
| 2026-10-18 | 2026-10-25 | 4.85 | 1.31 | -0.43 |
| 2026-10-25 | 2026-11-01 | -0.05 | 1.32 | -0.56 |
| 2026-11-01 | 2026-11-08 | -3.08 | 0.53 | -2.7 |
| 2026-11-08 | today | 1.27 | 1.49 | 2.59 |
