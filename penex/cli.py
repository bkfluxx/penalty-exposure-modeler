"""Command line interface: ``python3 -m penex <command>``."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .model import FACTOR_WEIGHTS, model_case
from .parser import draft_case_spec, parse_decision_amounts, parse_text
from .precedents import Precedents
from .statutes import BASE_DIR, DataError, Registry, parse_fx
from .report import money, render_markdown

EXAMPLES = BASE_DIR / "examples"


def _load(path: str | None, cls):
    return cls(path) if path else cls()


# --------------------------------------------------------------------------- #
def cmd_statutes(args) -> int:
    reg = _load(args.statutes, Registry)
    rows = reg.by_regime(args.regime) if args.regime else reg.all()
    if args.json:
        print(json.dumps({"as_of": reg.as_of, "statutes": rows}, indent=2))
        return 0
    print(f"Statute registry ({len(rows)} regimes, data as of {reg.as_of})\n")
    for s in rows:
        if s["penalty_model"] == "fixed_or_turnover":
            amount = f"up to {s['fixed_cap']:,.0f} {s['currency']} or {s['turnover_pct_cap']:.0%} of turnover"
        elif s["penalty_model"] == "per_violation_per_day":
            amount = f"{s['per_violation_amount']:,.0f} {s['currency']} per violation per day"
        elif s["penalty_model"] == "per_violation":
            extra = ""
            if s.get("per_violation_amount_intentional"):
                extra = f" (intentional/under-16: {s['per_violation_amount_intentional']:,.0f})"
            amount = f"{s['per_violation_amount']:,.0f} {s['currency']} per violation{extra}"
        elif s["penalty_model"] == "per_violation_tiered":
            amount = f"{len(s['tiers'])} tiers, per violation, annual cap {s.get('annual_cap', 0):,.0f} {s['currency']}"
        else:
            amount = (f"{s['per_violation_min']:,.0f}-{s['per_violation_max']:,.0f} {s['currency']} "
                      f"per consumer per incident")
        agg = (s.get("aggregation") or {}).get("rule")
        print(f"- [{s['id']}] {s['name']}")
        print(f"    {s['citation']}  |  {s['jurisdiction']}")
        print(f"    range: {amount}" + (f"  |  aggregation: {agg}" if agg else ""))
    return 0


def cmd_parse(args) -> int:
    reg = _load(args.statutes, Registry)
    text = Path(args.file).read_text(encoding="utf-8")
    parsed = parse_text(text, reg)
    parsed["largest_amounts"] = parse_decision_amounts(parsed, reg)
    spec = draft_case_spec(parsed, case_id=args.case_id or Path(args.file).stem,
                           entity=args.entity or "[fill in]", jurisdiction=args.jurisdiction,
                           registry=reg, sector=args.sector,
                           source_file=str(args.file))
    if args.json:
        print(json.dumps({"parsed": parsed, "draft_case_spec": spec}, indent=2))
    else:
        s = parsed["summary"]
        print(f"{args.file}: {s['paragraphs']} paragraphs, {s['matched_citations']}/{s['citations']} "
              f"citations matched to the registry, {s['counts']} candidate counts, "
              f"{s['amounts']} monetary figures")
        print("\nDraft violations (review before modelling):")
        for v in spec["alleged_violations"]:
            print(f"  - {v['citation']}  ({v['statute_id']})  count={v['count']}")
            print(f"      {v['notes']}")
        if parsed["unmatched_citations"]:
            print("\nCitations not matched to the registry:")
            for c in parsed["unmatched_citations"][:10]:
                print(f"  - {c['text']}  ...{c['context'][:80]}...")
        if parsed["largest_amounts"]:
            print("\nLargest monetary figures found (candidate outcomes):")
            for a in parsed["largest_amounts"][:5]:
                print(f"  - {a['amount']:,.0f} {a['currency'] or '?'}  |  {a['evidence'][:90]}")
    if args.emit_case:
        Path(args.emit_case).write_text(json.dumps(spec, indent=2), encoding="utf-8")
        print(f"\nDraft case spec written to {args.emit_case} (review before modelling)")
    return 0


def cmd_precedents(args) -> int:
    pr = _load(args.precedents, Precedents)
    if args.statute:
        rows = pr.by_statute(args.statute)
    elif args.jurisdiction:
        rows = pr.by_jurisdiction(args.jurisdiction)
    elif args.sector:
        rows = pr.by_sector(args.sector)
    else:
        rows = pr.records
    if args.json:
        print(json.dumps({"as_of": pr.as_of, "precedents": rows}, indent=2))
        return 0
    print(f"Precedents ({len(rows)} of {len(pr)} records, as of {pr.as_of})\n")
    for r in sorted(rows, key=lambda x: (x["decision_date"], x["entity"])):
        url = r["source"]["url"] if isinstance(r["source"], dict) else r["source"]
        print(f"- [{r['id']}] {r['decision_date']}  {r['entity']}  |  {r['jurisdiction']}  |  "
              f"{money(r['amount'], r['currency'])}  |  {r['outcome_type']}")
        print(f"    {(r.get('instrument') or ', '.join(r.get('statute_ids') or []))}")
        print(f"    {r.get('violation_summary', '')[:140]}")
        print(f"    source: {url}")
    st = Precedents.stats(rows)
    if st.get("awards"):
        a = st["awards"]
        print(f"\nAwards: n={a['n']} median {a['median']:,.0f} p90 {a['p90']:,.0f} max {a['max']:,.0f}")
    if st.get("ratios"):
        b = st["ratios"]
        print(f"Award/ceiling ratios: n={b['n']} p25 {b['p25']:.3f} median {b['median']:.3f} "
              f"p90 {b['p90']:.3f}")
    return 0


def cmd_model(args) -> int:
    reg = _load(args.statutes, Registry)
    pr = _load(args.precedents, Precedents)
    case = json.loads(Path(args.case).read_text(encoding="utf-8"))
    result = model_case(case, reg, pr, fx=parse_fx(args.fx))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_markdown(result, reg))
    if args.out:
        Path(args.out).write_text(render_markdown(result, reg), encoding="utf-8")
        print(f"\n[report written to {args.out}]", file=sys.stderr)
    return 0


def cmd_sources(args) -> int:
    reg = _load(args.statutes, Registry)
    pr = _load(args.precedents, Precedents)
    print(f"# Source inventory (statute data as of {reg.as_of}, precedent data as of {pr.as_of})\n")
    print("## Statutory sources")
    for s in reg.all():
        for src in s["sources"]:
            q = src.get("quality", "?")
            print(f"- [{s['id']}] {src['url']}")
            if src.get("quote"):
                print(f"    \"{src['quote'][:150]}\"")
            print(f"    quality: {q}; retrieved {src.get('retrieved', '?')}")
    print("\n## Precedent sources")
    for r in pr.records:
        src = r["source"]
        if isinstance(src, dict):
            print(f"- [{r['id']}] {src.get('url')} ({src.get('quality', '?')}, "
                  f"retrieved {src.get('retrieved', '?')})")
        else:
            print(f"- [{r['id']}] {src}")
    if args.verify_urls:
        import urllib.error
        import urllib.request
        print("\n## URL reachability check")
        urls = sorted({(s.get("url") if isinstance(s, dict) else s)
                       for r in pr.records for s in [r["source"]]} |
                      {src["url"] for s in reg.all() for src in s["sources"]})
        for u in urls:
            req = urllib.request.Request(u, method="HEAD",
                                         headers={"User-Agent": "penex-source-check/0.1"})
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    print(f"  {resp.status} {u}")
            except urllib.error.HTTPError as e:
                print(f"  {e.code} {u}")
            except Exception as e:  # noqa: BLE001
                print(f"  ERR {u} ({type(e).__name__})")
    return 0


def cmd_selfcheck(args) -> int:
    from .selfcheck import run_selfcheck
    return run_selfcheck()


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="penex",
        description="Statutory privacy-penalty exposure modeler (prototype). "
                    "Not legal advice.")
    p.add_argument("--version", action="version", version=f"penex {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("statutes", help="list statutory penalty ranges")
    s.add_argument("--regime", help="filter by regime substring (e.g. gdpr, ccpa, hipaa)")
    s.add_argument("--json", action="store_true")
    s.add_argument("--statutes")
    s.set_defaults(func=cmd_statutes)

    s = sub.add_parser("parse", help="parse a complaint / decision / verdict into per-violation counts")
    s.add_argument("file")
    s.add_argument("--jurisdiction", default="unknown")
    s.add_argument("--entity")
    s.add_argument("--sector")
    s.add_argument("--case-id")
    s.add_argument("--emit-case", help="write a draft case spec JSON for human review")
    s.add_argument("--json", action="store_true")
    s.add_argument("--statutes")
    s.set_defaults(func=cmd_parse)

    s = sub.add_parser("precedents", help="list decided matters and their outcomes")
    s.add_argument("--statute")
    s.add_argument("--jurisdiction")
    s.add_argument("--sector")
    s.add_argument("--json", action="store_true")
    s.add_argument("--precedents")
    s.set_defaults(func=cmd_precedents)

    s = sub.add_parser("model", help="compute the low/expected/max exposure band for a case")
    s.add_argument("case", help="case spec JSON")
    s.add_argument("--json", action="store_true")
    s.add_argument("--out", help="write the markdown report to this path")
    s.add_argument("--fx", action="append", default=[],
                   help="user-supplied rate, e.g. --fx EUR=1.09,USD (1 EUR = 1.09 USD)")
    s.add_argument("--statutes")
    s.add_argument("--precedents")
    s.set_defaults(func=cmd_model)

    s = sub.add_parser("sources", help="print the full source inventory for statutes and precedents")
    s.add_argument("--verify-urls", action="store_true",
                   help="also HEAD-check every source URL (needs network)")
    s.add_argument("--statutes")
    s.add_argument("--precedents")
    s.set_defaults(func=cmd_sources)

    s = sub.add_parser("factors", help="show the severity-factor weights used by the model")
    s.set_defaults(func=cmd_factors)

    s = sub.add_parser("selfcheck", help="validate data files, parser and model end to end")
    s.set_defaults(func=cmd_selfcheck)
    return p


def cmd_factors(args) -> int:
    print("Severity factor weights (applied multiplicatively to the statutory ceiling)\n")
    for name, w in FACTOR_WEIGHTS.items():
        sign = "+" if w["kind"] == "uplift" else "-"
        print(f"- {name}: {sign}{w['max']:.0%} max  |  {w['citation']}")
    print("\nInputs: true/false, 0-1 strength, or 0-100; plus 'duration_months' (uplift after 24 months).")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except DataError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"error: file not found: {e.filename}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
