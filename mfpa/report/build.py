"""Fill the report template with the engine's JSON files -> one self-contained HTML page.
Security: every string from the data is stripped of < > " ' ` before it reaches the page (fund names, notes, anything
that came from a CAS, CSV or INDmoney), and the embedded JSON escapes < > & so it can't close the <script> tag."""
import json, os, re
HERE = os.path.dirname(os.path.abspath(__file__))

def clean(x):
    if isinstance(x, str): return re.sub(r"[<>\"'`]", "", x)
    if isinstance(x, list): return [clean(v) for v in x]
    if isinstance(x, tuple): return [clean(v) for v in x]
    if isinstance(x, dict): return {k: clean(v) for k, v in x.items()}
    if isinstance(x, float): return round(x, 5)
    return x

def build(data_dir, out_html):
    J = lambda f: json.load(open(os.path.join(data_dir, f))) if os.path.exists(os.path.join(data_dir, f)) else None
    r = J("results.json")
    D = dict(end=r["end"], n50_10y=None, portfolio=r["portfolio"], funds=r["funds"], look=J("lookthrough.json"), universe=None,
             market=J("market.json"), regime=J("regime.json"), peers=J("peers.json"), plan=J("plan.json"), whatif=J("whatif.json"),
             holdings=J("holdings.json"), conviction=None)
    blob = json.dumps(clean(D), separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    html = open(os.path.join(HERE, "template.html"), encoding="utf-8").read().replace("__DATA__", blob)
    open(out_html, "w", encoding="utf-8").write(html)
    return out_html
