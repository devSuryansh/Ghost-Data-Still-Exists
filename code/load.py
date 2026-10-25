"""Load participant files under dataset/ into observations and activity."""

import csv
from dataclasses import dataclass, field
from pathlib import Path

from code.identity import IdentityIndex, load_identities
from code.parse_image import parse_image_file
from code.parse_json import parse_json_file
from code.parse_logs import parse_log_file
from code.parse_pdf import parse_pdf_file
from code.parse_sql import parse_sql_file
from code.parse_text import parse_text_file
from code.schema import Activity, CollectionScan, Gap, Observation
from code.tokens import link_ids_in_text


@dataclass
class World:
    dataset: Path
    identities: IdentityIndex
    observations: list[Observation] = field(default_factory=list)
    scans: list[CollectionScan] = field(default_factory=list)
    activities: list[Activity] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)
    manifest: dict[str, dict] = field(default_factory=dict)


def load_world(dataset: Path) -> World:
    identities = load_identities(dataset)
    world = World(dataset=dataset, identities=identities)
    manifest_path = dataset / "evidence_files.csv"
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            world.manifest[row["file_id"]] = row
            path = dataset / row["file_path"]
            evidence_id = row["file_id"]
            captured = row["captured_at"]
            suffix = path.suffix.casefold()
            if suffix == ".sql":
                observations, scans = parse_sql_file(path, evidence_id, captured)
                world.observations.extend(observations)
                world.scans.extend(scans)
            elif suffix == ".json":
                observations, scans = parse_json_file(path, evidence_id, captured)
                world.observations.extend(observations)
                world.scans.extend(scans)
            elif suffix == ".log":
                world.observations.extend(parse_log_file(path, evidence_id, captured))
            elif suffix == ".txt":
                world.observations.extend(parse_text_file(path, evidence_id, captured))
            elif suffix == ".pdf":
                world.observations.extend(parse_pdf_file(path, evidence_id, captured))
            elif suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                observations, gap = parse_image_file(path, evidence_id, captured)
                world.observations.extend(observations)
                if gap is not None:
                    world.gaps.append(gap)
    world.activities.extend(_load_activity(dataset / "system_activity.csv"))
    return world


def _load_activity(path: Path) -> list[Activity]:
    rows: list[Activity] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            details = row.get("details") or ""
            rows.append(
                Activity(
                    activity_id=row["activity_id"],
                    event_time=row["event_time"],
                    event_type=row["event_type"],
                    source_system=row.get("source_system") or "",
                    target_system=row.get("target_system") or "",
                    resource_id=row.get("resource_id") or "",
                    reported_result=row.get("reported_result") or "",
                    details=details,
                    link_ids=link_ids_in_text(details),
                )
            )
    return rows
