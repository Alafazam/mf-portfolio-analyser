"""Family plan model tests (offline): python3 -m unittest tests.test_plan -v"""
import copy, json, os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from mfpa.plan import model as M

with open(os.path.join(ROOT, "samples", "sample_family.json"), encoding="utf-8") as _fh:
    SAMPLE = json.load(_fh)


def plan(**over):
    """A small one-earner plan; keyword arguments replace top-level sections."""
    p = {"as_of": "2026-11-01",
         "earners": [{"name": "A", "age": 35, "take_home": 150000, "growth": 0.0, "employer": "private",
                      "pf": {"type": "none", "balance": 0, "monthly": 0}, "pension": {"type": "none"}, "retire_age": 60}],
         "spending": {"household": 60000}, "children": [], "goals": [],
         "investments": {"mutual_funds": 1000000}, "emergency": {"now": 600000, "target_months": 6, "top_up": 0},
         "retirement": {"spend_today": 600000, "medical_today": 0},
         "assumptions": {"equity_return": 0.0, "debt_return": 0.0, "inflation": 0.0, "retire_real_return": 0.03, "live_to": 90,
                         "pf_return": 0.0, "nps_return": 0.0, "unlisted_spending_share": 0.0, "medical_inflation_extra": 0.0,
                         "education_inflation": 0.0, "tax_on_retirement_spending": 0.0}}
    p.update(over)
    return p


class Ledger(unittest.TestCase):
    def test_money_is_conserved_every_month(self):
        """With zero returns and inflation: change in corpus + emergency + goal funds = money in − money out − goal payouts."""
        p = copy.deepcopy(SAMPLE)
        p["assumptions"].update(equity_return=0, debt_return=0, inflation=0, medical_inflation_extra=0, education_inflation=0, pf_return=0, nps_return=0)
        q = M.load(p)
        pr = M.project(q)
        rows = pr["rows"]
        due = {g["due"]: g["cost"] for g in pr["goals"]}
        start = q["investments"]["mutual_funds"] + q["investments"]["stocks"] + q["investments"]["other"] + q["emergency"]["now"] + \
            sum(c["fund_now"] for c in q["children"]) + sum(g["fund_now"] for g in q["goals"])
        prev = start
        for r in rows:
            tot = r["corpus"] + r["emg"] + r["goals"]
            flow = sum(r["income"]) + r["arrears"] + r["rent_recv"] - sum(r["out"].values()) - due.get(r["m"], 0)
            self.assertAlmostEqual(tot - prev, flow, delta=1.0, msg=f"month {r['m']}")
            prev = tot

    def test_sips_bigger_than_surplus_are_scaled_and_flagged(self):
        p = plan(children=[{"name": "C", "age": 5, "cost_today": 2000000, "sip": 500000}])
        pr = M.project(M.load(p))
        self.assertTrue(any("scaled down" in f["text"] for f in pr["flags"]))
        self.assertGreaterEqual(pr["rows"][0]["to_corpus"], -1)

    def test_emergency_top_up_lands_in_the_fund(self):
        p = plan(emergency={"now": 0, "target_months": 6, "top_up": 10000})
        pr = M.project(M.load(p))
        self.assertAlmostEqual(pr["rows"][0]["emg"], 10000)


class Loan(unittest.TestCase):
    def test_emi_formula_clears_on_time(self):
        P, r, n = 3000000, 0.09 / 12, 240
        emi = P * r * (1 + r) ** n / ((1 + r) ** n - 1)
        p = plan(home={"loan": {"balance": P, "rate": 0.09, "emi": emi, "prepay_now": 0, "prepay_after": 0}, "possession_months": 0, "maintenance": 0})
        rows = M.project(M.load(p))["rows"]
        cleared = next(i for i, x in enumerate(rows) if x["loan"] == 0)
        self.assertIn(cleared, (n - 2, n - 1, n))

    def test_prepayment_clears_sooner(self):
        base = {"balance": 3000000, "rate": 0.09, "emi": 27000, "prepay_now": 0, "prepay_after": 0}
        a = M.project(M.load(plan(home={"loan": dict(base), "possession_months": 0, "maintenance": 0})))["rows"]
        b = M.project(M.load(plan(home={"loan": dict(base, prepay_now=10000, prepay_after=10000), "possession_months": 0, "maintenance": 0})))["rows"]
        first = lambda rows: next(i for i, x in enumerate(rows) if x["loan"] == 0)
        self.assertLess(first(b), first(a))


class Pensions(unittest.TestCase):
    def _earner(self, ptype, service_now, **pen):
        # pay_commission False: no default +15% jump, so these check the pension maths alone
        return {"name": "G", "age": 40, "take_home": 100000, "growth": 0.0, "employer": "state_govt", "basic": 60000,
                "pay_commission": False, "pf": {"type": "none", "balance": 0, "monthly": 0}, "retire_age": 60,
                "pension": dict(type=ptype, service_years_now=service_now, **pen)}

    def test_pay_commission_raises_the_pension_with_basic(self):
        e = self._earner("OPS", 5, pct=0.5, min_years=10, full_years=20)
        e["pay_commission"] = None                                   # govt default: +15% net jump
        p = M.load(plan(earners=[e]))
        self.assertAlmostEqual(M.pension_at(p, 0, None)["monthly"], 0.5 * 60000 * 1.15)

    def test_ops_is_pct_of_last_basic_and_excludes_allowances(self):
        p = M.load(plan(earners=[self._earner("OPS", 5, pct=0.5, min_years=10, full_years=20)]))
        pz = M.pension_at(p, 0, None)
        self.assertAlmostEqual(pz["monthly"], 0.5 * 60000)        # basic 60k, not take-home 100k
        self.assertTrue(pz["indexed"])

    def test_ops_pro_rated_and_minimum_service(self):
        p = M.load(plan(earners=[self._earner("OPS", 0, pct=0.5, min_years=10, full_years=30)]))
        self.assertAlmostEqual(M.pension_at(p, 0, None)["monthly"], 0.5 * 60000 * 20 / 30)   # 20 years of 30
        p2 = M.load(plan(earners=[dict(self._earner("OPS", 0, pct=0.5, min_years=25, full_years=30))]))
        self.assertIsNone(M.pension_at(p2, 0, None))                                     # below minimum service

    def test_ops_commutation_lump_and_cut(self):
        p = M.load(plan(earners=[self._earner("OPS", 10, pct=0.5, min_years=10, full_years=20, commute=0.4)]))
        pz = M.pension_at(p, 0, None)
        self.assertAlmostEqual(pz["monthly"], 0.6 * 30000)
        self.assertAlmostEqual(pz["restore"], 30000)
        self.assertGreater(pz["lump"], 0)

    def test_ups_minimum_and_pro_rating(self):
        for service_now, expect in ((0, 0.5 * 60000 * 20 / 25), (10, 0.5 * 60000)):
            p = M.load(plan(earners=[self._earner("UPS", service_now)]))
            self.assertAlmostEqual(M.pension_at(p, 0, None)["monthly"], expect)
        e = self._earner("UPS", 0)
        e["basic"] = 10000
        p = M.load(plan(earners=[e]))
        self.assertEqual(M.pension_at(p, 0, None)["monthly"], 10000)                  # ₹10,000 minimum

    def test_nps_annuity_is_not_indexed(self):
        e = self._earner("NPS", 0)
        p = M.load(plan(earners=[e]))
        self.assertFalse(M.pension_at(p, 0, None)["indexed"])


class Independence(unittest.TestCase):
    def test_goal_after_stop_date_raises_what_is_needed(self):
        p0 = M.load(plan())
        p1 = M.load(plan(children=[{"name": "C", "age": 10, "cost_today": 3000000, "sip": 0}]))
        pr0, pr1 = M.project(p0), M.project(p1)
        for g in pr1["goals"]:
            g["bal_at_s"] = 0
        need0 = M.required(p0, pr0, 12)[0]
        need1 = M.required(p1, pr1, 12)[0]
        self.assertGreater(need1, need0 + 2000000)   # college fee after the stop date is counted

    def test_partner_who_keeps_working_lowers_need_but_not_savings(self):
        two = lambda keeps: plan(earners=[plan()["earners"][0],
                                          {"name": "B", "age": 33, "take_home": 60000, "growth": 0.0, "employer": "private",
                                           "pf": {"type": "none", "balance": 0, "monthly": 0}, "pension": {"type": "none"}, "retire_age": 60,
                                           "keeps_working": keeps}])
        pa, pb = M.load(two(False)), M.load(two(True))
        ra, rb = M.project(pa), M.project(pb)
        self.assertAlmostEqual(ra["rows"][120]["corpus"], rb["rows"][120]["corpus"])   # savings before the stop date are the same
        self.assertLess(M.required(pb, rb, 120)[0], M.required(pa, ra, 120)[0])     # partner income lowers what's needed after it

    def test_epf_not_spendable_before_55(self):
        e = dict(plan()["earners"][0], pf={"type": "EPF", "balance": 20000000, "monthly": 0})
        p = M.load(plan(earners=[e], investments={"mutual_funds": 0}))
        pr = M.project(p)
        need_at_45 = M.required(p, pr, 120)[0]    # stops at 45: ten years before EPF opens
        self.assertGreater(need_at_45, 0)

    def test_stress_never_earlier_than_base(self):
        r = M.run(copy.deepcopy(SAMPLE), with_levers=False)
        self.assertIsNotNone(r["base_age"])
        self.assertGreaterEqual(r["stress_age"], r["base_age"])

    def test_sample_ages_are_stable(self):
        r = M.run(copy.deepcopy(SAMPLE), with_levers=False)
        self.assertEqual((r["base_age"], r["stress_age"]), (47.0, 51.0))


class Tax(unittest.TestCase):
    def test_rebate_and_slabs(self):
        self.assertEqual(M.income_tax(1200000), 0)
        self.assertGreater(M.income_tax(1600000), 0)

    def test_rent_taxed_in_the_funders_hands(self):
        def p(funder):
            return M.load(plan(earners=[plan()["earners"][0], {"name": "B", "age": 33, "take_home": 10000, "growth": 0.0,
                                                               "pf": {"type": "none"}, "pension": {"type": "none"}, "retire_age": 60}],
                               home={"loan": {"balance": 0, "rate": 0.08, "emi": 0}, "possession_months": 0, "after_possession": "let_out",
                                     "rent_now": 30000, "maintenance": 0, "let_out": {"rent": 40000, "owner": "B", "funded_by": funder}}))
        self.assertEqual(M.rent_tax_year(p("B"), 0, 480000, 0), 0)        # low-income owner, own money: rebate
        self.assertGreater(M.rent_tax_year(p("A"), 0, 480000, 0), 0)      # funded by the high earner: clubbed


class PayCommission(unittest.TestCase):
    def test_arrears_paid_on_payout_month(self):
        e = {"name": "G", "age": 40, "take_home": 100000, "growth": 0.0, "employer": "state_govt",
             "pay_commission": {"effective": "2026-01", "payout": "2027-11", "net_jump": 0.15},
             "pf": {"type": "none"}, "pension": {"type": "none"}, "retire_age": 60}
        p = M.load(plan(earners=[e]))
        self.assertEqual(M.take_home(p, p["earners"][0], 11), (100000, 0.0))
        pay, arrears = M.take_home(p, p["earners"][0], 12)
        self.assertAlmostEqual(pay, 115000)
        self.assertAlmostEqual(arrears, 22 * 100000 * 0.15)   # Jan 2026 to Oct 2027


class SamplePage(unittest.TestCase):
    def test_sample_page_is_up_to_date(self):
        """The sample family has a fixed as_of date, so rebuilding gives the committed page byte for byte."""
        import tempfile
        from mfpa.plan.build import build
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "x.html")
            build(copy.deepcopy(SAMPLE), out, share=False, web_fonts=True)
            with open(out, encoding="utf-8") as a, open(os.path.join(ROOT, "samples", "sample-family.html"), encoding="utf-8") as b:
                self.assertEqual(a.read(), b.read(), "run: python3 -m mfpa plan-sample")

    def test_share_copy_hides_ages_and_rounds(self):
        from mfpa.plan.build import data
        D = data(M.run(copy.deepcopy(SAMPLE), with_levers=False), share=True)
        self.assertTrue(all(c["age"] is None for c in D["children"]))
        self.assertTrue(all(all(k is None for k in m["kids"]) for m in D["miles"]))
        self.assertEqual(D["miles"][3]["invested"] % 10000, 0)


if __name__ == "__main__":
    unittest.main()
