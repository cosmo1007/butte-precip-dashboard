# Butte County Precipitation Dashboard

Cumulative water-year precipitation for five CDEC stations in Butte County:
Cohasset (CST), Openshaw (OPS), Carpenter Ridge (CAR), Paradise (PDE), and
Chico University Farm (CES). Covers WY2016 through the current water year,
with a historical-average overlay for context.

**Live dashboard:** https://agubc-vina.github.io/butte-precip-dashboard/

## How it stays current

Historical water years are frozen in `cdec_cache/` and never re-fetched.
Only the current (in-progress) water year is pulled from CDEC on each
refresh. The spike filter cleans out single-point sensor glitches before
computing cumulative totals.

A GitHub Actions workflow (`.github/workflows/refresh.yml`) runs the
refresh automatically every Sunday at 7am Pacific. To trigger an
on-demand refresh, go to the
[Actions tab](https://github.com/AGUBC-vina/butte-precip-dashboard/actions/workflows/refresh.yml)
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

## License

**Code.** The build and refresh scripts, the dashboard HTML/CSS/JS, and any
GitHub Actions workflows are released under the MIT License. See
[`LICENSE`](LICENSE).

**Content.** The written analysis, figures, tables, and derived values are
released by Agricultural Groundwater Users of Butte County (AGUBC) under
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
See [`LICENSE-CONTENT`](LICENSE-CONTENT). Attribute to AGUBC and link back to
this repository.

**Underlying data.** The third-party datasets named elsewhere in this README are
not AGUBC's to license. They remain subject to their own terms, and neither
license above extends to them.
