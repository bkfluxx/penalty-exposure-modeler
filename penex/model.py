"""Exposure model: statutory ceilings x calibrated severity factors -> low / expected / max band.

The model is deliberately mechanical and auditable.  For every charged violation
it computes three numbers and records how each was derived:

    maximum  = the statutory ceiling that applies to the charge as pleaded
               (per-violation amount x count, or the turnover-linked / fixed cap,
               after any statutory aggregation rule)
    expected = ceiling x factor multiplier x k_expected
    low      = ceiling x factor multiplier x k_low

``factor multiplier`` comes from the case's aggravating / mitigating factors using
the published weights below.  ``k_expected`` / ``k_low`` are the ratio of amounts
actually imposed to the ceiling that applied, taken from comparable decided
matters (median and 25th percentile).  Where too few comparable records carry a
computable ceiling, the model falls back to conservative defaults and says so -
it never silently substitutes an invented number for observed data.
"""
from __future__ import annotations

from typing import Any

from .precedents import Precedents, regime_family
from .statutes import Registry, convert

# --------------------------------------------------------------------------- #
# severity factors
# --------------------------------------------------------------------------- #
# Weights are expressed as a fraction of the statutory ceiling and are applied
# multiplicatively.  They mirror the Art. 83(2) GDPR / ICO / CPPA factor lists;
# they are heuristics for triage, not a substitute for a regulator's own
# calculation.  Each is capped so a single factor cannot move the estimate more
# than a third of the ceiling.

FACTOR_WEIGHTS: dict[str, dict] = {
    "cooperation": {
        "kind": "reduction", "max": 0.30,
        "citation": "GDPR Art. 83(2)(f); EDPB Guidelines 04/2022 on the calculation of fines"},
    "self_reporting": {
        "kind": "reduction", "max": 0.20,
        "citation": "GDPR Art. 83(2)(h); ICO data protection fining guidance"},
    "remediation": {
        "kind": "reduction", "max": 0.10,
        "citation": "GDPR Art. 83(2)(c)"},
    "no_prior_infringements": {
        "kind": "reduction", "max": 0.05,
        "citation": "GDPR Art. 83(2)(e) (absence of previous infringements)"},
    "prior_infringements": {
        "kind": "uplift", "max": 0.25,
        "citation": "GDPR Art. 83(2)(e); CPPA enforcement policy on repeat conduct"},
    "intentional": {
        "kind": "uplift", "max": 0.25,
        "citation": "GDPR Art. 83(2)(b); Cal. Civ. Code s.1798.155 (intentional violations)"},
    "vulnerable_data_subjects": {
        "kind": "uplift", "max": 0.20,
        "citation": "GDPR Art. 83(2)(g); CCPA special treatment of consumers under 16"},
    "long_duration": {
        "kind": "uplift", "max": 0.15,
        "citation": "GDPR Art. 83(2)(a) (duration of the infringement)"},
}

DEFAULT_K_EXPECTED = 0.05
DEFAULT_K_LOW = 0.01
MIN_COMPARABLES_FOR_RATIOS = 2

# Used only when a per-violation regime has no comparable matter with a recorded
# amount.  These are the median and 25th percentile of the *implied violation
# equivalents* (settlement amount / per-violation amount) across the California
# AG settlement records in data/precedents.json - i.e. the observed pattern that
# such cases settle at the equivalent of a few hundred violations rather than at
# the arithmetic ceiling.
DEFAULT_IMPLIED_UNITS_EXPECTED = 600
DEFAULT_IMPLIED_UNITS_LOW = 150


def _strength(value: Any) -> float:
    """Accept bool, 0-1 float or 0-100 int for a factor's strength."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v > 1.0:
        v = v / 100.0
    return max(0.0, min(1.0, v))


def factor_multiplier(factors: dict) -> tuple[float, list[dict]]:
    """Multiplier in (0, 1] applied to the statutory ceiling, plus a trace."""
    mult = 1.0
    applied = []
    for name, value in (factors or {}).items():
        if name == "duration_months":
            w = FACTOR_WEIGHTS["long_duration"]
            months = float(value or 0)
            s = 0.0 if months <= 24 else min(1.0, (months - 24) / 24.0)
            if s > 0:
                mult *= 1 + w["max"] * s
                applied.append({"factor": "long_duration", "strength": round(s, 2),
                                "effect": f"+{w['max'] * s:.1%}", "citation": w["citation"],
                                "input": f"{months:.0f} months"})
            continue
        if name not in FACTOR_WEIGHTS:
            applied.append({"factor": name, "strength": None, "effect": "ignored",
                            "citation": None,
                            "input": str(value),
                            "note": "not a recognised factor; ignored (weights are fixed in code)"})
            continue
        w = FACTOR_WEIGHTS[name]
        s = _strength(value)
        if s <= 0:
            continue
        if w["kind"] == "reduction":
            mult *= 1 - w["max"] * s
            eff = f"-{w['max'] * s:.1%}"
        else:
            mult *= 1 + w["max"] * s
            eff = f"+{w['max'] * s:.1%}"
        applied.append({"factor": name, "strength": round(s, 2), "effect": eff,
                        "citation": w["citation"]})
    clamped = min(max(mult, 0.05), 1.0)
    if abs(clamped - mult) > 1e-9:
        applied.append({"factor": "clamp", "strength": None,
                        "effect": f"{mult:.3f} -> {clamped:.3f}",
                        "citation": None,
                        "note": "multiplier clamped: the statutory ceiling cannot be exceeded "
                                "and the floor is 5% of the ceiling"})
    return clamped, applied


# --------------------------------------------------------------------------- #
# calibration
# --------------------------------------------------------------------------- #

def _calibrate(statute: dict, stats: dict, comps: list[dict],
               units: float | None) -> tuple[float, float, str, str]:
    """Pick how 'expected' and 'low' are scaled, and say which was used.

    Returns ``(k_expected, k_low, mode, explanation)`` where ``mode`` is one of
    ``award_ceiling_ratio`` / ``settlement_to_ceiling`` / ``default``.

    Two calibrations, in order of preference:

    ``award_ceiling_ratio`` - for fixed/turnover regimes (GDPR, UK GDPR).  Uses
        the observed ratio of amount imposed to the ceiling that then applied
        (median -> expected, p25 -> low).

    ``settlement_to_ceiling`` - for per-violation regimes (CCPA, COPPA, HIPAA,
        Texas, BIPA).  Regulators settle these as lump sums, so the observable
        quantity is *how many violations the money is equivalent to*:
        ``amount / per-violation amount`` (e.g. a $1.2m CCPA settlement is
        equivalent to 480 violations at $2,500).  The median of that implied
        count across comparable matters, divided by the units charged in this
        case (violations, or violation-days for per-day statutes), gives the
        fraction of the arithmetic ceiling that actually gets paid.  This is
        what stops a 3.4m-consumer count from producing an $8.5bn "expected"
        value: the answer becomes per-violation amount x implied units, which is
        the scale the observed settlements actually occupy.

    ``default`` - documented fallback when neither can be computed.
    """
    ratios = stats.get("ratios") or {}
    if statute["penalty_model"] == "fixed_or_turnover" and ratios.get("n", 0) >= MIN_COMPARABLES_FOR_RATIOS:
        return (ratios["median"], ratios["p25"], "award_ceiling_ratio",
                f"award/ceiling ratios observed in {ratios['n']} comparable matters "
                f"(median {ratios['median']:.3f}, p25 {ratios['p25']:.3f})")

    per = statute.get("per_violation_amount")
    if per and units:
        implied = sorted(float(r["amount"]) / float(per) for r in comps if r.get("amount"))
        if implied:
            med = _median(implied)
            low = _pct(implied, 0.25)
            k_expect = min(1.0, med / float(units))
            k_low = min(1.0, low / float(units))
            thin = " (single comparable - treat as indicative)" if len(implied) == 1 else ""
            return (k_expect, k_low, "settlement_to_ceiling",
                    f"settlement-to-ceiling calibration{thin}: {len(implied)} comparable matter(s) "
                    f"settled for the equivalent of a median {med:,.0f} and a 25th-percentile "
                    f"{low:,.0f} violation-equivalents (amount / {per:,.0f} {statute['currency']} "
                    f"per violation); against the {units:,.0f} charged here that is "
                    f"{k_expect:.4%} / {k_low:.4%} of the arithmetic ceiling")
    if per and units:
        k_expect = min(1.0, DEFAULT_IMPLIED_UNITS_EXPECTED / float(units))
        k_low = min(1.0, DEFAULT_IMPLIED_UNITS_LOW / float(units))
        return (k_expect, k_low, "default",
                f"documented default violation-equivalents ({DEFAULT_IMPLIED_UNITS_EXPECTED:,} "
                f"median / {DEFAULT_IMPLIED_UNITS_LOW:,} low, the observed California AG settlement "
                f"pattern) - no comparable matter for this regime carries a recorded amount; "
                f"{units:,.0f} charged here gives {k_expect:.4%} / {k_low:.4%} of the ceiling")
    return (DEFAULT_K_EXPECTED, DEFAULT_K_LOW, "default",
            f"documented default ratios (median {DEFAULT_K_EXPECTED:.3f}, "
            f"low {DEFAULT_K_LOW:.3f}) - no usable comparable set for this regime")


def _median(values: list[float]) -> float:
    n = len(values)
    if n % 2:
        return values[n // 2]
    return (values[n // 2 - 1] + values[n // 2]) / 2


def _pct(values: list[float], p: float) -> float:
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def _confidence(n_comp: int, n_calibrated: int, turnover_known: bool, counts_sourced: bool,
                currency_ok: bool) -> dict:
    reasons = []
    if turnover_known:
        reasons.append("entity turnover supplied (turnover-linked caps computed)")
    else:
        reasons.append("entity turnover NOT supplied (turnover-linked caps may be underestimated)")
    if n_calibrated >= 2:
        reasons.append(f"{n_calibrated} charged violation(s) carry a band calibrated on comparable "
                       "decided matters")
    elif n_calibrated == 1:
        reasons.append("only 1 charged violation carries a band calibrated on comparable decided "
                       "matters (weak)")
    else:
        reasons.append("no charged violation has a comparable matter with a recorded amount "
                       "(documented defaults used instead)")
    if n_comp == 0:
        reasons.append("no comparable matters found for these statutes")
    if counts_sourced:
        reasons.append("per-violation counts were supplied/read from source text")
    else:
        reasons.append("one or more per-violation counts are missing or assumed")
    if not currency_ok:
        reasons.append("mixed currencies: sub-totals kept separate")
    if (n_calibrated >= 3 and turnover_known and counts_sourced and currency_ok and n_comp >= 3):
        level = "high"
    elif n_calibrated >= 1 and currency_ok and n_comp >= 1:
        level = "medium"
    else:
        level = "low"
    return {"level": level, "reasons": reasons}


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def model_case(case: dict, registry: Registry, precedents: Precedents,
               fx: dict | None = None) -> dict:
    fx = fx or {}
    warnings: list[str] = []
    trace: list[str] = []

    if "jurisdiction" not in case:
        raise ValueError("case spec needs a 'jurisdiction'")
    violations_in = case.get("alleged_violations") or []
    if not violations_in:
        raise ValueError("case spec has no 'alleged_violations'")

    turnover = None
    turnover_currency = None
    ent = case.get("entity") or {}
    if ent.get("global_annual_turnover"):
        t = ent["global_annual_turnover"]
        turnover = float(t.get("amount") or 0) or None
        turnover_currency = t.get("currency")

    mult, factor_trace = factor_multiplier(case.get("factors") or {})
    trace.append(f"factor multiplier applied to every statutory ceiling: {mult:.3f}")

    # statute id -> coarse legal family, so widened (partial) matches stay on the
    # same shelf of the statute book
    family_of_statute = {s["id"]: regime_family(s["regime"]) for s in registry.all()}

    per_violation: list[dict] = []
    used_precedents: dict[str, dict] = {}

    for v in violations_in:
        sid = v.get("statute_id")
        if not sid:
            raise ValueError(f"violation without statute_id: {v!r}")
        st = registry.get(sid)
        cap = registry.ceiling(
            sid,
            count=v.get("count"),
            turnover=turnover,
            turnover_currency=turnover_currency,
            tier=v.get("tier"),
            intentional=bool(v.get("intentional", case.get("factors", {}).get("intentional"))),
            under_16=bool(v.get("under_16")),
            days=v.get("days"),
            fx=fx,
        )
        v_notes = []
        if cap.warning:
            v_notes.append(cap.warning)
            warnings.append(f"{sid}: {cap.warning}")
        if v.get("count_basis"):
            v_notes.append(f"count basis: {v['count_basis']}")
        if v.get("count") is None and st["penalty_model"] != "fixed_or_turnover":
            warnings.append(f"{sid}: no per-violation count given in the case spec")

        comps = precedents.comparables(
            statute_ids={sid},
            jurisdiction=st["jurisdiction"],
            sector=ent.get("sector"),
            families={family_of_statute[sid]},
            record_families=family_of_statute,
        )
        for c in comps:
            used_precedents[c["id"]] = c
        stats = Precedents.stats(comps)
        awards = stats.get("awards") or {}
        if awards.get("p25") and awards.get("p90") and awards["p90"] > 10 * awards["p25"]:
            v_notes.append(
                f"highly dispersed comparable set (award p25 {awards['p25']:,.0f} to p90 "
                f"{awards['p90']:,.0f}): the median is a wide midpoint, not a point estimate")
            warnings.append(f"{sid}: comparable awards span more than a factor of 10 - read the "
                            "expected value as an order of magnitude, not a forecast")
        units = v.get("count")
        if units and v.get("days"):
            units = units * int(v["days"])
        k_expect, k_low, calib_mode, calib = _calibrate(st, stats, comps, units)

        # A ratio borrowed from undertakings far larger than this one is the
        # weakest assumption in the model - say so rather than hide it.
        caps = [float(c["statutory_cap_at_decision"]) for c in comps
                if c.get("statutory_cap_at_decision")]
        if caps and cap.max_amount:
            med_cap = _median(sorted(caps))
            if cap.max_amount * 100 < med_cap:
                v_notes.append(
                    f"size mismatch: the comparable matters faced ceilings of the order of "
                    f"{med_cap:,.0f} {cap.currency} (median) against {cap.max_amount:,.0f} here; "
                    "an award/ceiling ratio does not transfer cleanly across entity size")
                warnings.append(
                    f"{sid}: comparables are two or more orders of magnitude larger than this "
                    "entity - treat the calibrated band as indicative only")

        ceiling = cap.max_amount
        low = None if ceiling is None else ceiling * mult * k_low
        expected = None if ceiling is None else ceiling * mult * k_expect
        maximum = ceiling

        if st["penalty_model"] == "per_consumer_range" and cap.min_amount:
            # the statute itself is a range: floor the low end at the statutory minimum
            low = max(low or 0.0, cap.min_amount)
            v_notes.append("statutory damages range: low end cannot fall below the statutory minimum")

        per_violation.append({
            "statute_id": sid,
            "citation": v.get("citation") or st["citation"],
            "statute_name": st["name"],
            "jurisdiction": st["jurisdiction"],
            "count": v.get("count"),
            "ceiling": cap.as_dict(),
            "factor_multiplier": round(mult, 4),
            "calibration": calib,
            "calibration_mode": calib_mode,
            "band": {"low": low, "expected": expected, "max": maximum,
                     "currency": cap.currency},
            "comparables": {
                "n": stats.get("n", 0),
                "ids": [c["id"] for c in comps],
                "partial_match": all(c.get("partial_match") for c in comps) if comps else None,
                "award_band": stats.get("awards"),
                "ratio_band": stats.get("ratios"),
            },
            "notes": v_notes,
        })

    # ---- statutory aggregation across violations ------------------------- #
    agg_notes: list[str] = []
    groups: dict[tuple, list[dict]] = {}
    for pv in per_violation:
        st = registry.get(pv["statute_id"])
        rule = (st.get("aggregation") or {}).get("rule")
        if rule == "linked_processing_single_ceiling":
            groups.setdefault((rule, st["regime"], st["jurisdiction"]), []).append(pv)

    contributions: list[dict] = []
    grouped: set[int] = set()
    for key, members in groups.items():
        if len(members) < 2:
            continue
        rule, regime, jurisdiction = key
        for m in members:
            grouped.add(id(m))
        cols: dict[str, float | None] = {}
        for col in ("low", "expected", "max"):
            vals = [m["band"][col] for m in members if m["band"][col] is not None]
            if not vals:
                cols[col] = None
                continue
            gravest = max(vals)
            cols[col] = min(sum(vals), gravest)
        contributions.append({
            "label": f"{regime}: {len(members)} linked charges (Art. 83(3))",
            "low": cols["low"], "expected": cols["expected"], "max": cols["max"],
            "currency": members[0]["band"]["currency"],
            "statute_ids": [m["statute_id"] for m in members],
            "rule": rule,
        })
        agg_notes.append(
            f"{regime}: {len(members)} charges are linked processing operations; Art. 83(3) "
            f"caps the combined fine at the amount for the gravest infringement, so the "
            f"combined contribution is the lower of the summed columns and the gravest ceiling "
            f"(applied to {jurisdiction})")
        trace.append(f"aggregation applied: {regime} - linked_processing_single_ceiling "
                     f"over {len(members)} charges")

    for pv in per_violation:
        if id(pv) in grouped:
            continue
        contributions.append({
            "label": pv["citation"],
            "low": pv["band"]["low"], "expected": pv["band"]["expected"],
            "max": pv["band"]["max"], "currency": pv["band"]["currency"],
            "statute_ids": [pv["statute_id"]], "rule": None,
        })

    # BIPA-style "single recovery per person"
    for pv in per_violation:
        st = registry.get(pv["statute_id"])
        if (st.get("aggregation") or {}).get("rule") == "single_recovery_per_person":
            same = [x for x in per_violation if x["statute_id"] == pv["statute_id"]]
            if len(same) > 1:
                agg_notes.append(
                    f"{st['name']}: {len(same)} separate citations of the same statute. "
                    "Repeated collection/disclosure of the same person counts as ONE violation "
                    f"({(st.get('aggregation') or {}).get('citation')}); the ceiling assumes distinct "
                    "persons and must not be multiplied by the number of statutory duties breached.")
                warnings.append(f"{pv['statute_id']}: multiple citations - de-duplicate counts to "
                                "distinct persons before relying on the ceiling")

    # ---- case-level band -------------------------------------------------- #
    currencies = {c["currency"] for c in contributions}
    display = case.get("display_currency") or sorted(currencies)[0]
    subtotals: dict[str, dict] = {}
    currency_ok = True
    for c in contributions:
        cur = c["currency"]
        sub = subtotals.setdefault(cur, {"low": 0.0, "expected": 0.0, "max": 0.0,
                                         "violations": 0, "conversion": None})
        for col in ("low", "expected", "max"):
            val = c[col]
            if val is not None:
                sub[col] += val
        sub["violations"] += len(c["statute_ids"])


    for cur, sub in list(subtotals.items()):
        if cur == display:
            continue
        try:
            rate_basis = []
            for col in ("low", "expected", "max"):
                conv, how = convert(sub[col], cur, display, fx)
                sub[col] = conv
                rate_basis.append(how)
            sub["conversion"] = f"{cur} -> {display} using {rate_basis[0]}"
        except Exception as exc:  # noqa: BLE001 - surfaced as a warning, not a crash
            currency_ok = False
            warnings.append(f"could not convert {cur} to {display}: {exc}")

    case_band = None
    if currency_ok:
        case_band = {
            "low": sum(s["low"] for s in subtotals.values()),
            "expected": sum(s["expected"] for s in subtotals.values()),
            "max": sum(s["max"] for s in subtotals.values()),
            "currency": display,
        }
        if len(subtotals) > 1:
            case_band["note"] = ("sub-totals in other currencies converted with user-supplied "
                                 "rates; re-run with updated --fx for a current view")
    else:
        warnings.append("case-level total suppressed: mixed currencies without FX rates; "
                        "see per-currency subtotals")

    counts_sourced = all(pv["count"] is not None or
                         registry.get(pv["statute_id"])["penalty_model"] == "fixed_or_turnover"
                         for pv in per_violation)
    n_calibrated = sum(1 for pv in per_violation if pv["calibration_mode"] != "default")
    conf = _confidence(len(used_precedents), n_calibrated, turnover is not None,
                       counts_sourced, currency_ok)

    all_comps = Precedents.stats(list(used_precedents.values()))
    return {
        "case_id": case.get("case_id"),
        "entity": ent.get("name"),
        "jurisdiction": case.get("jurisdiction"),
        "as_of": registry.as_of,
        "factor_multiplier": round(mult, 4),
        "factor_trace": factor_trace,
        "violations": per_violation,
        "contributions": contributions,
        "case_band": case_band,
        "subtotals": subtotals,
        "aggregation_notes": agg_notes,
        "precedent_view": {
            "n_comparables": len(used_precedents),
            "ids": sorted(used_precedents),
            "award_band": all_comps.get("awards"),
            "ratio_band": all_comps.get("ratios"),
            "sectors": all_comps.get("sectors"),
            "method": ("fixed/turnover regimes are calibrated on the observed award-to-ceiling ratio "
                       "(median -> expected, p25 -> low); per-violation regimes are calibrated on "
                       "the violation-equivalents the comparable settlements actually bought "
                       "(amount / per-violation amount, median and p25). Defaults are used, and "
                       "flagged, where neither is available."),
        },
        "confidence": conf,
        "warnings": warnings,
        "trace": trace,
        "disclaimer": ("Prototype triage output, not legal advice. Statutory amounts and precedent "
                       "records are sourced (see data/*.json 'sources') but carry an 'as_of' date; "
                       "verify before relying on them. The expected/low values are calibrated "
                       "heuristics, not predictions of any particular regulator's decision."),
    }
