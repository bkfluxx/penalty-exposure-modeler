"""Statute registry: statutory penalty ranges, aggregation rules and citation patterns.

Everything the model needs about *statutes* lives in ``data/statutes.json``; this
module only loads, validates and applies it.  Keeping the legal content in data
(not code) means a compliance professional can update or extend the registry
without touching Python.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class DataError(Exception):
    """Raised when a registry / case file is malformed."""


# --------------------------------------------------------------------------- #
# currency handling
# --------------------------------------------------------------------------- #

def parse_fx(pairs: Iterable[str]) -> dict[tuple[str, str], float]:
    """Parse ``--fx EUR=1.09`` style arguments.

    Convention: ``A=X`` means **1 A = X B**, where B is the currency of the
    *case* turnover (the model refuses to guess, so the user always states the
    direction).  Rates are supplied by the user and never invented by the tool.
    """
    fx: dict[tuple[str, str], float] = {}
    for p in pairs or []:
        if "=" not in p:
            raise DataError(f"--fx expects FROM=RATE form, got {p!r}")
        code, rate = p.split("=", 1)
        # 'EUR=1.09,USD' -> 1 EUR = 1.09 USD
        parts = [x.strip() for x in rate.split(",") if x.strip()]
        if len(parts) == 1:
            fx[(code.strip().upper(), "CASE")] = float(parts[0])
        elif len(parts) == 2:
            fx[(code.strip().upper(), parts[1].upper())] = float(parts[0])
        else:
            raise DataError(f"--fx malformed: {p!r}")
    return fx


def convert(amount: float, src: str, dst: str, fx: dict[tuple[str, str], float]) -> tuple[float, str]:
    """Convert ``amount`` from ``src`` to ``dst``; raises if no rate is known."""
    src, dst = src.upper(), dst.upper()
    if src == dst:
        return amount, f"1 {src}"
    if (src, dst) in fx:
        return amount * fx[(src, dst)], f"user-supplied 1 {src} = {fx[(src, dst)]} {dst}"
    if (dst, src) in fx:
        return amount / fx[(dst, src)], f"user-supplied 1 {dst} = {fx[(dst, src)]} {src}"
    raise DataError(
        f"no FX rate for {src}->{dst}; supply one with --fx {src}=<rate>,{dst} "
        "(rates are user-supplied, never assumed by the tool)"
    )


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #

@dataclass
class Cap:
    """The applicable statutory ceiling for one charged violation."""
    min_amount: float | None
    max_amount: float | None
    currency: str
    basis: str
    aggregation: dict = field(default_factory=dict)
    warning: str | None = None

    def as_dict(self) -> dict:
        d = {
            "min": self.min_amount,
            "max": self.max_amount,
            "currency": self.currency,
            "basis": self.basis,
            "aggregation_rule": (self.aggregation or {}).get("rule"),
            "aggregation_citation": (self.aggregation or {}).get("citation"),
        }
        if self.warning:
            d["warning"] = self.warning
        return d


class Registry:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else DATA_DIR / "statutes.json"
        if not self.path.exists():
            raise DataError(f"statute registry not found: {self.path}")
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.as_of = raw.get("as_of")
        self.schema_version = raw.get("schema_version")
        self.notes = raw.get("notes", "")
        self._statutes = {s["id"]: s for s in raw.get("statutes", [])}
        if not self._statutes:
            raise DataError("statute registry is empty")
        self._validate()

    # -- basic access -------------------------------------------------------

    def _validate(self) -> None:
        required = {"id", "name", "regime", "jurisdiction", "citation",
                    "penalty_model", "currency", "sources"}
        models = {"fixed_or_turnover", "per_violation", "per_violation_per_day",
                  "per_violation_tiered", "per_consumer_range"}
        for sid, s in self._statutes.items():
            missing = required - set(s)
            if missing:
                raise DataError(f"statute {sid} missing fields: {sorted(missing)}")
            if s["penalty_model"] not in models:
                raise DataError(f"statute {sid} has unknown penalty_model {s['penalty_model']!r}")
            if not s["sources"]:
                raise DataError(f"statute {sid} has no sources (citation must be traceable)")
            if s["penalty_model"] == "fixed_or_turnover":
                if "fixed_cap" not in s or "turnover_pct_cap" not in s:
                    raise DataError(f"statute {sid}: fixed_or_turnover needs fixed_cap + turnover_pct_cap")
            if s["penalty_model"] == "per_violation" and "per_violation_amount" not in s:
                raise DataError(f"statute {sid}: per_violation needs per_violation_amount")
            if s["penalty_model"] == "per_violation_tiered" and not s.get("tiers"):
                raise DataError(f"statute {sid}: per_violation_tiered needs tiers")

    def __len__(self) -> int:
        return len(self._statutes)

    def ids(self) -> list[str]:
        return list(self._statutes)

    def all(self) -> list[dict]:
        return list(self._statutes.values())

    def get(self, statute_id: str) -> dict:
        try:
            return self._statutes[statute_id]
        except KeyError:
            raise DataError(
                f"unknown statute_id {statute_id!r}; known ids: {', '.join(sorted(self._statutes))}"
            ) from None

    def by_regime(self, regime: str) -> list[dict]:
        r = regime.lower()
        return [s for s in self._statutes.values() if r in s["regime"].lower()]

    def citation_patterns(self) -> list[tuple[str, re.Pattern]]:
        """(statute_id, compiled pattern) pairs used by the complaint parser."""
        out = []
        for sid, s in self._statutes.items():
            for pat in s.get("citation_patterns", []):
                out.append((sid, re.compile(pat, re.I)))
        return out

    # -- statutory ceiling --------------------------------------------------

    def ceiling(
        self,
        statute_id: str,
        *,
        count: int | None = None,
        turnover: float | None = None,
        turnover_currency: str | None = None,
        tier: str | None = None,
        intentional: bool = False,
        under_16: bool = False,
        days: int | None = None,
        fx: dict | None = None,
    ) -> Cap:
        """Apply the statutory range for one charged violation.

        ``count`` is the number of alleged violations (individuals, records,
        scans, days...).  For per-violation regimes a missing count is treated
        as 1 and a warning is emitted, because the number is materially
        sensitive and a reviewer must be able to see the assumption.
        """
        s = self.get(statute_id)
        model = s["penalty_model"]
        agg = s.get("aggregation", {})
        warn = None
        cnt = count if (count is not None and count > 0) else None
        if cnt is None and model != "fixed_or_turnover":
            cnt = 1
            warn = ("no per-violation count supplied; ceiling computed for a single "
                    "violation (count=1 assumed)")

        if model == "fixed_or_turnover":
            cap = float(s["fixed_cap"])
            basis = f"statutory cap {cap:,.0f} {s['currency']}"
            if turnover:
                tcur = (turnover_currency or s["currency"]).upper()
                t = turnover
                if tcur != s["currency"].upper():
                    t, how = convert(turnover, tcur, s["currency"], fx or {})
                    basis += f"; turnover converted ({how})"
                pct_cap = float(s["turnover_pct_cap"]) * t
                if pct_cap > cap:
                    cap = pct_cap
                    basis = (f"{s['turnover_pct_cap']:.1%} of {t:,.0f} "
                             f"{s['currency']} turnover = {pct_cap:,.0f} {s['currency']} "
                             f"(exceeds fixed cap of {float(s['fixed_cap']):,.0f})")
                else:
                    basis += f" (turnover-linked cap {pct_cap:,.0f} was lower)"
            else:
                warn = ("no turnover supplied: ceiling is the fixed statutory amount only; "
                        "for an undertaking the turnover-linked cap may be higher "
                        f"({float(s['turnover_pct_cap']):.0%} of worldwide annual turnover)")
            return Cap(float(s.get("min_amount") or 0.0), cap, s["currency"], basis,
                       agg, warn)

        if model == "per_violation":
            per = float(s["per_violation_amount"])
            if under_16 and s.get("per_violation_amount_under_16"):
                per = float(s["per_violation_amount_under_16"])
            elif intentional and s.get("per_violation_amount_intentional"):
                per = float(s["per_violation_amount_intentional"])
            total = per * cnt
            basis = f"{cnt:,} violation(s) x {per:,.0f} {s['currency']} per violation"
            cap = total
            if s.get("aggregate_cap"):
                cap = min(total, float(s["aggregate_cap"]))
                basis += f"; statutory aggregate cap {float(s['aggregate_cap']):,.0f}"
            return Cap(float(s.get("per_violation_min") or 0.0) * cnt, cap,
                       s["currency"], basis, agg, warn)

        if model == "per_violation_per_day":
            per = float(s["per_violation_amount"])
            d = days or 1
            if days is None:
                warn = ("per-day statute: no number of days supplied; computed for 1 day")
            total = per * cnt * d
            return Cap(float(s.get("per_violation_min") or 0.0) * cnt * d, total,
                       s["currency"],
                       f"{cnt:,} violation(s) x {d} day(s) x {per:,.0f} {s['currency']} "
                       f"per violation per day", agg, warn)

        if model == "per_violation_tiered":
            tiers = {t["id"]: t for t in s["tiers"]}
            key = tier or s.get("default_tier") or list(tiers)[-1]
            if key not in tiers:
                raise DataError(f"statute {statute_id}: unknown tier {key!r}; "
                                f"known tiers: {', '.join(tiers)}")
            t = tiers[key]
            total_max = float(t["per_violation_max"]) * cnt
            total_min = float(t["per_violation_min"]) * cnt
            basis = (f"tier {key} ({t['when']}): {cnt:,} violation(s) x "
                     f"{float(t['per_violation_min']):,.0f}-{float(t['per_violation_max']):,.0f} "
                     f"{s['currency']} per violation")
            if s.get("annual_cap"):
                ac = float(s["annual_cap"])
                if total_max > ac:
                    total_max = ac
                    basis += f"; capped at annual limit {ac:,.0f} {s['currency']}"
            return Cap(total_min, total_max, s["currency"], basis, agg, warn)

        if model == "per_consumer_range":
            lo = float(s["per_violation_min"]) * cnt
            hi = float(s["per_violation_max"]) * cnt
            return Cap(lo, hi, s["currency"],
                       f"{cnt:,} consumer(s) x {float(s['per_violation_min']):,.0f}-"
                       f"{float(s['per_violation_max']):,.0f} {s['currency']} "
                       f"(statutory damages range, per consumer per incident)",
                       agg, warn)

        raise DataError(f"unhandled penalty_model {model!r}")  # pragma: no cover
