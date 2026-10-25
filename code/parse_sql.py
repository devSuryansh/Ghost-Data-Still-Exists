"""Load SQLite snapshot exports into observations."""

import sqlite3
from pathlib import Path

from code.parse_obs import make_observation
from code.schema import CollectionScan, Observation


def _topology(table: str, file_name: str) -> str:
    label = f"{file_name} {table}".casefold()
    if "failover" in label:
        if "primary" in table.casefold():
            return "primary"
        return "failover"
    if "read_replica" in label or "read replica" in label:
        if table.casefold().endswith("primary") or table.casefold().endswith("_primary"):
            return "primary"
        return "read_replica"
    if "reporting" in label:
        if "primary" in table.casefold():
            return "primary"
        return "reporting"
    if "regional" in label or "replica_" in table.casefold():
        if table.casefold().endswith("primary") or "primary" == table.casefold().split("_")[-1]:
            return "primary"
        return "regional"
    if "primary" in table.casefold():
        return "primary"
    if "replica" in table.casefold():
        return "replica"
    return "primary"


def _category_hint(table: str, collection: str | None) -> str | None:
    text = f"{table} {collection or ''}".casefold()
    if "audit" in text:
        return "SECURITY_AUDIT_LOG"
    if "analytics" in text:
        return "ANALYTICS_PROFILE"
    if "search" in text:
        return "SEARCH_INDEX_ENTRY"
    if "support" in text:
        return "SUPPORT_MESSAGE"
    if "export" in text:
        return "USER_EXPORT"
    if "backup" in text or "restore" in text:
        return "BACKUP_ARCHIVE"
    if "connector" in text or "subscription" in text:
        return "DATA_FLOW"
    if "tombstone" in text:
        return "ACCOUNT_TOMBSTONE"
    if "profile" in text or "account" in text:
        return "USER_PROFILE"
    return None


def parse_sql_file(
    path: Path,
    evidence_id: str,
    manifest_at: str,
) -> tuple[list[Observation], list[CollectionScan]]:
    script = path.read_text(encoding="utf-8", errors="replace")
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    observations: list[Observation] = []
    scans: list[CollectionScan] = []
    try:
        connection.executescript(script)
    except sqlite3.DatabaseError:
        connection.close()
        return observations, scans
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    for table in tables:
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
        if "resource_id" not in columns and "record_json" not in columns:
            continue
        rows = list(connection.execute(f"SELECT * FROM {table}"))
        topology = _topology(table, path.name)
        present_ids: set[str] = set()
        category_for_scan = _category_hint(table, None) or "USER_PROFILE"
        for row in rows:
            payload = {key: row[key] for key in row.keys()}
            raw_json = payload.get("record_json")
            nested = {}
            if isinstance(raw_json, str) and raw_json.strip().startswith("{"):
                import json

                try:
                    loaded = json.loads(raw_json)
                except json.JSONDecodeError:
                    loaded = None
                if isinstance(loaded, dict):
                    nested = loaded
            resource_id = str(payload.get("resource_id") or nested.get("resource_id") or "")
            if not resource_id:
                continue
            fields = dict(nested)
            for key, value in payload.items():
                if key != "record_json":
                    fields.setdefault(key, value)
            record_type = _category_hint(table, str(payload.get("collection_name") or "")) 
            observed = str(payload.get("updated_at") or manifest_at)
            system = payload.get("origin_system")
            obs = make_observation(
                evidence_id=evidence_id,
                manifest_at=manifest_at,
                observed_at=observed,
                resource_id=resource_id,
                fields=fields,
                explicit_system=str(system) if system else None,
                record_type=record_type,
                topology=topology,
            )
            if obs is None:
                continue
            observations.append(obs)
            if obs.present:
                present_ids.add(obs.resource_id)
                category_for_scan = obs.category
        if _category_hint(table, None) in {"USER_PROFILE", "SEARCH_INDEX_ENTRY", "ANALYTICS_PROFILE"} or "profile" in table.casefold():
            scans.append(
                CollectionScan(
                    evidence_id=evidence_id,
                    manifest_at=manifest_at,
                    observed_at=manifest_at,
                    system_id="account_service" if "profile" in table.casefold() or "account" in table.casefold() else "account_service",
                    category=category_for_scan if category_for_scan else "USER_PROFILE",
                    present_ids=present_ids,
                )
            )
    connection.close()
    return observations, scans
