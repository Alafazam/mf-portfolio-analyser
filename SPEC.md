# Mutual Fund Portfolio Analyser — Spec v2

A Claude Code plugin (skill + slash command + standard-library Python + public reference data) that lets an Indian mutual fund investor analyse a whole portfolio from their CAS statement and get a plain-language screen of their funds, a tax-aware sequence of moves, and an HTML report.

v1 drafted 22 Nov 2026; **v2 after one adversarial review round** (section 15 lists every finding and what was done with it). **v0.1 built 22 Nov 2026:** CAS/CSV/INDmoney ingest, engine, report, CLI, skill, tests. Not yet: other CAS layouts, per-scheme exit-load table, ISIN history map, real redacted CAS fixtures.

---

## 1. Why this exists

Existing tools look at **one fund** (the `mf-analyser` skill) or at **stock trading** (`claude-trading-skills-india`). Nothing looks at a **whole mutual fund portfolio**: duplicates, regular vs direct cost, tax-aware selling over several years, and SIP placement. A personal prototype (`fund-analysis`, private) proved the analysis works for one investor; this project rebuilds it as **general rules**, not hand-written choices.

Name: **`mf-portfolio-analyser`**.

## 2. Users and framing

- Indian retail investors with 5–40 funds, a mix of regular/direct plans, SIPs across apps. Not finance professionals.
- **The output is a rules-based screen, not advice.** Wording is always "by these rules, X ranks below Y" and "candidate moves", never "sell X now". The user picks or confirms every replacement from a short list that always includes a low-cost index fund. No affiliate links, no monetisation.
- **Disclaimers** (README top, SKILL.md, the report's first screen and footer, every run's chat summary): this is a personal project built by an individual investor for their own portfolio and shared as an **educational sample**; it is **not investment, tax or legal advice**; the author is **not a SEBI-registered investment adviser**; past returns don't predict future returns; tax rules change; check with a registered adviser or tax professional before acting. Users run it on their own data at their own risk.
- No formal legal opinion is planned before release (author's decision, 22 Nov 2026); the wording rules and disclaimers above carry that weight.

## 3. Setup questions (asked first, 4 questions)

1. Investment horizon (under 3 years / 3–7 / 7+).
2. Tax regime: old (claims 80C) or new.
3. Equity long-term gains already booked this financial year **outside** mutual funds (shares, ETFs). Default ₹0, user can enter an amount.
4. Do you want fewer funds (consolidate), lower fees (regular → direct), or both?

## 4. Inputs

| Input | v1 support | Gives |
|---|---|---|
| **MF Central Detailed CAS PDF, period "since inception"** | **Primary, the only CAS layout supported in v1** | All folios, every transaction with type, date, units, NAV; current value; ISIN |
| INDmoney MCP | Optional add-on | Live SIP list (incl. step-ups), sector and market-cap split for the look-through |
| CSV (template) | Fallback | Holdings only. Tax calendar runs at fund level and every tax figure is marked "estimate, no purchase dates" |

Rules:
- **Reconciliation gate.** For every folio, units rebuilt from transactions must equal the CAS closing balance. Any mismatch → that fund is excluded from the plan and shown as "couldn't reconcile", never planned on.
- **Opening balances** (statement not from inception) → warn and ask for a since-inception CAS; those units are marked "cost unknown" and excluded from tax planning.
- Other layouts (CAMS/KFintech emailed CAS, NSDL/CDSL demat CAS) are v2, added only with real redacted test files.

## 5. Privacy and security (non-negotiable)

- **Claude never reads the raw CAS.** The skill forbids `Read` on the PDF or extracted text. Ingest runs as a script that strips name, PAN, address, email, phone and folio numbers before writing anything; only the redacted JSON is read by Claude. Folios become `F1`, `F2`.
- The PDF password (if any) is entered through a hidden terminal prompt or an environment variable, never in chat.
- Personal working files live in `~/.mfpa/<run-id>/` with `0700` permissions, outside any repo.
- **Report hardening:** embedded JSON escapes `<`, `>` and `&`; all text inserted into the page goes through an escape helper (no raw `innerHTML` with fund names). Text from CAS, CSV or INDmoney is data, never instructions.
- Publishing the report as a Claude artifact is offered, never automatic, and only after the user sees it locally.
- The plugin never logs in anywhere, never places orders, never handles credentials.

## 6. Fund identification and data

- **ISIN → AMFI scheme code** using AMFI `NAVAll.txt`; direct/regular twins matched on AMC + AMFI scheme code family + normalised base name, not name search.
- A shipped **ISIN history map** (mergers, renames, segregated portfolios) with an as-of date. Unmapped ISINs are listed in the report, never silently dropped.
- **Tax treatment per ISIN** (static, as-of dated): equity-oriented (≥65% domestic equity), specified fund under Sec 50AA (>65% debt/money market, or FoF ≥65% in such funds), or other (gold/silver/international FoFs, many multi-asset/balanced funds). Unknown → ask the user / mark "check".
- **NAVs** from mfapi.in with a 1-day cache TTL, retry with backoff, a descriptive User-Agent. The analysis end date comes from the **benchmark series only**; dead or merged schemes are excluded explicitly with a note. Liveness check: NAV date within 7 days of the latest, never a hard-coded year.
- **Market screen:** live fetch only for the user's own funds and the **categories they hold** (not every category), plus a **dated snapshot** published as a release asset, used when mfapi.in fails and shown with its date in the report.

## 7. Analysis (rules, not hand-picked)

Methods carried over from the prototype; **the plan, SIP and replacement logic is rewritten as rules** (the prototype hard-coded them for one portfolio).

| Step | Rule |
|---|---|
| **Benchmarks** | SEBI category benchmarks via index-fund proxies: Large cap → **Nifty 100** (not Nifty 50), Mid → Midcap 150, Small → Smallcap 250, Large & Mid → LargeMidcap 250, Flexi/Multi/Focused/Value/ELSS → Nifty 500, hybrids → stated blends. Sector/thematic, international, debt: no score, listed as "outside this screen". |
| **Fund stats (3Y)** | CAGR, excess vs benchmark, volatility ratio, beta, alpha, R², tracking error, up/down capture, max drawdown, rolling 3Y beat %. |
| **Long run** | vs category median **from Jun 2018** (post SEBI recategorisation), not 2013. Counts as a **tie-breaker** (25% of the score), not half. Survivorship bias stated. |
| **Scores** | Rank within category only when the category has ≥ 8 scored funds. Funds under 3 years: shown, not ranked. |
| **Flags** | "Lagging" needs **both** a lag worse than 1%/yr vs benchmark **and** rolling beat rate under 40%. Index funds are never "lagging" for tracking cost. |
| **Duplicates** | Correlation ≥ 0.97 counts only within the **same category or same index**. |
| **Replacement list** | Per flagged fund: the category's **cheapest index fund (always first)** plus the top 2 full-record active funds. The user chooses. |
| **Break-even** | For every move: tax + exit load + stamp duty ÷ expected edge per year = **years to earn back**. A move is "Clear" only if the break-even is under 2 years and the replacement wins most tests; otherwise "Lean" or "Close call". Close calls are not planned. |
| **Portfolio shape** | Detects tilts (e.g. mid caps > 2× their Nifty 500 share, too many funds, many regular plans). SIP "rebalance" option appears only when a tilt is detected; the rule is generic, not "mid caps". |
| **Look-through** | Only with INDmoney sector data; otherwise the section says "not available". |
| **Falls and recoveries** | Kept, moved to the appendix: episodes defined on each category's own index, so small caps are judged on small-cap falls. |
| **What-if replay** | Kept (the user asked for it) but labelled **"chosen with hindsight, not evidence"**, and shown next to the same replay into the category's index fund. Never used in any score. |

## 8. Tax engine

- Rules in `static/tax_rules.json` per financial year, citing **both** the Income-tax Act 1961 sections and the Income-tax Act 2025 sections in force from 1 Apr 2026 (verify the 2025 Act's numbering and any Budget 2026 changes before release). Later years in the calendar are marked "assumes today's rules".
- **Holding periods:** long-term only when held **more than** 12 months (equity) or 24 months (other); dates computed as anniversary **+1 day**, with a safe add-months helper (29 Feb). Every calendar date gets a 2–3 working-day buffer and the 3 pm cut-off note.
- **Room this year** = ₹1.25L − LTCG already realised in this FY (from the CAS) − the user's other equity LTCG (setup question 3) − a 5% buffer for NAV movement.
- **Partial redemptions follow FIFO lots per folio.** The planner walks lots oldest-first and outputs each switch as **units and rupees per folio**, with its exact realised gain. No pro-rata averaging.
- **Grandfathering** for equity units bought before 31 Jan 2018: cost = higher of actual cost and lower of (31-Jan-2018 NAV, sale value), using mfapi NAVs.
- **Lots:** transaction types tagged (purchase, SIP, switch-in, merger, dividend reinvestment, bonus, segregation). Mergers carry the original cost and date. ELSS lock-in per instalment.
- **Losses:** classified short- or long-term by holding period; long-term losses offset only long-term gains; carry-forward needs an ITR filed on time (stated).
- **Costs:** per-scheme exit load table (static, as-of dated; default "check scheme document" when unknown), STT, stamp duty. Surcharge cap and no 87A rebate on these gains noted.
- **50AA:** debt-type units bought on or after 1 Apr 2023 taxed at slab rate whatever the holding period.

## 9. Outputs

1. **Page 1 of the report: "What this screen suggests this month"** — at most 5 candidate moves in plain words, each with tax, cost, break-even years and a confirm-or-skip choice; tax room left this year; SIP changes.
2. **Appendix** — the analytic sections from the prototype (2×2, flags, screen, replacements, tax calendar per FY, SIPs, falls and recoveries, look-through, scorecard, fund detail, method and limits). The 2×2 drops the direct/regular/both toggle (direct only, regular shown as a note).
3. `~/.mfpa/<run-id>/*.json` — redacted intermediate results for follow-up questions.
4. Every static file used is stamped in "Method and limits" with its version and as-of date.

## 10. Runtime

- `python3 -m mfpa doctor` — checks Python ≥ 3.10 and `pdftotext`; prints the one-line install for Linux, macOS (brew) and Windows.
- `python3 -m mfpa run …` runs **in the background**, writes progress to a file the skill polls, and is **resumable step by step** (the first run can take several minutes).
- `python3 -m mfpa refresh-snapshot` — rebuilds the market snapshot (maintainers).

## 11. Packaging

```
mf-portfolio-analyser/
  .claude-plugin/plugin.json
  skills/mf-portfolio-analyser/SKILL.md      # workflow, privacy rules, wording rules, follow-ups
  skills/mf-portfolio-analyser/references/   # method.md (decision tables), tax.md, cas-howto.md
  commands/analyse-mf.md                     # /analyse-mf
  mfpa/  ingest/ data/ analysis/ tax/ report/ cli.py   # stdlib only
  static/  benchmarks.json categories.json tax_rules.json scoring.json
           isin_history.json tax_treatment.json exit_loads.json   # each {version, as_of, source}
  samples/ synthetic_cas.txt sample-report.html
  tests/   unit (stats, FIFO, dates, grandfathering, 50AA, room) + layout fixtures
  README.md
```

## 12. Sample (for the README and demo)

**Built synthetically from scratch**, not derived from any real portfolio: a made-up investor holding well-known funds across categories, with typical patterns (a few regular plans, two duplicate index funds, an ELSS ladder, a loss-making international FoF, SIPs on two apps). Amounts and dates are generated.

**Leak check, local only.** A pre-commit hook blocks any commit that contains values from the author's private data (amounts, ISIN+amount pairs, folio numbers, PAN, contact details). The hook and its pattern list live **outside the repo** (`~/.mfpa/leakcheck/`, installed with `git config core.hooksPath`), so the private values it checks for are never committed. The public repo only carries a generic check for PAN-shaped strings, 10+ digit folio-like numbers and email/phone patterns.

## 13. Tests

- Unit tests: holding-period edges (anniversary day, 29 Feb), FIFO partial redemption across lots, grandfathering, 50AA dating, room calculation, break-even.
- Parser: the synthetic CAS **plus at least 2 real, fully redacted MF Central CAS files** (from volunteers) before release; reconciliation must pass on all.
- End-to-end: the sample report is regenerated in CI and diffed.

## 14. Out of scope for v1

Stocks, NPS, EPF, US stocks; debt fund selection; placing orders; other CAS layouts; style-based scoring presets; non-English reports.

## 15. Adversarial review, round 1 — dispositions

| # | Finding (severity) | Decision |
|---|---|---|
| 1 | Plan/SIP/replacement logic is hand-written for one portfolio (Critical) | **Accepted.** Rewritten as rules (§7) with decision tables in `method.md`. |
| 2 | Partial switches use pro-rata gain; real redemptions are FIFO (Critical) | **Accepted.** §8 FIFO walk per folio, output in units. |
| 3 | ₹1.25L room ignores gains already booked (Critical) | **Accepted.** §3 Q3 + realised gains from CAS + buffer. |
| 4 | Tax class by category, not by actual equity share; 50AA (Critical) | **Accepted.** §6 per-ISIN tax treatment, §8 50AA. |
| 5 | No grandfathering; opening balances have no cost (High) | **Accepted.** Since-inception CAS required; grandfathering in §8. |
| 6 | Anniversary-day and 29 Feb bugs; cut-off (High) | **Accepted.** +1 day, safe date maths, buffers. |
| 7 | Case-for-change ignores switching cost (High) | **Accepted.** Break-even years added; required for "Clear". |
| 8 | Flags churn large-cap/index holders; Nifty 50 benchmark (High) | **Accepted.** Nifty 100, stricter lag rule, index fund first in every list. |
| 9 | What-if has hindsight bias (High) | **Adjusted.** Kept (you asked for it), labelled, shown next to the index-fund replay, never scored. |
| 10 | FIFO across folios; mergers reset cost (High) | **Accepted.** Per-folio FIFO with folio-level instructions; transaction types and merger carry-over. |
| 11 | NAV cache never refreshes; dead series move end date; hard-coded year (High) | **Accepted.** §6. |
| 12 | Script injection in the report (High) | **Accepted.** §5 escaping. |
| 13 | Raw CAS reaches the model; password handling (High) | **Accepted.** §5 redaction at ingest, hidden password prompt, `~/.mfpa`. |
| 14 | Output reads as personal advice (High) | **Adjusted.** §2 wording rules, user picks replacements, strong educational / not-advice / not-SEBI-registered disclaimers everywhere. No formal legal opinion (author's call). |
| 15 | CAS parser fitted to one layout (High) | **Accepted.** One layout in v1, reconciliation gate, real redacted fixtures. |
| 16 | Survivorship and pre-2018 categories in the long run (Medium) | **Accepted.** Long run from Jun 2018, tie-breaker weight. |
| 17 | Thresholds overfit to a mid-cap portfolio (Medium) | **Accepted.** Same-category duplicates, ≥ 8 funds to rank, shape detection, category-own falls. |
| 18 | Loss types, exit loads, surcharge, STT (Medium) | **Accepted.** §8. |
| 19 | Income-tax Act 2025 from 1 Apr 2026 (Medium) | **Accepted.** Cite both Acts; verify before release. |
| 20 | Load on mfapi.in (Medium) | **Adjusted.** Live stays default as you chose, but only for held categories, cached, with backoff; snapshot fallback. |
| 21 | ISIN mapping edge cases (Medium) | **Accepted.** ISIN history map, unmapped shown. |
| 22 | First run exceeds tool time limits; OS installs (Medium) | **Accepted.** Background runner, `doctor`. |
| 23 | Non-expert UX; no goals/regime questions (Medium) | **Accepted.** §3 questions, action page first. |
| 24 | Sample derived from a real portfolio is a fingerprint (Low) | **Accepted** (confirmed 22 Nov). Fully synthetic sample; private-value leak check runs as a local, uncommitted pre-commit hook (§12). |
| 25 | No versioning of static data (Low) | **Accepted.** `{version, as_of, source}` everywhere. |

Critic's "cut from v1" list — partly taken: cut summary-CAS input, the direct/regular/both toggle, the hard-coded mid-cap option B (replaced by generic shape detection), pre-2018 long run, and the 400-fund default fetch. **Kept:** INDmoney (your decision; optional), falls and recoveries (appendix), what-if (labelled), case-for-change (now with break-even).
