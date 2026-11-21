"""Block commits that contain personal data. Generic checks are public; optional private patterns
(one per line, exact strings) are read from ~/.mfpa/leakcheck/private_patterns.txt, which never enters the repo.
Usage (git pre-commit): python3 scripts/leakcheck.py  -> exit 1 and list the files on a hit."""
import os, re, subprocess, sys
GENERIC = {"PAN": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
           "phone": re.compile(r"(?<![\d.])[6-9]\d{9}(?![\d.])")}
ALLOW_EMAIL = {"noreply@anthropic.com"}
def staged():
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"], capture_output=True, text=True).stdout.split()
    return [f for f in out if os.path.isfile(f)]
def main(files=None):
    files = files or staged(); priv = []
    p = os.path.expanduser("~/.mfpa/leakcheck/private_patterns.txt")
    if os.path.exists(p): priv = [l.strip() for l in open(p) if l.strip()]
    hits = []
    for f in files:
        try: txt = open(f, encoding="utf-8", errors="ignore").read()
        except Exception: continue
        for name, rx in GENERIC.items():
            for m in rx.finditer(txt):
                if name == "email" and m.group(0) in ALLOW_EMAIL: continue
                hits.append(f"{f}: looks like a {name}")
                break
        if any(s in txt for s in priv): hits.append(f"{f}: contains a private value from ~/.mfpa/leakcheck")
    for h in sorted(set(hits)): print("LEAK CHECK:", h)
    return 1 if hits else 0
if __name__ == "__main__": sys.exit(main(sys.argv[1:] or None))
