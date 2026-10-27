"""Precedent store: decided enforcement actions, comparability scoring and ratio stats.

Precedents are the empirical half of the model.  Each record is a real, decided
matter with a source URL; records carry the statutory ceiling that applied at
the time where it can be stated, which lets the model compare outcomes as
*ratios to the statutory ceiling* rather than raw amounts (a $7,500-per-violation
statute and a "4% of worldwide turnover" statute are not comparable in absolute
terms).
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from .statutes import DATA_DIR, DataError

SECTOR_ALIASES = {
    "health": {"health", "health_app", "mental_health", "telehealth", "healthcare"},
    "social": {"social", "social_media", "social_network"},
    "retail": {"retail", "ecommerce", "e-commerce", "consumer_goods"},
    "kids": {"kids", "children", "edtech", "gaming_kids"},
    "adtech": {"adtech", "advertising", "marketing", "analytics"},
    "finance": {"finance", "fintech", "insurance"},
    "transport": {"transport", "mobility", "travel"},
    "telecom": {"telecom", "telco"},
}


def regime_family(text: str | None) -> str:
    """Coarse legal family of a regime / instrument, used to stop a children's
    privacy case being calibrated on health-privacy settlements.

    Deliberately blunt: it only has to be right about which shelf a regime sits
    on, and every widened match that relies on it is flagged as a partial match
    in the output.
    """
    t = (text or "").lower()
    if "gdpr" in t:
        return "gdpr"
    if "coppa" in t or "children" in t:
        return "childrens"
    if any(k in t for k in ("hipaa", "health breach", "my health my data",
                            "consumer health", "health privacy", "medical")):
        return "health"
    if "ccpa" in t or "california consumer privacy" in t:
        return "ccpa"
    if "caloppa" in t:
        return "ccpa"
    if "biometric" in t or "bipa" in t:
        return "biometric"
    if "unfair" in t or "ftc act" in t:
        return "ftc-act5"
    if "broker" in t:
        return "data-broker"
    if "comprehensive" in t:
        return "comprehensive-state"
    return t.strip() or "unknown"


def _sector_group(sector: str | None) -> str | None:
    if not sector:
        return None
    s = sector.lower().strip()
    for group, members in SECTOR_ALIASES.items():
        if s in members:
            return group
    return s


class Precedents:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DATA_DIR / "precedents.json"
        if not self.path.exists():
            raise DataError(f"precedent file not found: {self.path}")
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.as_of = raw.get("as_of")
        self.schema_version = raw.get("schema_version")
        self.notes = raw.get("notes", "")
        self.records: list[dict] = raw.get("precedents", [])
        self._validate()

    def _validate(self) -> None:
        ids = set()
        for r in self.records:
            for f in ("id", "entity", "jurisdiction", "decision_date", "amount",
                      "currency", "outcome_type", "source"):
                if f not in r:
                    raise DataError(f"precedent {r.get('id', '?')} missing field {f!r}")
            if r["id"] in ids:
                raise DataError(f"duplicate precedent id {r['id']}")
            ids.add(r["id"])
            if not (r.get("statute_ids") or r.get("instrument")):
                raise DataError(f"precedent {r['id']} cites no statute")
            src = r["source"]
            if isinstance(src, dict):
                if not src.get("url"):
                    raise DataError(f"precedent {r['id']} source has no url")
            elif not src:
                raise DataError(f"precedent {r['id']} has no source")

    def __len__(self) -> int:
        return len(self.records)

    def get(self, pid: str) -> dict:
        for r in self.records:
            if r["id"] == pid:
                return r
        raise DataError(f"unknown precedent id {pid!r}")

    def by_statute(self, statute_id: str) -> list[dict]:
        return [r for r in self.records if statute_id in (r.get("statute_ids") or [])]

    def by_jurisdiction(self, jurisdiction: str) -> list[dict]:
        j = jurisdiction.lower()
        return [r for r in self.records if j in (r.get("jurisdiction") or "").lower()]

    def by_sector(self, sector: str) -> list[dict]:
        j = sector.lower()
        return [r for r in self.records if j in (r.get("sector") or "").lower()]

    # -- comparability ------------------------------------------------------

    def score(self, record: dict, *, statute_ids: set[str], jurisdiction: str | None,
              sector: str | None, sector_only: bool = False) -> float:
        """Transparent comparability score (weights are documented in the README).

        A record that shares no statute with the query starts four points down, so
        a matching jurisdiction and sector alone can never lift it into the strict
        comparable set - that is what keeps federal health-privacy settlements out
        of a children's-privacy calibration.
        """
        score = 0.0
        rec_statutes = set(record.get("statute_ids") or [])
        if rec_statutes & statute_ids:
            score += 3.0
            if record.get("statute_ids") and statute_ids and (
                    set(record["statute_ids"]) <= statute_ids or statute_ids <= rec_statutes):
                score += 1.0
        elif not sector_only:
            score -= 4.0
        if jurisdiction and record.get("jurisdiction"):
            if jurisdiction.lower() == record["jurisdiction"].lower():
                score += 2.0
            elif jurisdiction.split("-")[0].lower() in record["jurisdiction"].lower():
                score += 1.0
        if sector:
            rs, cs = _sector_group(record.get("sector")), _sector_group(sector)
            if rs and cs and rs == cs:
                score += 1.0
        # decided matters are more informative than pending ones
        if "annul" in (record.get("status") or "").lower():
            score -= 1.0
        if (record.get("amount") or 0) <= 0:
            score -= 1.0
        return score

    def families_of(self, record: dict, record_families: dict[str, str] | None = None) -> set[str]:
        fam = set()
        for sid in (record.get("statute_ids") or []):
            if record_families and sid in record_families:
                fam.add(record_families[sid])
        if not fam:
            fam.add(regime_family(record.get("instrument") or record.get("jurisdiction")))
        return fam

    def comparables(self, *, statute_ids: set[str], jurisdiction: str | None = None,
                    sector: str | None = None, min_score: float = 1.0,
                    limit: int = 12, include_partial: bool = True,
                    families: set[str] | None = None,
                    record_families: dict[str, str] | None = None) -> list[dict]:
        """Rank precedents by comparability.

        Strict set: shares a statute with the query.  If that is empty, and
        ``include_partial`` is set, the set is widened to matters from the same
        legal *family* that also share the jurisdiction or the sector - every such
        record is returned flagged ``partial_match`` so the report cannot present
        it as a like-for-like comparison.
        """
        scored = []
        for r in self.records:
            s = self.score(r, statute_ids=statute_ids, jurisdiction=jurisdiction, sector=sector)
            scored.append((s, r))
        scored.sort(key=lambda x: (-x[0], x[1]["decision_date"]))
        strict = [(s, r) for s, r in scored if s >= min_score]
        if not strict and include_partial:
            for s, r in scored:
                fam_hit = bool(families) and bool(families & self.families_of(r, record_families))
                jur_hit = bool(jurisdiction) and jurisdiction.lower() == \
                    (r.get("jurisdiction") or "").lower()
                sec_hit = bool(sector) and _sector_group(sector) == _sector_group(r.get("sector"))
                if fam_hit and (jur_hit or sec_hit):
                    strict.append((s, r))
        out = []
        for s, r in strict[:limit]:
            rec = dict(r)
            rec["match_score"] = round(s, 2)
            rec["partial_match"] = s < 3.0
            out.append(rec)
        return out

    @staticmethod
    def stats(records: list[dict]) -> dict:
        """Award distribution and award-to-ceiling ratios for a comparable set."""
        awards = [float(r["amount"]) for r in records if r.get("amount")]
        ratios = []
        for r in records:
            cap = r.get("statutory_cap_at_decision")
            if cap and float(cap) > 0 and r.get("amount"):
                ratios.append(float(r["amount"]) / float(cap))
        out = {
            "n": len(records),
            "n_with_amount": len(awards),
            "n_with_cap": len(ratios),
            "awards": _pcts(awards),
            "ratios": _pcts(ratios),
            "sectors": sorted({(r.get("sector") or "unknown") for r in records}),
            "date_range": [min((r["decision_date"] for r in records), default=None),
                           max((r["decision_date"] for r in records), default=None)],
            "outcome_types": sorted({r.get("outcome_type") or "unknown" for r in records}),
        }
        return out


def _pcts(values: list[float]) -> dict | None:
    if not values:
        return None
    vs = sorted(values)

    def q(p: float) -> float:
        if len(vs) == 1:
            return vs[0]
        k = (len(vs) - 1) * p
        lo, hi = int(k), min(int(k) + 1, len(vs) - 1)
        return vs[lo] + (vs[hi] - vs[lo]) * (k - lo)

    return {
        "min": vs[0], "p25": q(0.25), "median": statistics.median(vs),
        "p75": q(0.75), "p90": q(0.90), "max": vs[-1],
        "mean": statistics.fmean(vs), "n": len(vs),
    }
