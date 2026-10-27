"""End-to-end self check: data integrity, parser, model.

    python3 -m penex selfcheck

Runs in a few seconds, needs no network, and is the thing to run after editing
``data/*.json`` so a typo cannot silently change an exposure number.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .model import FACTOR_WEIGHTS, model_case
from .parser import draft_case_spec, parse_text
from .precedents import Precedents
from .statutes import BASE_DIR, DataError, Registry
from .report import render_markdown

KNOWN_NON_REGISTRY_INSTRUMENTS = {"ftc-act-5-unfair", "ucl-fal", "caloppa", "kopipa"}


class Checker:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.warned: list[str] = []

    def ok(self, msg: str) -> None:
        self.passed.append(msg)

    def fail(self, msg: str) -> None:
        self.failed.append(msg)

    def warn(self, msg: str) -> None:
        self.warned.append(msg)

    def check(self, cond: bool, msg: str) -> bool:
        (self.ok if cond else self.fail)(msg)
        return cond


def run_selfcheck() -> int:
    c = Checker()
    print("penex selfcheck\n" + "-" * 40)

    # 1. data files load and validate
    try:
        reg = Registry()
        c.ok(f"statutes.json loads and validates ({len(reg)} regimes, as of {reg.as_of})")
    except DataError as e:
        c.fail(f"statutes.json: {e}")
        return _report(c)
    try:
        pr = Precedents()
        c.ok(f"precedents.json loads and validates ({len(pr)} decisions, as of {pr.as_of})")
    except DataError as e:
        c.fail(f"precedents.json: {e}")
        return _report(c)

    # 2. every statute: compiles patterns, has sources, coherent numbers
    for s in reg.all():
        for pat in s.get("citation_patterns", []):
            try:
                re.compile(pat)
            except re.error as e:
                c.fail(f"statute {s['id']}: bad citation pattern {pat!r} ({e})")
        if not s.get("sources"):
            c.fail(f"statute {s['id']}: no sources")
        if s["penalty_model"] == "fixed_or_turnover" and s["turnover_pct_cap"] <= 0:
            c.fail(f"statute {s['id']}: non-positive turnover percentage")
    c.ok("all citation patterns compile and every regime cites at least one source")

    # 3. precedents: statute ids resolve; dates parse; amounts positive
    for r in pr.records:
        for sid in (r.get("statute_ids") or []):
            if sid not in reg.ids() and sid not in KNOWN_NON_REGISTRY_INSTRUMENTS:
                c.fail(f"precedent {r['id']}: statute_id {sid!r} is not in the registry")
        if not re.fullmatch(r"\d{4}(-\d{2}){0,2}", str(r["decision_date"])):
            c.fail(f"precedent {r['id']}: decision_date {r['decision_date']!r} is not YYYY[-MM[-DD]]")
        if r["amount"] is not None and float(r["amount"]) < 0:
            c.fail(f"precedent {r['id']}: negative amount")
    n_nonc = len(pr.records) - len([r for r in pr.records if r["verification"] == "primary-verified"])
    c.ok("precedent statute ids resolve and dates/amounts are well formed")
    c.warn(f"{n_nonc} of {len(pr.records)} precedent records are secondary-reported or better-only; "
           "re-verify before reliance (see 'penex sources')")

    # 4. parser on the bundled fixtures
    ex = BASE_DIR / "examples"
    for txt in sorted(ex.glob("*.txt")):
        text = txt.read_text(encoding="utf-8")
        parsed = parse_text(text, reg)
        c.check(parsed["summary"]["matched_citations"] > 0,
                f"parser matched at least one citation in {txt.name} "
                f"({parsed['summary']['matched_citations']} matched, "
                f"{parsed['summary']['draft_violations']} draft violations)")
        c.check(any(v["count"] is not None for v in parsed["violations"]),
                f"parser extracted at least one per-violation count from {txt.name}")

    # 5. model on the bundled cases, with band-order and aggregation invariants
    for case_file in sorted(ex.glob("*.json")):
        case = json.loads(case_file.read_text(encoding="utf-8"))
        res = model_case(case, reg, pr)
        band = res["case_band"] or {}
        if band:
            c.check(band["low"] <= band["expected"] <= band["max"],
                    f"band ordering low <= expected <= max holds for {case_file.name}")
            c.check(band["max"] >= 0, f"non-negative ceiling for {case_file.name}")
        else:
            c.warn(f"{case_file.name}: case-level band suppressed (see warnings)")
        c.check(all("ceiling" in v and v["band"]["max"] is None or v["band"]["max"] >= 0
                    for v in res["violations"]),
                f"per-violation ceilings computable and non-negative for {case_file.name}")
        md = render_markdown(res, reg)
        c.check("Exposure band" in md and "maximum" in md.lower(),
                f"markdown report renders for {case_file.name}")
        c.check("not legal advice" in md.lower(),
                f"{case_file.name} report carries the not-legal-advice disclaimer")

    # 6. parser -> case spec -> model round trip
    txt = ex / "complaint_fixture_gdpr_transfers.txt"
    if txt.exists():
        parsed = parse_text(txt.read_text(encoding="utf-8"), reg)
        spec = draft_case_spec(parsed, case_id="roundtrip", entity="Roundtrip Co",
                               jurisdiction="EU/EEA", registry=reg,
                               turnover=500_000_000, turnover_currency="EUR")
        spec["alleged_violations"] = spec["alleged_violations"] or [{"statute_id": "gdpr-art83-5", "count": 100000}]
        res = model_case(spec, reg, pr)
        c.check(bool(res["violations"]), "draft case spec produced by the parser can be modelled")
        c.check(spec["provenance"]["review_required"] is True,
                "draft case spec is flagged as requiring human review")

    # 7. arithmetic spot-checks against the statutes, recomputed independently
    cap = reg.ceiling("gdpr-art83-5", turnover=100_000_000, turnover_currency="EUR")
    c.check(abs(cap.max_amount - 20_000_000) < 1,
            "GDPR Art. 83(5): a 100m turnover entity is capped at the 20m fixed floor")
    cap = reg.ceiling("gdpr-art83-5", turnover=2_000_000_000, turnover_currency="EUR")
    c.check(abs(cap.max_amount - 80_000_000) < 1,
            "GDPR Art. 83(5): 4% of a 2bn turnover (80m) beats the 20m floor")
    cap = reg.ceiling("ccpa-ag-1798.155", count=1000)
    c.check(abs(cap.max_amount - 2_500_000) < 1,
            "CCPA: 1,000 violations x $2,500 = $2.5m")
    cap = reg.ceiling("ccpa-ag-1798.155", count=1000, intentional=True)
    c.check(abs(cap.max_amount - 7_500_000) < 1,
            "CCPA: intentional violations use the $7,500 rate")
    cap = reg.ceiling("hipaa-160404", count=100, tier="tier4")
    c.check(abs(cap.max_amount - 2_190_294) < 1,
            "HIPAA: the annual cap binds above 30 tier-4 violations")
    cap = reg.ceiling("texas-cubi-503001", count=10_000)
    c.check(abs(cap.max_amount - 250_000_000) < 1,
            "Texas CUBI: 10,000 violations x $25,000 = $250m")
    cap = reg.ceiling("coppa-ftc-5l", count=10)
    c.check(abs(cap.max_amount - 530_880) < 1,
            "COPPA: 10 violations x $53,088")
    cap = reg.ceiling("uk-gdpr-higher", turnover=1_000_000_000, turnover_currency="GBP")
    c.check(abs(cap.max_amount - 40_000_000) < 1,
            "UK GDPR higher maximum: 4% of a 1bn turnover beats the 17.5m floor")

    # 8. turnover currency mismatch must be refused, not guessed
    try:
        reg.ceiling("gdpr-art83-5", turnover=100_000_000, turnover_currency="USD")
        c.fail("currency mismatch was silently converted (it must raise)")
    except DataError:
        c.ok("turnover in a foreign currency is refused unless an FX rate is supplied")

    # 9. factors behave
    mult, _ = __import__("penex.model", fromlist=["factor_multiplier"]).factor_multiplier(
        {"cooperation": True, "prior_infringements": True})
    c.check(0.05 <= mult <= 1.0, f"factor multiplier stays inside its clamp (got {mult:.3f})")
    c.check("cooperation" in FACTOR_WEIGHTS and "prior_infringements" in FACTOR_WEIGHTS,
            "factor weights are declared and documented in code")

    return _report(c)


def _report(c: Checker) -> int:
    print(f"\n{len(c.passed)} checks passed")
    for p in c.passed:
        print(f"  PASS  {p}")
    if c.warned:
        print(f"\n{len(c.warned)} warnings")
        for w in c.warned:
            print(f"  WARN  {w}")
    if c.failed:
        print(f"\n{len(c.failed)} FAILURES")
        for f in c.failed:
            print(f"  FAIL  {f}")
        return 1
    print("\nselfcheck OK")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(run_selfcheck())
