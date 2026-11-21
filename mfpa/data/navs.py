"""NAV history from mfapi.in with a local cache (1-day TTL) in ~/.mfpa/nav, retries with backoff."""
import json, os, time, datetime as dt, urllib.request
CACHE = os.path.expanduser("~/.mfpa/nav")
UA = "mf-portfolio-analyser/0.1 (+https://github.com/Alafazam/mf-portfolio-analyser)"

def nav(code, ttl_hours=24):
    """{date: nav} for an AMFI scheme code."""
    os.makedirs(CACHE, mode=0o700, exist_ok=True)
    p = os.path.join(CACHE, f"{code}.json")
    if not (os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl_hours * 3600):
        for attempt in range(4):
            try:
                req = urllib.request.Request(f"https://api.mfapi.in/mf/{code}", headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=60) as r: data = r.read()
                json.loads(data); open(p, "wb").write(data); break
            except Exception:
                if attempt == 3 and not os.path.exists(p): raise
                time.sleep(2 + 3 * attempt)
    d = json.load(open(p))
    return {dt.datetime.strptime(x["date"], "%d-%m-%Y").date(): float(x["nav"]) for x in d["data"] if float(x["nav"]) > 0}

def on_or_after(series, d, max_days=10):
    """(date, nav) of the first NAV on or after d: the allotment date for a purchase made on d."""
    for k in range(max_days):
        x = d + dt.timedelta(days=k)
        if x in series: return x, series[x]
    return None, None

def on_or_before(series, d, max_days=10):
    for k in range(max_days):
        x = d - dt.timedelta(days=k)
        if x in series: return x, series[x]
    return None, None
