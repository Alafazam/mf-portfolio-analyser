"""Turn samples/sample_portfolio.json (a made-up purchase pattern) into transactions, FIFO lots and holdings,
using real NAVs on each date. Writes samples/sample_holdings.json — the same shape the CAS ingest will produce."""
import json, os, sys, datetime as dt
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from mfpa.data.navs import nav, on_or_after, on_or_before
from mfpa.analysis.stats import xirr
P = json.load(open(os.path.join(ROOT, "samples", "sample_portfolio.json")))
AS_OF = dt.date.fromisoformat(P["as_of"])
D = lambda s: dt.date.fromisoformat(s)

def months(start, end, day):
    y, m = start.year, start.month
    while True:
        try: d = dt.date(y, m, day)
        except ValueError: d = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))  # day 29-31 in a short month: last day
        if d > end: break
        if d >= start: yield d
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

def add_years(d, n):
    try: return d.replace(year=d.year + n)
    except ValueError: return d.replace(year=d.year + n, day=28)

out = []
for h in P["holdings"]:
    s = nav(h["code"]); last_d, last_nav = on_or_before(s, AS_OF)
    folios, flows, realised = [], [], []
    for f in h["folios"]:
        buys = [(D(d), a) for d, a in f.get("buys", [])]
        if "sip" in f:
            sp = f["sip"]; buys += [(d, sp["amount"]) for d in months(D(sp["start"]), D(sp["end"]), sp["day"])]
        lots = []
        txns = sorted([(d, "buy", a) for d, a in buys] + [(D(d), "sell", a) for d, a in f.get("sells", [])])
        for d, kind, amt in txns:
            ad, p = on_or_after(s, d)
            if ad is None or ad > AS_OF: continue
            if kind == "buy":
                net = amt * (1 - 0.00005)  # stamp duty 0.005%
                lots.append(dict(date=str(ad), units=net / p, cost=amt)); flows.append((ad, -amt))
            else:  # FIFO sale
                units = amt / p; left = units; gain = 0.0
                for l in lots:
                    if left <= 1e-9: break
                    take = min(l["units"], left); c = l["cost"] * take / l["units"]
                    gain += take * p - c; l["cost"] -= c; l["units"] -= take; left -= take
                lots = [l for l in lots if l["units"] > 1e-9]
                flows.append((ad, amt)); realised.append(dict(date=str(ad), amount=amt, gain=round(gain)))
        for l in lots:
            ld = D(l["date"]); l["value"] = l["units"] * last_nav; l["gain"] = l["value"] - l["cost"]
            months_lt = 12 if h["tax_class"] == "equity" else 24
            l["long_term_from"] = str(add_years(ld, months_lt // 12) + dt.timedelta(days=1))
            if h.get("elss"): l["unlocks"] = str(add_years(ld, 3) + dt.timedelta(days=1))
        folios.append(dict(id=f["id"], via=f["via"], lots=lots))
    all_lots = [l for f in folios for l in f["lots"]]
    value = sum(l["value"] for l in all_lots); cost = sum(l["cost"] for l in all_lots)
    first = min(D(l["date"]) for l in all_lots)
    x = xirr(flows + [(last_d, value)]) if flows else None
    yrs = (last_d - first).days / 365
    out.append(dict(key=h["key"], name=h["name"], plan=h["plan"], code=h["code"], direct_code=h["direct_code"], category=h["category"],
                    index=h.get("index", False), elss=h.get("elss", False), tax_class=h["tax_class"], nav=last_nav, nav_date=str(last_d),
                    invested=round(cost), value=round(value), gain=round(value - cost), held_since=str(first), years=round(yrs, 1),
                    xirr=x if yrs >= 1 else None, cagr=((value / cost) ** (1 / yrs) - 1) if yrs >= 1 else None,
                    folios=folios, realised_this_fy=[r for r in realised if r["date"] >= "2026-04-01"]))
    print(f"{h['name'][:30]:30s} {h['plan'][:3]} inv {cost:9,.0f} val {value:9,.0f} gain {value-cost:+9,.0f} xirr {(x or 0):6.1%} since {first} folios {len(folios)}" + (f" realised {realised}" if realised else ""))
json.dump(dict(investor=P["investor"], as_of=P["as_of"], holdings=out, sips_active=P["sips_active"]),
          open(os.path.join(ROOT, "samples", "sample_holdings.json"), "w"), indent=1)
tot_i = sum(h["invested"] for h in out); tot_v = sum(h["value"] for h in out)
print(f"TOTAL invested {tot_i:,} value {tot_v:,} gain {tot_v - tot_i:+,}")
