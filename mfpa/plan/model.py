"""Family money plan: one monthly cash-flow ledger, a two-phase independence test, levers and stress rows.

Everything is computed here, once; the HTML page only displays the result (spec section 16.3).
Nominal rupees inside the ledger; "real" figures are divided by the inflation index since the start month.
Planning maths, not advice."""
import copy, json, math, os
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATIC = os.path.join(ROOT, "static")


_CACHE = {}


def _static(name):
    """Read a static rules file once; callers get their own copy."""
    if name not in _CACHE:
        with open(os.path.join(STATIC, name), encoding="utf-8") as fh:
            _CACHE[name] = json.load(fh)
    return copy.deepcopy(_CACHE[name])


def mrate(r):
    return (1 + r) ** (1 / 12) - 1


def ym(s):
    y, m = str(s).split("-")[:2]
    return int(y), int(m)


def month_index(start, s):
    """Months from the plan's start month to 'YYYY-MM' (negative if before)."""
    y0, m0 = ym(start)
    y, m = ym(s)
    return (y - y0) * 12 + (m - m0)


def label(start, m):
    y0, m0 = ym(start)
    t = (y0 * 12 + m0 - 1) + m
    return "%s %d" % ("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()[t % 12], t // 12)


# ---------------------------------------------------------------- inputs and defaults
def load(path_or_dict):
    """Fill defaults from static files and record which fields were guessed (shown on the page)."""
    p = copy.deepcopy(path_or_dict) if isinstance(path_or_dict, dict) else json.load(open(path_or_dict))
    hd, pc, pd = _static("household_defaults.json"), _static("pay_commission.json"), _static("pension_defaults.json")
    guesses = []

    def dflt(d, k, v, why):
        if d.get(k) is None:
            d[k] = v
            guesses.append(why)

    p.setdefault("as_of", date.today().isoformat())
    a = p.setdefault("assumptions", {})
    for k, v in dict(equity_return=0.11, debt_return=0.065, inflation=0.06, retire_real_return=0.03, live_to=95,
                     pf_return=0.0825, nps_return=0.09).items():
        a.setdefault(k, v)
    dflt(a, "education_inflation", hd["education_inflation"], "Education costs rise 8% a year")
    dflt(a, "medical_inflation_extra", hd["medical_inflation_extra"], "Medical costs rise 4% a year faster than prices")
    dflt(a, "unlisted_spending_share", hd["unlisted_spending_share"], "5% of take-home goes on things not listed")
    dflt(a, "tax_on_retirement_spending", hd["tax_on_retirement_spending"], "About 5% tax on money drawn in retirement")
    a.setdefault("stress", hd["stress"])
    a.setdefault("goal_derisk_months", hd["goal_derisk_months"])
    a.setdefault("premium_age_bands", hd["premium_age_bands"])
    for e in p["earners"]:
        e.setdefault("growth", 0.07)
        e.setdefault("keeps_working", False)
        e.setdefault("retire_age", 60)
        share = pd["basic_share_of_take_home_default"].get(e.get("employer", "private"), 0.4)
        if e.get("basic") is None and e.get("pension", {}).get("type") in ("OPS", "UPS"):
            e["basic"] = round(e["take_home"] * share)
            guesses.append(f"{e['name']}'s basic pay is about {round(share * 100)}% of take-home")
        pen = e.setdefault("pension", {"type": "none"})
        if pen["type"] == "OPS":
            o = pd["OPS"]
            dflt(pen, "pct", o["pct_of_last_basic"], f"{e['name']}'s pension: {round(o['pct_of_last_basic'] * 100)}% of last basic (central rule)")
            dflt(pen, "full_years", o["full_years"], f"{e['name']}'s full pension after {o['full_years']} years of service (central rule)")
            pen.setdefault("min_years", o["min_years"])
            pen.setdefault("family_pct", o["family_pension_pct"])
            pen.setdefault("commute", 0.0)
        if pen["type"] == "UPS":
            for k, v in dict(pct=pd["UPS"]["pct_of_avg_basic"], min_years=pd["UPS"]["min_years"], full_years=pd["UPS"]["full_years"],
                             min_pension=pd["UPS"]["min_pension"], family_pct=pd["UPS"]["family_pension_pct"]).items():
                pen.setdefault(k, v)
        if pen["type"] == "NPS":
            pen.setdefault("annuity_share", pd["NPS"]["annuity_share"]["government" if "govt" in e.get("employer", "") else "other"])
            pen.setdefault("annuity_rate", pd["NPS"]["annuity_rate"])
            pen.setdefault("balance", 0)
            pen.setdefault("monthly", 0)
        if e.get("employer", "").endswith("govt") and e.get("pay_commission") is None:
            e["pay_commission"] = dict(effective=pc["default_effective"], payout_lag_months=pc["default_payout_lag_months"], net_jump=pc["default_net_jump"])
            guesses.append(f"Pay commission: +{round(pc['default_net_jump'] * 100)}% take-home for {e['name']} (not yet announced)")
        e.setdefault("pf", {"type": "none", "balance": 0, "monthly": 0})
    h = p.setdefault("home", {})
    if h:
        h.setdefault("possession_months", 0)
        h.setdefault("after_possession", "move_in")
        dflt(h, "rent_growth", hd["rent_growth"], "Your rent rises 5% a year")
        dflt(h, "maintenance", hd["maintenance"], "Maintenance about ₹4,000 a month")
        if h.get("let_out"):
            dflt(h["let_out"], "vacant_months", hd["vacant_months"], "The let-out house stands empty about 1 month a year")
            h["let_out"].setdefault("growth", hd["rent_growth"])
    sp = p.setdefault("spending", {})
    for k in ("household", "card_needs", "card_wants", "transfers", "bills", "travel", "other", "medical", "insurance_premiums_yearly"):
        sp.setdefault(k, 0)
    for c in p.setdefault("children", []):
        c.setdefault("goal_age", 18)
        c.setdefault("school_fee", 0)
        c.setdefault("school_until", hd["school_until_age"])
        c.setdefault("fund_now", 0)
        c.setdefault("sip", 0)
        c.setdefault("sip_step", 0.10)
    for g in p.setdefault("goals", []):
        g.setdefault("inflation", a["inflation"])
        g.setdefault("fund_now", 0)
        g.setdefault("sip", 0)
        g.setdefault("sip_step", 0.0)
    inv = p.setdefault("investments", {})
    for k in ("mutual_funds", "stocks", "other"):
        inv.setdefault(k, 0)
    em = p.setdefault("emergency", {})
    em.setdefault("now", inv.pop("emergency", 0) if "emergency" in inv else 0)
    em.setdefault("target_months", 6)
    em.setdefault("top_up", 0)
    em.setdefault("seed", 0)
    p.setdefault("insurance", {})
    r = p.setdefault("retirement", {})
    if r.get("spend_today") is None:
        r["spend_today"] = 12 * (sp["household"] + sp["card_needs"] + sp["card_wants"] + sp["bills"] + sp["other"])
        guesses.append("Retirement spending = today's living costs without rent, EMI, SIPs, school and transfers")
    r.setdefault("medical_today", 12 * sp["medical"] + sp["insurance_premiums_yearly"])
    p["guesses"] = [g for g in guesses if g]
    p["main"] = next((i for i, e in enumerate(p["earners"]) if not e.get("keeps_working")), 0)
    return p


# ---------------------------------------------------------------- tax helpers (new regime)
def income_tax(taxable):
    t = _static("tax_rules.json")["income_tax_new_regime"]
    if taxable <= t["rebate_taxable_upto"]:
        return 0.0
    tax, lo = 0.0, 0
    for hi, rate in t["slabs"]:
        top = taxable if hi is None else min(taxable, hi)
        if top > lo:
            tax += (top - lo) * rate
        if hi is None or taxable <= hi:
            break
        lo = hi
    return tax * (1 + t["cess"])


def rent_tax_year(p, m, gross_year, interest_year):
    """Tax on a let-out house's rent for one year, in the hands of whoever funded it (clubbing), else the owner."""
    lo = p["home"]["let_out"]
    who = lo.get("funded_by") or lo.get("owner")
    e = next((x for x in p["earners"] if x["name"] == who), None)
    base = 12 * take_home(p, e, m)[0] / 0.85 if e else 0      # rough gross income of that person
    taxable_rent = max(0.0, gross_year * 0.7 - interest_year)  # 30% standard deduction; interest only against this rent
    return max(0.0, income_tax(base + taxable_rent) - income_tax(base))


# ---------------------------------------------------------------- earners
def earner_age(p, e, m):
    return e["age"] + m / 12


def take_home(p, e, m, stop_at=None):
    """(monthly take-home, arrears paid this month) for earner e in month m. stop_at: month the earner stops."""
    if e is None or earner_age(p, e, m) >= e["retire_age"] or (stop_at is not None and m >= stop_at):
        return 0.0, 0.0
    y = m // 12
    pay = e["take_home"] * (1 + e["growth"]) ** y
    cb = e.get("career_break")
    if cb:
        if cb["start_year"] * 12 <= m < (cb["start_year"] + cb["years"]) * 12:
            return 0.0, 0.0
        if m >= (cb["start_year"] + cb["years"]) * 12:
            pay *= cb.get("return_pct", 1.0)
    arrears = 0.0
    pc = e.get("pay_commission")
    if pc:
        eff = month_index(p["as_of"], pc["effective"])
        pay_m = eff + pc.get("payout_lag_months", 24) if pc.get("payout") is None else month_index(p["as_of"], pc["payout"])
        if m >= pay_m:
            pay *= 1 + pc["net_jump"]
        if m == pay_m:
            arrears = sum(e["take_home"] * (1 + e["growth"]) ** max(0, k // 12) for k in range(eff, pay_m)) * pc["net_jump"]
    return pay, arrears


# ---------------------------------------------------------------- the ledger
def project(p, stop=None, months=None):
    """Monthly ledger from month 0. stop: month the main earner stops (contributions stop; used for what-if only).
    Returns rows (one per month) with balances, flows and flags."""
    a, sp, h = p["assumptions"], p["spending"], p.get("home") or {}
    inf, rE, rD = a["inflation"], mrate(a["equity_return"]), mrate(a["debt_return"])
    rPF, rNPS, mx = mrate(a["pf_return"]), mrate(a["nps_return"]), a["medical_inflation_extra"]
    main = p["earners"][p["main"]]
    months = months or int(round((main["retire_age"] - main["age"]) * 12))
    inv, em = p["investments"], p["emergency"]
    corpus = inv["mutual_funds"] + inv["stocks"] + inv["other"] - em["seed"]
    emg = em["now"] + em["seed"]
    pf = [e["pf"].get("balance", 0) for e in p["earners"]]
    nps = [e["pension"].get("balance", 0) if e["pension"]["type"] == "NPS" else 0 for e in p["earners"]]
    loan = (h.get("loan") or {}).get("balance", 0)
    poss = h.get("possession_months", 0)
    goals = []
    for c in p["children"]:
        gm = int(round((c["goal_age"] - c["age"]) * 12))
        if gm > 0:
            goals.append(dict(name=f"{c['name']}'s higher education", kind="child", due=gm, bal=c["fund_now"], sip=c["sip"], step=c["sip_step"],
                              cost=c["cost_today"] * (1 + a["education_inflation"]) ** (gm / 12), child=c["name"]))
    for g in p["goals"]:
        gm = month_index(p["as_of"], f"{g['year']}-06")
        if gm > 0:
            goals.append(dict(name=g["name"], kind="goal", due=gm, bal=g["fund_now"], sip=g["sip"], step=g["sip_step"],
                              cost=g["cost_today"] * (1 + g["inflation"]) ** (gm / 12)))
    rows, flags = [], []
    let_tax_cache = {}
    for m in range(months):   # up to (not including) the main earner's retirement month
        y = m // 12
        defl = (1 + inf) ** (m / 12)
        inc = [take_home(p, e, m, stop if i == p["main"] else None) for i, e in enumerate(p["earners"])]
        pay_in = sum(x[0] for x in inc) + sum(x[1] for x in inc)
        # spending
        base = sum(sp[k] for k in ("household", "card_needs", "card_wants", "transfers", "bills", "travel", "other")) * (1 + inf) ** y
        med = sp["medical"] * (1 + inf + mx) ** y
        band = 1.0
        for age, mult in a["premium_age_bands"]:
            if earner_age(p, main, m) >= age:
                band = mult
        prem = sp["insurance_premiums_yearly"] / 12 * (1 + inf) ** y * band
        school = sum(c["school_fee"] * (1 + a["education_inflation"]) ** y for c in p["children"] if c["age"] + m / 12 < c["school_until"])
        unlisted = a["unlisted_spending_share"] * sum(x[0] for x in inc)
        # housing
        rent_paid = rent_recv = maint = 0.0
        if h:
            if m < poss or h["after_possession"] == "let_out":
                rent_paid = h.get("rent_now", 0) * (1 + h["rent_growth"]) ** y
            if m >= poss:
                maint = h["maintenance"] * (1 + inf) ** y
                if h["after_possession"] == "let_out" and h.get("let_out"):
                    lo = h["let_out"]
                    k = (m - poss) // 12
                    gross = lo["rent"] * (1 + lo["growth"]) ** k * (1 - lo["vacant_months"] / 12)
                    if k not in let_tax_cache:
                        let_tax_cache[k] = rent_tax_year(p, m, gross * 12, 12 * loan * (h.get("loan") or {}).get("rate", 0) / 12 if loan else 0)
                    rent_recv = gross - let_tax_cache[k] / 12
        # loan
        emi_paid = 0.0
        if loan > 0:
            L = h["loan"]
            interest = loan * L["rate"] / 12
            pre = 0 if (stop is not None and m >= stop) else (L.get("prepay_now", 0) if m < poss else L.get("prepay_after", L.get("prepay_now", 0)))
            emi_paid = min(L["emi"] + pre, loan + interest)
            loan = loan + interest - emi_paid
            if loan < 1:
                loan = 0.0
        out = base + med + prem + school + unlisted + rent_paid + maint + emi_paid
        surplus = pay_in + rent_recv - out
        working = stop is None or m < stop
        # allocation: emergency fund -> goal SIPs -> corpus
        target = em["target_months"] * (base + rent_paid + maint + (h.get("loan") or {}).get("emi", 0) * (loan > 0))
        to_emg = to_goals = 0.0
        if surplus >= 0:
            if working and emg < target:
                to_emg = min(surplus, target - emg, max(em["top_up"], 0) * (1 + inf) ** y if em["top_up"] else target - emg)
                surplus -= to_emg
                emg += to_emg
            want = sum(g["sip"] * (1 + g["step"]) ** y for g in goals if m < g["due"]) if working else 0
            if want > 0:
                share = min(1.0, surplus / want)
                if share < 0.999 and m % 12 == 0:
                    flags.append(dict(m=m, text="Goal SIPs are larger than what's left after spending; they were scaled down."))
                for g in goals:
                    if m < g["due"]:
                        add = g["sip"] * (1 + g["step"]) ** y * share
                        g["bal"] += add
                        to_goals += add
                surplus -= to_goals
            corpus += surplus
            to_corpus = surplus
        else:
            short = -surplus
            take = min(emg, short)
            emg -= take
            corpus -= short - take
            to_corpus = -(short - take)
            if working and not any(f["m"] > m - 12 for f in flags if f["text"].startswith("Spending")):
                flags.append(dict(m=m, text="Spending is more than income; the gap comes from savings."))
        # goal payouts
        for g in goals:
            if m == g["due"]:
                pay_goal = min(g["bal"], g["cost"])
                g["paid"] = pay_goal
                g["short"] = g["cost"] - pay_goal
                if g["short"] > 1:
                    corpus -= g["short"]
                g["bal"] = 0.0
        # growth
        corpus *= 1 + rE
        emg *= 1 + rD
        for g in goals:
            if m < g["due"]:
                g["bal"] *= 1 + (rD if g["due"] - m <= a["goal_derisk_months"] else rE)
        for i, e in enumerate(p["earners"]):
            on = inc[i][0] > 0
            pf[i] = pf[i] * (1 + rPF) + (e["pf"].get("monthly", 0) * (1 + e["growth"]) ** y if on else 0)
            if e["pension"]["type"] == "NPS":
                nps[i] = nps[i] * (1 + rNPS) + (e["pension"].get("monthly", 0) * (1 + e["growth"]) ** y if on else 0)
        rows.append(dict(m=m, defl=defl, corpus=corpus, emg=emg, goals=sum(g["bal"] for g in goals), pf=list(pf), nps=list(nps), loan=loan,
                         income=[x[0] for x in inc], arrears=sum(x[1] for x in inc), rent_recv=rent_recv,
                         out=dict(living=base, medical=med + prem, school=school, unlisted=unlisted, rent=rent_paid, maintenance=maint, emi=emi_paid),
                         to_emg=to_emg, to_goals=to_goals, to_corpus=to_corpus, target_emg=target))
    return dict(rows=rows, goals=goals, flags=flags)


# ---------------------------------------------------------------- pensions
def pension_at(p, i, stop_month):
    """Pension for earner i who stops work at stop_month: dict(start_month, monthly_nominal, indexed, lump, family_pct)."""
    e = p["earners"][i]
    pen = e["pension"]
    if pen["type"] in ("none", None):
        return None
    ret_m = int(round((e["retire_age"] - e["age"]) * 12))
    end_m = min(ret_m, stop_month) if stop_month is not None else ret_m
    service = pen.get("service_years_now", 0) + end_m / 12
    if pen["type"] in ("OPS", "UPS"):
        if service < pen["min_years"]:
            return None
        last_take = take_home(p, e, max(0, end_m - 1))[0]
        basic = e["basic"] * last_take / e["take_home"]           # basic moves with pay
        pct = pen["pct"] * min(1.0, service / pen["full_years"])
        monthly = pct * basic * (1 + pen.get("da_at_retirement", 0.0))   # DR on top; DA resets at pay commissions, so default 0 (cautious)
        if pen["type"] == "UPS":
            monthly = max(monthly, pen["min_pension"])
        lump = 0.0
        if pen["type"] == "OPS" and pen.get("commute"):
            lump = pen["commute"] * monthly * 12 * _static("pension_defaults.json")["OPS"]["commutation"]["factor_years"]
            monthly_after = monthly * (1 - pen["commute"])
        else:
            monthly_after = monthly
        if pen["type"] == "UPS":
            lump = basic / 10 * int(service * 2)
        start = ret_m if pen["type"] == "OPS" or end_m >= ret_m else ret_m   # pension starts at superannuation age
        return dict(start=start, monthly=monthly_after, restore=monthly if pen.get("commute") else None, restore_after=15 * 12,
                    indexed=True, lump=lump, family_pct=pen["family_pct"])
    if pen["type"] == "NPS":
        return dict(start=max(end_m, int(round((60 - e["age"]) * 12))), nps=True, share=pen["annuity_share"], rate=pen["annuity_rate"], indexed=False, lump=0.0)
    return None


# ---------------------------------------------------------------- independence test
def required(p, proj, s, stress=False):
    """Smallest liquid corpus (today's rupees) at month s that lasts to the end of the plan, given what else is coming.
    Also returns the cash-flow years for display."""
    a, h = p["assumptions"], p.get("home") or {}
    inf = a["inflation"]
    rows = proj["rows"]
    rs = rows[min(s, len(rows) - 1)]
    D_s = rs["defl"]
    youngest = min(e["age"] for e in p["earners"])
    years = int(math.ceil(a["live_to"] - (youngest + s / 12)))
    # flows after the stop month, year by year, in today's rupees (at the start month's prices)
    need, income, add_assets = [], [], []
    pf_bal = list(rs["pf"])
    nps_bal = list(rs["nps"])
    goals = [dict(g) for g in proj["goals"]]
    pens = {i: pension_at(p, i, s if i == p["main"] else (None if p["earners"][i].get("keeps_working") else s)) for i in range(len(p["earners"]))}
    loan = rs["loan"]
    L = h.get("loan") or {}
    poss = h.get("possession_months", 0)
    liquidity = _static("liquidity.json")
    nps_lump_done = set()
    for k in range(years):
        m = s + 12 * k
        defl = (1 + inf) ** (m / 12)
        yr = m // 12
        n = p["retirement"]["spend_today"] + p["retirement"]["medical_today"] * (1 + a["medical_inflation_extra"]) ** (m / 12)
        n += sum(c["school_fee"] * 12 * ((1 + a["education_inflation"]) / (1 + inf)) ** (m / 12) for c in p["children"] if c["age"] + m / 12 < c["school_until"])
        if h:
            if m < poss or h["after_possession"] == "let_out":
                n += 12 * h.get("rent_now", 0) * (1 + h["rent_growth"]) ** yr / defl
            if m >= poss:
                n += 12 * h["maintenance"]
                if h["after_possession"] == "let_out" and h.get("let_out"):
                    lo = h["let_out"]
                    n -= 12 * lo["rent"] * (1 + lo["growth"]) ** max(0, (m - poss) // 12) * (1 - lo["vacant_months"] / 12) / defl * 0.9
        # loan keeps its EMI (no more prepayment)
        if loan > 0:
            paid = 0.0
            for _ in range(12):
                if loan <= 0:
                    break
                it = loan * L["rate"] / 12
                pay = min(L["emi"], loan + it)
                loan = loan + it - pay
                paid += pay
            n += paid / defl
        # goals still to be paid: bucket keeps growing without SIPs
        for g in goals:
            if g["due"] > s and g["due"] <= m + 12 and not g.get("done"):
                months = g["due"] - s
                grown = g.get("bal_at_s", None)
                if grown is None:
                    grown = 0.0
                short = max(0.0, g["cost"] - grown)
                n += short / ((1 + inf) ** (g["due"] / 12))
                g["done"] = True
        inc = 0.0
        for i, e in enumerate(p["earners"]):
            if i != p["main"] and e.get("keeps_working"):
                inc += 12 * take_home(p, e, m)[0] / defl
            pz = pens[i]
            if pz and m >= pz["start"]:
                if pz.get("nps"):
                    if i not in nps_lump_done:
                        bal = nps_bal[i]
                        add_assets.append((k, bal * (1 - pz["share"]) / defl))
                        pz["annuity"] = bal * pz["share"] * pz["rate"]
                        pz["annuity_defl"] = defl
                        nps_lump_done.add(i)
                    inc += pz["annuity"] / defl
                else:
                    mon = pz["monthly"]
                    if pz.get("restore") and m >= pz["start"] + pz["restore_after"]:
                        mon = pz["restore"]
                    start_defl = (1 + inf) ** (pz["start"] / 12)
                    inc += 12 * mon / start_defl                   # indexed: constant in real terms from its start
                    if pz["lump"] and not pz.get("lump_done"):
                        add_assets.append((k, pz["lump"] / start_defl))
                        pz["lump_done"] = True
        # PF/GPF becomes spendable at its liquidity age
        for i, e in enumerate(p["earners"]):
            age = e["age"] + m / 12
            t = e["pf"].get("type", "none")
            avail_age = liquidity.get(t, {}).get("available_from_age", e["retire_age"]) if t == "EPF" else e["retire_age"]
            if pf_bal[i] > 0 and age >= avail_age:
                add_assets.append((k, pf_bal[i] * (1 + a["pf_return"]) ** (12 * k / 12) / ((1 + inf) ** (12 * k / 12)) / D_s))
                pf_bal[i] = 0.0
        need.append(n * (1 + a["tax_on_retirement_spending"]))
        income.append(inc)
    adds = {}
    for k, v in add_assets:
        adds[k] = adds.get(k, 0) + v
    real = (1 + a["equity_return"] * 0.75 + a["debt_return"] * 0.25) / (1 + inf) - 1   # not used; kept for reference
    base_r = a["retire_real_return"]
    st = a["stress"]

    def lasts(L0):
        c = L0
        for k in range(years):
            r = base_r
            if stress:
                r = st["first_year"] if k == 0 else (st["real"] if k <= st["years"] else base_r)
            c += adds.get(k, 0.0)
            c = c * (1 + r) - max(0.0, need[k] - income[k])
            if c < 0:
                return False
        return True

    lo, hi = 0.0, 1e10
    if lasts(0):
        return 0.0, need, income
    for _ in range(60):
        mid = (lo + hi) / 2
        if lasts(mid):
            hi = mid
        else:
            lo = mid
    return hi, need, income


def goal_balances_at(p, s):
    """Goal bucket balances at month s when SIPs stop at s (run the ledger with stop=s)."""
    pr = project(p, stop=s, months=s)
    return {g["name"]: g["bal"] for g in pr["goals"]}


def independence(p, proj=None, full=False):
    """Earliest stop year (base and stress) where the liquid corpus covers what's required.
    full=True keeps going to the main earner's retirement (for the chart)."""
    proj = proj or project(p)
    rows = proj["rows"]
    out = []
    first_base = first_stress = None
    for s in range(0, len(rows), 12):
        # goal buckets at s if SIPs stop then
        bals = goal_balances_at(p, s) if s else {g["name"]: 0 for g in proj["goals"]}
        for g in proj["goals"]:
            g["bal_at_s"] = bals.get(g["name"], 0.0) * (1 + p["assumptions"]["debt_return"]) ** max(0, (g["due"] - s) / 12)
        req_b, _, _ = required(p, proj, s)
        req_s, _, _ = required(p, proj, s, stress=True)
        have = rows[s]["corpus"] / rows[s]["defl"]
        out.append(dict(m=s, have=have, req=req_b, req_stress=req_s))
        if first_base is None and have >= req_b:
            first_base = s
        if first_stress is None and have >= req_s:
            first_stress = s
        if not full and first_base is not None and first_stress is not None and s > first_stress + 24:
            break
    return dict(path=out, base=first_base, stress=first_stress)


def age_at(p, m):
    if m is None:
        return None
    return p["earners"][p["main"]]["age"] + m / 12


# ---------------------------------------------------------------- levers, guesses, stress
def _variant(p, fn):
    q = copy.deepcopy(p)
    fn(q)
    return q


def _fi_age(q):
    r = independence(q)
    return age_at(q, r["base"]), age_at(q, r["stress"])


def levers(p, base_ages):
    L = []

    def add(name, fn):
        q = _variant(p, fn)
        b, s = _fi_age(q)
        L.append(dict(name=name, base=b, stress=s, delta=None if b is None or base_ages[0] is None else b - base_ages[0]))

    add("Spend 10% less, now and in retirement", lambda q: (q["spending"].update({k: v * 0.9 for k, v in q["spending"].items() if k in ("household", "card_needs", "card_wants", "other")}),
                                                             q["retirement"].update(spend_today=q["retirement"]["spend_today"] * 0.9)))
    h = p.get("home") or {}
    if h.get("let_out"):
        other = "move_in" if h["after_possession"] == "let_out" else "let_out"
        add("Move into the new house" if other == "move_in" else "Rent the new house out", lambda q: q["home"].update(after_possession=other))
    if (h.get("loan") or {}).get("prepay_now") or (h.get("loan") or {}).get("prepay_after"):
        add("Stop prepaying the loan (invest the money instead)", lambda q: q["home"]["loan"].update(prepay_now=0, prepay_after=0))
    for i, e in enumerate(p["earners"]):
        if i == p["main"]:
            continue
        if e.get("keeps_working"):
            add(f"{e['name']} also stops when the main earner stops", lambda q, i=i: q["earners"][i].update(keeps_working=False))
        else:
            add(f"{e['name']} keeps working to retirement", lambda q, i=i: q["earners"][i].update(keeps_working=True))
    add("Retirement spending 10% lower", lambda q: q["retirement"].update(spend_today=q["retirement"]["spend_today"] * 0.9))
    return L


def guesses_effect(p, base_ages):
    G = []

    def add(name, lo_fn, hi_fn):
        lo, hi = _fi_age(_variant(p, lo_fn))[0], _fi_age(_variant(p, hi_fn))[0]
        G.append(dict(name=name, low=lo, high=hi, spread=None if lo is None or hi is None else abs(hi - lo)))

    add("Return after inflation in retirement: 2.5% vs 3.5%", lambda q: q["assumptions"].update(retire_real_return=0.025),
        lambda q: q["assumptions"].update(retire_real_return=0.035))
    add("Retirement spending: 10% more vs 10% less", lambda q: q["retirement"].update(spend_today=q["retirement"]["spend_today"] * 1.1),
        lambda q: q["retirement"].update(spend_today=q["retirement"]["spend_today"] * 0.9))
    add("Spending not listed: 10% vs 0% of take-home", lambda q: q["assumptions"].update(unlisted_spending_share=0.10),
        lambda q: q["assumptions"].update(unlisted_spending_share=0.0))
    for i, e in enumerate(p["earners"]):
        if e.get("pay_commission"):
            add(f"Pay commission for {e['name']}: +12% vs +18%", lambda q, i=i: q["earners"][i]["pay_commission"].update(net_jump=0.12),
                lambda q, i=i: q["earners"][i]["pay_commission"].update(net_jump=0.18))
        if e["pension"]["type"] in ("OPS", "UPS"):
            add(f"{e['name']}'s pension: none vs as entered", lambda q, i=i: q["earners"][i]["pension"].update(type="none"), lambda q: None)
    G.sort(key=lambda g: -(g["spread"] or 0))
    return G


def term_gap(p, proj):
    """If the main earner's income stopped now: what's needed (loan + household costs until the youngest child is 22 +
    goals) minus what's there (liquid investments, other earners' income, existing cover). Never 'you need ₹X cover'."""
    a = p["assumptions"]
    r = a["retire_real_return"]
    kids = [c["age"] for c in p["children"]] or [22]
    years = max(15, int(math.ceil(22 - min(kids))))
    sp = p["spending"]
    yearly = 12 * sum(sp[k] for k in ("household", "card_needs", "card_wants", "bills", "travel", "other", "medical")) + sp["insurance_premiums_yearly"]
    yearly += 12 * sum(c["school_fee"] for c in p["children"])
    h = p.get("home") or {}
    if h and h.get("possession_months", 0) > 0:
        yearly += 12 * h.get("rent_now", 0) * min(1.0, h["possession_months"] / 12)
    pv = lambda amt, n: sum(amt / (1 + r) ** k for k in range(n))
    need = dict(loan=(h.get("loan") or {}).get("balance", 0), living=pv(yearly, years),
                goals=sum(g["cost"] / (1 + a["inflation"]) ** (g["due"] / 12) / (1 + r) ** (g["due"] / 12) for g in proj["goals"]))
    others = sum(12 * e["take_home"] * (1 - a["unlisted_spending_share"]) for i, e in enumerate(p["earners"]) if i != p["main"])
    have = dict(investments=p["investments"]["mutual_funds"] + p["investments"]["stocks"] + p["investments"]["other"] + p["emergency"]["now"],
                goal_funds=sum(c["fund_now"] for c in p["children"]) + sum(g["fund_now"] for g in p["goals"]),
                pf=sum(e["pf"].get("balance", 0) for e in p["earners"]), others_income=pv(others, years),
                cover=p["insurance"].get("term_cover", 0))
    gap = sum(need.values()) - sum(have.values())
    return dict(years=years, need=need, have=have, gap=max(0.0, gap))


# ---------------------------------------------------------------- to-do rules
def todos(p, proj, fi):
    T = []
    r0 = proj["rows"][0]
    fixed = r0["out"]["living"] + r0["out"]["rent"] + r0["out"]["emi"] + r0["out"]["maintenance"]
    months = (p["emergency"]["now"] + p["emergency"]["seed"]) / fixed if fixed else 99
    if months < 3:
        T.append(dict(when="now", text=f"Emergency fund covers about {months:.1f} months of fixed costs. Build it to at least 3 months first, then {p['emergency']['target_months']}."))
    g = term_gap(p, proj)
    if g["gap"] > 0:
        T.append(dict(when="now", text=f"If the main earner's income stopped today, there'd be a shortfall of about ₹{g['gap'] / 1e5:.0f}L after investments, other income and existing cover. That's the gap term insurance would need to fill; check it against your policy."))
    if any(c["age"] < 1 for c in p["children"]):
        T.append(dict(when="now", text="Add the youngest child to the family health policy; insurers usually allow it only within a set window after birth."))
    T.append(dict(when="now", text="Check the family floater amount and consider a super top-up for large hospital bills."))
    lo = (p.get("home") or {}).get("let_out") or {}
    if lo.get("funded_by") and lo.get("owner") and lo["funded_by"] != lo["owner"]:
        T.append(dict(when="before possession", text=f"The house is owned by {lo['owner']} but funded by {lo['funded_by']}: under clubbing rules the rent is taxed as {lo['funded_by']}'s income. Check with a CA."))
    if (p.get("home") or {}).get("possession_months", 0) > 0:
        T.append(dict(when="before possession", text="Budget separately for registration, interiors and furniture so the emergency fund and SIPs stay untouched."))
    for f in proj["flags"][:1]:
        T.append(dict(when="now", text=f["text"] + f" (first from {label(p['as_of'], f['m'])})"))
    T.append(dict(when="every year", text="Step up SIPs with each raise; compare this year's milestone row with your actual net worth."))
    return T


# ---------------------------------------------------------------- one call
def run(plan, with_levers=True):
    p = load(plan)
    proj = project(p)
    fi = independence(p, proj, full=True)
    base_age, stress_age = age_at(p, fi["base"]), age_at(p, fi["stress"])
    res = dict(plan=p, proj=proj, fi=fi, base_age=base_age, stress_age=stress_age, todos=todos(p, proj, fi), term=term_gap(p, proj))
    if with_levers:
        res["levers"] = levers(p, (base_age, stress_age))
        res["guess_effects"] = guesses_effect(p, (base_age, stress_age))
    return res
