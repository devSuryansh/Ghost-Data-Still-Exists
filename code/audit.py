"""Run the deletion audit for one request or a whole file."""

import csv
import json
from pathlib import Path

from code.intent import classify_intent
from code.link import link_resources
from code.load import World, load_world
from code.state import Resolved, absent_account_evidence, resolve_resource
from code.steps import build_steps
from code.usage import Usage


def audit_dataset(dataset: Path, requests_name: str, usage: Usage | None = None) -> list[dict]:
    world = load_world(dataset)
    usage = usage or Usage()
    links = link_resources(world.identities, world.observations, world.activities)
    requests = _read_requests(dataset / requests_name)
    _attach_reported_anonymize(links, world, requests)
    rows = []
    for request in requests:
        rows.append(audit_request(world, links, request, usage))
    rows.sort(key=lambda row: row["case_id"])
    return rows


def audit_request(world: World, links: dict[str, set[str]], request: dict, usage: Usage) -> dict:
    case_id = request["case_id"]
    intent = classify_intent(request.get("request_text") or "", usage)
    if not intent.deletion_authorized:
        return {"case_id": case_id, "deletion_status": "NOT_APPLICABLE", "steps_json": "[]"}
    subject = world.identities.subject_for_email(request.get("email") or "")
    if subject is None:
        return {"case_id": case_id, "deletion_status": "INCOMPLETE", "steps_json": "[]"}
    audit_at = request["audit_at"]
    resource_ids = set(links.get(subject.user_id, set()))
    resource_ids = _prefer_targeted_accounts(resource_ids, world, audit_at)
    resolved: list[Resolved] = []
    for resource_id in sorted(resource_ids):
        state = resolve_resource(resource_id, world.observations, audit_at)
        if state is None and resource_id.startswith("account_"):
            state = Resolved(
                resource_id=resource_id,
                system_id="account_service",
                category="USER_PROFILE",
                action="DELETE",
                present=False,
                direct_pii=False,
                attributable=False,
                enabled=None,
                restore_allowed=None,
                retention_until=None,
                legal_active=None,
                evidence_id="",
                observed_at="",
            )
        if state is None:
            continue
        if state.category == "USER_PROFILE" and not state.present and not state.evidence_id:
            state.evidence_id = absent_account_evidence(
                subject.link_ids,
                world.observations,
                world.scans,
                audit_at,
            )
        resolved.append(state)
    status, steps = build_steps(resolved, audit_at)
    return {
        "case_id": case_id,
        "deletion_status": status,
        "steps_json": json.dumps(steps, separators=(",", ":"), ensure_ascii=False),
    }


def _prefer_targeted_accounts(resource_ids: set[str], world: World, audit_at: str) -> set[str]:
    """Keep the account whose latest in-cutoff signal is the newest.

    Older not-found lookups for a different account id are not a second profile.
    """
    accounts = [resource_id for resource_id in resource_ids if resource_id.startswith("account_")]
    if len(accounts) <= 1:
        return resource_ids

    def signal(resource_id: str) -> str:
        times = [
            obs.observed_at
            for obs in world.observations
            if obs.resource_id == resource_id and obs.observed_at <= audit_at
        ]
        times.extend(
            act.event_time
            for act in world.activities
            if act.resource_id == resource_id
            and act.event_type == "DELETE_RECORD"
            and act.event_time <= audit_at
        )
        return max(times) if times else ""

    timed = {resource_id: signal(resource_id) for resource_id in accounts}
    newest = max(timed.values())
    if not newest:
        return resource_ids
    dropped = {resource_id for resource_id, when in timed.items() if when < newest}
    # A profile that is still present stays even if an older lookup exists.
    for resource_id in list(dropped):
        if any(
            obs.resource_id == resource_id and obs.present and obs.observed_at <= audit_at
            for obs in world.observations
        ):
            dropped.discard(resource_id)
    return {resource_id for resource_id in resource_ids if resource_id not in dropped}


def _attach_reported_anonymize(links: dict[str, set[str]], world: World, requests: list[dict]) -> None:
    """Tie an anonymized profile to the one request reported just after that anonymize."""
    from datetime import datetime

    owned = {resource_id for resource_ids in links.values() for resource_id in resource_ids}

    def has_analytics(user_id: str) -> bool:
        return any(resource_id.startswith("analytics_") for resource_id in links.get(user_id, set()))

    def parse(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    for act in world.activities:
        if act.source_system != "deletion_worker" or act.event_type != "ANONYMIZE_RECORD":
            continue
        if not act.resource_id.startswith("analytics_") or act.resource_id in owned:
            continue
        event_time = parse(act.event_time)
        matches = []
        for request in requests:
            reported = parse(request["reported_at"])
            delta = (reported - event_time).total_seconds()
            if 0 <= delta <= 15 * 60:
                subject = world.identities.subject_for_email(request.get("email") or "")
                if subject and not has_analytics(subject.user_id):
                    matches.append(subject.user_id)
        unique = set(matches)
        if len(unique) != 1:
            continue
        user_id = next(iter(unique))
        links.setdefault(user_id, set()).add(act.resource_id)
        owned.add(act.resource_id)


def write_output(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["case_id", "deletion_status", "steps_json"],
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _read_requests(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
