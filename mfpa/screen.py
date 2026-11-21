"""Whole-market screen -> static/market_snapshot.json (maintainers run `python3 -m mfpa refresh-snapshot`).

Every open-ended direct-growth fund in the scored categories (AMFI list), tested like the user's funds:
3Y vs the category benchmark, plus a long-run comparison with the category median from Jun 2018 (after SEBI's
recategorisation; funds alive today only, so the median flatters the category a little). Overall = 75% 3Y + 25% long run."""
import json, os, math, sys, time, datetime as dt, statistics as st
from concurrent.futures import ThreadPoolExecutor
from .data import amfi
from .data.navs import nav
from .analysis.stats import Grid, blend, stats, roll_beat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LONG_START = dt.date(2018, 6, 1)

def prank(vals, x):
    vs = [v for v in vals if v is not None]
    if x is None or len(vs) < 2: return .5
    return (sum(v < x for v in vs) + .5 * sum(v == x for v in vs) - .5) / (len(vs) - 1)

def refresh(out=None, workers=3):
    BM = json.load(open(os.path.join(ROOT, "static", "benchmarks.json"))); SC = json.load(open(os.path.join(ROOT, "static", "scoring.json")))
    cats = BM["categories"]
    rows = amfi.rows(); latest = max(dt.datetime.strptime(r["date"], "%d-%b-%Y").date() for r in rows.values() if r["date"][:2].isdigit())
    cand = {c: r for c, r in rows.items() if r["category"] in cats and "direct" in r["plan"].lower() and amfi.is_growth(r)
            and not any(w in r["name"].lower() for w in ("index", "etf", "segregated"))
            and (latest - dt.datetime.strptime(r["date"], "%d-%b-%Y").date()).days <= 7}
    print(f"{len(cand)} funds to screen", file=sys.stderr)
    def load(code):
        for a in range(4):
            try: return code, nav(code)
            except Exception: time.sleep(2 + 3 * a)
        return code, None
    with ThreadPoolExecutor(workers) as ex: got = dict(ex.map(load, list(cand) + list(BM["proxies"].values())))
    S = {k: got[c] for k, c in BM["proxies"].items()}
    g = Grid([S[k] for k in ("N500", "N50", "MID150", "SMALL250", "BOND")]); FRI = g.fri
    R = {k: g.rets(s) for k, s in S.items()}
    for cat, c in cats.items(): R["B:" + cat] = blend(R, c["weights"])
    FR = {c: g.rets(got[c]) for c in cand if got.get(c)}
    # falls: Nifty 500 episodes of 10%+
    mkt = R["N500"]; i0 = next(i for i, v in enumerate(mkt) if v is not None); lvl = [1.0]
    for v in mkt[i0:]: lvl.append(lvl[-1] * (1 + (v or 0)))
    fallwk = [False] * (len(FRI) - 1); k = peak = 0
    while k < len(lvl) - 1:
        k += 1
        if lvl[k] >= lvl[peak]: peak = k; continue
        if lvl[k] / lvl[peak] - 1 <= -0.10:
            j = k; tr = k
            while j < len(lvl) and lvl[j] < lvl[peak]:
                if lvl[j] < lvl[tr]: tr = j
                j += 1
            for t in range(peak, tr): fallwk[i0 + t] = True
            k = peak = (j if j < len(lvl) else len(lvl) - 1)
    out_rows, under3 = [], 0
    for code, r in cand.items():
        fr = FR.get(code)
        if not fr: continue
        br = R["B:" + r["category"]]; s = stats(fr, br, 156)
        if not s: under3 += 1; continue
        rb, nw = roll_beat(fr, br)
        ks = [i for i, f in enumerate(fallwk) if f and fr[i] is not None and br[i] is not None]
        frel = (math.prod(1 + fr[i] for i in ks) / math.prod(1 + br[i] for i in ks) - 1) if len(ks) >= 20 else None
        first = next(FRI[i] for i, x in enumerate(fr) if x is not None)
        out_rows.append(dict(code=code, name=r["name"], category=r["category"], since=str(first), beat=rb, windows=nw if rb is not None else 0,
                             short=(nw if rb is not None else 0) < SC["short_record_windows"], falls_rel=frel, **{k2: s[k2] for k2 in ("cagr", "bench_cagr", "excess", "vol_ratio", "down_cap", "up_cap", "mdd", "bench_mdd", "r2", "alpha", "beta")}))
    # long run vs category median from Jun 2018
    NW = len(FRI) - 1; ls = next(i for i, d in enumerate(FRI) if d >= LONG_START)
    med = {}
    for cat in cats:
        cs = [x["code"] for x in out_rows if x["category"] == cat]
        med[cat] = [st.median(v) if i >= ls and len(v := [FR[c][i] for c in cs if FR[c][i] is not None]) >= 5 else None for i in range(NW)]
    cg = lambda rr: math.prod(1 + v for v in rr) ** (52 / len(rr)) - 1 if rr else None
    for x in out_rows:
        fr, mr = FR[x["code"]], med[x["category"]]; idx = [i for i in range(ls, NW) if fr[i] is not None and mr[i] is not None]
        yrs = len(idx) / 52; x["long_years"] = round(yrs, 1)
        for n in (5,):
            w = idx[-52 * n:] if yrs >= n - .05 else None
            x[f"cagr_{n}y"] = cg([fr[i] for i in w]) if w else None; x[f"med_{n}y"] = cg([mr[i] for i in w]) if w else None
        x["cagr_10y"] = None; x["med_10y"] = None
        if yrs < 5: x["long"] = None; continue
        f_, m_ = [fr[i] for i in idx], [mr[i] for i in idx]
        win = lambda kk: [math.prod(1 + v for v in f_[e - kk:e]) > math.prod(1 + v for v in m_[e - kk:e]) for e in range(kk, len(f_) + 1)]
        w3, w5 = win(156), win(260); dn = [(a, b) for a, b in zip(f_, m_) if b < 0]
        def mdd(rr):
            l = pk = 1; mm = 0
            for v in rr: l *= 1 + v; pk = max(pk, l); mm = min(mm, l / pk - 1)
            return mm
        x["long"] = dict(years=round(yrs, 1), excess=cg(f_) - cg(m_), beat3=sum(w3) / len(w3), beat5=(sum(w5) / len(w5)) if w5 else None,
                         down_cap=st.mean(a for a, b in dn) / st.mean(b for a, b in dn), mdd=mdd(f_), med_mdd=mdd(m_), start=str(FRI[idx[0]]))
    T, L, B = SC["three_year"], SC["long_run"], SC.get("blend", {"three_year": 0.75, "long_run": 0.25})
    for cat in cats:
        rs = [x for x in out_rows if x["category"] == cat]
        for x in rs:
            p = dict(excess=prank([y["excess"] for y in rs], x["excess"]), consistency=prank([y["beat"] for y in rs], x["beat"]), downside=prank([-y["down_cap"] for y in rs], -x["down_cap"]),
                     worst_fall=prank([y["mdd"] - y["bench_mdd"] for y in rs], x["mdd"] - x["bench_mdd"]), falls=prank([y["falls_rel"] for y in rs], x["falls_rel"]))
            x["score3"] = round(100 * sum(T[k2] * p[k2] for k2 in T))
        lr = [x for x in rs if x["long"]]
        for x in lr:
            L_ = x["long"]
            p = dict(excess=prank([y["long"]["excess"] for y in lr], L_["excess"]), beat3=prank([y["long"]["beat3"] for y in lr], L_["beat3"]),
                     beat5=prank([y["long"]["beat5"] for y in lr], L_["beat5"]), downside=prank([-y["long"]["down_cap"] for y in lr], -L_["down_cap"]),
                     worst_fall=prank([y["long"]["mdd"] for y in lr], L_["mdd"]))
            L_["score"] = round(100 * sum(L[k2] * p[k2] for k2 in L))
        for x in rs:
            x["score"] = round(B["three_year"] * x["score3"] + B["long_run"] * x["long"]["score"]) if x["long"] else x["score3"]; x["no_long"] = not x["long"]
        for i, x in enumerate(sorted(rs, key=lambda y: (-y["score"], y["no_long"]))): x["rank"] = i + 1; x["of"] = len(rs)
    snap = dict(version=2, as_of=str(g.end), source="mfapi.in NAVs + AMFI NAVAll.txt; 3Y vs category benchmark (75%) + long run vs category median from Jun 2018 (25%)",
                bench={k: v["label"] for k, v in cats.items()}, listed=len(cand), screened=len(out_rows), under3y=under3, rows=out_rows)
    out = out or os.path.join(ROOT, "static", "market_snapshot.json")
    json.dump(snap, open(out, "w")); print(f"wrote {out}: {len(out_rows)} funds, data to {g.end}", file=sys.stderr)
    return out
