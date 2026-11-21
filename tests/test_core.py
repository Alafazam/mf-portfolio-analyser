"""Unit tests (offline) and one integration test (needs internet for the AMFI list): python3 -m unittest -v"""
import os, sys, json, tempfile, unittest, datetime as dt
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from mfpa.ingest.cas import add_years, parse, kind_of, detect_sips
from mfpa.analysis.stats import xirr
from mfpa.report.build import clean

CAS = """          Consolidated Account Statement
          ( From Date : 01-Jan-2013          To Date : 20-Nov-2026 )
FOLIO NO: 111                 KYC : OK
Test Fund - Direct Plan - Growth (Advisor: INZ000305337/X) ISIN: INF000TEST01     Opening Unit Balance: 0.000
 10-JAN-2020   Purchase                       10,000.00     100.000    100.0000     100.000
 10-JAN-2021   Purchase                       12,000.00     100.000    120.0000     200.000
 15-JUN-2026   Redemption - Electronic Payment   (15,000.00)   (100.000)    150.0000     100.000
Closing Unit Balance: 100.000          Nav as on 20-NOV-2026: INR 160.0000        Valuation on 20-Nov-2026: INR 16,000.00
FOLIO NO: 222                 KYC : OK
Other Fund - Direct Plan - Growth (Advisor: DIRECT/DIRECT) ISIN: INF000TEST02     Opening Unit Balance: 0.000
 10-JAN-2024   Purchase                       1,000.00      10.000    100.0000      10.000
Closing Unit Balance: 12.000          Nav as on 20-NOV-2026: INR 110.0000        Valuation on 20-Nov-2026: INR 1,320.00
"""

class Dates(unittest.TestCase):
    def test_leap_day(self): self.assertEqual(add_years(dt.date(2024, 2, 29), 1), dt.date(2025, 2, 28))
    def test_anniversary_plus_one(self):
        # held MORE than 12 months: first long-term day is the day after the anniversary
        self.assertEqual(add_years(dt.date(2025, 12, 9), 1) + dt.timedelta(days=1), dt.date(2026, 12, 10))

class CasParser(unittest.TestCase):
    def setUp(self):
        self.f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False); self.f.write(CAS); self.f.close()
        self.p = parse(self.f.name)
    def tearDown(self): os.unlink(self.f.name)
    def test_fifo_redemption_takes_oldest_lot(self):
        lots = self.p["folios"][0]["lots"]
        self.assertEqual(len(lots), 1); self.assertEqual(lots[0]["date"], dt.date(2021, 1, 10)); self.assertAlmostEqual(lots[0]["cost"], 12000)
    def test_realised_gain(self):
        r = self.p["folios"][0]["realised"][0]; self.assertEqual(r["gain"], 15000 - 10000)
    def test_reconciliation_flags_mismatch(self):
        self.assertTrue(self.p["folios"][0]["reconciled"]); self.assertFalse(self.p["folios"][1]["reconciled"])
        self.assertEqual(len(self.p["warnings"]), 1)
    def test_kinds(self):
        self.assertEqual(kind_of("Systematic Investment (1)", 5), "sip"); self.assertEqual(kind_of("Switch In - Merger", 5), "merger_in")
        self.assertEqual(kind_of("Redemption", -5), "redemption"); self.assertEqual(kind_of("Purchase-BSE", 5), "purchase")

class Sips(unittest.TestCase):
    def test_monthly_pattern(self):
        today = dt.date(2026, 11, 20)
        lots = [dict(kind="purchase", estimated=False, date=str(d), cost=c) for d, c in
                [(dt.date(2026, 8, 9), 11000), (dt.date(2026, 9, 9), 11000), (dt.date(2026, 10, 9), 11000), (dt.date(2026, 11, 9), 11000)]]
        s = detect_sips([dict(name="X", plan="Direct", folios=[dict(via="INDmoney", lots=lots)])], today)
        self.assertEqual(s[0]["amount"], 11000); self.assertEqual(s[0]["day"], 9)
    def test_one_off_is_not_a_sip(self):
        lots = [dict(kind="purchase", estimated=False, date="2026-10-01", cost=50000)]
        self.assertEqual(detect_sips([dict(name="X", plan="Direct", folios=[dict(via="", lots=lots)])], dt.date(2026, 11, 20)), [])

class Report(unittest.TestCase):
    def test_strings_are_cleaned(self):
        self.assertEqual(clean({"n": "<img src=x onerror=alert(1)>Fund"})["n"], "img src=x onerror=alert(1)Fund")
        self.assertNotIn("<", json.dumps(clean(["</script><b>"])))

class Xirr(unittest.TestCase):
    def test_simple(self):
        r = xirr([(dt.date(2020, 1, 1), -100), (dt.date(2021, 1, 1), 110)]); self.assertAlmostEqual(r, 0.0998, places=3)

class SyntheticRoundTrip(unittest.TestCase):
    """Parse the synthetic CAS written from the sample and check every holding's units come back (needs internet: AMFI list)."""
    def test_round_trip(self):
        from mfpa.ingest.cas import to_holdings
        try: from mfpa.data import amfi; amfi.rows()
        except Exception: self.skipTest("no internet")
        p = parse(os.path.join(ROOT, "samples", "synthetic_cas.txt"))
        self.assertFalse(p["warnings"], p["warnings"])
        hs, warn, _ = to_holdings(p)
        sample = json.load(open(os.path.join(ROOT, "samples", "sample_holdings.json")))["holdings"]
        want = {h["code"]: sum(l["units"] for f in h["folios"] for l in f["lots"]) for h in sample}
        got = {h["code"]: sum(l["units"] for f in h["folios"] for l in f["lots"]) for h in hs}
        for code, u in want.items(): self.assertAlmostEqual(got.get(code, 0), u, places=2, msg=str(code))

if __name__ == "__main__": unittest.main()
