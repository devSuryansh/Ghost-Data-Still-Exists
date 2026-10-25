"""The disk verifier must reject mutated output files."""

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from code.verify_output import VerifyError, verify_output


def _write(path: Path, rows: list[tuple[str, str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["case_id", "deletion_status", "steps_json"])
        for row in rows:
            writer.writerow(row)


def _step(number: int, phase: str, operation: str, state: str, evidence: str) -> str:
    return json.dumps(
        [
            {
                "step_no": number,
                "phase": phase,
                "system_id": "account_service",
                "resource_id": "account_001",
                "operation": operation,
                "state": state,
                "evidence_id": evidence,
            }
        ],
        separators=(",", ":"),
    )


class VerifierTest(unittest.TestCase):
    def test_valid_small_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "output.csv"
            _write(path, [("case_b", "NOT_APPLICABLE", "[]"), ("case_a", "NOT_APPLICABLE", "[]")])
            # unsorted on purpose below. This one is sorted.
            path.unlink()
            _write(path, [("case_a", "NOT_APPLICABLE", "[]"), ("case_b", "NOT_APPLICABLE", "[]")])
            rows = verify_output(path, expected_ids=["case_a", "case_b"])
            self.assertEqual([row["case_id"] for row in rows], ["case_a", "case_b"])

    def test_mutations_fail(self):
        complete = _step(1, "VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT", "evidence_01")
        finding = _step(1, "FINDING", "REPORT_REMAINING_RECORD", "PRESENT", "evidence_01")
        bad_evidence_finding = _step(1, "FINDING", "REPORT_REMAINING_RECORD", "PRESENT", "")
        cited_remediation = json.dumps(
            [
                {
                    "step_no": 1,
                    "phase": "FINDING",
                    "system_id": "account_service",
                    "resource_id": "account_001",
                    "operation": "REPORT_REMAINING_RECORD",
                    "state": "PRESENT",
                    "evidence_id": "evidence_01",
                },
                {
                    "step_no": 2,
                    "phase": "REMEDIATION",
                    "system_id": "account_service",
                    "resource_id": "account_001",
                    "operation": "DELETE_RECORD",
                    "state": "ABSENT",
                    "evidence_id": "evidence_01",
                },
                {
                    "step_no": 3,
                    "phase": "VERIFICATION",
                    "system_id": "account_service",
                    "resource_id": "account_001",
                    "operation": "VERIFY_RECORD_ABSENT",
                    "state": "ABSENT",
                    "evidence_id": "",
                },
            ],
            separators=(",", ":"),
        )
        cases = {
            "unsorted": [("case_b", "NOT_APPLICABLE", "[]"), ("case_a", "NOT_APPLICABLE", "[]")],
            "duplicate": [("case_a", "NOT_APPLICABLE", "[]"), ("case_a", "NOT_APPLICABLE", "[]")],
            "bad_status": [("case_a", "DONE", "[]")],
            "na_with_steps": [("case_a", "NOT_APPLICABLE", complete)],
            "complete_without_evidence": [
                ("case_a", "COMPLETE", _step(1, "VERIFICATION", "VERIFY_RECORD_ABSENT", "ABSENT", ""))
            ],
            "finding_without_evidence": [("case_a", "INCOMPLETE", bad_evidence_finding)],
            "remediation_with_evidence": [("case_a", "INCOMPLETE", cited_remediation)],
            "bad_operation": [("case_a", "COMPLETE", _step(1, "VERIFICATION", "DELETE_RECORD", "ABSENT", "evidence_01"))],
            "not_json": [("case_a", "NOT_APPLICABLE", "not-json")],
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, rows in cases.items():
                path = Path(tmp) / f"{name}.csv"
                _write(path, rows)
                with self.subTest(name=name):
                    with self.assertRaises(VerifyError):
                        verify_output(path, expected_ids=[row[0] for row in rows] if name != "unsorted" else ["case_a", "case_b"])


if __name__ == "__main__":
    unittest.main()
