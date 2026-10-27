"""Markdown rendering of model output - the one-page deliverable a compliance
buyer actually reads."""
from __future__ import annotations

from .statutes import Registry


def money(x, currency: str) -> str:
    if x is None:
        return "n/a"
    return f"{x:,.0f} {currency}"


def _fmt_ratio_band(band: dict | None) -> str:
    if not band:
        return "n/a"
    return (f"p25 {band.get('p25', 0):.3f} / median {band.get('median', 0):.3f} / "
            f"p90 {band.get('p90', 0):.3f} (n={band.get('n')})")


def render_markdown(result: dict, registry: Registry) -> str:
    L: list[str] = []
    a = L.append
    band = result.get("case_band") or {}
    cur = band.get("currency", "")

    a(f"# Penalty exposure estimate - {result.get('entity') or result.get('case_id')}")
    a("")
    a(f"*Case* `{result.get('case_id')}`  |  *Jurisdiction* {result.get('jurisdiction')}  |  "
      f"*Statute data as of* {result.get('as_of')}")
    a("")
    if band:
        a("## Exposure band")
        a("")
        a("| | Amount |")
        a("|---|---|")
        a(f"| Low | {money(band.get('low'), cur)} |")
        a(f"| **Expected** | **{money(band.get('expected'), cur)}** |")
        a(f"| Maximum (statutory ceiling) | {money(band.get('max'), cur)} |")
        a("")
        a(f"Confidence: **{result['confidence']['level']}**")
        a("")
        for r in result["confidence"]["reasons"]:
            a(f"- {r}")
    else:
        a("## Exposure band")
        a("")
        a("Case-level total suppressed (mixed currencies without FX rates). Per-currency subtotals:")
        a("")
        a("| Currency | Low | Expected | Max |")
        a("|---|---|---|---|")
        for c, s in result.get("subtotals", {}).items():
            a(f"| {c} | {money(s['low'], c)} | {money(s['expected'], c)} | {money(s['max'], c)} |")
    a("")

    if result.get("aggregation_notes"):
        a("**Aggregation rules applied**")
        a("")
        for n in result["aggregation_notes"]:
            a(f"- {n}")
        a("")

    if result.get("contributions") and len(result["contributions"]) > 1:
        a("### How the case total is built")
        a("")
        a("| Contribution | Low | Expected | Max |")
        a("|---|---|---|---|")
        for c in result["contributions"]:
            cur = c["currency"]
            a(f"| {c['label']} | {money(c['low'], cur)} | {money(c['expected'], cur)} | "
              f"{money(c['max'], cur)} |")
        a("")

    a("## Per-violation detail")
    a("")
    for pv in result["violations"]:
        b = pv["band"]
        a(f"### {pv['citation']} - {pv['statute_name']}")
        a("")
        a(f"- Jurisdiction: {pv['jurisdiction']}")
        a(f"- Per-violation count used: **{pv['count'] if pv['count'] is not None else 'not stated (1 assumed)'}**")
        a(f"- Statutory ceiling: {money(pv['ceiling']['max'], b['currency'])}  ")
        a(f"  basis: {pv['ceiling']['basis']}")
        if pv["ceiling"].get("aggregation_rule"):
            a(f"- Aggregation rule: `{pv['ceiling']['aggregation_rule']}` "
              f"({pv['ceiling'].get('aggregation_citation')})")
        a(f"- Band: low {money(b['low'], b['currency'])}  /  "
          f"expected {money(b['expected'], b['currency'])}  /  max {money(b['max'], b['currency'])}")
        a(f"- Calibration ({pv.get('calibration_mode', 'default')}): {pv['calibration']}")
        c = pv["comparables"]
        if c.get("ids"):
            a(f"- Comparables used ({c['n']}): {', '.join(c['ids'])}"
              f"{' (widened/partial match)' if c.get('partial_match') else ''}")
            if c.get("ratio_band"):
                a(f"- Observed award/ceiling ratios: {_fmt_ratio_band(c['ratio_band'])}")
            if c.get("award_band"):
                ab = c["award_band"]
                a(f"- Observed awards: median {ab['median']:,.0f}, p90 {ab['p90']:,.0f} "
                  f"(min {ab['min']:,.0f}, max {ab['max']:,.0f})")
        else:
            a("- Comparables used: none")
        for n in pv["notes"]:
            a(f"- Note: {n}")
        a("")

    pv = result.get("precedent_view") or {}
    a("## Precedent view")
    a("")
    a(f"- Comparable matters: {pv.get('n_comparables')} ({', '.join(pv.get('ids') or []) or 'none'})")
    a(f"- Observed award/ceiling ratios across those matters: {_fmt_ratio_band(pv.get('ratio_band'))}")
    ab = pv.get("award_band")
    if ab:
        a(f"- Observed awards: median {ab['median']:,.0f}, p25 {ab['p25']:,.0f}, "
          f"p90 {ab['p90']:,.0f} (n={ab['n']})")
    a(f"- Method: {pv.get('method')}")
    a("")

    if result.get("factor_trace"):
        a("## Severity factors applied")
        a("")
        a("| Factor | Strength | Effect | Authority |")
        a("|---|---|---|---|")
        for f in result["factor_trace"]:
            a(f"| {f['factor']} | {f.get('strength')} | {f.get('effect')} | "
              f"{f.get('citation') or f.get('note') or ''} |")
        a(f"| **combined** | | **x{result['factor_multiplier']}** | |")
        a("")

    if result.get("warnings"):
        a("## Warnings")
        a("")
        for w in result["warnings"]:
            a(f"- {w}")
        a("")

    a("## Method and limits")
    a("")
    a("- *Maximum* is the statutory ceiling for the charge as pleaded, after statutory "
      "aggregation rules; it is a legal ceiling, not a forecast.")
    a("- *Expected* and *low* apply the case's severity-factor multiplier to the ceiling and a "
      "ratio calibrated on comparable decided matters (median / 25th percentile of "
      "award-to-ceiling ratios).")
    a("- Precedents are matched on statute, jurisdiction and sector; partial matches are flagged.")
    a(f"- {result.get('disclaimer')}")
    a("")
    return "\n".join(L)
