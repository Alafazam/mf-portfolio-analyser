# Method: metrics, flags and plan rules

All numbers are computed from public NAVs (mfapi.in) and AMFI's scheme list. Weights and thresholds live in `static/scoring.json`; benchmarks in `static/benchmarks.json`.

## Per-fund tests (direct plan, weekly returns, last 3 years)
| Metric | Meaning |
|---|---|
| CAGR, excess | Annual return; excess = fund − category benchmark |
| Volatility ratio | Fund volatility ÷ benchmark volatility |
| Beta, alpha, R², tracking error | Regression of weekly fund returns on the benchmark |
| Up / down capture | Average fund return in benchmark-up (-down) weeks ÷ the benchmark's |
| Worst fall | Maximum drawdown vs the benchmark's |
| Rolling 3Y beat % | Share of rolling 3-year windows in which the fund beat the benchmark |
| Falls | Fund vs benchmark across all weeks of Nifty 500 falls of 10%+ |

Benchmarks (index-fund NAV proxies): Large cap → Nifty 100; Mid → Midcap 150; Small → Smallcap 250; Large & mid → 50/50 Nifty 100 + Midcap 150; Flexi, Focused, Value, Contra, ELSS → Nifty 500; Multi cap → 50/25/25; Aggressive hybrid → 65/35 Nifty 50 + bonds; Multi asset → 65/20/15 Nifty 500 + bonds + gold. Sector/thematic, international, debt and liquid funds are listed, not scored.

## Market screen score (0–100, within category)
- **3Y score** = 35% excess + 25% rolling beat + 20% downside capture + 10% worst fall vs benchmark + 10% falls.
- **Long-run score** (funds with 5+ years since Jun 2018) vs the weekly **category median**: 35% lead/yr + 25% rolling 3Y wins + 15% rolling 5Y wins + 15% downside capture + 10% worst fall. Median of funds alive today (survivorship flatters it slightly).
- **Overall** = 75% 3Y + 25% long run (3Y alone without a long record). "Short record" = under 100 rolling windows.

## Flags (direct plan)
| Flag | Rule |
|---|---|
| Index fund | Tracks an index; judged on cost and tracking |
| Duplicate | Same index as another held index fund (keep the larger) |
| Exit candidate | Behind the benchmark and (vol ratio > 1.05, or down capture > 1, or worst fall 3+ points deeper) |
| Lagging | More than 1%/yr behind the benchmark **and** ahead in under 40% of rolling 3Y windows |
| Volatile, but ahead | Ahead, but vol ratio > 1.10, down capture > 1.05, or worst fall 3+ points deeper |
| Steady compounder | Ahead, beat ≥ 60%, down capture < 0.95, vol ratio ≤ 1.05 |
| Neither | Everything else |

## Plan
1. **Candidate moves:** duplicates → merge into the kept fund; exit and lagging funds → the top full-record active fund in the category that beats its benchmark and takes ≤ 100% of falls, with the category's index fund as the alternative; regular plans of kept funds → the same fund's direct plan.
2. **Case for change** (replacement vs current, 7 tests: 3Y excess, 3Y consistency, down capture, worst fall, long-run lead, long-run 3Y and 5Y wins; ties within half a point ignored) plus **break-even** = (exit load on short-term units + STT + stamp duty) ÷ yearly edge. Clear ≥ 80 and break-even under 2 years; Lean 55–79; Close call below 55 (not planned).
3. **Calendar:** one queue — duplicates, exits (strongest case first), switches (lowest gain share first). Each financial year: room = ₹1.25L × 95% − gains already booked this year (statement + user's other equity LTCG) + optional loss booking. Lots oldest first (FIFO); a lot is used only once long-term and out of ELSS lock-in, on that date if inside the year. Partial lots are split by units. Four years at most; anything left is shown with tax-if-done-now and what waiting costs per year (regular-plan commission, or the gap to the replacement), with the payback in years.
4. **Cost unknown** (units older than the statement start): held, not planned. **Didn't reconcile:** excluded and listed.

## SIPs
A SIP moves only to a full-record fund ≥ 5 points higher in the same category (each target used once); a regular-plan SIP with no better fund moves to the same fund's direct plan. Option B: if mid + small caps exceed half of SIP money, the largest of those SIPs moves to the top full-record flexi cap. Higher-scored funds passed over are listed with the reason.

## What-if
Each purchase still held is replayed, on its date and amount, into the suggested fund's direct plan and valued at the latest NAV. It is chosen with hindsight: a description of the past, not evidence for the future, and not used in any score.
