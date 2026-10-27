# Penalty exposure estimate - Acme Wellness, Inc.

*Case* `ACME-US-2026-002`  |  *Jurisdiction* US-CA  |  *Statute data as of* 2026-10-13

## Exposure band

| | Amount |
|---|---|
| Low | 1,457,871,903 USD |
| **Expected** | **1,537,009,515 USD** |
| Maximum (statutory ceiling) | 1,038,329,350,294 USD |

Confidence: **high**

- entity turnover supplied (turnover-linked caps computed)
- 5 charged violation(s) carry a band calibrated on comparable decided matters
- per-violation counts were supplied/read from source text

### How the case total is built

| Contribution | Low | Expected | Max |
|---|---|---|---|
| Cal. Civ. Code 1798.155(b) | 850,000 USD | 1,400,000 USD | 8,500,000,000 USD |
| Tex. Bus. & Com. Code 503.001 | 1,381,250,000 USD | 1,387,500,000 USD | 22,500,000,000 USD |
| RCW 19.373.030 via RCW 19.373.090 | 5,125,000 USD | 8,750,000 USD | 1,575,000,000 USD |
| 45 CFR 164.312 via 45 CFR 160.404 | 21,903 USD | 109,515 USD | 2,190,294 USD |
| 16 CFR Part 312 (COPPA Rule) | 69,125,000 USD | 137,750,000 USD | 2,388,960,000 USD |
| 16 CFR Part 318 (Health Breach Notification Rule) | 1,500,000 USD | 1,500,000 USD | 1,003,363,200,000 USD |

## Per-violation detail

### Cal. Civ. Code 1798.155(b) - CCPA/CPRA - civil penalty in an action by the Attorney General

- Jurisdiction: US-CA
- Per-violation count used: **3400000**
- Statutory ceiling: 8,500,000,000 USD  
  basis: 3,400,000 violation(s) x 2,500 USD per violation
- Aggregation rule: `no_aggregate_cap` (Cal. Civ. Code s. 1798.155(b))
- Band: low 850,000 USD  /  expected 1,400,000 USD  /  max 8,500,000,000 USD
- Calibration (settlement_to_ceiling): settlement-to-ceiling calibration: 7 comparable matter(s) settled for the equivalent of a median 560 and a 25th-percentile 340 violation-equivalents (amount / 2,500 USD per violation); against the 3,400,000 charged here that is 0.0165% / 0.0100% of the arithmetic ceiling
- Comparables used (7): healthline-2023, sephora-2022, doordash-2024, tilting-point-2024, jam-city-2025, disney-2026, general-motors-2026
- Observed awards: median 1,400,000, p90 6,750,000 (min 375,000, max 12,750,000)
- Note: count basis: consumers whose personal information was sold without notice or opt-out (complaint, para 1)

### Tex. Bus. & Com. Code 503.001 - Texas CUBI - capture or use of biometric identifier

- Jurisdiction: US-TX
- Per-violation count used: **900000**
- Statutory ceiling: 22,500,000,000 USD  
  basis: 900,000 violation(s) x 25,000 USD per violation
- Aggregation rule: `no_aggregate_cap` (Tex. Bus. & Com. Code s. 503.001(d))
- Band: low 1,381,250,000 USD  /  expected 1,387,500,000 USD  /  max 22,500,000,000 USD
- Calibration (settlement_to_ceiling): settlement-to-ceiling calibration: 2 comparable matter(s) settled for the equivalent of a median 55,500 and a 25th-percentile 55,250 violation-equivalents (amount / 25,000 USD per violation); against the 900,000 charged here that is 6.1667% / 6.1389% of the arithmetic ceiling
- Comparables used (2): texas-v-meta-2024, texas-v-google-2025
- Observed awards: median 1,387,500,000, p90 1,397,500,000 (min 1,375,000,000, max 1,400,000,000)
- Note: count basis: consumers whose face geometry templates were captured (complaint, para 3)

### RCW 19.373.030 via RCW 19.373.090 - Washington My Health My Data Act - penalties via the Consumer Protection Act

- Jurisdiction: US-WA
- Per-violation count used: **210000**
- Statutory ceiling: 1,575,000,000 USD  
  basis: 210,000 violation(s) x 7,500 USD per violation
- Band: low 5,125,000 USD  /  expected 8,750,000 USD  /  max 1,575,000,000 USD
- Calibration (settlement_to_ceiling): settlement-to-ceiling calibration: 2 comparable matter(s) settled for the equivalent of a median 1,167 and a 25th-percentile 683 violation-equivalents (amount / 7,500 USD per violation); against the 210,000 charged here that is 0.5556% / 0.3254% of the arithmetic ceiling
- Comparables used (2): anthem-2018-hipaa, goodrx-2023-hbnr (widened/partial match)
- Observed awards: median 8,750,000, p90 14,550,000 (min 1,500,000, max 16,000,000)
- Note: count basis: consumers whose health data was sold without valid authorisation (complaint, para 4)

### 45 CFR 164.312 via 45 CFR 160.404 - HIPAA - civil money penalty tiers

- Jurisdiction: US-Federal
- Per-violation count used: **14000**
- Statutory ceiling: 2,190,294 USD  
  basis: tier tier3 (willful neglect, corrected within 30 days): 14,000 violation(s) x 14,602-73,011 USD per violation; capped at annual limit 2,190,294 USD
- Aggregation rule: `annual_identical_violations_cap` (45 CFR 160.404(b)(2)(i)(B))
- Band: low 21,903 USD  /  expected 109,515 USD  /  max 2,190,294 USD
- Calibration (default): documented default ratios (median 0.050, low 0.010) - no usable comparable set for this regime
- Comparables used (1): anthem-2018-hipaa
- Observed awards: median 16,000,000, p90 16,000,000 (min 16,000,000, max 16,000,000)
- Note: count basis: records exposed by the access-control failure, corrected within 30 days (complaint, para 5)

### 16 CFR Part 312 (COPPA Rule) - COPPA Rule - civil penalty per violation

- Jurisdiction: US-Federal
- Per-violation count used: **45000**
- Statutory ceiling: 2,388,960,000 USD  
  basis: 45,000 violation(s) x 53,088 USD per violation
- Aggregation rule: `no_aggregate_cap` (15 U.S.C. 45(m)(1)(A))
- Band: low 69,125,000 USD  /  expected 137,750,000 USD  /  max 2,388,960,000 USD
- Calibration (settlement_to_ceiling): settlement-to-ceiling calibration: 2 comparable matter(s) settled for the equivalent of a median 2,595 and a 25th-percentile 1,302 violation-equivalents (amount / 53,088 USD per violation); against the 45,000 charged here that is 5.7661% / 2.8935% of the arithmetic ceiling
- Comparables used (2): epic-games-2022-coppa, tilting-point-2024
- Observed awards: median 137,750,000, p90 247,550,000 (min 500,000, max 275,000,000)
- Note: count basis: child accounts collected without verifiable parental consent (complaint, para 6)

### 16 CFR Part 318 (Health Breach Notification Rule) - FTC Health Breach Notification Rule - civil penalty per violation per day

- Jurisdiction: US-Federal
- Per-violation count used: **210000**
- Statutory ceiling: 1,003,363,200,000 USD  
  basis: 210,000 violation(s) x 90 day(s) x 53,088 USD per violation per day
- Band: low 1,500,000 USD  /  expected 1,500,000 USD  /  max 1,003,363,200,000 USD
- Calibration (settlement_to_ceiling): settlement-to-ceiling calibration (single comparable - treat as indicative): 1 comparable matter(s) settled for the equivalent of a median 28 and a 25th-percentile 28 violation-equivalents (amount / 53,088 USD per violation); against the 18,900,000 charged here that is 0.0001% / 0.0001% of the arithmetic ceiling
- Comparables used (1): goodrx-2023-hbnr
- Observed awards: median 1,500,000, p90 1,500,000 (min 1,500,000, max 1,500,000)
- Note: count basis: affected consumers, times 90 days during which notification was not made

## Precedent view

- Comparable matters: 12 (anthem-2018-hipaa, disney-2026, doordash-2024, epic-games-2022-coppa, general-motors-2026, goodrx-2023-hbnr, healthline-2023, jam-city-2025, sephora-2022, texas-v-google-2025, texas-v-meta-2024, tilting-point-2024)
- Observed award/ceiling ratios across those matters: n/a
- Observed awards: median 2,150,000, p25 1,350,000, p90 1,265,000,000 (n=12)
- Method: fixed/turnover regimes are calibrated on the observed award-to-ceiling ratio (median -> expected, p25 -> low); per-violation regimes are calibrated on the violation-equivalents the comparable settlements actually bought (amount / per-violation amount, median and p25). Defaults are used, and flagged, where neither is available.

## Severity factors applied

| Factor | Strength | Effect | Authority |
|---|---|---|---|
| remediation | 0.5 | -5.0% | GDPR Art. 83(2)(c) |
| prior_infringements | 1.0 | +25.0% | GDPR Art. 83(2)(e); CPPA enforcement policy on repeat conduct |
| intentional | 1.0 | +25.0% | GDPR Art. 83(2)(b); Cal. Civ. Code s.1798.155 (intentional violations) |
| clamp | None | 1.484 -> 1.000 | multiplier clamped: the statutory ceiling cannot be exceeded and the floor is 5% of the ceiling |
| **combined** | | **x1.0** | |

## Method and limits

- *Maximum* is the statutory ceiling for the charge as pleaded, after statutory aggregation rules; it is a legal ceiling, not a forecast.
- *Expected* and *low* apply the case's severity-factor multiplier to the ceiling and a ratio calibrated on comparable decided matters (median / 25th percentile of award-to-ceiling ratios).
- Precedents are matched on statute, jurisdiction and sector; partial matches are flagged.
- Prototype triage output, not legal advice. Statutory amounts and precedent records are sourced (see data/*.json 'sources') but carry an 'as_of' date; verify before relying on them. The expected/low values are calibrated heuristics, not predictions of any particular regulator's decision.
