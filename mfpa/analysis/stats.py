"""Weekly-return statistics vs a benchmark (standard library only)."""
import math, statistics as st, datetime as dt

class Grid:
    """Weekly (Friday-aligned) grid ending at the last date common to the given benchmark series."""
    def __init__(self, series, start=dt.date(2013, 1, 1)):
        end = min(max(s) for s in series)
        self.fri, d = [], end
        while d > start: self.fri.append(d); d -= dt.timedelta(weeks=1)
        self.fri.reverse(); self.end = end
    def rets(self, s):
        px = []
        for f in self.fri:
            v = None
            for k in range(7):
                if (f - dt.timedelta(days=k)) in s: v = s[f - dt.timedelta(days=k)]; break
            px.append(v)
        # weekly moves beyond +-50% are splits or data errors: treated as 0
        return [(0.0 if abs(b / a - 1) > .5 else b / a - 1) if a and b else None for a, b in zip(px, px[1:])]

def blend(R, w):
    n = len(next(iter(R.values())))
    return [sum(w[k] * R[k][i] for k in w) if all(R[k][i] is not None for k in w) else None for i in range(n)]

def stats(fr, br, weeks):
    pairs = [(a, b) for a, b in zip(fr[-weeks:], br[-weeks:]) if a is not None and b is not None]
    if len(pairs) < weeks * .9: return None
    y, x = [a for a, b in pairs], [b for a, b in pairs]
    n = len(pairs); yrs = n / 52
    g = lambda rr: math.prod(1 + v for v in rr) ** (1 / yrs) - 1
    beta = st.covariance(x, y) / st.variance(x)
    up = [(a, b) for a, b in pairs if b > 0]; dn = [(a, b) for a, b in pairs if b < 0]
    def mdd(rr):
        l = pk = 1; m = 0
        for v in rr: l *= 1 + v; pk = max(pk, l); m = min(m, l / pk - 1)
        return m
    vol, bvol = st.stdev(y) * 52 ** .5, st.stdev(x) * 52 ** .5
    return dict(weeks=n, cagr=g(y), bench_cagr=g(x), excess=g(y) - g(x), vol=vol, bench_vol=bvol, vol_ratio=vol / bvol, beta=beta,
                alpha=(st.mean(y) - beta * st.mean(x)) * 52, r2=st.correlation(x, y) ** 2,
                up_cap=st.mean(a for a, b in up) / st.mean(b for a, b in up), down_cap=st.mean(a for a, b in dn) / st.mean(b for a, b in dn),
                mdd=mdd(y), bench_mdd=mdd(x))

def roll_beat(fr, br, win=156):
    w = []
    for e in range(win, len(fr) + 1):
        a, b = fr[e - win:e], br[e - win:e]
        if any(v is None for v in a + b): continue
        w.append(math.prod(1 + v for v in a) > math.prod(1 + v for v in b))
    return (sum(w) / len(w), len(w)) if w else (None, 0)

def xirr(flows):
    """Annual rate r where sum(cf / (1+r)^(days/365)) = 0, by bisection. flows: [(date, amount)], outflows negative."""
    t0 = min(d for d, _ in flows)
    f = lambda r: sum(c / (1 + r) ** ((d - t0).days / 365) for d, c in flows)
    lo, hi = -0.99, 5.0
    if f(lo) * f(hi) > 0: return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0: hi = mid
        else: lo = mid
    return (lo + hi) / 2
