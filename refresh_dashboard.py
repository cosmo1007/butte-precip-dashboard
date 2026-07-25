#!/usr/bin/env python3
"""
Butte County Precipitation Dashboard - Refresh Script
======================================================

Fetches only the current water year from CDEC. Historical water years are
frozen in ./cdec_cache/ and never re-fetched. Applies the spike filter to
remove sensor glitches, recomputes historical averages, and rebuilds
butte_precip_dashboard.html in place.

Usage:
    python3 refresh_dashboard.py

Run whenever you want to pull fresh data. Completed water years are never
re-fetched, so CDEC is hit with minimal traffic (5 requests per refresh).
"""
import csv, json, os, re, sys
from datetime import datetime, timedelta, date
from io import StringIO

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library not installed. Run: pip install requests")
    sys.exit(1)

# ------- Config -------
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, 'cdec_cache')
DASHBOARD_FILE = os.path.join(HERE, 'index.html')

STATIONS = {
    'CST': {'name': 'Cohasset', 'sensor': '2', 'dur': 'H', 'kind': 'accumulated',
            'elevation': '1,600 ft', 'lat': 39.875278, 'lon': -121.770554,
            'operator': 'CAL FIRE'},
    'OPS': {'name': 'Openshaw', 'sensor': '2', 'dur': 'D', 'kind': 'accumulated',
            'elevation': '268 ft', 'lat': 39.589833, 'lon': -121.635161,
            'operator': 'CAL FIRE'},
    'CAR': {'name': 'Carpenter Ridge', 'sensor': '2', 'dur': 'H', 'kind': 'accumulated',
            'elevation': '4,812 ft', 'lat': 40.069, 'lon': -121.582,
            'operator': 'CAL FIRE'},
    'PDE': {'name': 'Paradise', 'sensor': '2', 'dur': 'D', 'kind': 'accumulated',
            'elevation': '1,750 ft', 'lat': 39.7536, 'lon': -121.6247,
            'operator': 'DWR'},
    'CES': {'name': 'Chico University Farm', 'sensor': '2', 'dur': 'M',
            'kind': 'monthly_incremental', 'elevation': '185 ft',
            'lat': 39.700, 'lon': -121.817, 'operator': 'NWS'},
}
START_WY = 2016

# ------- NOAA Atlas 14 precipitation-frequency thresholds -------
# Point estimates (inches) from the NOAA Precipitation Frequency Data Server,
# NOAA Atlas 14 Volume 6 Version 2, partial-duration series, retrieved
# 2026-07-24 for each station's own CDEC coordinates:
#   https://hdsc.nws.noaa.gov/cgi-bin/new/fe_text_mean.csv
#       ?lat=<lat>&lon=<lon>&data=depth&units=english&series=pds
# Keys are window lengths in days; values are depths at each ARI in NOAA_ARI.
# These are fixed published values — they do not need re-fetching on refresh.
NOAA_ARI = [1, 2, 5, 10, 25, 50, 100]
NOAA = {
    'CST': {1: [3.59, 4.66, 6.01, 7.09, 8.52, 9.6, 10.7],
            2: [4.93, 6.39, 8.26, 9.75, 11.7, 13.2, 14.7],
            3: [5.85, 7.56, 9.76, 11.5, 13.9, 15.6, 17.4],
            4: [6.57, 8.5, 11, 12.9, 15.5, 17.5, 19.4],
            7: [8.31, 10.7, 13.8, 16.2, 19.3, 21.6, 23.9],
            10: [9.5, 12.3, 15.7, 18.4, 21.8, 24.4, 26.9],
            20: [12.7, 16.4, 20.9, 24.3, 28.6, 31.8, 34.8],
            30: [15.3, 19.7, 25, 29, 34, 37.6, 41]},
    'OPS': {1: [2.11, 2.76, 3.59, 4.24, 5.08, 5.71, 6.32],
            2: [2.77, 3.66, 4.78, 5.64, 6.77, 7.6, 8.4],
            3: [3.22, 4.24, 5.54, 6.54, 7.83, 8.78, 9.7],
            4: [3.59, 4.71, 6.12, 7.22, 8.65, 9.68, 10.7],
            7: [4.51, 5.84, 7.51, 8.82, 10.5, 11.8, 13],
            10: [5.14, 6.59, 8.44, 9.88, 11.8, 13.1, 14.5],
            20: [6.86, 8.76, 11.1, 13, 15.4, 17.2, 18.9],
            30: [8.32, 10.6, 13.5, 15.7, 18.5, 20.5, 22.5]},
    'CAR': {1: [4.65, 5.8, 7.33, 8.58, 10.3, 11.6, 13],
            2: [6.57, 8.36, 10.7, 12.6, 15.2, 17.2, 19.2],
            3: [7.9, 10.2, 13.1, 15.5, 18.7, 21.1, 23.6],
            4: [8.91, 11.5, 14.9, 17.6, 21.2, 24, 26.8],
            7: [11.6, 15, 19.3, 22.8, 27.5, 31, 34.6],
            10: [13.2, 17, 21.9, 25.9, 31.1, 35, 38.9],
            20: [17.3, 22.4, 28.7, 33.7, 40.2, 45, 49.7],
            30: [20.8, 26.8, 34.3, 40.1, 47.6, 53, 58.2]},
    'PDE': {1: [3.86, 5, 6.42, 7.53, 8.96, 10, 11],
            2: [5.05, 6.56, 8.46, 9.96, 11.9, 13.3, 14.8],
            3: [5.96, 7.73, 9.97, 11.7, 14.1, 15.8, 17.5],
            4: [6.67, 8.62, 11.1, 13, 15.6, 17.5, 19.5],
            7: [8.34, 10.6, 13.5, 15.8, 18.8, 21, 23.2],
            10: [9.68, 12.2, 15.4, 18, 21.3, 23.7, 26.1],
            20: [13.2, 16.6, 20.8, 24.1, 28.4, 31.5, 34.5],
            30: [15.8, 20, 25, 28.9, 33.8, 37.3, 40.7]},
    # CES is monthly manual entry — no storm analysis is possible, but the
    # thresholds are kept so the panel can explain what it would compare to.
    'CES': {1: [2.02, 2.82, 3.78, 4.48, 5.35, 5.96, 6.53],
            2: [2.6, 3.69, 4.99, 5.97, 7.18, 8.04, 8.84],
            3: [3.01, 4.29, 5.84, 7, 8.45, 9.47, 10.4],
            4: [3.3, 4.71, 6.41, 7.69, 9.29, 10.4, 11.5],
            7: [4.07, 5.77, 7.8, 9.32, 11.2, 12.5, 13.8],
            10: [4.62, 6.5, 8.73, 10.4, 12.4, 13.9, 15.2],
            20: [6.2, 8.54, 11.3, 13.4, 15.9, 17.7, 19.3],
            30: [7.66, 10.3, 13.5, 15.9, 18.8, 20.8, 22.7]},
}
STORM_DURATIONS = [1, 2, 3, 4, 7, 10, 20, 30]

# ------- Water-year helpers -------
def current_water_year(today=None):
    """Return the WY number for a given date. Oct–Dec counts toward next WY."""
    today = today or date.today()
    return today.year + 1 if today.month >= 10 else today.year

def is_completed_wy(wy, today=None):
    """A water year is complete once its Sep 30 end date has passed."""
    today = today or date.today()
    return today > date(wy, 9, 30)

# ------- CDEC fetch -------
API = 'https://cdec.water.ca.gov/dynamicapp/req/CSVDataServlet'

def fetch(station, sensor, dur, start, end):
    r = requests.get(API, params={'Stations': station, 'SensorNums': sensor,
                                   'dur_code': dur, 'Start': start, 'End': end},
                     timeout=60)
    r.raise_for_status()
    rows = []
    for row in csv.DictReader(StringIO(r.text)):
        try:
            v = row['VALUE'].strip()
            if v in ('', '---', '-9999', '-9998'): continue
            val = float(v)
            if val < -100: continue
            rows.append([row['DATE TIME'], val])
        except Exception:
            continue
    return rows

def cache_is_final(blob, wy, dur):
    """True if a cached file actually covers the whole water year.

    A cache written mid-year is missing that year's final days. Trusting it
    the moment the WY rolls over — which is what a bare os.path.exists check
    does — freezes those missing days in permanently, a few more every year.
    """
    if blob.get('final'):
        return True
    rows = blob.get('rows') or []
    if not rows:
        return False
    try:
        last = datetime.strptime(rows[-1][0], '%Y%m%d %H%M').date()
    except Exception:
        return False
    if dur == 'M':
        return (last.year, last.month) >= (wy, 9)
    # Accumulated gauges rebaseline in the last days of September, so CDEC
    # stops returning data a day or two before Sep 30.
    return last >= date(wy, 9, 28)


def fetch_or_cache(code, wy, meta):
    """Use cached file only if it covers the completed WY. Otherwise fetch."""
    path = os.path.join(CACHE_DIR, f'{code}_{wy}.json')
    if is_completed_wy(wy) and os.path.exists(path):
        try:
            blob = json.load(open(path))
        except (ValueError, OSError):
            blob = None
        if blob and cache_is_final(blob, wy, meta['dur']):
            return blob['rows'], 'cached'
    # Current WY, missing cache, or a cache that stopped short of Sep 30
    start = f'{wy-1}-10-01'
    end = min(f'{wy}-09-30', date.today().isoformat())
    rows = fetch(code, meta['sensor'], meta['dur'], start, end)
    with open(path, 'w') as f:
        json.dump({'rows': rows, 'station': code, 'wy': wy,
                   'final': is_completed_wy(wy)}, f)
    return rows, 'fetched'

# ------- Spike filter + cumulative calc -------
def clean_spikes(parsed):
    """Drop single-point readings that sit > 1\" below both neighbors (sensor glitch)."""
    cleaned = []
    n = len(parsed)
    for i in range(n):
        dt, v = parsed[i]
        if 0 < i < n - 1:
            prev_v = parsed[i-1][1]
            next_v = parsed[i+1][1]
            if v < prev_v - 1.0 and v < next_v - 1.0:
                continue  # spike-down glitch
            if v > prev_v + 5.0 and v > next_v + 5.0:
                continue  # spike-up (unusual but safety net)
        cleaned.append((dt, v))
    return cleaned

def process_accumulated(rows, wy):
    start = date(wy-1, 10, 1)
    parsed = []
    for r in rows:
        try:
            dt = datetime.strptime(r[0], '%Y%m%d %H%M')
            parsed.append((dt, float(r[1])))
        except Exception:
            continue
    parsed.sort()
    if not parsed:
        return [None] * 366
    parsed = clean_spikes(parsed)
    cumulative = 0.0
    last_val = parsed[0][1]
    daily_cum = {}
    for dt, v in parsed:
        d = dt.date()
        if d < start: continue
        day_idx = (d - start).days
        if day_idx < 0 or day_idx > 365: continue
        diff = v - last_val
        if diff < -1.0:
            pass  # gauge reset — rebaseline without crediting negative
        elif diff > 0:
            cumulative += diff
        last_val = v
        daily_cum[day_idx] = cumulative
    result = [None] * 366
    cur = 0.0
    seen = False
    for i in range(366):
        if i in daily_cum:
            cur = daily_cum[i]; seen = True; result[i] = round(cur, 2)
        else:
            result[i] = round(cur, 2) if seen else 0.0
    return result

def native_cumulative(rows, wy):
    """Cumulative inches since Oct 1 at the record's own resolution.

    Returns [(datetime, cumulative)], keeping hourly stations hourly so that
    rolling windows are true n x 24-hour windows rather than calendar days.
    """
    start = date(wy - 1, 10, 1)
    parsed = []
    for r in rows:
        try:
            dt = datetime.strptime(r[0], '%Y%m%d %H%M')
            parsed.append((dt, float(r[1])))
        except Exception:
            continue
    parsed.sort()
    if not parsed:
        return []
    parsed = clean_spikes(parsed)
    series = []
    cumulative = 0.0
    last_val = parsed[0][1]
    for dt, v in parsed:
        if dt.date() < start:
            last_val = v
            continue
        diff = v - last_val
        if diff < -1.0:
            pass          # gauge reset — rebaseline without crediting negative
        elif diff > 0:
            cumulative += diff
        last_val = v
        series.append((dt, cumulative))
    return series


def classify_ari(total, thresholds):
    """Highest ARI whose threshold this total meets. 0 if below the 1-year."""
    best = 0
    for ari, depth in zip(NOAA_ARI, thresholds):
        if total >= depth:
            best = ari
    return best


def compute_storms(rows, wy, code, meta):
    """Largest rolling total at each duration, classified against NOAA Atlas 14.

    Monthly stations are skipped — a month total cannot resolve a storm.
    """
    if meta['kind'] != 'accumulated':
        return None
    series = native_cumulative(rows, wy)
    if len(series) < 2:
        return None
    lookup = {dt: c for dt, c in series}
    thresholds = NOAA.get(code)
    if not thresholds:
        return None
    out = []
    for days in STORM_DURATIONS:
        span = timedelta(days=days)
        best = None
        for dt, c in series:
            prior = lookup.get(dt - span)
            if prior is None:
                continue
            total = c - prior
            if best is None or total > best[0]:
                best = (total, dt)
        if best is None or best[0] <= 0:
            continue
        total, end_dt = best
        out.append({
            'days': days,
            'in': round(total, 2),
            'start': (end_dt - span).strftime('%Y-%m-%d'),
            'end': end_dt.strftime('%Y-%m-%d'),
            'ari': classify_ari(total, thresholds[days]),
        })
    if not out:
        return None
    return {'resolution': 'hourly' if meta['dur'] == 'H' else 'daily',
            'rows': out}


def process_monthly(rows, wy):
    start = date(wy-1, 10, 1)
    month_totals = {}
    for r in rows:
        try:
            dt = datetime.strptime(r[0], '%Y%m%d %H%M')
            month_totals[(dt.year, dt.month)] = float(r[1])
        except Exception:
            continue
    result = [None] * 366
    for i in range(366):
        d = start + timedelta(days=i)
        first_of = date(d.year, d.month, 1)
        nextm = date(d.year+1, 1, 1) if d.month == 12 else date(d.year, d.month+1, 1)
        days_in_month = (nextm - first_of).days
        month_val = month_totals.get((d.year, d.month), 0.0)
        prior = 0.0
        cur_d = start
        while cur_d < first_of:
            prior += month_totals.get((cur_d.year, cur_d.month), 0.0)
            cur_d = date(cur_d.year+1, 1, 1) if cur_d.month == 12 else date(cur_d.year, cur_d.month+1, 1)
        frac = d.day / days_in_month
        result[i] = round(prior + frac * month_val, 2)
    return result

# ------- Dashboard rebuild -------
def build_data():
    today = date.today()
    end_wy = current_water_year(today)
    water_years = list(range(START_WY, end_wy + 1))
    out = {'stations': {}, 'water_years': water_years,
           'generated_at': datetime.utcnow().isoformat() + 'Z'}
    fetch_count = 0
    cache_count = 0
    for code, meta in STATIONS.items():
        print(f'\n{code} ({meta["name"]}):')
        station_data = {'meta': {k: meta[k] for k in ['name','elevation','lat','lon','operator','kind']},
                        'noaa': NOAA.get(code),
                        'years': {}}
        for wy in water_years:
            rows, source = fetch_or_cache(code, wy, meta)
            if source == 'fetched': fetch_count += 1
            else: cache_count += 1
            if meta['kind'] == 'accumulated':
                arr = process_accumulated(rows, wy)
            else:
                arr = process_monthly(rows, wy)
            # Trim current WY to today
            if wy == end_wy:
                wy_start = date(wy-1, 10, 1)
                days_elapsed = (today - wy_start).days
                for i in range(days_elapsed + 1, 366):
                    arr[i] = None
            valid = [v for v in arr if v is not None]
            total = max(valid) if valid else 0.0
            year_entry = {'cumulative_daily': arr, 'total': round(total, 2)}
            storms = compute_storms(rows, wy, code, meta)
            if storms:
                year_entry['storms'] = storms
            station_data['years'][str(wy)] = year_entry
            tag = '[cached]' if source == 'cached' else '[fetched]'
            print(f'  WY{wy} {tag}: total={total:.2f}"')
        out['stations'][code] = station_data

    # Historical averages: all completed water years
    complete_ys = [str(wy) for wy in water_years if is_completed_wy(wy, today)]
    for code, sdata in out['stations'].items():
        averages = []
        for day_idx in range(366):
            vals = []
            for y in complete_ys:
                v = sdata['years'].get(y, {}).get('cumulative_daily', [None])[day_idx]
                if v is not None:
                    vals.append(v)
            averages.append(round(sum(vals)/len(vals), 2) if vals else None)
        sdata['historical_avg'] = averages

    print(f'\nSummary: {fetch_count} fetched, {cache_count} cached')
    return out

def update_html(data):
    if not os.path.exists(DASHBOARD_FILE):
        print(f'ERROR: dashboard file not found at {DASHBOARD_FILE}')
        sys.exit(1)
    html = open(DASHBOARD_FILE).read()
    data_json = json.dumps(data, separators=(',', ':'))
    new_html, n = re.subn(r'const DATA = \{.*?\};',
                          f'const DATA = {data_json};',
                          html, count=1, flags=re.DOTALL)
    if n != 1:
        print('ERROR: could not find DATA placeholder in HTML')
        sys.exit(1)
    with open(DASHBOARD_FILE, 'w') as f:
        f.write(new_html)
    print(f'\nUpdated {DASHBOARD_FILE}')

if __name__ == '__main__':
    print(f'Butte County Precipitation Dashboard — Refresh')
    print(f'Date: {date.today()}  |  Current WY: {current_water_year()}')
    print(f'Cache: {CACHE_DIR}')
    data = build_data()
    update_html(data)
    print('\nDone.')
