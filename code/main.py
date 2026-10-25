"""Audit every deletion request and write repo-root output.csv."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from code.audit import audit_dataset, write_output
from code.usage import Usage
from code.verify_output import verify_output


def main() -> None:
    dataset = ROOT / "dataset"
    usage = Usage()
    rows = audit_dataset(dataset, "deletion_requests.csv", usage)
    output = ROOT / "output.csv"
    write_output(rows, output)
    verify_output(output, expected_count=518)
    metrics = usage.as_dict()
    metrics["requests"] = len(rows)
    metrics_path = ROOT / "code" / "evaluation" / "last_run.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output} rows={len(rows)} model_calls={usage.model_calls}")


if __name__ == "__main__":
    main()
