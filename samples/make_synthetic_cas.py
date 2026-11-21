"""Write the synthetic sample as an MF Central 'Detailed' CAS text file (samples/synthetic_cas.txt), in the same layout
pdftotext produces, so the CAS parser can be tested end to end without anyone's real statement. Fake folios, no PAN."""
import json, os, datetime as dt
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import sys; sys.path.insert(0, ROOT)
from mfpa.data import amfi
H = json.load(open(os.path.join(ROOT, "samples", "sample_holdings.json")))
P = {h["key"]: h for h in json.load(open(os.path.join(ROOT, "samples", "sample_portfolio.json")))["holdings"]}
VIA = {"INDmoney": "INZ000305337/INDMONEY PRIVATE LIMITED", "Distributor": "ARN-000000/SAMPLE DISTRIBUTOR"}
end = dt.date.fromisoformat(H["as_of"])
L = [" " * 90 + "Consolidated Account Statement", " " * 86 + f"( From Date : 01-Jan-2013          To Date : {end:%d-%b-%Y} )", "",
     "   PAN: XXXXXXXXXX", "   Sample Investor", ""]
fol = 900000
for h in H["holdings"]:
    r = amfi.rows()[h["code"]]
    for f in h["folios"]:
        fol += 1
        L += [f"FOLIO NO: {fol}" + " " * 80 + "KYC : OK",
              f"{r['name']} - {h['plan']} Plan - Growth (Advisor: {VIA.get(f['via'], 'DIRECT/DIRECT')}) ISIN: {r['isin']}          Opening Unit Balance: 0.000", ""]
        bal = 0.0
        txns = sorted([(l["date"], "buy", l) for l in f["lots"]], key=lambda t: t[0])
        for d, _, l in txns:
            u = round(l["units"], 3); bal = round(bal + u, 3); price = l["cost"] / l["units"]
            desc = "Systematic Investment (1)" if h["key"] in ("uti_n50", "mo_mid", "quant_elss", "mo_nasdaq") or f["id"] == "F2" else "Purchase"
            L.append(f" {dt.date.fromisoformat(d):%d-%b-%Y}".upper() + f"              {desc:50s}{l['cost']:>14,.2f}{u:>14,.3f}{price:>12,.4f}{bal:>14,.3f}")
        L += ["", f"Closing Unit Balance: {bal:,.3f}" + " " * 30 + f"Nav as on {end:%d-%b-%Y}".upper() + f": INR {h['nav']:,.4f}" + " " * 18 + f"Valuation on {end:%d-%b-%Y}: INR {bal * h['nav']:,.2f}", ""]
open(os.path.join(ROOT, "samples", "synthetic_cas.txt"), "w").write("\n".join(L))
print("wrote samples/synthetic_cas.txt")
