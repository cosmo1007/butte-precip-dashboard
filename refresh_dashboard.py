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

def fetch_or_cache(code, wy, meta):
    """Use cached file if the WY is completed. Otherwise fetch fresh."""
    path = os.path.join(CACHE_DIR, f'{code}_{wy}.json')
    if is_completed_wy(wy) and os.path.exists(path):
        return json.load(open(path))['rows'], 'cached'
    # Current WY (or missing cache) — fetch from CDEC
    start = f'{wy-1}-10-01'
    end = min(f'{wy}-09-30', date.today().isoformat())
    rows = fetch(code, meta['sensor'], meta['dur'], start, end)
    with open(path, 'w') as f:
        json.dump({'rows': rows, 'station': code, 'wy': wy}, f)
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
            station_data['years'][str(wy)] = {'cumulative_daily': arr, 'total': round(total, 2)}
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
