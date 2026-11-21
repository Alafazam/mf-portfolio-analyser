# Mutual Fund Portfolio Analyser

> **Educational sample, not advice.** Built by an individual investor to review their own portfolio, shared as an example.
> It is **not investment, tax or legal advice**, and the author is **not a SEBI-registered investment adviser**.
> Past returns don't predict future returns; tax rules change. Check with a registered professional before acting.
> You run it on your own data, at your own risk.

A Claude Code plugin that looks at a **whole Indian mutual fund portfolio**, not one fund at a time:

- **Scorecard:** each fund against its SEBI category benchmark over 3 years (return, volatility, beta/alpha, up/down capture, worst fall, rolling consistency), for both its direct and regular plan.
- **Flags and a return-vs-volatility 2×2:** exit candidates, laggards, volatile-but-ahead, steady compounders, duplicate index funds.
- **Whole-market screen:** every open-ended direct-growth fund in your categories (AMFI list), scored 0–100 within its category.
- **Consolidation plan** with a case-for-change score and break-even for every move; the index fund is always an option.
- **Tax calendar on your real purchase lots:** oldest units first, only long-term and unlocked lots, within each year's ₹1.25L room after gains you've already booked; anything beyond four years shown with the tax of doing it now.
- **SIP review:** where each SIP would go by score, with a rebalance option when mid and small caps dominate.
- **Falls and recoveries, peer check, fund detail,** and a single offline **HTML report**.
- **Family money plan** (`/plan-family`): budget by phase, emergency fund, children's goals, home loan and rent-vs-move-in, OPS/UPS/NPS pensions and pay commissions, yearly milestones, and the age the family could stop depending on salary in a base and a stress case.

Website: **[alafazam.com/mf-portfolio-analyser](https://alafazam.com/mf-portfolio-analyser/)**. See it on made-up data: [`samples/sample-report.html`](samples/sample-report.html) (a made-up investor holding real funds; purchases invented, values from real NAVs) and [`samples/sample-family.html`](samples/sample-family.html) (a made-up family).

## Install

```bash
git clone https://github.com/Alafazam/mf-portfolio-analyser
```

In Claude Code, add the folder as a plugin (or copy `skills/mf-portfolio-analyser` into `~/.claude/skills/`), then run `/analyse-mf`.

Requirements: Python 3.10+ (standard library only), `pdftotext` (poppler) for CAS PDFs, and `qpdf` for password-protected PDFs (so the password never appears on a command line). Check with:

```bash
python3 -m mfpa doctor
```

## Run it

Best input: the **MF Central Detailed CAS** from inception ([how to get it](skills/mf-portfolio-analyser/references/cas-howto.md)). Run this in your own terminal so the PDF password prompt stays hidden:

```bash
python3 -m mfpa run --cas ~/Downloads/your-cas.pdf
```

Other inputs (tax figures become estimates, since there are no purchase dates):

```bash
python3 -m mfpa run --csv templates/holdings.csv
```

```bash
python3 -m mfpa run --indmoney holdings.json sips.json
```

Add `--other-ltcg 40000` if you've already booked equity long-term gains this year outside mutual funds (shares, ETFs). The first run downloads NAV histories and takes a few minutes; later runs use a 1-day cache in `~/.mfpa/`.

### Family plan

```bash
python3 -m mfpa plan --init family
```

Fill `~/.mfpa/plans/family/plan.json` (or let `/plan-family` interview you), then:

```bash
python3 -m mfpa plan --file ~/.mfpa/plans/family/plan.json
```

Add `--from-run <run dir>` to take investments from a fund run, and `--share` for a copy with rounded amounts and no children's ages. How it works: [`references/plan.md`](skills/mf-portfolio-analyser/references/plan.md).

## Privacy

- The CAS PDF and its text never leave your computer and are never shown to Claude. The tool extracts what it needs, deletes the raw text, and writes a redacted summary (no name, PAN, address, contact details or folio numbers) to `~/.mfpa/runs/…` with owner-only permissions.
- The PDF password is asked in a hidden prompt (or read from `MFPA_CAS_PASSWORD`), never in chat. It reaches `qpdf` through an owner-only temporary file, never the command line, and is kept out of error messages. Without qpdf the run stops, unless you add `--allow-password-arg` (fine if you're the only user of the computer).
- The raw CAS text is deleted even if a run fails. Every file a run writes is readable only by you.
- Your report makes no network requests when opened (system fonts, no web fonts).
- The report contains fund names, amounts and dates only. Text inside fund names or files is cleaned before it reaches the page.
- The tool never logs in anywhere or places orders. You make every transaction.

## How it decides

- [`skills/mf-portfolio-analyser/references/method.md`](skills/mf-portfolio-analyser/references/method.md): every metric, score, flag and plan rule.
- [`skills/mf-portfolio-analyser/references/tax.md`](skills/mf-portfolio-analyser/references/tax.md): the tax rules used (FY 2026-27) and their limits.
- [`static/`](static): benchmarks, tax rules, scoring weights and the dated market snapshot, each with a version and as-of date.
- [`SPEC.md`](SPEC.md): the design, including one adversarial review round and what was done with each finding.

Data: [mfapi.in](https://www.mfapi.in) NAVs and AMFI's daily scheme list (`NAVAll.txt`), both free and public. Refresh the market snapshot with `python3 -m mfpa refresh-snapshot`.

## Tests

```bash
python3 -m unittest discover -v -s tests
```

Includes a round trip (the sample portfolio written as a synthetic MF Central CAS and parsed back) and the family plan model: money conserved every month, loans against the EMI formula, OPS/UPS/NPS cases, EPF and NPS access ages, rent clubbing, pay-commission arrears, and the stress case never earlier than the base.

## Limits

- v1 reads only the MF Central **Detailed** CAS layout. A fund whose units don't reconcile with the statement is left out of the plan and listed.
- Benchmarks are index-fund NAVs (from 2019); the long run compares with the category median since June 2018 (funds alive today, so slightly flattering).
- Tax classes come from AMFI categories and names; check funds near the 65% equity line against their factsheets.
- The "if it had all been in…" figures are chosen with hindsight and are not evidence.

MIT licence.
