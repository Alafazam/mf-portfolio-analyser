"""CSV and INDmoney inputs (no purchase-level dates): one estimated lot per holding.
Tax figures from these inputs are estimates; the report says so. Use the CAS for exact lots."""
import csv, json, re, os, datetime as dt
from ..data import amfi
from .cas import nice_name, analysis_category, tax_class, add_years

STOP = {"fund", "growth", "option", "plan", "direct", "regular", "the", "of", "-", "g", "dir", "reg", "erstwhile", "formerly"}
def toks(s): return {t for t in re.sub(r"[^a-z0-9&]+", " ", s.lower()).split() if t not in STOP}

def match(name, plan):
    """Best AMFI growth scheme for a free-text fund name and plan, by word overlap."""
    want = toks(name); best, score = None, 0
    for r in amfi.rows().values():
        if not amfi.is_growth(r): continue
        if plan and plan.lower() not in (r["plan"] + " " + r["name"]).lower() and r["plan"]: continue
        t = toks(r["name"]); j = len(want & t) / max(1, len(want | t))
        if j > score: best, score = r, j
    return best if score >= 0.6 else None

def holding_from(r, invested, value, as_of, bought=None):
    cat, is_index = analysis_category(r)
    plan = "Regular" if "regular" in (r["plan"] + r["name"]).lower() else "Direct"
    direct = r["code"] if plan == "Direct" else (amfi.twin(r["code"], "Direct") or r["code"])
    d = bought or (as_of - dt.timedelta(days=400)); tc = tax_class(r, d); months = 12 if tc == "equity" else 24
    lot = dict(date=str(d), units=value / float(r["nav"]) if r["nav"] not in ("", "N.A.") else 0, cost=invested, value=value, gain=value - invested, kind="purchase",
               long_term_from=str(add_years(d, months // 12) + dt.timedelta(days=1)), estimated=bought is None)
    if r.get("category") == "ELSS": lot["unlocks"] = str(add_years(d, 3) + dt.timedelta(days=1))
    yrs = (as_of - d).days / 365
    return dict(key=re.sub(r"\W+", "_", nice_name(r["name"]).lower()) + "_" + plan.lower(), name=nice_name(r["name"]), plan=plan, code=r["code"], direct_code=direct,
                category=cat, index=is_index, elss=r.get("category") == "ELSS", tax_class=tc, nav=float(r["nav"]) if r["nav"] not in ("", "N.A.") else None,
                invested=round(invested), value=round(value), gain=round(value - invested), held_since=str(d), years=round(yrs, 1), xirr=None,
                cagr=((value / invested) ** (1 / yrs) - 1) if yrs >= 1 and invested > 0 else None, folios=[dict(id="F1", via="", lots=[lot])],
                realised_this_fy=[], cost_unknown=False, reconciled=True, estimate=True)

def from_csv(path, as_of=None):
    """Columns: isin or fund, plan (Direct/Regular), invested, value, [bought YYYY-MM-DD], [sip_amount], [sip_day], [via]."""
    as_of = as_of or dt.date.today(); hs, sips, warn = [], [], []
    for row in csv.DictReader(open(path, encoding="utf-8")):
        r = amfi.by_isin(row.get("isin", "").strip()) if row.get("isin") else match(row.get("fund", ""), row.get("plan", ""))
        if not r: warn.append(f"Couldn't identify: {row.get('fund') or row.get('isin')}"); continue
        b = dt.date.fromisoformat(row["bought"]) if row.get("bought") else None
        h = holding_from(r, float(row["invested"]), float(row["value"]), as_of, b); hs.append(h)
        if row.get("sip_amount"): sips.append(dict(fund=h["name"], plan=h["plan"], amount=int(float(row["sip_amount"])), day=int(row.get("sip_day") or 1), via=row.get("via", "")))
    warn.append("CSV input: no purchase dates per instalment, so tax figures are estimates.")
    return dict(investor=dict(name="Investor", sample=False), as_of=str(as_of), holdings=hs, sips_active=sips, warnings=warn)

def from_indmoney(holdings_json, sips_json=None, as_of=None):
    """Saved outputs of the INDmoney MCP: networth_holdings(asset_type='MF') and mf_sips()."""
    as_of = as_of or dt.date.today(); hs, sips, warn = [], [], []
    H = json.load(open(holdings_json)); H = json.loads(H["result"]) if "result" in H else H
    for row in H.get("holdings", []):
        name = row["investment"]; plan = "Direct" if re.search(r"direct", name, re.I) else "Regular"   # INDmoney omits the plan for regular plans
        r = match(name, plan)
        if not r: warn.append(f"Couldn't identify: {name}"); continue
        hs.append(holding_from(r, row["invested_amount"], row["market_value"], as_of))
    if sips_json:
        S = json.load(open(sips_json)); S = json.loads(S["result"]) if "result" in S else S
        for f in S.get("mf_sips", []):
            r = amfi.by_isin(f.get("isin", "")) or match(f["name"], f.get("planType", ""))
            for s in f.get("active_sips", []):
                sips.append(dict(fund=nice_name(r["name"]) if r else f["name"], plan=f.get("planType", ""), amount=s["amount"],
                                 day=int(s["sip_start_date"][:2]), via="INDmoney"))
    warn.append("INDmoney input: no purchase dates per instalment, so tax figures are estimates. A CAS gives exact lots.")
    return dict(investor=dict(name="Investor", sample=False), as_of=str(as_of), holdings=hs, sips_active=sips, warnings=warn)
