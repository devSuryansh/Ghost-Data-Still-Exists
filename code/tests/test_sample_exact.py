"""Compare the engine with the 32 public answers. This file is the only test that opens sample_output.csv."""

import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from code.audit import audit_dataset
from code.usage import Usage

FIELDS = ("phase", "operation", "system_id", "resource_id", "state", "evidence_id")


def _key(step: dict) -> tuple:
    return tuple(step[field] for field in FIELDS)


class SampleExactTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        usage = Usage()
        rows = audit_dataset(ROOT / "dataset", "sample_deletion_requests.csv", usage)
        cls.pred = {row["case_id"]: row for row in rows}
        with (ROOT / "dataset" / "sample_output.csv").open(newline="", encoding="utf-8") as handle:
            cls.gold = list(csv.DictReader(handle))
        cls.usage = usage

    def test_status_matches_all_32(self):
        mismatches = [
            row["case_id"]
            for row in self.gold
            if self.pred[row["case_id"]]["deletion_status"] != row["deletion_status"]
        ]
        self.assertEqual(mismatches, [])

    def test_step_sequences(self):
        bad = []
        for row in self.gold:
            gold_steps = json.loads(row["steps_json"])
            pred_steps = json.loads(self.pred[row["case_id"]]["steps_json"])
            if [_key(step) for step in gold_steps] != [_key(step) for step in pred_steps]:
                bad.append(row["case_id"])
        # audit_record_6645 and audit_record_5569 are in the public answer and in no other dataset file.
        self.assertEqual(bad, ["case_18", "case_20"])

    def test_only_those_audit_steps_differ(self):
        for case_id, missing in (("case_18", "audit_record_6645"), ("case_20", "audit_record_5569")):
            gold_steps = json.loads(next(row["steps_json"] for row in self.gold if row["case_id"] == case_id))
            pred_steps = json.loads(self.pred[case_id]["steps_json"])
            gold_keys = [_key(step) for step in gold_steps]
            pred_keys = [_key(step) for step in pred_steps]
            absent = [key for key in gold_keys if key not in pred_keys]
            extra = [key for key in pred_keys if key not in gold_keys]
            self.assertEqual(extra, [])
            self.assertEqual(len(absent), 1)
            self.assertEqual(absent[0][3], missing)
            self.assertEqual(absent[0][1], "VERIFY_RECORD_PRESENT")

    def test_decoy_local_part_is_not_linked(self):
        steps = json.loads(self.pred["case_06"]["steps_json"])
        resources = {step["resource_id"] for step in steps}
        self.assertIn("search_001", resources)
        self.assertNotIn("search_8814", resources)
        self.assertNotIn("search_4203", resources)

    def test_model_was_not_called(self):
        self.assertEqual(self.usage.model_calls, 0)
        self.assertEqual(self.usage.input_tokens, 0)
        self.assertEqual(self.usage.output_tokens, 0)


if __name__ == "__main__":
    unittest.main()
