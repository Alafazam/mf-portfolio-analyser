"""python3 -m mfpa <command>

  doctor                         check Python and pdftotext; print install commands
  run --cas FILE.pdf             analyse a portfolio from an MF Central Detailed CAS (asks for the PDF password, hidden)
  run --csv FILE.csv             ... from the CSV template (estimates)
  run --indmoney H.json [S.json] ... from saved INDmoney MCP output (estimates)
  sample                         rebuild the synthetic sample report
  refresh-snapshot               rebuild static/market_snapshot.json from live data (maintainers; slow)

Personal files go to ~/.mfpa/runs/<timestamp>/ (0700). Progress is written to progress.txt there.
Educational screen only; not investment, tax or legal advice."""
import argparse, os, sys, json, shutil, getpass, platform, datetime as dt, traceback
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def doctor():
    ok = True
    print(f"Python {platform.python_version()}: " + ("OK" if sys.version_info >= (3, 10) else "needs 3.10 or newer")); ok &= sys.version_info >= (3, 10)
    if shutil.which("pdftotext"): print("pdftotext: OK")
    else:
        ok = False; print("pdftotext: missing (needed for CAS PDFs). Install:")
        print("  Linux (Debian/Ubuntu): sudo apt install -y poppler-utils\n  macOS: brew install poppler\n  Windows: winget install oschwartz10612.Poppler  (or use WSL)")
    print("qpdf: OK (password-protected PDFs)" if shutil.which("qpdf") else
          "qpdf: missing (only needed for password-protected PDFs). Install: sudo apt install -y qpdf  /  brew install qpdf")
    try:
        from .data.amfi import rows; n = len(rows()); print(f"AMFI scheme list: OK ({n} schemes)")
    except Exception as e: ok = False; print(f"AMFI scheme list: can't download ({e})")
    print("All good." if ok else "Fix the items above, then run again.")
    return ok

def run_dir():
    d = os.path.expanduser(f"~/.mfpa/runs/{dt.datetime.now():%Y%m%d-%H%M%S}"); os.makedirs(d, mode=0o700, exist_ok=True); return d

def progress(d, msg):
    open(os.path.join(d, "progress.txt"), "a").write(f"{dt.datetime.now():%H:%M:%S} {msg}\n"); print(msg, flush=True)

def run(args):
    from .engine import Engine
    from .report.build import build
    os.umask(0o077)   # every file and folder this run creates is owner-only, wherever --out points
    d = args.out or run_dir(); os.makedirs(d, mode=0o700, exist_ok=True)
    txt = os.path.join(d, "cas.txt")
    try:
        if args.cas:
            from .ingest.cas import pdf_to_text, ingest
            pw = os.environ.get("MFPA_CAS_PASSWORD")
            if pw is None and not args.no_password and sys.stdin.isatty(): pw = getpass.getpass("CAS PDF password (leave empty if none): ") or None
            progress(d, "Reading the CAS PDF"); pdf_to_text(args.cas, txt, pw, args.allow_password_arg)
            progress(d, "Building purchase lots and checking units"); data = ingest(txt, os.path.join(d, "holdings_in.json"))
        elif args.csv:
            from .ingest.simple import from_csv
            progress(d, "Reading the CSV"); data = from_csv(args.csv)
        elif args.indmoney:
            from .ingest.simple import from_indmoney
            progress(d, "Reading INDmoney data"); data = from_indmoney(args.indmoney[0], args.indmoney[1] if len(args.indmoney) > 1 else None)
        else: raise SystemExit("Give --cas, --csv or --indmoney")
        json.dump(data, open(os.path.join(d, "holdings_in.json"), "w"), indent=1, default=str)
        for w in data.get("warnings", []): progress(d, "Note: " + w)
        if args.other_ltcg: data["other_ltcg_this_fy"] = args.other_ltcg
        progress(d, "Fetching NAVs and scoring funds (first run takes a few minutes)")
        e = Engine(data, os.path.join(d, "data")).run()
        out = build(os.path.join(d, "data"), os.path.join(d, "report.html"), web_fonts=False)
        progress(d, f"Done: {out}")
        print(json.dumps(dict(report=out, data=os.path.join(d, "data"), warnings=data.get("warnings", [])), indent=1))
    except Exception as e:
        progress(d, f"Failed: {type(e).__name__}: {e}"); raise
    finally:
        if os.path.exists(txt): os.remove(txt)   # raw CAS text holds personal details: always delete it, success or failure

def sample():
    sys.path.insert(0, HERE)
    import runpy
    runpy.run_path(os.path.join(HERE, "samples", "make_sample.py"), run_name="__main__")
    from .engine import Engine
    from .report.build import build
    data = json.load(open(os.path.join(HERE, "samples", "sample_holdings.json")))
    Engine(data, os.path.join(HERE, "samples", "out")).run()
    print(build(os.path.join(HERE, "samples", "out"), os.path.join(HERE, "samples", "sample-report.html")))

def main():
    ap = argparse.ArgumentParser(prog="python3 -m mfpa", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    r = sub.add_parser("run")
    r.add_argument("--cas"); r.add_argument("--csv"); r.add_argument("--indmoney", nargs="+")
    r.add_argument("--out"); r.add_argument("--no-password", action="store_true")
    r.add_argument("--allow-password-arg", action="store_true", help="without qpdf, pass the PDF password to pdftotext on the command line (visible to other users of this computer)")
    r.add_argument("--other-ltcg", type=float, default=0, help="equity long-term gains already booked this FY outside mutual funds (shares, ETFs)")
    sub.add_parser("sample"); sub.add_parser("refresh-snapshot")
    a = ap.parse_args()
    if a.cmd == "doctor": sys.exit(0 if doctor() else 1)
    if a.cmd == "run": run(a)
    if a.cmd == "sample": sample()
    if a.cmd == "refresh-snapshot":
        from .screen import refresh; refresh()
