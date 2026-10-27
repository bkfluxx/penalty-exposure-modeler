# Penalty exposure estimate - Acme Messaging Ireland Ltd

*Case* `ACME-EU-2026-001`  |  *Jurisdiction* EU/EEA  |  *Statute data as of* 2026-10-13

## Exposure band

| | Amount |
|---|---|
| Low | 843,551 EUR |
| **Expected** | **1,042,148 EUR** |
| Maximum (statutory ceiling) | 20,000,000 EUR |

Confidence: **medium**

- entity turnover supplied (turnover-linked caps computed)
- 2 charged violation(s) carry a band calibrated on comparable decided matters
- per-violation counts were supplied/read from source text

**Aggregation rules applied**

- EU GDPR: 2 charges are linked processing operations; Art. 83(3) caps the combined fine at the amount for the gravest infringement, so the combined contribution is the lower of the summed columns and the gravest ceiling (applied to EU/EEA)

## Per-violation detail

### Art. 46(1) GDPR - GDPR Art. 83(5) - higher-tier administrative fine

- Jurisdiction: EU/EEA
- Per-violation count used: **2400000**
- Statutory ceiling: 20,000,000 EUR  
  basis: statutory cap 20,000,000 EUR (turnover-linked cap 19,200,000 was lower)
- Aggregation rule: `linked_processing_single_ceiling` (GDPR Art. 83(3))
- Band: low 843,551 EUR  /  expected 1,042,148 EUR  /  max 20,000,000 EUR
- Calibration (award_ceiling_ratio): award/ceiling ratios observed in 4 comparable matters (median 0.090, p25 0.072)
- Comparables used (7): whatsapp-2021-transparency, instagram-2022-children, meta-ireland-2023-transfers, tiktok-2023-children, tiktok-2025-transfers, amazon-2021-luxembourg, google-ireland-2026-location
- Observed award/ceiling ratios: p25 0.072 / median 0.090 / p90 0.222 (n=4)
- Observed awards: median 405,000,000, p90 927,600,000 (min 225,000,000, max 1,200,000,000)
- Note: count basis: users whose personal data was transferred to the US (complaint, para 2)
- Note: size mismatch: the comparable matters faced ceilings of the order of 4,185,000,000 EUR (median) against 20,000,000 here; an award/ceiling ratio does not transfer cleanly across entity size

### Art. 32 GDPR - GDPR Art. 83(4) - lower-tier administrative fine

- Jurisdiction: EU/EEA
- Per-violation count used: **1**
- Statutory ceiling: 10,000,000 EUR  
  basis: statutory cap 10,000,000 EUR (turnover-linked cap 9,600,000 was lower)
- Aggregation rule: `linked_processing_single_ceiling` (GDPR Art. 83(3))
- Band: low 421,775 EUR  /  expected 521,074 EUR  /  max 10,000,000 EUR
- Calibration (award_ceiling_ratio): award/ceiling ratios observed in 4 comparable matters (median 0.090, p25 0.072)
- Comparables used (7): whatsapp-2021-transparency, instagram-2022-children, meta-ireland-2023-transfers, tiktok-2023-children, tiktok-2025-transfers, amazon-2021-luxembourg, google-ireland-2026-location (widened/partial match)
- Observed award/ceiling ratios: p25 0.072 / median 0.090 / p90 0.222 (n=4)
- Observed awards: median 405,000,000, p90 927,600,000 (min 225,000,000, max 1,200,000,000)
- Note: count basis: single failure of security of processing; counts are not per data subject in the decision practice
- Note: size mismatch: the comparable matters faced ceilings of the order of 4,185,000,000 EUR (median) against 10,000,000 here; an award/ceiling ratio does not transfer cleanly across entity size

## Precedent view

- Comparable matters: 7 (amazon-2021-luxembourg, google-ireland-2026-location, instagram-2022-children, meta-ireland-2023-transfers, tiktok-2023-children, tiktok-2025-transfers, whatsapp-2021-transparency)
- Observed award/ceiling ratios across those matters: p25 0.072 / median 0.090 / p90 0.222 (n=4)
- Observed awards: median 405,000,000, p25 374,000,000, p90 927,600,000 (n=7)
- Method: fixed/turnover regimes are calibrated on the observed award-to-ceiling ratio (median -> expected, p25 -> low); per-violation regimes are calibrated on the violation-equivalents the comparable settlements actually bought (amount / per-violation amount, median and p25). Defaults are used, and flagged, where neither is available.

## Severity factors applied

| Factor | Strength | Effect | Authority |
|---|---|---|---|
| cooperation | 0.6 | -18.0% | GDPR Art. 83(2)(f); EDPB Guidelines 04/2022 on the calculation of fines |
| self_reporting | 1.0 | -20.0% | GDPR Art. 83(2)(h); ICO data protection fining guidance |
| remediation | 1.0 | -10.0% | GDPR Art. 83(2)(c) |
| no_prior_infringements | 1.0 | -5.0% | GDPR Art. 83(2)(e) (absence of previous infringements) |
| long_duration | 0.25 | +3.8% | GDPR Art. 83(2)(a) (duration of the infringement) |
| **combined** | | **x0.5819** | |

## Warnings

- gdpr-art83-5: comparables are two or more orders of magnitude larger than this entity - treat the calibrated band as indicative only
- gdpr-art83-4: comparables are two or more orders of magnitude larger than this entity - treat the calibrated band as indicative only

## Method and limits

- *Maximum* is the statutory ceiling for the charge as pleaded, after statutory aggregation rules; it is a legal ceiling, not a forecast.
- *Expected* and *low* apply the case's severity-factor multiplier to the ceiling and a ratio calibrated on comparable decided matters (median / 25th percentile of award-to-ceiling ratios).
- Precedents are matched on statute, jurisdiction and sector; partial matches are flagged.
- Prototype triage output, not legal advice. Statutory amounts and precedent records are sourced (see data/*.json 'sources') but carry an 'as_of' date; verify before relying on them. The expected/low values are calibrated heuristics, not predictions of any particular regulator's decision.
