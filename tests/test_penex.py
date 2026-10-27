"""Unit tests for the PenaltyExposure modeler.

    python3 -m unittest discover -s tests -t . -v      (from the repo root)
"""
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from penex import Precedents, Registry, model_case, parse_text, render_markdown  # noqa: E402
from penex.cli import main  # noqa: E402
from penex.model import factor_multiplier  # noqa: E402
from penex.statutes import DataError  # noqa: E402

REG = Registry()
PR = Precedents()
EX = ROOT / "examples"


class TestStatutoryRanges(unittest.TestCase):
    def test_gdpr_fixed_cap_binds_for_small_turnover(self):
        cap = REG.ceiling("gdpr-art83-5", turnover=100_000_000, turnover_currency="EUR")
        self.assertAlmostEqual(cap.max_amount, 20_000_000)

    def test_gdpr_turnover_cap_binds_for_large_turnover(self):
        cap = REG.ceiling("gdpr-art83-5", turnover=2_000_000_000, turnover_currency="EUR")
        self.assertAlmostEqual(cap.max_amount, 80_000_000)
        self.assertIn("4.0%", cap.basis)

    def test_lower_tier_is_half_the_higher_tier(self):
        hi = REG.ceiling("gdpr-art83-5", turnover=2_000_000_000, turnover_currency="EUR")
        lo = REG.ceiling("gdpr-art83-4", turnover=2_000_000_000, turnover_currency="EUR")
        self.assertAlmostEqual(lo.max_amount, hi.max_amount / 2)

    def test_currency_mismatch_is_refused_not_guessed(self):
        with self.assertRaises(DataError):
            REG.ceiling("gdpr-art83-5", turnover=100_000_000, turnover_currency="USD")

    def test_missing_turnover_warns(self):
        cap = REG.ceiling("gdpr-art83-5")
        self.assertAlmostEqual(cap.max_amount, 20_000_000)
        self.assertIsNotNone(cap.warning)

    def test_ccpa_per_violation(self):
        self.assertAlmostEqual(REG.ceiling("ccpa-ag-1798.155", count=1000).max_amount, 2_500_000)
        self.assertAlmostEqual(
            REG.ceiling("ccpa-ag-1798.155", count=1000, intentional=True).max_amount, 7_500_000)

    def test_ccpa_private_right_range(self):
        cap = REG.ceiling("ccpa-1798.150", count=1000)
        self.assertAlmostEqual(cap.min_amount, 100_000)
        self.assertAlmostEqual(cap.max_amount, 750_000)

    def test_hipaa_annual_cap_binds(self):
        cap = REG.ceiling("hipaa-160404", count=100, tier="tier4")
        self.assertAlmostEqual(cap.max_amount, 2_190_294)
        self.assertIn("annual limit", cap.basis)

    def test_hipaa_tier_floor(self):
        cap = REG.ceiling("hipaa-160404", count=100, tier="tier1")
        self.assertAlmostEqual(cap.min_amount, 145 * 100)

    def test_per_day_statute(self):
        cap = REG.ceiling("ftc-hbnr", count=10, days=5)
        self.assertAlmostEqual(cap.max_amount, 53_088 * 10 * 5)
        cap = REG.ceiling("ftc-hbnr", count=10)
        self.assertIsNotNone(cap.warning)

    def test_texas_and_coppa_and_uk(self):
        self.assertAlmostEqual(REG.ceiling("texas-cubi-503001", count=10_000).max_amount, 250_000_000)
        self.assertAlmostEqual(REG.ceiling("coppa-ftc-5l", count=10).max_amount, 530_880)
        self.assertAlmostEqual(
            REG.ceiling("uk-gdpr-higher", turnover=1_000_000_000, turnover_currency="GBP").max_amount,
            40_000_000)

    def test_missing_count_assumed_one_and_flagged(self):
        cap = REG.ceiling("ccpa-ag-1798.155")
        self.assertAlmostEqual(cap.max_amount, 2_500)
        self.assertIn("count=1 assumed", cap.warning)


class TestParser(unittest.TestCase):
    def setUp(self):
        self.text = (EX / "complaint_fixture_gdpr_transfers.txt").read_text(encoding="utf-8")
        self.parsed = parse_text(self.text, REG)

    def test_matches_tier_citations(self):
        ids = {v["statute_id"] for v in self.parsed["violations"]}
        self.assertIn("gdpr-art83-5", ids)
        self.assertIn("gdpr-art83-4", ids)

    def test_extracts_large_counts(self):
        values = {c["value"] for c in self.parsed["counts"]}
        self.assertIn(533_000_000, values)
        self.assertIn(4_200_000, values)

    def test_every_count_carries_evidence(self):
        for c in self.parsed["counts"]:
            self.assertTrue(c["phrase"])
            self.assertGreater(c["confidence"], 0)

    def test_does_not_invent_counts(self):
        parsed = parse_text("The respondent infringed Article 46(1) GDPR.", REG)
        self.assertEqual(parsed["counts"], [])
        for v in parsed["violations"]:
            self.assertIsNone(v["count"])

    def test_amounts_are_normalised(self):
        parsed = parse_text("The authority imposed a fine of EUR 225 million on the respondent.", REG)
        self.assertTrue(any(a["value"] == 225_000_000 and a["currency"] == "EUR"
                            for a in parsed["amounts"]))

    def test_count_is_carried_to_a_following_citation_paragraph_and_flagged(self):
        text = (EX / "complaint_fixture_ccpa_ag.txt").read_text(encoding="utf-8")
        parsed = parse_text(text, REG)
        ccpa = next(v for v in parsed["violations"] if v["statute_id"] == "ccpa-ag-1798.155")
        self.assertEqual(ccpa["count"], 3_400_000)
        self.assertIn("carried from paragraph", ccpa["count_source"])
        self.assertLess(ccpa["count_confidence"], 0.85)   # discounted, because it is inferred

    def test_draft_case_spec_is_conservative(self):
        from penex.parser import draft_case_spec
        spec = draft_case_spec(self.parsed | {"violations": [
            {"statute_id": "gdpr-art83-5", "citation": "Art. 83(5)", "count": 533_000_000,
             "count_confidence": 0.2, "units": [], "paragraph": 1}]},
            case_id="x", entity="y", jurisdiction="EU/EEA", registry=REG)
        self.assertIsNone(spec["alleged_violations"][0]["count"])
        self.assertTrue(spec["provenance"]["review_required"])


class TestPrecedents(unittest.TestCase):
    def test_store_is_populated_and_sourced(self):
        self.assertGreaterEqual(len(PR), 20)
        for r in PR.records:
            self.assertTrue(r["source"]["url"].startswith("http"))

    def test_gdpr_comparables_are_found(self):
        ids = {c["id"] for c in PR.comparables(statute_ids={"gdpr-art83-5"}, jurisdiction="EU/EEA",
                                               sector="social_media")}
        self.assertIn("meta-ireland-2023-transfers", ids)
        self.assertIn("tiktok-2025-transfers", ids)

    def test_ccpa_comparables_are_found(self):
        ids = {c["id"] for c in PR.comparables(statute_ids={"ccpa-ag-1798.155"}, jurisdiction="US-CA",
                                               sector="health")}
        self.assertIn("sephora-2022", ids)
        self.assertIn("healthline-2023", ids)
        self.assertIn("disney-2026", ids)

    def test_ratios_are_below_one(self):
        stats = Precedents.stats(PR.by_statute("gdpr-art83-5"))
        self.assertIsNotNone(stats["ratios"])
        self.assertLess(stats["ratios"]["max"], 1.0)
        self.assertGreater(stats["ratios"]["median"], 0.0)


class TestModel(unittest.TestCase):
    def setUp(self):
        self.health = json.loads((EX / "case_acme_health_multi.json").read_text(encoding="utf-8"))
        self.eu = json.loads((EX / "case_acme_eu_transfers.json").read_text(encoding="utf-8"))

    def test_band_ordering_eu(self):
        res = model_case(self.eu, REG, PR)
        b = res["case_band"]
        self.assertLessEqual(b["low"], b["expected"])
        self.assertLessEqual(b["expected"], b["max"])

    def test_art_83_3_caps_the_combined_total(self):
        res = model_case(self.eu, REG, PR)
        ceilings = [v["band"]["max"] for v in res["violations"]]
        self.assertEqual(len(ceilings), 2)
        self.assertAlmostEqual(res["case_band"]["max"], max(ceilings))
        self.assertTrue(any("linked processing" in n for n in res["aggregation_notes"]))

    def test_expected_is_far_below_ceiling_for_ccpa(self):
        res = model_case(self.health, REG, PR)
        ccpa = next(v for v in res["violations"] if v["statute_id"] == "ccpa-ag-1798.155")
        self.assertGreater(ccpa["band"]["max"], 8_000_000_000)          # 3.4m x $2,500
        self.assertLess(ccpa["band"]["expected"], 0.01 * ccpa["band"]["max"])
        self.assertGreater(ccpa["band"]["expected"], 100_000)           # not a token number either

    def test_severity_factors_reduce_and_clamp(self):
        mult, trace = factor_multiplier({"cooperation": 0.6, "remediation": 0.5,
                                         "no_prior_infringements": True})
        self.assertLess(mult, 1.0)
        self.assertGreater(mult, 0.05)
        self.assertTrue(any(t["factor"] == "cooperation" for t in trace))

    def test_uplifts_cannot_exceed_the_statutory_ceiling(self):
        mult, trace = factor_multiplier({"cooperation": 0.6, "remediation": 0.5,
                                         "no_prior_infringements": True,
                                         "prior_infringements": True, "intentional": True})
        self.assertLessEqual(mult, 1.0)
        self.assertTrue(any(t["factor"] == "clamp" for t in trace))

    def test_unknown_factor_is_ignored_not_guessed(self):
        mult, trace = factor_multiplier({"made_up_factor": 0.9})
        self.assertAlmostEqual(mult, 1.0)
        self.assertTrue(any(t.get("note") for t in trace))

    def test_uncompared_regime_drops_confidence_to_low(self):
        case = {
            "case_id": "bipa", "jurisdiction": "US-IL",
            "entity": {"name": "X", "sector": "retail"},
            "alleged_violations": [{"statute_id": "illinois-bipa-14-20", "count": 500_000}],
        }
        res = model_case(case, REG, PR)
        self.assertEqual(res["confidence"]["level"], "low")
        self.assertTrue(any("default" in v["calibration"] for v in res["violations"]))

    def test_missing_count_is_warned(self):
        case = {
            "case_id": "nocount", "jurisdiction": "US-CA",
            "entity": {"name": "X", "sector": "retail"},
            "alleged_violations": [{"statute_id": "ccpa-ag-1798.155"}],
        }
        res = model_case(case, REG, PR)
        self.assertTrue(any("no per-violation count" in w for w in res["warnings"]))

    def test_report_renders_with_disclaimer(self):
        md = render_markdown(model_case(self.health, REG, PR), REG)
        self.assertIn("Exposure band", md)
        self.assertIn("not legal advice", md.lower())
        self.assertIn("How the case total is built", md)


class TestCli(unittest.TestCase):
    def _run(self, argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_statutes_command(self):
        code, out = self._run(["statutes", "--regime", "gdpr"])
        self.assertEqual(code, 0)
        self.assertIn("gdpr-art83-5", out)

    def test_model_command_json(self):
        code, out = self._run(["model", str(EX / "case_acme_eu_transfers.json"), "--json"])
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIn("case_band", data)

    def test_precedents_command(self):
        code, out = self._run(["precedents", "--statute", "ccpa-ag-1798.155"])
        self.assertEqual(code, 0)
        self.assertIn("sephora-2022", out)

    def test_parse_command_emits_case(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            out_path = Path(d) / "draft.json"
            code, out = self._run(["parse", str(EX / "complaint_fixture_ccpa_ag.txt"),
                                   "--jurisdiction", "US-CA", "--emit-case", str(out_path)])
            self.assertEqual(code, 0)
            draft = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertTrue(draft["alleged_violations"])

    def test_unknown_statute_errors_cleanly(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["model", str(EX / "case_acme_eu_transfers.json"), "--statutes",
                         "/nonexistent.json"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
