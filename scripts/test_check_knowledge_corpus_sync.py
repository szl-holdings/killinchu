#!/usr/bin/env python3
"""Self-test for check_knowledge_corpus_sync.py.

Proves the guard actually catches what it claims to: knowledge.json drift between
killinchu and a11oy, AND Doctrine-v11 honesty regressions in the corpus (Conjecture
1 silently marked proven, F23 promoted into the locked set, the locked-count
theorem dropped, a missing version, an un-qualified Theorem U). Also proves a valid,
in-sync, honest corpus passes. Stdlib unittest, no network — guards the validator so
a future edit can't silently neuter it.
"""
import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_knowledge_corpus_sync import (  # noqa: E402
    main,
    validate_honesty,
)


# A minimal but structurally faithful "good" corpus: declares v11, keeps
# Λ-uniqueness (TH_L1) conjectured, lists F23 as a conjecture (not locked), pins a
# locked-count theorem.
GOOD = {
    "version": "6.0.0",
    "doctrine": "Doctrine v11 LOCKED",
    "theorems": [
        {"id": "TH_L1", "name": "Λ_uniqueness", "maturity": "conjectured"},
        {"id": "TH_L2", "name": "Λ_min_max_bounds", "maturity": "proven"},
    ],
    "proof_summary": {
        "locked_proven": 8,
        "locked_ids": ["F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22"],
        "locked_count_theorem": "locked_count_eight",
        "conjecture": ["F23"],
    },
}


def _txt(obj):
    return json.dumps(obj, ensure_ascii=False)


def _write(d, name, obj_or_text):
    p = os.path.join(d, name)
    data = obj_or_text if isinstance(obj_or_text, str) else _txt(obj_or_text)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(data)
    return p


class HonestyTests(unittest.TestCase):
    def _errs(self, obj):
        text = _txt(obj)
        return validate_honesty(text, obj, "test")

    def test_good_corpus_has_no_errors(self):
        self.assertEqual(self._errs(GOOD), [])

    def test_lambda_uniqueness_marked_proven_fails(self):
        bad = copy.deepcopy(GOOD)
        bad["theorems"][0]["maturity"] = "proven"
        errs = self._errs(bad)
        self.assertTrue(any("Λ-uniqueness" in e and "conjectured" in e for e in errs), errs)

    def test_f23_promoted_to_locked_fails(self):
        bad = copy.deepcopy(GOOD)
        bad["proof_summary"]["locked_ids"].append("F23")
        errs = self._errs(bad)
        self.assertTrue(any("F23" in e and "locked_ids" in e for e in errs), errs)

    def test_f23_missing_from_conjecture_fails(self):
        bad = copy.deepcopy(GOOD)
        bad["proof_summary"]["conjecture"] = []
        errs = self._errs(bad)
        self.assertTrue(any("conjecture must include 'F23'" in e for e in errs), errs)

    def test_missing_locked_count_theorem_fails(self):
        bad = copy.deepcopy(GOOD)
        del bad["proof_summary"]["locked_count_theorem"]
        errs = self._errs(bad)
        self.assertTrue(any("locked_count_theorem" in e for e in errs), errs)

    def test_missing_version_fails(self):
        bad = copy.deepcopy(GOOD)
        del bad["version"]
        errs = self._errs(bad)
        self.assertTrue(any("version" in e for e in errs), errs)

    def test_missing_doctrine_v11_fails(self):
        bad = copy.deepcopy(GOOD)
        bad["doctrine"] = "Doctrine vX"
        errs = self._errs(bad)
        self.assertTrue(any("v11" in e for e in errs), errs)

    def test_lambda_theorem_absent_fails(self):
        bad = copy.deepcopy(GOOD)
        bad["theorems"] = [{"id": "TH_L2", "name": "other", "maturity": "proven"}]
        errs = self._errs(bad)
        self.assertTrue(any("TH_L1" in e for e in errs), errs)

    def test_theorem_u_without_conditional_fails(self):
        bad = copy.deepcopy(GOOD)
        bad["note"] = "Theorem U holds and is fully proven."
        errs = self._errs(bad)
        self.assertTrue(any("Theorem U" in e for e in errs), errs)

    def test_theorem_u_with_conditional_ok(self):
        ok = copy.deepcopy(GOOD)
        ok["note"] = "Theorem U holds conditional on the declared axioms."
        self.assertEqual(self._errs(ok), [])

    def test_non_object_corpus_fails(self):
        errs = validate_honesty("[]", [], "test")
        self.assertTrue(any("not a valid JSON object" in e for e in errs), errs)


class SyncTests(unittest.TestCase):
    def test_identical_and_honest_passes(self):
        with tempfile.TemporaryDirectory() as d:
            a = _write(d, "self.json", GOOD)
            b = _write(d, "sibling.json", GOOD)
            rc = main(["--self", a, "--sibling", b])
            self.assertEqual(rc, 0)

    def test_drift_fails(self):
        with tempfile.TemporaryDirectory() as d:
            a = _write(d, "self.json", GOOD)
            drifted = copy.deepcopy(GOOD)
            drifted["version"] = "6.0.1"  # any byte difference
            b = _write(d, "sibling.json", drifted)
            rc = main(["--self", a, "--sibling", b])
            self.assertEqual(rc, 1)

    def test_in_sync_but_dishonest_fails(self):
        with tempfile.TemporaryDirectory() as d:
            bad = copy.deepcopy(GOOD)
            bad["theorems"][0]["maturity"] = "proven"  # identical in both, but dishonest
            a = _write(d, "self.json", bad)
            b = _write(d, "sibling.json", bad)
            rc = main(["--self", a, "--sibling", b])
            self.assertEqual(rc, 1)

    def test_missing_input_is_usage_error(self):
        with tempfile.TemporaryDirectory() as d:
            a = _write(d, "self.json", GOOD)
            rc = main(["--self", a, "--sibling", os.path.join(d, "nope.json")])
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
