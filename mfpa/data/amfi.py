"""AMFI scheme list (NAVAll.txt): scheme code, ISIN, name, plan, option, category. Cached 1 day in ~/.mfpa/amfi."""
import os, re, time, urllib.request
CACHE = os.path.expanduser("~/.mfpa/amfi/NAVAll.txt")
URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
CAT = {"large cap fund": "Large cap", "large & mid cap fund": "Large & mid", "mid cap fund": "Mid cap", "small cap fund": "Small cap",
       "multi cap fund": "Multi cap", "flexi cap fund": "Flexi cap", "focused fund": "Focused", "value fund": "Value", "contra fund": "Contra",
       "elss": "ELSS", "elss- tax saver fund": "ELSS", "aggressive hybrid fund": "Aggressive hybrid",
       "multi asset allocation": "Multi asset", "multi asset allocation fund": "Multi asset"}

def _load():
    if not (os.path.exists(CACHE) and time.time() - os.path.getmtime(CACHE) < 86400):
        os.makedirs(os.path.dirname(CACHE), mode=0o700, exist_ok=True)
        req = urllib.request.Request(URL, headers={"User-Agent": "mf-portfolio-analyser/0.1"})
        open(CACHE, "wb").write(urllib.request.urlopen(req, timeout=60).read())
    rows, cat, raw = {}, None, None
    for line in open(CACHE, encoding="utf-8", errors="replace"):
        line = line.strip()
        m = re.match(r"Open Ended Schemes\((?:\w+) Schemes? - (.+)\)$", line)
        if m: raw = m.group(1).strip(); cat = CAT.get(raw.lower(), raw); continue
        if line.startswith(("Open Ended", "Close Ended", "Interval")): cat = None; raw = None; continue
        p = line.split(";")
        if len(p) < 8 or not p[0].isdigit(): continue
        rows[int(p[0])] = dict(code=int(p[0]), isin=p[1].strip(), isin2=p[2].strip(), name=p[3].strip(), plan=p[4].strip(), option=p[5].strip(),
                                nav=p[6].strip(), date=p[7].strip(), category=cat, amfi_category=raw)
    return rows

_ROWS = None
def rows():
    global _ROWS
    if _ROWS is None: _ROWS = _load()
    return _ROWS

GROWTH = re.compile(r"^\s*(direct\s+)?growth(\s+option|\s+plan)?\s*$", re.I)
def is_growth(r): return bool(GROWTH.match(r["option"])) or (not r["option"] and not re.search(r"idcw|dividend|bonus", r["name"], re.I))
def by_isin(isin):
    return next((r for r in rows().values() if isin in (r["isin"], r["isin2"])), None)

def twin(code, want="Regular"):
    """The same scheme's growth option in the other plan (Direct <-> Regular), matched on scheme name and AMFI category."""
    r = rows().get(code)
    if not r: return None
    cands = [x for x in rows().values() if x["name"].lower() == r["name"].lower() and x["category"] == r["category"]
             and want.lower() in x["plan"].lower() and is_growth(x) and x["code"] != code]
    if cands: return cands[0]["code"]
    # some schemes carry no plan/option labels: the regular plan is the same-name scheme whose NAV is 70-99% of the direct's
    try: n0 = float(r["nav"])
    except ValueError: return None
    same = [x for x in rows().values() if x["name"].lower() == r["name"].lower() and x["code"] != code and not x["plan"]]
    def ratio(x):
        try: return float(x["nav"]) / n0
        except (ValueError, ZeroDivisionError): return 0
    pick = [x for x in same if (0.70 <= ratio(x) < 0.995 if want == "Regular" else 1.005 < ratio(x) <= 1.43)]
    return max(pick, key=ratio)["code"] if pick else None
