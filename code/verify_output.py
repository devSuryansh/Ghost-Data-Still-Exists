"""Re-read an output CSV from disk and check the submission contract."""

import csv
import json
from pathlib import Path

FINDING_OPS = {
    "REPORT_REMAINING_RECORD": "PRESENT",
    "REPORT_EXPOSED_PII": "PRESENT",
    "REPORT_ACTIVE_DATA_FLOW": "ACTIVE",
    "REPORT_RESTORE_RISK": "ACTIVE",
}
REMEDIATION_OPS = {
    "DISABLE_DATA_FLOW": "DISABLED",
    "BLOCK_RESTORE": "BLOCKED",
    "DELETE_RECORD": "ABSENT",
    "REDACT_RECORD": "REDACTED",
    "ANONYMIZE_RECORD": "ANONYMIZED",
}
VERIFICATION_OPS = {
    "VERIFY_RECORD_ABSENT": "ABSENT",
    "VERIFY_RECORD_PRESENT": "PRESENT",
    "VERIFY_RECORD_REDACTED": "REDACTED",
    "VERIFY_RECORD_ANONYMIZED": "ANONYMIZED",
    "VERIFY_DATA_FLOW_DISABLED": "DISABLED",
    "VERIFY_RESTORE_BLOCKED": "BLOCKED",
}
PHASE_OPS = {
    "FINDING": FINDING_OPS,
    "REMEDIATION": REMEDIATION_OPS,
    "VERIFICATION": VERIFICATION_OPS,
}
PHASE_RANK = {"FINDING": 0, "REMEDIATION": 1, "VERIFICATION": 2}
STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
HEADER = ["case_id", "deletion_status", "steps_json"]


class VerifyError(Exception):
    pass


def verify_output(path: Path, expected_ids: list[str] | None = None, expected_count: int | None = 518) -> list[dict]:
    """Return parsed rows or raise VerifyError.

    expected_count is used when expected_ids is omitted. Pass expected_count
    None together with expected_ids to check that set only.
    """
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != HEADER:
            raise VerifyError(f"header {reader.fieldnames} != {HEADER}")
        rows = list(reader)
    if expected_ids is not None:
        wanted = list(expected_ids)
        got = [row["case_id"] for row in rows]
        if got != sorted(wanted):
            raise VerifyError("case id set or plain-text order does not match")
    else:
        count = 518 if expected_count is None else expected_count
        if len(rows) != count:
            raise VerifyError(f"row count {len(rows)} != {count}")
    ids = [row["case_id"] for row in rows]
    if ids != sorted(ids):
        raise VerifyError("rows are not sorted by case_id as plain text")
    if len(ids) != len(set(ids)):
        raise VerifyError("duplicate case_id")
    for row in rows:
        _check_row(row)
    return rows


def _check_row(row: dict) -> None:
    status = row.get("deletion_status")
    if status not in STATUSES:
        raise VerifyError(f"{row.get('case_id')} bad status")
    try:
        steps = json.loads(row.get("steps_json") or "")
    except json.JSONDecodeError as exc:
        raise VerifyError(f"{row.get('case_id')} steps are not JSON") from exc
    if not isinstance(steps, list):
        raise VerifyError(f"{row.get('case_id')} steps_json is not an array")
    if status == "NOT_APPLICABLE":
        if steps:
            raise VerifyError(f"{row.get('case_id')} NOT_APPLICABLE must use []")
        return
    last_phase = -1
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            raise VerifyError("step is not an object")
        if step.get("step_no") != index:
            raise VerifyError(f"{row['case_id']} step_no gap at {index}")
        phase = step.get("phase")
        if phase not in PHASE_RANK:
            raise VerifyError(f"{row['case_id']} bad phase")
        rank = PHASE_RANK[phase]
        if rank < last_phase:
            raise VerifyError(f"{row['case_id']} phase order")
        last_phase = rank
        operation = step.get("operation")
        state = step.get("state")
        allowed = PHASE_OPS[phase]
        if operation not in allowed or allowed[operation] != state:
            raise VerifyError(f"{row['case_id']} bad operation or state")
        for key in ("system_id", "resource_id", "evidence_id"):
            if key not in step or not isinstance(step[key], str):
                raise VerifyError(f"{row['case_id']} missing {key}")
        evidence = step["evidence_id"]
        if status == "COMPLETE":
            if phase != "VERIFICATION" or evidence == "":
                raise VerifyError(f"{row['case_id']} complete steps must be cited verifications")
        elif phase == "FINDING":
            if evidence == "":
                raise VerifyError(f"{row['case_id']} finding missing evidence")
        elif evidence != "":
            raise VerifyError(f"{row['case_id']} remediation or future verification cited evidence")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Check an output CSV from disk")
    parser.add_argument("csv_path")
    parser.add_argument("--count", type=int, default=518)
    args = parser.parse_args()
    verify_output(Path(args.csv_path), expected_count=args.count)
    print(f"ok {args.csv_path}")


if __name__ == "__main__":
    main()
