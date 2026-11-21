# Tax rules used (as of FY 2026-27)

Source: Income-tax Act 1961 (s.111A, 112A, 50AA as amended by the Finance (No.2) Act 2024) and the Income-tax Act 2025 in force from 1 Apr 2026 (section numbers changed; rates assumed unchanged — verify). Later years in the calendar assume today's rules. Values in `static/tax_rules.json`.

| Item | Rule used |
|---|---|
| Equity-oriented funds (≥ 65% domestic equity, incl. ELSS, aggressive hybrid, equity index funds) | Long-term after **more than 12 months**: 12.5% above **₹1.25L** a year (shared with listed shares and equity ETFs). Short-term: 20%. |
| Other funds (gold/silver/international FoFs, most multi-asset and balanced-advantage funds) | Long-term after **more than 24 months**: 12.5%, **no ₹1.25L exemption**. Short-term: slab rate. |
| Specified funds, Sec 50AA (> 65% debt or money market; debt-type units bought on or after 1 Apr 2023) | Slab rate whatever the holding period. |
| Cess | 4% on the tax. Surcharge on these gains is capped at 15%. The 87A rebate does not apply to them. |
| Holding period | Counted from allotment; the first long-term day is the day **after** the anniversary. 29 Feb anniversaries fall on 28 Feb. |
| ELSS | Each instalment locked for 3 years from its own allotment. |
| Grandfathering | Equity units bought on or before 31 Jan 2018: cost = higher of actual cost and the lower of (NAV on 31 Jan 2018, sale value). |
| FIFO | Redemptions use the oldest units of that folio first. |
| Losses | Short-term losses offset any capital gain; long-term losses only long-term gains. Carry forward 8 years if the return is filed on time. |
| Costs | Exit load: default 1% within 365 days (check the scheme document; index funds and ELSS differ). STT 0.001% on equity redemptions. Stamp duty 0.005% on purchases. |
| Switching | A switch (including regular → direct of the same fund) is a redemption plus a purchase: taxable, may carry exit load, and starts a new holding period (and a new 3-year lock-in for ELSS). |

Limits: the classifier uses AMFI categories and names to decide the tax class; check funds near the 65% line (multi-asset, balanced advantage, equity savings) against the scheme's factsheet. This is not tax advice.
