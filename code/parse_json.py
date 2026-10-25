"""JSON evidence: exports, snapshot bundles, ledgers, and manifests."""

import json
from pathlib import Path

from code.parse_obs import fields_from_mapping, make_observation
from code.schema import CollectionScan, Observation, category_for_resource, system_for


def _walk(node, inherited: dict, out: list[dict]) -> None:
    if isinstance(node, dict):
        context = dict(inherited)
        for key in ("captured_at", "recorded_at", "observed_at", "exported_at"):
            if key in node and not isinstance(node[key], (dict, list)):
                context[key] = node[key]
        for key in ("data_store", "system", "service", "collection", "record_type"):
            if key in node and isinstance(node[key], str):
                context[key] = node[key]
        if "resource_id" in node and isinstance(node["resource_id"], str):
            flat = fields_from_mapping(node)
            flat["_context"] = context
            out.append(flat)
        for value in node.values():
            if isinstance(value, (dict, list)):
                _walk(value, context, out)
    elif isinstance(node, list):
        for item in node:
            _walk(item, inherited, out)


def _empty_collections(node, inherited: dict, out: list[dict]) -> None:
    if isinstance(node, dict):
        context = dict(inherited)
        for key in ("captured_at", "recorded_at", "observed_at", "data_store", "system", "collection"):
            if key in node and isinstance(node[key], str):
                context[key] = node[key]
        records = node.get("records")
        if isinstance(records, list) and len(records) == 0 and context.get("collection"):
            out.append(context)
        for value in node.values():
            if isinstance(value, (dict, list)):
                _empty_collections(value, context, out)
    elif isinstance(node, list):
        for item in node:
            _empty_collections(item, inherited, out)


def _collection_category(collection: str, data_store: str) -> str:
    text = f"{collection} {data_store}".casefold()
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
    if "backup" in text:
        return "BACKUP_ARCHIVE"
    if "connector" in text or "flow" in text:
        return "DATA_FLOW"
    if "tombstone" in text or "deleted_customer" in text:
        return "ACCOUNT_TOMBSTONE"
    if "profile" in text or "account" in text:
        return "USER_PROFILE"
    return category_for_resource(collection or "account_0", collection or None)


def parse_json_file(
    path: Path,
    evidence_id: str,
    manifest_at: str,
) -> tuple[list[Observation], list[CollectionScan]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [], []
    found: list[dict] = []
    _walk(data, {}, found)
    observations: list[Observation] = []
    for fields in found:
        context = fields.pop("_context", {})
        resource_id = str(fields.get("resource_id") or "")
        observed = str(
            fields.get("observed_at")
            or fields.get("recorded_at")
            or context.get("observed_at")
            or context.get("recorded_at")
            or context.get("captured_at")
            or manifest_at
        )
        record_type = fields.get("record_type") or context.get("record_type") or context.get("collection")
        explicit = fields.get("system") or fields.get("service") or context.get("data_store") or context.get("system")
        obs = make_observation(
            evidence_id=evidence_id,
            manifest_at=manifest_at,
            observed_at=observed,
            resource_id=resource_id,
            fields=fields,
            explicit_system=str(explicit) if explicit else None,
            record_type=str(record_type) if record_type else None,
            topology="primary",
            event_name=str(fields.get("event") or ""),
        )
        if obs is not None:
            captured = context.get("captured_at")
            if captured and isinstance(data, dict) and "snapshots" in data:
                obs.cohort = f"{evidence_id}|{captured}"
            observations.append(obs)

    scans: list[CollectionScan] = []
    empties: list[dict] = []
    _empty_collections(data, {}, empties)
    for context in empties:
        collection = str(context.get("collection") or "")
        category = _collection_category(collection, context.get("data_store") or "")
        system = system_for(category, context.get("data_store") or context.get("system"))
        observed = str(context.get("captured_at") or context.get("recorded_at") or manifest_at)
        scans.append(
            CollectionScan(
                evidence_id=evidence_id,
                manifest_at=manifest_at,
                observed_at=observed,
                system_id=system,
                category=category,
                present_ids=set(),
            )
        )
    return observations, scans
