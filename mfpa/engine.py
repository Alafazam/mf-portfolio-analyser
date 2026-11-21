"""mf-portfolio-analyser engine: normalised holdings in, every report data file out.

Input (dict, as produced by samples/make_sample.py today and the CAS ingest later):
  {"investor": {...}, "as_of": "YYYY-MM-DD",
   "holdings": [{key, name, plan, code, direct_code, category, index, elss, tax_class, nav, invested, value, gain,
                 held_since, years, xirr, cagr, folios: [{id, via, lots: [{date, units, cost, value, gain, long_term_from, unlocks?}]}],
                 realised_this_fy: [{date, amount, gain}]}],
   "sips_active": [{fund, plan?, amount, day, via}]}
Output: results, regime, peers, market, lot_status, plan, whatif, holdings .json in out_dir — the files the report template reads.
Rules follow SPEC.md §7–8. Wording is a rules-based screen, not advice."""
import json, os, math, copy, statistics as st, datetime as dt, re
from .data.navs import nav, on_or_after, on_or_before
from .data import amfi
from .analysis.stats import Grid, blend, stats, roll_beat, xirr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S_ = lambda f: json.load(open(os.path.join(ROOT, "static", f)))
BM, TAX, SC, SNAP = S_("benchmarks.json"), S_("tax_rules.json"), S_("scoring.json"), S_("market_snapshot.json")
EXEMPT = TAX["equity"]["ltcg_exemption"]; BUFFER = TAX["planning"]["buffer"]
MIDSMALL = {"Mid cap", "Small cap"}
D = dt.date.fromisoformat

def add_years(d, n):
    try: return d.replace(year=d.year + n)
    except ValueError: return d.replace(year=d.year + n, day=28)

def fy_end(d): return dt.date(d.year + (d.month > 3), 3, 31)
def fy_label(start_year, first=False): return f"FY {start_year}-{str(start_year + 1)[2:]}" + (f" (by 31 Mar {start_year + 1})" if first else "")

class Engine:
    def __init__(self, data, out_dir):
        self.data, self.out = data, out_dir; os.makedirs(out_dir, mode=0o700, exist_ok=True); os.chmod(out_dir, 0o700)
        self.as_of = D(data["as_of"]); self.H = data["holdings"]
        self.scored = [h for h in self.H if h["category"] in BM["categories"]]
        self.snap = {r["code"]: r for r in SNAP["rows"]}
        for h in self.H:
            if h["plan"] == "Regular": h["regular_code"] = h["code"]
            else: h["regular_code"] = amfi.twin(h["direct_code"], "Regular")
        self.mine = {h["direct_code"]: h["name"] for h in self.scored}

    def save(self, name, obj):
        with os.fdopen(os.open(os.path.join(self.out, name), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh: json.dump(obj, fh, indent=1, default=str)

    # ---------------- prices ----------------
    def grid(self):
        self.B = {k: nav(c) for k, c in BM["proxies"].items()}
        self.g = Grid([self.B[k] for k in ("N500", "N50", "MID150", "SMALL250", "BOND")])
        self.R = {k: self.g.rets(s) for k, s in self.B.items()}
        for cat, c in BM["categories"].items():
            self.R["B:" + cat] = blend(self.R, c["weights"]) if all(k in self.R for k in c["weights"]) else None
        self.FR = {}
        for h in self.scored:
            for k in ("direct_code", "regular_code"):
                c = h.get(k)
                if c and c not in self.FR: self.FR[c] = self.g.rets(nav(c))

    # ---------------- scorecard (results.json) ----------------
    def scorecard(self):
        g, FRI = self.g, self.g.fri; funds = []
        def px(rr):
            out, l = [None] * len(FRI), None
            for i, x in enumerate(rr):
                if x is None: continue
                if l is None: l = 1.0; out[i] = 1.0
                l *= 1 + x; out[i + 1] = l
            return out
        for h in self.scored:
            br = self.R["B:" + h["category"]]; bp = px(br)
            for plan, code in (("Direct", h["direct_code"]), ("Regular", h.get("regular_code"))):
                if not code: continue
                fr = self.FR[code]; s3 = stats(fr, br, 156)
                common = sum(1 for a, b in zip(fr, br) if a is not None and b is not None)
                full = stats(fr, br, min(common, 520)) if common > 52 else None
                rows = []
                for e in range(156, len(fr) + 1):
                    a, b = fr[e - 156:e], br[e - 156:e]
                    if any(v is None for v in a + b): continue
                    rows.append((str(FRI[e]), math.prod(1 + v for v in a) ** (1 / 3) - 1, math.prod(1 + v for v in b) ** (1 / 3) - 1))
                fp = px(fr); idx = [i for i in range(len(FRI)) if fp[i] and bp[i]]
                gs = []
                if idx:
                    i0 = idx[0] if len(idx) < 520 else idx[-520]
                    gs = [(str(FRI[i]), fp[i] / fp[i0], bp[i] / bp[i0]) for i in range(i0, len(FRI)) if fp[i] and bp[i]]
                own = [v for v in fr if v is not None]; n = min(len(own), 520)
                funds.append(dict(name=h["name"], plan=plan, code=code, category=h["category"], index=h["index"], benchmark=BM["categories"][h["category"]]["label"],
                                  value=h["value"], since=str(FRI[next(i for i, v in enumerate(fr) if v is not None)]) if own else None,
                                  s3=s3, full=full, own_cagr=(math.prod(1 + v for v in own[-n:]) ** (52 / n) - 1) if n else None, own_years=round(n / 52, 1),
                                  roll_beat=(sum(f > b for _, f, b in rows) / len(rows)) if rows else None, roll_n=len(rows),
                                  roll_avg_excess=st.mean(f - b for _, f, b in rows) if rows else None, roll=rows[::4], growth=gs[::2] + gs[-1:]))
        self.results = dict(end=str(g.end), funds=funds, portfolio=self.portfolio(px))
        self.save("results.json", self.results)

    def portfolio(self, px):
        out = {}
        for plan in ("Direct", "Regular"):
            legs = [(self.FR[h["direct_code"] if plan == "Direct" or h["plan"] == "Direct" else h["code"]], self.R["B:" + h["category"]], h["value"]) for h in self.scored]
            pr, br = [], []
            for i in range(len(self.g.fri) - 1):
                av = [(f, b, w) for f, b, w in legs if f[i] is not None and b[i] is not None]
                tw = sum(w for *_, w in av)
                if tw < .6 * sum(w for *_, w in legs): pr.append(None); br.append(None); continue
                pr.append(sum(w * f[i] for f, b, w in av) / tw); br.append(sum(w * b[i] for f, b, w in av) / tw)
            common = sum(1 for a in pr if a is not None); rows = []
            for e in range(156, len(pr) + 1):
                a, b = pr[e - 156:e], br[e - 156:e]
                if any(v is None for v in a + b): continue
                rows.append((str(self.g.fri[e]), math.prod(1 + v for v in a) ** (1 / 3) - 1, math.prod(1 + v for v in b) ** (1 / 3) - 1))
            pp, bp = px(pr), px(br); idx = [i for i in range(len(self.g.fri)) if pp[i] and bp[i]]
            gs = [(str(self.g.fri[i]), pp[i] / pp[idx[0]], bp[i] / bp[idx[0]]) for i in idx]
            own = [v for v in pr if v is not None]
            out[plan] = dict(plan=plan, s3=stats(pr, br, 156), full=stats(pr, br, min(common, 520)), roll_beat=sum(f > b for _, f, b in rows) / len(rows) if rows else None,
                             roll=rows[::4], growth=gs[::2] + gs[-1:], own_cagr=math.prod(1 + v for v in own) ** (52 / len(own)) - 1, own_years=round(len(own) / 52, 1), since=gs[0][0] if gs else None)
        return out

    # ---------------- flags (python mirror of the report's rule) ----------------
    def flags(self):
        F = SC["flags"]; self.flag = {}
        for f in self.results["funds"]:
            if f["plan"] != "Direct" or not f["s3"]: continue
            s = f["s3"]; dd = s["mdd"] - s["bench_mdd"]; rb = f["roll_beat"] or 0
            if f["index"]: k = "index"
            elif s["excess"] < 0 and (s["vol_ratio"] > F["exit_vol"] or s["down_cap"] > 1 or dd < F["dd_gap"]): k = "exit"
            elif s["excess"] < F["lag_excess"] and rb < F["lag_beat"]: k = "lag"
            elif s["excess"] > 0 and (s["vol_ratio"] > F["vol_ratio_hi"] or s["down_cap"] > F["down_hi"] or dd < F["dd_gap"]): k = "vol"
            elif s["excess"] > 0 and rb >= F["steady_beat"] and s["down_cap"] < F["steady_down"] and s["vol_ratio"] <= 1.05: k = "steady"
            else: k = "ok"
            self.flag[f["name"]] = k
        # duplicate index funds: same category and same index name
        idx = {}
        for h in self.scored:
            if h["index"]:
                m = re.search(r"\b(nifty|sensex|bse|s&p)\b.*", h["name"], re.I)
                key = (h["category"], (m.group(0) if m else h["name"]).lower().replace(" fund", "").strip())
                idx.setdefault(key, []).append(h)
        self.dups = {}
        for hs in idx.values():
            if len(hs) > 1:
                keep = max(hs, key=lambda h: h["value"])
                for h in hs:
                    if h is not keep: self.dups[h["name"]] = keep["name"]

    # ---------------- regimes ----------------
    def regime(self):
        mkt = self.R["N500"]; i0 = next(i for i, v in enumerate(mkt) if v is not None)
        lvl = [1.0]
        for v in mkt[i0:]: lvl.append(lvl[-1] * (1 + (v or 0)))
        phase = ["rising"] * (len(lvl) - 1); eps = []; k = peak = 0
        while k < len(lvl) - 1:
            k += 1
            if lvl[k] >= lvl[peak]: peak = k; continue
            if lvl[k] / lvl[peak] - 1 <= -0.10:
                j = k; tr = k
                while j < len(lvl) and lvl[j] < lvl[peak]:
                    if lvl[j] < lvl[tr]: tr = j
                    j += 1
                end = j if j < len(lvl) else len(lvl) - 1
                eps += [dict(type="fall", a=peak, b=tr, depth=lvl[tr] / lvl[peak] - 1), dict(type="recovery", a=tr, b=end, recovered=j < len(lvl), gain=lvl[end] / lvl[tr] - 1)]
                for t in range(peak, tr): phase[t] = "fall"
                for t in range(tr, end): phase[t] = "recovery"
                k = peak = end
        FRI = self.g.fri; date = lambda kk: str(FRI[i0 + kk])
        def cum(rr, a, b):
            seg = rr[i0 + a:i0 + b]
            return None if not seg or any(v is None for v in seg) else math.prod(1 + v for v in seg) - 1
        out = dict(episodes=[dict(e, start=date(e["a"]), end=date(e["b"]), weeks=e["b"] - e["a"]) for e in eps], funds={},
                   ref=[(str(FRI[i0 + t]), lvl[t]) for t in range(0, len(lvl), 2)])
        for h in self.scored:
            fr, br = self.FR[h["direct_code"]], self.R["B:" + h["category"]]
            agg = {}
            for ph in ("fall", "recovery", "rising"):
                ks = [t for t, p in enumerate(phase) if p == ph and fr[i0 + t] is not None and br[i0 + t] is not None]
                if len(ks) < 8: agg[ph] = None; continue
                fc = math.prod(1 + fr[i0 + t] for t in ks); bc = math.prod(1 + br[i0 + t] for t in ks)
                agg[ph] = dict(weeks=len(ks), fund=fc - 1, bench=bc - 1, rel=fc / bc - 1)
            out["funds"][h["name"]] = dict(benchmark=BM["categories"][h["category"]]["label"], phases=agg,
                                           episodes=[dict(type=e["type"], start=e["start"], end=e["end"], fund=cum(fr, e["a"], e["b"]), bench=cum(br, e["a"], e["b"])) for e in out["episodes"]])
        self.save("regime.json", out)

    # ---------------- market screen, peers, replacements ----------------
    def best(self, cat, exclude=(), n=1):
        pool = [r for r in SNAP["rows"] if r["category"] == cat and not r["short"] and r["code"] not in exclude and r["excess"] > 0 and r["down_cap"] <= 1.0]
        return sorted(pool, key=lambda r: (not r["long"], -r["score"]))[:n]

    def nice(self, r): return self.mine.get(r["code"]) or re.sub(r"\s*\(erstwhile.*?\)|\s+Fund.*$", "", r["name"], flags=re.I).strip()

    def market(self):
        rows = [dict(r, mine=self.mine.get(r["code"])) for r in SNAP["rows"]]
        self.market_rows = rows
        peers = {}
        for cat in sorted({h["category"] for h in self.scored if not h["index"]}):
            cr = [r for r in rows if r["category"] == cat]
            if not cr: continue
            pick = [r for r in cr if r["mine"]] + sorted([r for r in cr if not r["mine"] and not r["short"]], key=lambda r: -r["score"])[:5]
            peers[cat] = sorted([dict(name=r["mine"] or self.nice(r), full=r["name"], mine=bool(r["mine"]), code=r["code"], beat=r["beat"], windows=r["windows"],
                                      cagr=r["cagr"], bench_cagr=r["bench_cagr"], excess=r["excess"], vol_ratio=r["vol_ratio"], down_cap=r["down_cap"], mdd=r["mdd"], bench_mdd=r["bench_mdd"])
                                 for r in pick], key=lambda r: -r["excess"])
        self.save("peers.json", peers)
        self.peers = peers

    # ---------------- lots ----------------
    def lots(self):
        out = {}
        for h in self.H:
            lots = [dict(l, folio=f["id"]) for f in h["folios"] for l in f["lots"]]
            nav_now = h["nav"]
            rows = [dict(date=l["date"], units=l["units"], value=l["value"], gain=l["gain"], cost=l["cost"], lt_on=l["long_term_from"], unlock=l.get("unlocks"), folio=l["folio"]) for l in lots]
            today = str(self.as_of)
            st_rows = [r for r in rows if r["lt_on"] > today]
            out[f"{h['name']}|{h['plan']}"] = dict(fund=h["name"], plan=h["plan"], nav=nav_now, value=round(h["value"]), gain=round(h["gain"]),
                perf=dict(held_since=h["held_since"], before_statement=False, folios=len(h["folios"]), xirr=h["xirr"], cagr=h["cagr"], years=h["years"]),
                lt_value=round(sum(r["value"] for r in rows if r["lt_on"] <= today)), st_value=round(sum(r["value"] for r in st_rows)),
                all_lt_on=max((r["lt_on"] for r in st_rows), default=None), locked_value=round(sum(r["value"] for r in rows if (r["unlock"] or "") > today)),
                pre_statement=False, lots=sorted(rows, key=lambda r: r["date"]))
        self.lot_status = out
        self.save("lot_status.json", dict(as_of=str(self.as_of), funds=out))

    # ---------------- case for change ----------------
    def case(self, cur_code, new_code, value, st_value=0):
        a, b = self.snap.get(cur_code), self.snap.get(new_code)
        if not a or not b: return None
        T = [("3Y return vs benchmark", lambda r: r["excess"], 1), ("3Y consistency", lambda r: r["beat"], 1), ("Share of falls taken", lambda r: r["down_cap"], -1),
             ("Worst fall vs benchmark", lambda r: r["mdd"] - r["bench_mdd"], 1), ("Long-run lead over median", lambda r: (r["long"] or {}).get("excess"), 1),
             ("Long-run 3Y windows ahead", lambda r: (r["long"] or {}).get("beat3"), 1), ("Long-run 5Y windows ahead", lambda r: (r["long"] or {}).get("beat5"), 1)]
        wins = n = 0
        for _, f, sign in T:
            x, y = f(a), f(b)
            if x is None or y is None: continue
            d = (y - x) * sign
            if abs(d) < SC["case"]["tie"]: continue
            n += 1; wins += d > 0
        score = round(100 * wins / n) if n else None
        cost = TAX["costs"]["default_exit_load"]["rate"] * st_value + TAX["costs"]["stt_equity_redemption"] * value + TAX["costs"]["stamp_duty"] * value
        edge = (b["excess"] - a["excess"]) * value
        be = cost / edge if edge > 0 else None
        label = "Clear" if score is not None and score >= SC["case"]["clear"] and (be is None or be < SC["case"]["breakeven_years_clear"]) and edge > 0 else \
                "Lean" if score is not None and score >= SC["case"]["lean"] else "Close call"
        return dict(score=score, label=label, kind="replace", wins=wins, tests=n, replacement=b["name"], breakeven_years=be, switch_cost=round(cost))

    # ---------------- plan ----------------
    def plan(self):
        today = self.as_of; tstr = str(today); fy0 = fy_end(today)
        LS = self.lot_status
        # long-term gains already booked this FY: from the statement, plus any the user reports from shares/ETFs
        realised = sum((r["gain"] or 0) for h in self.H for r in h.get("realised_this_fy", [])) + self.data.get("other_ltcg_this_fy", 0)
        exits, switches, hold, others, losses, target = [], [], [], [], [], []
        replace_of = {}
        for h in self.H:
            key = f"{h['name']}|{h['plan']}"
            if h not in self.scored:
                kind = h["category"]; tc = h["tax_class"]
                note = {"equity": "Outside the screen (sector or theme fund); listed only", "other": "Not equity-oriented for tax: 12.5% after 24 months, no ₹1.25L exemption",
                        "specified_50AA": "Sec 50AA: slab rate whatever the holding period"}.get(tc, "Outside this analysis")
                if h["gain"] < 0 and tc != "specified_50AA":
                    losses.append(dict(fund=h["name"], value=round(h["value"]), gain=round(h["gain"])))
                else:
                    others.append(dict(fund=h["name"], plan=h["plan"], value=round(h["value"]), gain=round(h["gain"]), kind=kind, note=note))
                continue
            fl = self.flag.get(h["name"])
            if h.get("cost_unknown"):
                hold.append(dict(fund=h["name"], plan=h["plan"], value=round(h["value"]), gain=round(h["gain"]),
                                 note="Cost unknown (units bought before the statement start): left out of tax planning; download a CAS from inception"))
                continue
            if h["name"] in self.dups:
                keep = self.dups[h["name"]]
                exits.append(dict(h=h, into=f"{keep} (same index)", case=dict(score=100, label="Clear", kind="duplicate", why="Same index as a fund you keep; merging only removes clutter.")))
                continue
            if fl in ("exit", "lag"):
                b = self.best(h["category"], exclude={h["direct_code"]})
                alt = BM["index_alternative"].get(h["category"])
                if b:
                    rep = b[0]; replace_of[key] = rep
                    into = f"{self.nice(rep)} (direct, #{rep['rank']} of {rep['of']})" + (f", or {alt['name']} (index)" if alt else "")
                    exits.append(dict(h=h, into=into, rep=rep, case=self.case(h["direct_code"], rep["code"], h["value"], LS[key]["st_value"])))
                    continue
            if h["plan"] == "Regular":
                switches.append(dict(h=h, into="same fund, direct", case=dict(score=100, label="Clear", kind="fee", why="Same fund, same stocks; only the regular-plan commission goes away.")))
            else:
                note = {"steady": "Hold; keep adding", "vol": "Hold; ahead of its benchmark but swings harder", "index": "Hold; low-cost index exposure",
                        "ok": "Hold; review next year"}.get(fl, "Hold")
                hold.append(dict(fund=h["name"], plan=h["plan"], value=round(h["value"]), gain=round(h["gain"]), note=note))
        # One queue, within each year's tax-free room: duplicates, then exits (strongest case first), then regular->direct switches.
        # Lots go oldest first (FIFO); a lot is sold only once it is long-term and out of any ELSS lock-in, on that date if it falls in the year.
        years = {}
        def yr(d): return d.year if d.month > 3 else d.year - 1
        def fy(ystart): return years.setdefault(ystart, dict(fy=fy_label(ystart, ystart == yr(today)), consolidation=[], steps=[], losses=None))
        if losses: fy(yr(today))["losses"] = losses
        queue = []
        for pri, group in ((0, [e for e in exits if e["case"].get("kind") == "duplicate"]), (1, [e for e in exits if e["case"].get("kind") != "duplicate"]), (2, switches)):
            for m in group:
                h = m["h"]; ls = sorted(copy.deepcopy(LS[f"{h['name']}|{h['plan']}"]["lots"]), key=lambda l: l["date"])
                tot = sum(l["value"] for l in ls)
                queue.append(dict(m=m, pri=pri, lots=ls, total=tot, ratio=sum(l["gain"] for l in ls) / max(1, tot), score=-(m["case"].get("score") or 0)))
        queue.sort(key=lambda q: (q["pri"], q["score"] if q["pri"] == 1 else q["ratio"]))
        ystart = yr(today)
        while any(q["lots"] for q in queue) and ystart < yr(today) + 4:
            y = fy(ystart); fy_end_s = str(dt.date(ystart + 1, 3, 31))
            room = EXEMPT * (1 - BUFFER) + (-sum(l["gain"] for l in y["losses"]) if y["losses"] else 0)
            if ystart == yr(today): room -= realised
            for q in queue:
                lots = q["lots"]
                if not lots or room <= 1: continue
                v = gs_ = u = 0.0; dates = []
                ready = lambda l: l["lt_on"] <= fy_end_s and (l["unlock"] or "") <= fy_end_s
                while lots and room > 1 and ready(lots[0]):
                    l = lots[0]; when = max(today, D(l["lt_on"]), D(l["unlock"]) if l["unlock"] else today)
                    if when > today: dates.append(when)
                    if l["gain"] <= room: v += l["value"]; gs_ += l["gain"]; u += l["units"]; room -= l["gain"]; lots.pop(0)
                    else:
                        f = room / l["gain"]; v += l["value"] * f; gs_ += l["gain"] * f; u += l["units"] * f
                        for kk in ("value", "gain", "units"): l[kk] *= (1 - f)
                        room = 0
                if lots and all(ready(l) for l in lots) and sum(l["gain"] for l in lots) <= EXEMPT * TAX["planning"]["tiny_leftover_share"]:
                    for l in lots: v += l["value"]; gs_ += l["gain"]; u += l["units"]; room -= l["gain"]
                    lots.clear()
                if v <= 0: continue
                m = q["m"]; h = m["h"]
                when_txt = "" if not dates else "; sell each lot once it is long-term: " + ", ".join(d.strftime("%-d %b %Y") for d in sorted(set(dates))[:6]) + (" …" if len(set(dates)) > 6 else "")
                row_ = dict(fund=h["name"], plan=h["plan"], value=round(v), gain=round(gs_), units=round(u, 3), frac=v / q["total"], case=m["case"], fifo=True,
                            perf=LS[f"{h['name']}|{h['plan']}"]["perf"])
                if q["pri"] < 2: y["consolidation"].append(dict(row_, action="Sell", into=m["into"] + when_txt))
                else: y["steps"].append(dict(row_, action="Switch", into=m["into"] + (" (new 3-year lock-in starts)" if h["elss"] else "") + when_txt))
            ystart += 1
        # beyond 4 years: the tax of finishing now against what waiting costs each year
        rc = {(f["name"], f["plan"]): f for f in self.results["funds"]}
        beyond = []
        for q in queue:
            lots = q["lots"]
            if not lots: continue
            m = q["m"]; h = m["h"]; v = sum(l["value"] for l in lots); gn = sum(l["gain"] for l in lots)
            if q["pri"] == 2:
                d_, r_ = rc.get((h["name"], "Direct")), rc.get((h["name"], "Regular"))
                drag = (d_["s3"]["cagr"] - r_["s3"]["cagr"]) if d_ and r_ and d_["s3"] and r_["s3"] else None; why = "regular-plan commission"
            else:
                cur, rep = self.snap.get(h["direct_code"]), m.get("rep")
                drag = (rep["excess"] - cur["excess"]) if cur and rep else None; why = "gap to the replacement over 3 years"
            tax = max(0, gn) * TAX["equity"]["ltcg_rate"] * (1 + TAX["cess"])
            per_yr = drag * v if drag and drag > 0 else None
            beyond.append(dict(fund=h["name"], plan=h["plan"], kind="sell" if q["pri"] < 2 else "switch", into=m["into"], value=round(v), gain=round(gn), tax_now=round(tax),
                               cost_per_year=round(per_yr) if per_yr else None, cost_why=why, payback_years=(tax / per_yr) if per_yr else None,
                               perf=LS[f"{h['name']}|{h['plan']}"]["perf"]))
        ys = [years[k] for k in sorted(years)]
        for i, y in enumerate(ys):
            y["gains"] = sum(s["gain"] for s in y["steps"])
            y["total_gain"] = y["gains"] + sum(r["gain"] for r in y["consolidation"]) + (sum(l["gain"] for l in y["losses"]) if y["losses"] else 0) + (realised if i == 0 else 0)
            if not y["consolidation"]: y["consolidation"] = None
        if ys:
            ys[0]["note"] = (f"Already booked this year: ₹{realised:,.0f} of long-term gains. " if realised else "") + \
                            f"Partial switches are sized oldest units first (first-in, first-out), and each year keeps ₹{EXEMPT * BUFFER:,.0f} (5%) spare for price movement."
        # target list
        kept = [h for h in self.scored if h["name"] not in self.dups and not any(e["h"] is h for e in exits if "rep" in e)]
        for h in kept:
            r = self.snap.get(h["direct_code"]); fl = self.flag.get(h["name"])
            why = (f"#{r['rank']} of {r['of']} {h['category'].lower()} funds (score {r['score']}). " if r else "") + \
                  {"steady": "Ahead of its benchmark most of the time and takes less of the falls.", "vol": "Ahead of its benchmark but swings harder.",
                   "index": "Low-cost index exposure.", "ok": "Neither clearly ahead nor behind; review next year."}.get(fl, "")
            target.append(dict(fund=h["name"], role=h["category"] + (" (index)" if h["index"] else ""), why=why))
        seen = set()
        for e in exits:
            if "rep" not in e or e["rep"]["code"] in seen: continue
            seen.add(e["rep"]["code"]); r = e["rep"]
            target.append(dict(fund=self.nice(r), role=r["category"] + ", new", new=True,
                               why=f"#{r['rank']} of {r['of']} in the whole-market screen (score {r['score']}); replaces {e['h']['name']}."))
        self.replace_of = replace_of; self.exits = exits
        self.plan_out = dict(as_of=str(today), exempt=EXEMPT, realised_this_fy=realised, years=ys, beyond=beyond, hold=hold, others=others, target=target, sips=self.sips())
        self.save("plan.json", self.plan_out)

    # ---------------- SIPs ----------------
    def sips(self):
        byname = {h["name"]: h for h in self.H}; taken = set(); out = []
        for s in self.data.get("sips_active", []):
            h = byname.get(s["fund"]); x = dict(s, action="keep", to=None, now=None, same=None, rebal=None, skipped=[])
            if h and h in self.scored and not h["index"]:
                cur = self.snap.get(h["direct_code"])
                if cur:
                    x["now"] = dict(name=h["name"], score=cur["score"], rank=cur["rank"], of=cur["of"], category=h["category"])
                    pool = sorted([r for r in SNAP["rows"] if r["category"] == h["category"] and not r["short"] and r["code"] != h["direct_code"] and r["code"] not in taken], key=lambda r: -r["score"])
                    if pool and pool[0]["score"] >= cur["score"] + SC["sip_move_points"]:
                        x["same"] = dict(name=self.nice(pool[0]), score=pool[0]["score"], rank=pool[0]["rank"], of=pool[0]["of"], code=pool[0]["code"]); taken.add(pool[0]["code"])
                        x["skipped"] = [dict(name=self.nice(r), score=r["score"], rank=r["rank"], why="record too short to judge" if r["short"] else "")
                                        for r in SNAP["rows"] if r["category"] == h["category"] and r["score"] > pool[0]["score"] and r["short"]]
                    elif s.get("plan") == "Regular":
                        x["same"] = dict(name=h["name"] + " (direct)", score=cur["score"], rank=cur["rank"], of=cur["of"], code=h["direct_code"])
            elif h and h["index"]:
                x["now"] = None
            x["rebal"] = x["same"]
            out.append(x)
        tot = sum(x["amount"] for x in out)
        cat = lambda name: (byname.get(name) or {}).get("category")
        tilt = sum(x["amount"] for x in out if cat(x["fund"]) in MIDSMALL) / tot if tot else 0
        if tilt > 0.5:   # option B: move the largest mid/small SIP to the top flexi cap
            flexi = sorted([r for r in SNAP["rows"] if r["category"] == "Flexi cap" and not r["short"] and r["long"]], key=lambda r: -r["score"])
            cand = sorted([x for x in out if cat(x["fund"]) in MIDSMALL], key=lambda x: -x["amount"])
            if flexi and cand:
                cand[0]["rebal"] = dict(name=self.nice(flexi[0]), score=flexi[0]["score"], rank=flexi[0]["rank"], of=flexi[0]["of"], code=flexi[0]["code"])
        name_of = lambda x, k: (x[k] or {}).get("name") or x["fund"]
        now = [(x["fund"], x["amount"]) for x in out]; same = [(name_of(x, "same"), x["amount"]) for x in out]; rebal = [(name_of(x, "rebal"), x["amount"]) for x in out]
        catname = {**{h["name"]: h["category"] for h in self.H}}
        def mid(rows):
            def c(n): return catname.get(n) or next((r["category"] for r in SNAP["rows"] if self.nice(r) == n), None)
            return round(100 * sum(a for n, a in rows if c(n) in MIDSMALL) / tot) if tot else 0
        self.sip_list = out
        return dict(list=out, now=now, same=same, option=rebal, total=tot, new_total=tot, mid_now=mid(now), mid_same=mid(same), mid_rebal=mid(rebal),
                    mids=sorted({n for n, _ in now + same + rebal if (catname.get(n) or next((r["category"] for r in SNAP["rows"] if self.nice(r) == n), None)) in MIDSMALL}),
                    note=f"{len(out)} SIPs, Rs{tot:,} a month. Each SIP fund is scored against the whole-market screen; a SIP moves only when a fund with a full record scores at least {SC['sip_move_points']} points higher, "
                         f"and a regular-plan SIP moves to the same fund's direct plan. {mid(now)}% of the SIP money goes to mid and small caps"
                         + (" — above half, so option B also moves the largest of those SIPs to the top flexi cap." if tilt > 0.5 else "; no tilt, so options A and B are the same."))

    # ---------------- what-if ----------------
    def whatif(self):
        out = {}
        def replay(h, code):
            s = nav(code); last_d, last_nav = on_or_before(s, self.as_of); units = 0.0
            for l in self.lot_status[f"{h['name']}|{h['plan']}"]["lots"]:
                d, p = on_or_after(s, D(l["date"]))
                if p is None: return None
                units += l["cost"] / p
            return units * last_nav
        for h in self.scored:
            key = f"{h['name']}|{h['plan']}"; opts = []
            rep = self.replace_of.get(key)
            if rep: opts.append(("exit", self.nice(rep), rep["code"]))
            if h["name"] in self.dups:
                k = next(x for x in self.scored if x["name"] == self.dups[h["name"]]); opts.append(("exit", k["name"], k["direct_code"]))
            if h["plan"] == "Regular": opts.append(("fee", h["name"] + " direct", h["direct_code"]))
            for x in self.sip_list:
                if x["fund"] == h["name"]:
                    if x["same"] and x["same"].get("code") and x["same"]["code"] != h["code"]: opts.append(("sip_a" if x["rebal"] != x["same"] else "sip", x["same"]["name"], x["same"]["code"]))
                    if x["rebal"] and x["rebal"] != x["same"] and x["rebal"].get("code"): opts.append(("sip_b", x["rebal"]["name"], x["rebal"]["code"]))
            res = []
            for kind, name, code in opts:
                v = replay(h, code)
                if v is None: res.append(dict(kind=kind, name=name, note="replacement started after your first purchase")); continue
                res.append(dict(kind=kind, name=name, value=round(v), diff=round(v - h["value"]), diff_pct=(v - h["value"]) / h["value"]))
            if res: out[key] = dict(actual=round(h["value"]), invested=round(h["invested"]), approx=False, options=res)
        self.save("whatif.json", out)

    # ---------------- holdings file the report reads ----------------
    def holdings_file(self):
        eq = [[h["name"], h["plan"], h["invested"], h["value"]] for h in self.scored]
        self.save("holdings.json", dict(as_of=str(self.as_of), investor=self.data.get("investor"), equity=eq,
                                        others=[[h["name"], h["plan"], h["invested"], h["value"], h["category"]] for h in self.H if h not in self.scored],
                                        sips=self.sip_list))
        self.save("market.json", dict(rows=self.market_rows, bench={k: v["label"] for k, v in BM["categories"].items()}, listed=SNAP["listed"], screened=SNAP["screened"],
                                      under3y=SNAP["under3y"], end=SNAP["as_of"], replacements=self.replacements()))

    def replacements(self):
        out = []
        for e in self.exits:
            if "rep" not in e: continue
            h = e["h"]; cur = self.snap.get(h["direct_code"])
            picks = self.best(h["category"], exclude={h["direct_code"]}, n=3)
            out.append(dict(fund=h["name"] + (f" ({h['plan'].lower()})" if h["plan"] == "Regular" else ""), category=h["category"], when="Sell when long-term", value=h["value"],
                            current=cur and dict(name=cur["name"], score=cur["score"], rank=cur["rank"], of=cur["of"]),
                            picks=[dict(r, mine=self.mine.get(r["code"])) for r in picks]))
        return out

    def run(self):
        self.grid(); self.scorecard(); self.flags(); self.regime(); self.market(); self.lots(); self.plan(); self.whatif(); self.holdings_file()
        return self
