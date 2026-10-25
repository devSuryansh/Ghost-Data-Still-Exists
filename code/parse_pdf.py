"""Text PDFs via pdftotext. A field is kept only when it appears in the extract."""

import subprocess
from pathlib import Path

from code.parse_obs import make_observation
from code.schema import Observation
from code.tokens import link_ids_in_text, resources_in


def extract_pdf_text(path: Path) -> str:
    completed = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout or ""


def parse_pdf_file(path: Path, evidence_id: str, manifest_at: str) -> list[Observation]:
    text = extract_pdf_text(path)
    if not text:
        return []
    observations: list[Observation] = []
    seen: set[str] = set()
    lowered_path = path.name.casefold()
    for resource_id in sorted(resources_in(text)):
        if resource_id in seen:
            continue
        seen.add(resource_id)
        start = text.find(resource_id)
        window = text[max(0, start - 400): start + 400]
        # Keep identifiers only when that exact value is in the extracted window.
        extra = {token for token in link_ids_in_text(window) if token in window or token in window.casefold()}
        record_type = None
        if "support_" in resource_id and ("attachment" in lowered_path or "attachment" in window.casefold()):
            record_type = "SUPPORT_ATTACHMENT"
        if resource_id.startswith("audit_record_"):
            record_type = "SECURITY_AUDIT_LOG"
        fields = {"result": "FOUND"}
        if "retain until" in window.casefold():
            # The retain-until date is kept only when the digits are in the window.
            import re

            retain = re.search(r"retain until\s+(\d{1,2}\s+\w+\s+\d{4})", window, re.I)
            if retain and retain.group(1) in window:
                fields["retention_note"] = retain.group(1)
        obs = make_observation(
            evidence_id=evidence_id,
            manifest_at=manifest_at,
            observed_at=manifest_at,
            resource_id=resource_id,
            fields=fields,
            record_type=record_type,
            topology="primary",
            extra_link_ids=extra,
        )
        if obs is not None:
            observations.append(obs)
    return observations
