"""MF Central "Detailed" CAS (PDF -> text) to the normalised holdings the engine reads.

Privacy: this module reads the statement text locally and writes ONLY fund-level data: no investor name, PAN, address,
email, phone or folio numbers (folios become F1, F2, ...). Claude should never read the PDF or its raw text; it reads the
JSON this writes. Supported layout (v1): MF Central "Detailed" CAS, period from inception (or the earliest date allowed).

Checks: every folio's units rebuilt from transactions must equal the statement's closing balance; a folio that doesn't
reconcile is reported and left out of the plan. Units held before the statement's start date have no known cost; the
holding is marked cost_unknown and left out of tax planning."""
import re, os, json, shutil, subprocess, datetime as dt
from ..data import amfi
from ..data.navs import nav, on_or_before

GRANDFATHER = dt.date(2018, 1, 31)
VIA = {"INZ000305337": "INDmoney", "INZ000208032": "Groww", "INZ000031633": "Zerodha Coin", "INZ000006031": "Paytm Money", "INZ000183631": "Kuvera"}
DEBT_CATS = re.compile(r"liquid|overnight|money market|duration|gilt|corporate bond|credit risk|banking and psu|floater|dynamic bond|debt", re.I)
OTHER_CATS = re.compile(r"fof|fund of fund|multi asset|balanced advantage|dynamic asset|conservative hybrid|equity savings|gold|silver|international|overseas|global|emerging market|nasdaq|world|u\.\s?s\.|\bus\b", re.I)

def pdf_to_text(pdf, out_txt, password=None, allow_password_arg=False):
    """PDF -> layout text. A password never goes on a command line (other users could see it in `ps`):
    the PDF is first decrypted with qpdf, which reads the password from an owner-only temporary file."""
    if not shutil.which("pdftotext"): raise RuntimeError("pdftotext not found: run `python3 -m mfpa doctor` for the install command")
    src, tmp = pdf, []
    try:
        if password:
            if shutil.which("qpdf"):
                d = os.path.dirname(out_txt)
                pwf = os.path.join(d, ".pw"); fd = os.open(pwf, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as fh: fh.write(password)
                dec = os.path.join(d, ".decrypted.pdf"); tmp += [pwf, dec]
                subprocess.run(["qpdf", f"--password-file={pwf}", "--decrypt", pdf, dec], check=True, capture_output=True)
                os.chmod(dec, 0o600); src = dec
            elif allow_password_arg:
                subprocess.run(["pdftotext", "-layout", "-upw", password, pdf, out_txt], check=True, capture_output=True)
                os.chmod(out_txt, 0o600); return out_txt
            else:
                raise RuntimeError("Password-protected PDF: install qpdf so the password isn't passed on the command line "
                                   "(Linux: sudo apt install -y qpdf, macOS: brew install qpdf), or rerun with --allow-password-arg "
                                   "if you're the only user on this computer.")
        fd = os.open(out_txt, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600); os.close(fd)
        subprocess.run(["pdftotext", "-layout", src, out_txt], check=True, capture_output=True)
        return out_txt
    except subprocess.CalledProcessError as e:
        # the command line may hold the password: report the tool and its own message only
        msg = (e.stderr or b"").decode(errors="replace").replace(password or "\0", "***").strip()[:300]
        raise RuntimeError(f"{e.cmd[0]} could not read the PDF (wrong password or not a CAS PDF?): {msg}") from None
    finally:
        for t in tmp:
            if os.path.exists(t): os.remove(t)

def _num(s): return -float(s.strip("()").replace(",", "")) if s.startswith("(") else float(s.replace(",", ""))
def _date(s): return dt.datetime.strptime(s, "%d-%b-%Y").date()
def add_years(d, n):
    try: return d.replace(year=d.year + n)
    except ValueError: return d.replace(year=d.year + n, day=28)

def kind_of(desc, units):
    d = desc.lower()
    if units < 0: return "switch_out" if "switch" in d else "redemption"
    if "merger" in d or "consolidat" in d: return "merger_in"
    if "switch" in d: return "switch_in"
    if "reinvest" in d or "idcw" in d or "dividend" in d: return "dividend_reinvest"
    if "bonus" in d: return "bonus"
    if "segregat" in d: return "segregation"
    if "systematic" in d or "sip" in d or "sys." in d: return "sip"
    return "purchase"

def nice_name(amfi_name):
    n = re.sub(r"\s*\((erstwhile|formerly)[^)]*\)", "", amfi_name, flags=re.I)
    n = re.sub(r"\s*-\s*(direct|regular).*$", "", n, flags=re.I)
    n = re.sub(r"\s+Fund\b.*$", "", n, flags=re.I).strip(" -")
    return n.replace("Aditya Birla Sun Life", "ABSL").replace("Prudential", "Pru")

def analysis_category(r):
    """Category the engine scores against; index funds get the category of the index they track."""
    name, cat = r["name"], (r.get("category") or "")
    if re.search(r"index|etf", name, re.I) or "index" in (r.get("amfi_category") or "").lower():
        if re.search(r"smallcap|small cap", name, re.I): return "Small cap", True
        if re.search(r"midcap|mid cap", name, re.I): return "Mid cap", True
        if re.search(r"nifty 50\b|nifty 100\b|sensex|next 50|bse 100", name, re.I): return "Large cap", True
        if re.search(r"nifty 500|total market|multicap", name, re.I): return "Flexi cap", True
        return "Index (other)", True
    return cat, False

def tax_class(r, first_buy):
    c = (r.get("amfi_category") or "") + " " + r["name"]
    if DEBT_CATS.search(c): return "specified_50AA" if first_buy and first_buy >= dt.date(2023, 4, 1) else "debt_pre_2023"
    if OTHER_CATS.search(c): return "other"
    return "equity"

def parse(txt_path, as_of=None):
    with open(txt_path, encoding="utf-8", errors="replace") as fh: txt = fh.read()
    m = re.search(r"From Date\s*:\s*(\d{2}-\w{3}-\d{4})\s+To Date\s*:\s*(\d{2}-\w{3}-\d{4})", txt)
    if not m: raise ValueError("Not an MF Central detailed CAS (no 'From Date ... To Date' line). v1 supports only that layout.")
    start, end = _date(m.group(1)), _date(m.group(2))
    blocks = re.split(r"\n(?=\s*FOLIO NO\s*:)", txt, flags=re.I)[1:]
    folios, warnings = [], []
    for b in blocks:
        isin = (re.search(r"INF[A-Z0-9]{9}", b) or [None])[0]
        if not isin: continue
        adv = re.search(r"Advisor:\s*([A-Z0-9-]+)\s*/", b)
        via = VIA.get(adv.group(1), "Distributor" if adv and adv.group(1).startswith("ARN") else "Direct") if adv else "Unknown"
        mo = re.search(r"Opening Unit Balance:\s*([\d,\.]+)", b) or re.search(r"Balance:\s*([\d,\.]+)", b)
        opening = _num(mo.group(1)) if mo else 0.0
        mc = re.search(r"Closing Unit Balance:\s*([\d,\.]+)", b); closing = _num(mc.group(1)) if mc else None
        mn = re.search(r"Nav as on\s+(\d{2}-\w{3}-\d{4})\s*:\s*INR\s*([\d,\.]+)", b, re.I)
        nav_date, nav_now = (_date(mn.group(1).title()), _num(mn.group(2))) if mn else (None, None)
        lots = [dict(date=None, units=opening, cost=None, kind="opening")] if opening > 1e-6 else []
        realised = []
        for line in b.splitlines():
            t = re.match(r"\s*(\d{2}-[A-Z]{3}-\d{4})\s+(.*)$", line)
            if not t: continue
            toks = re.findall(r"\(?[\d,]+\.\d+\)?", t.group(2))
            if len(toks) < 4: continue
            amt, units, price, _bal = (_num(x) for x in toks[-4:])
            if abs(units) < 1e-9: continue
            d = _date(t.group(1).title()); desc = re.sub(r"\(?[\d,]+\.\d+\)?", "", t.group(2)).strip()
            k = kind_of(desc, units)
            if units > 0: lots.append(dict(date=d, units=units, cost=abs(amt) if k not in ("bonus", "segregation") else 0.0, kind=k))
            else:
                left = -units; gain = 0.0; cost_out = 0.0
                for l in lots:
                    if left <= 1e-9: break
                    take = min(l["units"], left)
                    if l["cost"] is not None:
                        c = l["cost"] * take / l["units"]
                        if l["date"] and l["date"] <= GRANDFATHER:   # grandfathering: cost = max(actual, min(FMV 31-Jan-2018, sale price))
                            c = max(c, min(take * gf_nav(isin), take * price)) if gf_nav(isin) else c
                        cost_out += c; l["cost"] -= l["cost"] * take / l["units"]
                    else: cost_out = None
                    l["units"] -= take; left -= take
                lots = [l for l in lots if l["units"] > 1e-9]
                realised.append(dict(date=str(d), amount=round(abs(amt)), gain=None if cost_out is None else round(abs(amt) - cost_out)))
        held = sum(l["units"] for l in lots)
        ok = closing is None or abs(held - closing) < 0.002
        if not ok: warnings.append(f"{isin}: units from transactions ({held:.3f}) don't match the closing balance ({closing:.3f}); left out of the plan")
        folios.append(dict(isin=isin, via=via, lots=lots, nav=nav_now, nav_date=nav_date, closing=closing, reconciled=ok, realised=realised))
    return dict(start=start, end=end, folios=folios, warnings=warnings)

_GF = {}
def gf_nav(isin):
    if isin not in _GF:
        r = amfi.by_isin(isin); _GF[isin] = None
        if r:
            try: _GF[isin] = on_or_before(nav(r["code"]), GRANDFATHER)[1]
            except Exception: pass
    return _GF[isin]

def to_holdings(parsed, fy_start=None):
    """Group folios by ISIN into holdings with lots in the engine's format."""
    by = {}
    for i, f in enumerate([f for f in parsed["folios"] if f["closing"] is None or f["closing"] > 1e-6], 1):
        f["id"] = f"F{i}"; by.setdefault(f["isin"], []).append(f)
    holdings, warnings = [], list(parsed["warnings"])
    today = max((f["nav_date"] for fs in by.values() for f in fs if f["nav_date"]), default=parsed["end"])
    fy0 = dt.date(today.year if today.month > 3 else today.year - 1, 4, 1)
    for isin, fs in by.items():
        r = amfi.by_isin(isin)
        if not r: warnings.append(f"{isin}: not in AMFI's current scheme list (merged or closed?); listed, not analysed"); continue
        cat, is_index = analysis_category(r)
        plan = "Regular" if "regular" in (r["plan"] + r["name"]).lower() else "Direct" if "direct" in (r["plan"] + r["name"]).lower() else "Unknown"
        direct = r["code"] if plan == "Direct" else (amfi.twin(r["code"], "Direct") or r["code"])
        all_lots, folios = [], []
        cost_unknown = any(l["cost"] is None for f in fs for l in f["lots"])
        first = min((l["date"] for f in fs for l in f["lots"] if l["date"]), default=None)
        tc = tax_class(r, first); months = 12 if tc == "equity" else 24
        elss = (r.get("category") == "ELSS")
        nav_now = next((f["nav"] for f in fs if f["nav"]), None)
        for f in fs:
            lots = []
            for l in f["lots"]:
                d = l["date"] or parsed["start"]
                v = l["units"] * (nav_now or 0)
                lot = dict(date=str(d), units=l["units"], cost=l["cost"] if l["cost"] is not None else v, value=v, kind=l["kind"],
                           long_term_from=str(add_years(d, months // 12) + dt.timedelta(days=1)), estimated=l["cost"] is None)
                lot["gain"] = lot["value"] - lot["cost"]
                if elss: lot["unlocks"] = str(add_years(d, 3) + dt.timedelta(days=1))
                lots.append(lot)
            folios.append(dict(id=f["id"], via=f["via"], lots=lots)); all_lots += lots
        value = sum(l["value"] for l in all_lots); cost = sum(l["cost"] for l in all_lots)
        flows = [(dt.date.fromisoformat(l["date"]), -l["cost"]) for l in all_lots if not l["estimated"]] + [(today, value)]
        from ..analysis.stats import xirr
        yrs = (today - first).days / 365 if first else 0
        realised = [x for f in fs for x in f["realised"] if x["date"] >= str(fy0)]
        h = dict(key=re.sub(r"\W+", "_", nice_name(r["name"]).lower()) + "_" + plan.lower(), name=nice_name(r["name"]), plan=plan, code=r["code"], direct_code=direct,
                 category=cat, index=is_index, elss=elss, tax_class=tc, nav=nav_now, invested=round(cost), value=round(value), gain=round(value - cost),
                 held_since=str(first) if first else None, years=round(yrs, 1), xirr=xirr(flows) if yrs >= 1 and not cost_unknown else None,
                 cagr=((value / cost) ** (1 / yrs) - 1) if yrs >= 1 and cost > 0 else None, folios=folios, realised_this_fy=realised,
                 cost_unknown=cost_unknown, reconciled=all(f["reconciled"] for f in fs))
        if cost_unknown: warnings.append(f"{h['name']}: units bought before the statement's start date; cost unknown, left out of tax planning. Download a CAS from inception.")
        holdings.append(h)
    return holdings, warnings, today

def detect_sips(holdings, today):
    """A SIP is active when a folio has 3+ purchases in the last ~100 days at a similar amount (within 10%), about a
    month apart, the latest within ~40 days. Platforms label instalments differently ("Systematic", "Purchase-BSE"...)."""
    out = []
    for h in holdings:
        for f in h["folios"]:
            buys = sorted([l for l in f["lots"] if l["kind"] in ("sip", "purchase") and not l["estimated"]], key=lambda l: l["date"])
            recent = [l for l in buys if (today - dt.date.fromisoformat(l["date"])).days <= 100]
            if len(recent) < 3 or (today - dt.date.fromisoformat(recent[-1]["date"])).days > 40: continue
            amt = recent[-1]["cost"]; same = [l for l in recent if abs(l["cost"] - amt) <= 0.10 * amt]
            gaps = [(dt.date.fromisoformat(b["date"]) - dt.date.fromisoformat(a["date"])).days for a, b in zip(same, same[1:])]
            if len(same) >= 3 and all(20 <= g <= 40 for g in gaps):
                out.append(dict(fund=h["name"], plan=h["plan"], amount=int(round(amt / 100.0) * 100), day=dt.date.fromisoformat(same[-1]["date"]).day, via=f["via"]))
    return out

def ingest(cas_txt, out_json, investor=None):
    p = parse(cas_txt)
    holdings, warnings, today = to_holdings(p)
    data = dict(investor=investor or dict(name="Investor", sample=False), as_of=str(today), statement=dict(start=str(p["start"]), end=str(p["end"])),
                holdings=[h for h in holdings if h["reconciled"]], excluded=[h["name"] for h in holdings if not h["reconciled"]],
                sips_active=detect_sips(holdings, today), warnings=warnings)
    os.makedirs(os.path.dirname(out_json), mode=0o700, exist_ok=True)
    with os.fdopen(os.open(out_json, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh: json.dump(data, fh, indent=1, default=str)
    return data
