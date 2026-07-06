# Backtest data snapshots

Committed CSV snapshots of public FRED monthly series, so the calibration
backtest (`v3/backtest.py`) runs offline and reproducibly. Source: the keyless
FRED CSV endpoint `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>`.

| File | Series | Coverage | Fetched |
|------|--------|----------|---------|
| UNRATE.csv | U.S. civilian unemployment rate (monthly, %) | 1948-01 – 2026-06 | 2026-07-06 |
| CPIAUCSL.csv | CPI, all urban consumers, SA (monthly index) | 1947-01 – 2026-05 | 2026-07-06 |
| INDPRO.csv | Industrial production index (monthly) | 1919-01 – 2026-05 | 2026-07-06 |

Refresh with `python3 v3/backtest.py --fetch` (stdlib urllib; network use is
opt-in, same posture as `v3/feeds/`). These data are U.S. government works /
public data republished by FRED; they are simulation inputs here, not a
rebroadcast feed.
