"""Rule-based extraction of violations from complaints, penalty notices and verdicts.

Given a text file (an AG/DPA complaint, a regulator's decision, or a court
judgment) the parser produces:

* ``citations``  - statutory provisions cited, normalised against the registry,
* ``counts``     - per-violation counts with the exact phrase they came from,
* ``amounts``    - monetary penalties mentioned (useful for turning a decided
                    case into a new precedent record),
* ``violations`` - a draft per-violation list ready for the exposure model.

Every extraction carries its evidence span and a confidence score, so nothing
has to be taken on trust.  The parser is deliberately conservative: it never
infers a count that is not written in the text, and it flags what it could not
resolve.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

from .statutes import Registry

# --------------------------------------------------------------------------- #
# building blocks
# --------------------------------------------------------------------------- #

_NUM = r"(\d{1,3}(?:[,\u00a0 ]\d{3})+|\d+(?:[.,]\d+)?)"
_MULT = r"(thousand|million|billion|bn|mn|k|m)"
_MULTIPLIERS = {
    "thousand": 1_000, "k": 1_000,
    "million": 1_000_000, "mn": 1_000_000, "m": 1_000_000,
    "billion": 1_000_000_000, "bn": 1_000_000_000,
}

SUBJECT_NOUNS = (
    r"(?:data subjects?|users?|consumers?|individuals?|customers?|persons?|people|"
    r"residents?|account holders?|guests?|patients?|minors|children|employees|"
    r"members|drivers|subscribers|students|records?|accounts?|data sets?)"
)

COUNT_PATTERNS: list[tuple[str, re.Pattern, float]] = [
    ("subjects", re.compile(rf"{_NUM}\s*{_MULT}?\s*{SUBJECT_NOUNS}\b", re.I), 0.85),
    ("separate_offences",
     re.compile(rf"{_NUM}\s*{_MULT}?\s*(?:separate\s+)?(?:violations|infringements|"
                r"instances|occasions|scans|uploads|disclosures)\b", re.I), 0.8),
    ("affecting",
     re.compile(rf"affect(?:ing|ed)\s+(?:approximately\s+|about\s+|some\s+)?"
                rf"{_NUM}\s*{_MULT}?", re.I), 0.6),
    ("class_size", re.compile(rf"class of\s+{_NUM}\s*{_MULT}?", re.I), 0.6),
    ("each_of", re.compile(rf"for each of\s+(?:the\s+)?{_NUM}\b", re.I), 0.5),
]

AMOUNT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("amount",
     re.compile(rf"(?:EUR|USD|GBP|€|\$|£)\s?{_NUM}\s*{_MULT}?", re.I)),
    ("amount_words",
     re.compile(rf"(?:fine|penalty|penalties|pay|payment|settle(?:ment)? of|sum of)\s+"
                rf"(?:of\s+|up to\s+|not more than\s+)?(?:EUR|USD|GBP|€|\$|£)?\s?"
                rf"{_NUM}\s*{_MULT}?", re.I)),
]

CURRENCY_SYMBOLS = {"€": "EUR", "eur": "EUR", "$": "USD", "usd": "USD",
                     "£": "GBP", "gbp": "GBP"}

# a "violation unit" marker: tells the model/analyst what the count refers to
UNIT_MARKERS = {
    "per_scan": re.compile(r"(per scan|each scan|every scan|each time|per individual)", re.I),
    "per_person": re.compile(r"(per person|per consumer|per individual|per data subject)", re.I),
    "per_day": re.compile(r"(per day|each day|daily)", re.I),
    "per_record": re.compile(r"(per record|per account)", re.I),
}


@dataclass
class Citation:
    statute_id: str | None
    text: str
    context: str
    paragraph: int


@dataclass
class Count:
    value: int | None
    kind: str
    phrase: str
    confidence: float
    paragraph: int
    raw: str


@dataclass
class Amount:
    value: float
    currency: str | None
    phrase: str
    paragraph: int


def _to_int(raw: str, mult: str | None) -> int | None:
    s = raw.replace("\u00a0", "").replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", s):
        s = s.replace(",", "")
    else:
        # handle decimal comma / dot: keep first separator as decimal point
        s = s.replace(",", ".")
    try:
        val = float(s)
    except ValueError:
        return None
    if mult:
        val *= _MULTIPLIERS.get(mult.lower(), 1)
    return int(round(val))


def _paragraphs(text: str) -> list[str]:
    text = text.replace("\r\n", "\n")
    parts = re.split(r"\n\s*\n|(?:(?<=\n)\s*\d{1,3}\.\s+)", text)
    return [p.strip() for p in parts if p.strip()]


def _context(text: str, start: int, end: int, pad: int = 90) -> str:
    a = max(0, start - pad)
    b = min(len(text), end + pad)
    return re.sub(r"\s+", " ", text[a:b]).strip()


# --------------------------------------------------------------------------- #
# main entry points
# --------------------------------------------------------------------------- #

def parse_text(text: str, registry: Registry) -> dict:
    """Extract citations, per-violation counts and amounts from ``text``."""
    patterns = registry.citation_patterns()
    paragraphs = _paragraphs(text)

    citations: list[Citation] = []
    counts: list[Count] = []
    amounts: list[Amount] = []

    # paragraph-level citation context for de-duplication
    for pi, para in enumerate(paragraphs):
        for sid, pat in patterns:
            for m in pat.finditer(para):
                citations.append(Citation(sid, m.group(0), _context(para, m.start(), m.end()), pi))
        for kind, pat, conf in COUNT_PATTERNS:
            for m in pat.finditer(para):
                raw, mult = m.group(1), (m.group(2) if m.groups() and len(m.groups()) > 1 else None)
                value = _to_int(raw, mult)
                # a bare year or article number is not a count
                if value is not None and 1900 <= value <= 2100 and mult is None:
                    continue
                counts.append(Count(value, kind, _context(para, m.start(), m.end()),
                                    conf, pi, m.group(0)))
        for kind, pat in AMOUNT_PATTERNS:
            for m in pat.finditer(para):
                raw = m.group(1)
                mult = m.group(2) if (m.groups() and len(m.groups()) > 1) else None
                value = _to_int(raw, mult)
                if value is None:
                    continue
                head = para[max(0, m.start() - 12):m.start() + len(m.group(0))]
                cur = None
                for sym, code in CURRENCY_SYMBOLS.items():
                    if sym.lower() in head.lower():
                        cur = code
                        break
                amounts.append(Amount(float(value), cur, _context(para, m.start(), m.end()), pi))

    # per-paragraph violation units
    violations: list[dict] = []
    by_para: dict[int, dict] = {}
    counts_by_para: dict[int, list[Count]] = {}
    for c in counts:
        counts_by_para.setdefault(c.paragraph, []).append(c)
    for c in citations:
        slot = by_para.setdefault(c.paragraph, {"paragraph": c.paragraph, "citations": [], "counts": [], "units": []})
        if c.statute_id not in [x["statute_id"] for x in slot["citations"]]:
            slot["citations"].append({"statute_id": c.statute_id, "text": c.text})
    for c in counts:
        if c.paragraph in by_para:
            by_para[c.paragraph]["counts"].append(c)
    for pi, slot in by_para.items():
        para = paragraphs[pi]
        for unit, pat in UNIT_MARKERS.items():
            if pat.search(para):
                slot["units"].append(unit)

    def _best_count(cands: list[Count]) -> Count | None:
        for c in sorted(cands, key=lambda x: (-x.confidence, -(x.value or 0))):
            if c.value:
                return c
        return None

    for pi in sorted(by_para):
        slot = by_para[pi]
        best = _best_count(slot["counts"])
        carried_from = None
        if best is None:
            # A pleading often states the population in one paragraph and the
            # provision it breaches in the next.  Carry the nearest earlier count
            # rather than reporting nothing - but flag it and discount it, because
            # the link is the parser's inference, not the document's assertion.
            for back in range(pi - 1, max(-1, pi - 3), -1):
                cand = _best_count(counts_by_para.get(back, []))
                if cand:
                    best, carried_from = cand, back
                    break
        for cit in slot["citations"]:
            entry = {
                "statute_id": cit["statute_id"],
                "citation": cit["text"],
                "count": best.value if best else None,
                "count_kind": best.kind if best else None,
                "count_evidence": best.phrase if best else None,
                "count_confidence": (best.confidence * (0.6 if carried_from is not None else 1.0))
                                    if best else 0.0,
                "count_source": (f"carried from paragraph {carried_from + 1} of the split text "
                                 "(citing paragraph states no count)") if carried_from is not None
                                else "citing paragraph",
                "units": slot["units"],
                "paragraph": pi,
                "source": f"paragraph {pi + 1}",
            }
            violations.append(entry)

    unresolved = [c for c in citations if not c.statute_id]

    return {
        "citations": [asdict(c) for c in citations],
        "unmatched_citations": [asdict(c) for c in unresolved],
        "counts": [asdict(c) for c in counts],
        "amounts": [asdict(a) for a in amounts],
        "violations": violations,
        "summary": {
            "paragraphs": len(paragraphs),
            "citations": len(citations),
            "matched_citations": len(citations) - len(unresolved),
            "counts": len(counts),
            "amounts": len(amounts),
            "draft_violations": len(violations),
        },
    }


def draft_case_spec(parsed: dict, *, case_id: str, entity: str, jurisdiction: str,
                    registry: Registry, turnover: float | None = None,
                    turnover_currency: str = "EUR", sector: str | None = None,
                    source_file: str | None = None) -> dict:
    """Turn parser output into a case spec the model can consume.

    The draft is intentionally conservative: counts with confidence < 0.5 are
    left as ``null`` so the model flags them instead of silently assuming a
    number of violations.
    """
    seen: set[str] = set()
    violations = []
    for v in parsed.get("violations", []):
        sid = v.get("statute_id")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        count = v.get("count") if (v.get("count_confidence") or 0) >= 0.5 else None
        violations.append({
            "statute_id": sid,
            "citation": v.get("citation"),
            "count": count,
            "count_basis": v.get("count_evidence"),
            "notes": (f"parser confidence {v.get('count_confidence', 0):.2f}; "
                      f"count source: {v.get('count_source', 'n/a')}; "
                      f"units detected: {', '.join(v.get('units') or []) or 'n/a'}"),
        })
    return {
        "case_id": case_id,
        "entity": {
            "name": entity,
            "sector": sector,
            "global_annual_turnover": ({"amount": turnover, "currency": turnover_currency}
                                       if turnover else None),
        },
        "jurisdiction": jurisdiction,
        "alleged_violations": violations,
        "factors": {},
        "provenance": {
            "mode": "drafted from complaint text by penex.parser",
            "source_file": source_file,
            "review_required": True,
            "checked": ["statute citations", "per-violation counts"],
            "not_checked": ["legal characterisation", "count accuracy against exhibits"],
        },
    }


def parse_decision_amounts(parsed: dict, registry: Registry) -> list[dict]:
    """Largest monetary figures mentioned, normalised - a first pass at turning a
    decided case into a precedent record (a human still has to confirm what the
    figure refers to)."""
    out = []
    for a in sorted(parsed.get("amounts", []), key=lambda x: -x["value"]):
        out.append({"amount": a["value"], "currency": a["currency"], "evidence": a["phrase"]})
    return out
