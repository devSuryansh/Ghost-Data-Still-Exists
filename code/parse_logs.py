"""Log evidence. Field parsers only. Prose in the line is not an instruction."""

import json
import re
from pathlib import Path

from code.parse_obs import make_observation
from code.schema import Observation
from code.tokens import link_ids_in_text, resources_in

TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
KV_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(\"[^\"]*\"|\S+)")


def _topology(path: Path) -> str:
    name = path.name.casefold()
    if "replica" in name:
        return "replica"
    if "failover" in name:
        return "failover"
    return "primary"


def _pairs(line: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, raw in KV_RE.findall(line):
        value = raw.strip().strip("\"'")
        value = value.replace('\\"', '"')
        found[key] = value
    return found


def _from_line(line: str) -> dict[str, str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return {}
    if stripped.startswith("{") or '{"' in stripped:
        start = stripped.find("{")
        try:
            payload = json.loads(stripped[start:])
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            flat = {str(key): str(value) for key, value in payload.items() if not isinstance(value, (dict, list))}
            stamp = TIME_RE.search(stripped[:start])
            if stamp and "timestamp" not in flat:
                flat["timestamp"] = stamp.group(0)
            return flat
    fields = _pairs(stripped)
    message = fields.get("message")
    if message and ("resource_id" in message or "event" in message):
        inner = _pairs(message.replace('\\"', '"'))
        for key, value in inner.items():
            fields.setdefault(key, value)
    stamp = TIME_RE.search(stripped)
    if stamp:
        fields.setdefault("timestamp", stamp.group(0))
    if "resource_id" not in fields:
        ids = resources_in(stripped)
        if len(ids) == 1:
            fields["resource_id"] = next(iter(ids))
    return fields


def parse_log_file(path: Path, evidence_id: str, manifest_at: str) -> list[Observation]:
    grouped: dict[str, dict[str, str]] = {}
    order: list[str] = []
    loose: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        # Ignore instruction-like prose. Only structured fields are read.
        fields = _from_line(line)
        if not fields:
            continue
        trace = fields.get("trace_id") or fields.get("requestId")
        if trace and trace.startswith("tr-"):
            if fields.get("event") in {"cache_lookup", "connection_acquired"} and not fields.get("resource_id"):
                continue
            bucket = grouped.get(trace)
            if bucket is None:
                bucket = {}
                grouped[trace] = bucket
                order.append(trace)
            if fields.get("event"):
                events = bucket.get("_events", "")
                bucket["_events"] = (events + " " + fields["event"]).strip()
            bucket.update({key: value for key, value in fields.items() if value != "" and key != "event"})
            if "event" not in bucket or fields.get("event", "").endswith("_completed") or "resource_id" in fields:
                if fields.get("event"):
                    bucket["event"] = fields["event"]
        elif fields.get("resource_id"):
            loose.append(fields)

    observations: list[Observation] = []
    topology = _topology(path)
    for trace in order:
        obs = _emit(grouped[trace], evidence_id, manifest_at, topology)
        if obs is not None:
            observations.append(obs)
    for fields in loose:
        obs = _emit(fields, evidence_id, manifest_at, topology)
        if obs is not None:
            observations.append(obs)
    return observations


def _emit(fields: dict[str, str], evidence_id: str, manifest_at: str, topology: str) -> Observation | None:
    resource_id = fields.get("resource_id") or ""
    if not resource_id:
        return None
    observed = fields.get("timestamp") or fields.get("time") or manifest_at
    system = fields.get("service") or fields.get("function") or fields.get("system")
    extra = set()
    for key in ("lookup_key", "match_key", "correlation_key", "subject_key", "subject_reference", "email"):
        if fields.get(key):
            extra.update(link_ids_in_text(fields[key]))
    return make_observation(
        evidence_id=evidence_id,
        manifest_at=manifest_at,
        observed_at=observed,
        resource_id=resource_id,
        fields=fields,
        explicit_system=system,
        record_type=fields.get("record_type"),
        topology=topology,
        event_name=((fields.get("_events") or "") + " " + (fields.get("event") or "")).strip(),
        extra_link_ids=extra,
    )
