"""Plain-text records such as the account handover log."""

import re
from pathlib import Path

from code.parse_obs import make_observation
from code.schema import Observation
from code.tokens import link_ids_in_text

LINE_RE = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)\s*\|\s*"
    r"(?P<system>[^|]+)\|\s*(?P<resource>[^|]+)\|\s*(?P<rtype>[^|]+)\|\s*"
    r"(?P<result>[^|]+)\|\s*(?P<subject>.*)$"
)


def parse_text_file(path: Path, evidence_id: str, manifest_at: str) -> list[Observation]:
    observations: list[Observation] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip().lstrip("-").strip()
        match = LINE_RE.match(line)
        if not match:
            continue
        subject = match.group("subject").strip()
        fields = {
            "result": match.group("result").strip(),
            "record_type": match.group("rtype").strip(),
            "system": match.group("system").strip(),
            "subject_reference": subject,
        }
        extra = link_ids_in_text(subject)
        obs = make_observation(
            evidence_id=evidence_id,
            manifest_at=manifest_at,
            observed_at=match.group("time"),
            resource_id=match.group("resource").strip(),
            fields=fields,
            explicit_system=match.group("system").strip(),
            record_type=match.group("rtype").strip(),
            topology="primary",
            extra_link_ids=extra,
        )
        if obs is not None:
            observations.append(obs)
    return observations
