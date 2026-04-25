# Butte County Precipitation Dashboard

Cumulative water-year precipitation for five CDEC stations in Butte County:
Cohasset (CST), Openshaw (OPS), Carpenter Ridge (CAR), Paradise (PDE), and
Chico University Farm (CES). Covers WY2016 through the current water year,
with a historical-average overlay for context.

**Live dashboard:** https://cosmo1007.github.io/butte-precip-dashboard/

## How it stays current

Historical water years are frozen in `cdec_cache/` and never re-fetched.
Only the current (in-progress) water year is pulled from CDEC on each
refresh. The spike filter cleans out single-point sensor glitches before
computing cumulative totals.

A GitHub Actions workflow (`.github/workflows/refresh.yml`) runs the
refresh automatically every Sunday at 7am Pacific. To trigger an
on-demand refresh, go to the
[Actions tab](https://github.com/cosmo1007/butte-precip-dashboard/actions/workflows/refresh.yml)
and click "Run workflow."

## Files

- `index.html` — the dashboard (self-contained, single file)
- `refresh_dashboard.py` — fetches new data, applies spike filter, rebuilds the HTML
- `requirements.txt` — Python dependencies (`requests` only)
- `cdec_cache/` — frozen raw data for completed water years (one JSON per station per WY)
- `.github/workflows/refresh.yml` — scheduled + manual refresh job

## Running locally

```bash
pip install -r requirements.txt
python3 refresh_dashboard.py
open index.html
```

## Data source

[California Data Exchange Center (CDEC)](https://cdec.water.ca.gov/),
sensor 2 (precipitation, accumulated). Hourly data for CST and CAR; daily
for OPS and PDE; monthly manual entry for CES.

## Spike filter

Single-point readings that fall more than 1" below both their immediate
neighbors are dropped before cumulative totals are computed. This catches
sensor glitches like the 2019-06-02 CAR reading that briefly dipped from
72.32" to 15.00" and back, which would otherwise inflate the water-year
total by ~57".
