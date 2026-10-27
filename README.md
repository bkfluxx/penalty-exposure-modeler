# PenaltyExposure Modeler

A working prototype of a statutory privacy-penalty exposure model. It reads an
enforcement complaint / penalty notice / judgment, turns it into per-violation
counts under each cited statute, applies the statutory range for that statute and
jurisdiction, calibrates the answer against comparable decided matters, and
prints a **low / expected / maximum** exposure band for the case.

Pure Python standard library. No API keys, no LLM calls, no network needed to run
(the data files were researched and are committed with their sources).

```
python3 -m penex selfcheck        # validate everything, ~1 second
python3 -m penex statutes         # every statutory range in the registry
python3 -m penex model examples/case_acme_health_multi.json --out report.md
```

> Prototype triage output, **not legal advice**. Statutory amounts and precedent
> figures are sourced (see `penex sources`) and carry an `as_of` date.

---

## What it does, in the four steps of the brief

### 1. Parses enforcement complaints and verdicts into per-violation counts

`penex parse` runs a transparent, rule-based extractor over the text and emits a
draft case spec:

```
python3 -m penex parse examples/complaint_fixture_ccpa_ag.txt --jurisdiction US-CA --emit-case draft.json
```

It extracts

* **statutory citations** normalised against the registry (`Art. 83(5)` →
  `gdpr-art83-5`, `1798.155` → `ccpa-ag-1798.155`, `45 CFR 164.312` → `hipaa-160404`),
  with the paragraph each came from,
* **per-violation counts** — "533 million users", "3,400,000 consumers",
  "14,000 records" — each with the exact phrase it came from and a confidence
  score,
* **monetary figures** in the document, which is how a decided case becomes a new
  precedent record,
* **violation units** (`per scan`, `per person`, `per day`) which decide whether a
  count may be multiplied by anything.

The parser never infers a number that is not written down: a count below the
confidence threshold is emitted as `null` so the model has to flag it, and every
draft spec is stamped `review_required: true`. Roughly 250 lines of regex, fully
inspectable — it is not a black box and it is not an LLM.

### 2. Applies the statutory ranges

`data/statutes.json` holds 17 regimes across the EU, UK, California, Texas,
Illinois, Colorado, Washington and US federal law, each with the provision text,
the penalty model that applies to it, and the source it was read from. Five
penalty models are implemented:

| Model | Regimes | Arithmetic |
|---|---|---|
| `fixed_or_turnover` | GDPR Art. 83(4)/(5)/(6), UK GDPR (DPA 2018 s.157) | higher of a fixed amount and a % of worldwide annual turnover |
| `per_violation` | CCPA s.1798.155, COPPA, Texas CUBI, TDPSA, Texas data broker, Colorado CPA, Washington MHMD | per-violation amount × count, with a higher rate for intentional violations / under-16s |
| `per_violation_per_day` | FTC Health Breach Notification Rule | per-violation amount × count × days |
| `per_violation_tiered` | HIPAA (45 CFR 160.404 + 102.3) | tier picked on knowledge / willfulness, then the annual cap for identical violations |
| `per_consumer_range` | CCPA private right of action (s.1798.150) | the statute *is* a range: a floor and a ceiling |

Statutory **aggregation rules** are enforced, not just documented:

* **GDPR Art. 83(3)** — linked processing operations are capped at the amount for
  the gravest infringement, so two linked charges do not simply add up.
* **HIPAA** — the annual cap for identical violations binds (14,000 tier-3
  violations would be $1bn without it; the cap makes it $2.19m).
* **BIPA (as amended by Public Act 103-0769)** — repeated collection from the same
  person is *one* violation, so counts must be distinct persons; the model warns
  when the same statute is cited more than once.
* **Turnover currency** — a turnover in a currency the statute does not use is
  **refused**, not converted, unless the user supplies a rate (`--fx EUR=1.09,USD`).
  The tool never invents an exchange rate.

### 3. Maps comparable precedents and settlement outcomes

`data/precedents.json` holds 22 real decided matters (€1.2bn Meta transfers,
£20m British Airways, $1.2m Sephora, $2.75m Disney, $12.75m General Motors,
$1.4bn Texas v Meta, $275m Epic Games, $1.5m GoodRx, …), each with a source URL, an
outcome type, a status and a `verification` field (`primary-verified` /
`secondary-reported`).

Matching is a transparent score: **+3** shares a statute with the charge, **+1** the
statute sets are nested, **+2** same jurisdiction, **+1** same sector; a record
sharing *no* statute starts **−4**, so jurisdiction and sector alone can never drag
an unrelated matter into the comparison set. If no charge matches a statute
directly, the set is widened to the same **legal family** (GDPR, CCPA, biometric,
health, children's privacy) *and* the same jurisdiction or sector — and every such
record is returned flagged as a **partial match** in the report.

### 4. Produces the low / expected / maximum band

```
maximum  = the statutory ceiling for the charge as pleaded, after aggregation rules
expected = ceiling × severity-factor multiplier × k_expected
low      = ceiling × severity-factor multiplier × k_low
```

`k` is where the empirical work happens, and there are two calibrations:

* **`award_ceiling_ratio`** (fixed/turnover regimes): the observed ratio of the
  amount imposed to the ceiling that then applied — median for *expected*, p25 for
  *low*. Across the GDPR records that is p25 0.072 / median 0.090.
* **`settlement_to_ceiling`** (per-violation regimes): regulators settle these as
  lump sums, so the observable quantity is **how many violations the money bought**
  (`amount / per-violation amount`). A $1.2m CCPA settlement is 480 violations at
  $2,500; the median across the California AG settlements is ~560. Applying
  `per_violation × implied units` is what stops a 3.4m-consumer count from
  producing an $8.5bn "expected" value. The model returns ~$1.4m for that count —
  which is where the real AG settlements actually sit.
* **`default`** — a documented fallback (600 / 150 violation-equivalents), used and
  **flagged in the report** when a regime has no comparable with a recorded amount.

The **severity-factor multiplier** implements the Art. 83(2)-style factor list with
published weights (cooperation up to −30%, self-reporting −20%, remediation −10%,
no prior infringements −5%; prior infringements +25%, intentional +25%, vulnerable
data subjects +20%, duration over 24 months +15%). Reductions and uplifts are
multiplied, clamped to [0.05, 1.0] — an uplift can never take you above the
statutory ceiling — and every factor, its weight, its effect and its authority is
printed in the report.

---

## What the output looks like

Both example cases are real runs, regenerated by `make demo`:

| Case | Low | Expected | Max (ceiling) |
|---|---|---|---|
| `case_acme_eu_transfers.json` (GDPR, Art. 46 + Art. 32, €480m turnover) | €843,551 | €1,042,148 | €20,000,000 |
| `case_acme_health_multi.json` (6 charges, 5 regimes, 4 jurisdictions) | $1,457,871,903 | $1,537,009,515 | $1,038,329,350,294 |

The second table is the point of the product: the ceiling is a trillion dollars and
the expected value is a billion and a half, dominated by Texas biometric exposure —
and the report shows exactly which precedent set produced each line.

The Markdown report contains: the band and its confidence, the aggregation rules
applied, a "how the case total is built" contribution table, per-violation detail
(ceiling, basis, count and its source, calibration mode, the comparables used with
their scores and amounts, notes), the precedent view, the factor table with
authorities, all warnings, and the method limits.

## Commands

```
python3 -m penex statutes [--regime gdpr] [--json]
python3 -m penex parse <file> [--jurisdiction US-CA] [--emit-case draft.json] [--json]
python3 -m penex precedents [--statute ccpa-ag-1798.155] [--jurisdiction US-TX] [--sector health]
python3 -m penex model <case.json> [--out report.md] [--json] [--fx EUR=1.09,USD]
python3 -m penex factors                 # the severity weights and their authorities
python3 -m penex sources [--verify-urls] # every source URL behind the data
python3 -m penex selfcheck               # 31 end-to-end checks
make test                                # 37 unit tests (unittest, no deps)
```

Python 3.10+ (developed and run on 3.14.7). No third-party packages.

## Layout

```
penex/
  statutes.py    registry loading, validation, statutory range arithmetic
  parser.py      complaint / verdict -> citations, counts, amounts
  precedents.py  precedent store, comparability scoring, distribution stats
  model.py       ceiling x severity factors, calibrations, aggregation, bands
  report.py      the Markdown deliverable
  selfcheck.py   end-to-end validation of data + parser + model
  cli.py         command line interface
data/
  statutes.json  17 regimes: provision text, ranges, aggregation rules, sources
  precedents.json 22 decided matters with amounts, sources and verification status
examples/        two synthetic complaint fixtures, two hypothetical case specs
tests/           37 unit tests
tools/inspect_case.py  one-line-per-charge summary of a model run
reports/         generated example reports (make demo)
```

## Case spec format

```json
{
  "case_id": "ACME-EU-2026-001",
  "entity": {"name": "Acme", "sector": "social_media",
             "global_annual_turnover": {"amount": 480000000, "currency": "EUR"}},
  "jurisdiction": "EU/EEA",
  "display_currency": "EUR",
  "alleged_violations": [
    {"statute_id": "gdpr-art83-5", "citation": "Art. 46(1) GDPR",
     "count": 2400000, "count_basis": "users whose data was transferred"}
  ],
  "factors": {"cooperation": 0.6, "self_reporting": true, "duration_months": 30}
}
```

`count` is the number of violations as pleaded (individuals, records, days — the
model tells you which unit each statute multiplies). `factors` accepts `true`/`false`
or a strength from 0-1 (or 0-100). Everything the model prints is reproducible from
this file plus the two data files.

## Limitations — read before you rely on it

1. **This is a prototype, not legal advice.** No output has been reviewed by a
   lawyer, and the model does not characterise conduct: telling it a fact pattern
   is an Art. 46 transfer case is your legal call, not its.
2. **The ceiling is not a forecast.** It is the statutory maximum for the charge as
   pleaded. `maximum` will routinely be orders of magnitude above anything a
   regulator has ever imposed, and the report says so.
3. **Small data, honestly labelled.** 22 precedents is enough structure to
   demonstrate the method, not enough for statistical confidence. 8 of the 22 are
   `secondary-reported` — the enforcer's page was not individually captured — and
   `penex selfcheck` warns about it. Re-verify before reliance.
4. **Ratio transfer across entity size is the weakest assumption.** An award/ceiling
   ratio observed for a €100bn-revenue undertaking is applied to a €480m one. The
   model detects when comparables are two or more orders of magnitude larger and
   emits a warning rather than hiding it.
5. **Regulatory practice moves faster than the data file.** Amounts, appeal
   outcomes (Amazon's Luxembourg fine is flagged `reported_contested`) and
   inflation-adjusted statutory figures all change. Everything carries an `as_of`
   date (`2026-10-13` here) and `penex sources` lists every URL to re-check.
6. **Per-violation statutes have no meaningful ceiling.** 3.4m consumers × $2,500 is
   $8.5bn. The calibration exists precisely because that number is not useful; the
   statutory maximum is reported anyway so nobody can lose sight of it.
7. **Not modelled:** joint and several liability, individual liability of officers,
   injunctive and corrective-action costs, private class-action exposure (except the
   CCPA s.1798.150 range), insurance, the effect of a cure period on the amount, or
   multi-jurisdiction coordination.

## Extending it

* **New statute:** append an entry to `data/statutes.json` (with a source URL and at
  least one `citation_patterns` regex), run `python3 -m penex selfcheck`.
* **New precedent:** append to `data/precedents.json` with `statute_ids`, an
  `outcome_type`, a `source.url` and a `verification` value. If you can state the
  ceiling that applied at the time, add `statutory_cap_at_decision` — that record
  then contributes to ratio calibration as well as the award band.
* **Turn a decided case into a precedent:** `python3 -m penex parse decision.txt`
  prints the largest monetary figures it found; paste the right one into
  `precedents.json` with the source URL and a human check.
* The self-check recomputes eight statutory ceilings independently of the model, so
  a mistyped amount in the data file fails loudly rather than silently moving a
  number.
