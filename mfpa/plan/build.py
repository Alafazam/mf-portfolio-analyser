"""Turn a model run into the family plan page (one self-contained HTML file).
share=True: amounts rounded to bands, children's ages and ownership/transfer details removed (spec 16.4)."""
import json, os, re
from .model import run, label, age_at

HERE = os.path.dirname(os.path.abspath(__file__))


def _clean(x):
    if isinstance(x, str):
        return re.sub(r"[<>\"'`]", "", x)
    if isinstance(x, list):
        return [_clean(v) for v in x]
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, float):
        return round(x, 4)
    return x


def _band(v):
    """Round for the share copy: under ₹1L to ₹10k, under ₹1 Cr to ₹1L, above to ₹10L."""
    if v is None:
        return None
    a = abs(v)
    step = 1e4 if a < 1e5 else (1e5 if a < 1e7 else 1e6)
    return round(v / step) * step


def data(res, share=False):
    p, proj, fi = res["plan"], res["proj"], res["fi"]
    rows = proj["rows"]
    main = p["earners"][p["main"]]
    S = (lambda v: _band(v)) if share else (lambda v: v)
    inv = lambda r: r["corpus"] + sum(r["pf"]) + sum(r["nps"])

    # events by year
    events = {}
    def ev(m, text, kind):
        if m is not None and 0 <= m < len(rows):
            events.setdefault(m // 12, []).append(dict(text=text, kind=kind))
    h = p.get("home") or {}
    if h.get("possession_months"):
        ev(h["possession_months"], "Possession", "home")
    for i in range(1, len(rows)):
        if rows[i - 1]["loan"] > 0 and rows[i]["loan"] == 0:
            ev(i, "Home loan cleared", "good")
            break
    for i, r in enumerate(rows):
        if r["emg"] >= r["target_emg"] > 0:
            ev(i, "Emergency fund full", "good")
            break
    marks, k = [1e7, 2e7, 3e7, 5e7, 1e8], 0
    for i, r in enumerate(rows):
        while k < len(marks) and inv(r) >= marks[k]:
            ev(i, "Crossed ₹%g Cr" % (marks[k] / 1e7), "money")
            k += 1
    for c in p["children"]:
        for age, what in ((6, "starts class 1"), (c["goal_age"], "starts college")):
            mm = int(round((age - c["age"]) * 12))
            if mm >= 0:
                ev(mm, f"{c['name']} {what}", "child")
    for e in p["earners"]:
        pc = e.get("pay_commission")
        if pc and rows:
            from .model import month_index
            pm = month_index(p["as_of"], pc["payout"]) if pc.get("payout") else month_index(p["as_of"], pc["effective"]) + pc.get("payout_lag_months", 24)
            ev(pm, f"Pay commission for {e['name']} (with arrears)", "money")
        if e is not main:
            ev(int(round((e["retire_age"] - e["age"]) * 12)), f"{e['name']} retires", "home")
    ev(fi["base"], "Independent (base case)", "fi")
    ev(fi["stress"], "Independent (stress case)", "fi")

    path = {x["m"]: x for x in fi["path"]}
    miles = []
    for y in range(0, len(rows) // 12):
        r = rows[min(y * 12 + 11, len(rows) - 1)]
        pth = path.get(y * 12)
        miles.append(dict(year=label(p["as_of"], r["m"]).split()[1], age=round(main["age"] + r["m"] / 12),
                          kids=[None if share else int(c["age"] + r["m"] / 12) for c in p["children"]],
                          invested=S(inv(r)), invested_real=S(inv(r) / r["defl"]), goals=S(r["goals"]), loan=S(r["loan"]),
                          pct=None if not pth else min(1.0, pth["have"] / pth["req"]) if pth["req"] else 1.0,
                          events=events.get(y, [])))

    def phase(m, title):
        if m is None or m >= len(rows):
            return None
        r = rows[m]
        ins = [dict(name=f"{e['name']} take-home", v=S(r["income"][i])) for i, e in enumerate(p["earners"]) if r["income"][i] > 0]
        if r["rent_recv"]:
            ins.append(dict(name="Rent received (after vacancy and tax)", v=S(r["rent_recv"])))
        names = dict(living="Living costs", medical="Medical and insurance", school="School fees", unlisted="Spending not listed",
                     rent="Rent", maintenance="Maintenance", emi="Home loan (EMI + prepayment)")
        outs = [dict(name=names[k], v=S(v)) for k, v in r["out"].items() if v > 0]
        alloc = [dict(name="Emergency fund", v=S(r["to_emg"])), dict(name="Goal SIPs", v=S(r["to_goals"])), dict(name="Investments (left over)", v=S(r["to_corpus"]))]
        return dict(title=title, when=label(p["as_of"], m), ins=ins, outs=outs, alloc=[a for a in alloc if abs(a["v"] or 0) > 0])
    loan_clear = next((i for i in range(1, len(rows)) if rows[i - 1]["loan"] > 0 and rows[i]["loan"] == 0), None)
    phases = [phase(0, "Now"), phase(h.get("possession_months") or None, "After possession"),
              phase(loan_clear + 1 if loan_clear else None, "After the loan is cleared")]
    phases = [x for x in phases if x]

    goals = []
    for g in proj["goals"]:
        goals.append(dict(name=g["name"], due=label(p["as_of"], g["due"]).split()[1], cost=S(g["cost"]), paid=S(g.get("paid", 0)), short=S(g.get("short", 0))))

    tiles = dict(base=res["base_age"], stress=res["stress_age"],
                 need=S(next((x["req"] for x in fi["path"] if x["m"] == fi["base"]), None)) if fi["base"] is not None else None,
                 need_stress=S(next((x["req_stress"] for x in fi["path"] if x["m"] == fi["stress"]), None)) if fi["stress"] is not None else None,
                 loan=label(p["as_of"], loan_clear).split()[1] if loan_clear else None,
                 loan_age=round(age_at(p, loan_clear)) if loan_clear else None,
                 emg=next((label(p["as_of"], i) for i, r in enumerate(rows) if r["emg"] >= r["target_emg"] > 0), None))
    T = res["term"]
    term = dict(years=T["years"], need={k: S(v) for k, v in T["need"].items()}, have={k: S(v) for k, v in T["have"].items()}, gap=S(T["gap"]))
    pathc = [dict(age=round(main["age"] + x["m"] / 12, 1), have=S(x["have"]), req=S(x["req"]), req_stress=S(x["req_stress"])) for x in fi["path"]]
    earners = [dict(name=e["name"], age=e["age"], employer=e.get("employer"), pension=e["pension"]["type"], keeps=e.get("keeps_working"),
                    retire=e["retire_age"]) for e in p["earners"]]
    return _clean(dict(label=p.get("label", "Family plan"), as_of=p["as_of"], share=share, main=main["name"], earners=earners,
                       children=[dict(name=c["name"], age=None if share else c["age"]) for c in p["children"]],
                       tiles=tiles, path=pathc, miles=miles, phases=phases, goals=goals, levers=res.get("levers", []),
                       guesses=p["guesses"], guess_effects=res.get("guess_effects", []), term=term, todos=res["todos"],
                       assumptions=p["assumptions"], flags=proj["flags"][:3]))


def build(plan, out_html, share=False, web_fonts=True):
    res = run(plan)
    D = data(res, share=share)
    blob = json.dumps(D, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = open(os.path.join(HERE, "template.html"), encoding="utf-8").read().replace("__DATA__", blob)
    if not web_fonts:
        html = re.sub(r'<link rel="(preconnect|stylesheet)" href="https://fonts\.(googleapis|gstatic)\.com[^"]*"[^>]*>\n?', "", html)
    with os.fdopen(os.open(out_html, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644 if web_fonts else 0o600), "w", encoding="utf-8") as fh:
        fh.write(html)
    return out_html, res
