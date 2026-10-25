"""Exact identifier links, then resource-id propagation.

A resource is tied to a subject only when a token matches that subject and
nobody else. Source resource ids inherit the same subject. Account numbers
that are the same integer as the user id are linked when that account id
already appears in evidence or activity.
"""

from collections import defaultdict

from code.identity import IdentityIndex
from code.schema import Activity, Observation


def link_resources(
    identities: IdentityIndex,
    observations: list[Observation],
    activities: list[Activity],
) -> dict[str, set[str]]:
    """Return user_id -> resource ids."""
    owners: dict[str, set[str]] = defaultdict(set)
    known_ids = {obs.resource_id for obs in observations}
    known_ids.update(act.resource_id for act in activities if act.resource_id)

    def assign(resource_id: str, user_id: str) -> None:
        if not resource_id or not user_id:
            return
        current = owners[resource_id]
        if current and user_id not in current:
            current.add("CONFLICT")
            return
        current.add(user_id)

    for obs in observations:
        users = identities.users_for_tokens(obs.link_ids)
        if len(users) == 1:
            assign(obs.resource_id, next(iter(users)))

    for act in activities:
        users = identities.users_for_tokens(act.link_ids)
        if len(users) == 1 and act.resource_id:
            assign(act.resource_id, next(iter(users)))

    changed = True
    while changed:
        changed = False
        for obs in observations:
            owner_set = owners.get(obs.resource_id, set())
            real = {user for user in owner_set if user != "CONFLICT"}
            if len(real) != 1 or "CONFLICT" in owner_set:
                continue
            user_id = next(iter(real))
            for source_id in obs.source_ids:
                before = set(owners.get(source_id, set()))
                assign(source_id, user_id)
                if owners.get(source_id) != before:
                    changed = True

    # Profiles numbered like the low user ids (account_004 for user_04) are the
    # same subject when no other account is already tied to that person.
    for user_id in identities.subjects:
        number = _user_number(user_id)
        if number is None or number > 10:
            continue
        account_id = f"account_{number:03d}"
        owned_accounts = [
            resource_id
            for resource_id, users in owners.items()
            if resource_id.startswith("account_") and user_id in users and "CONFLICT" not in users
        ]
        if any(resource_id != account_id for resource_id in owned_accounts):
            continue
        if account_id in owned_accounts:
            continue
        current = owners.get(account_id, set())
        if "CONFLICT" in current or (current and user_id not in current):
            continue
        assign(account_id, user_id)
        known_ids.add(account_id)

    _pair_absent_accounts(owners, observations)
    _pair_null_analytics(owners, observations)
    _pair_adjacent_anonymize(owners, activities)
    _pair_accounts_by_day(owners, activities)

    linked: dict[str, set[str]] = defaultdict(set)
    for resource_id, user_ids in owners.items():
        real = {user for user in user_ids if user != "CONFLICT"}
        if "CONFLICT" in user_ids or len(real) != 1:
            continue
        linked[next(iter(real))].add(resource_id)
    return linked


def _pair_absent_accounts(owners: dict[str, set[str]], observations: list[Observation]) -> None:
    """Match unowned 404 profiles to audit subjects in the same file.

    Pairing runs only when the two counts are equal. Accounts are ordered by
    observation time. Subjects are ordered by user id.
    """
    by_file: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        by_file[obs.evidence_id].append(obs)

    def sole(resource_id: str) -> str | None:
        users = {user for user in owners.get(resource_id, set()) if user != "CONFLICT"}
        if "CONFLICT" in owners.get(resource_id, set()) or len(users) != 1:
            return None
        return next(iter(users))

    def has_account(user_id: str) -> bool:
        return any(
            resource_id.startswith("account_") and sole(resource_id) == user_id
            for resource_id in owners
        )

    for obs_list in by_file.values():
        audit_users: list[str] = []
        seen: set[str] = set()
        for obs in obs_list:
            if obs.category == "SECURITY_AUDIT_LOG" and obs.present:
                user_id = sole(obs.resource_id)
                if user_id and user_id not in seen:
                    seen.add(user_id)
                    audit_users.append(user_id)
        needing = sorted(
            [user_id for user_id in audit_users if not has_account(user_id)],
            key=_user_sort,
        )
        accounts: list[str] = []
        seen_accounts: set[str] = set()
        for obs in sorted(obs_list, key=lambda item: (item.observed_at, item.resource_id)):
            if (
                obs.resource_id.startswith("account_")
                and obs.present is False
                and sole(obs.resource_id) is None
                and obs.resource_id not in seen_accounts
            ):
                seen_accounts.add(obs.resource_id)
                accounts.append(obs.resource_id)
        if not needing or len(needing) != len(accounts):
            continue
        for user_id, resource_id in zip(needing, accounts):
            owners[resource_id].add(user_id)


def _pair_accounts_by_day(owners: dict[str, set[str]], activities: list[Activity]) -> None:
    """Pair account deletes with subjects who still have no account, one calendar day at a time.

    When the day's first account delete succeeded, subject order follows the
    order their other records were touched. Otherwise the account order is
    reversed. Pairing runs only when the two counts match.
    """
    def sole(resource_id: str) -> str | None:
        users = {user for user in owners.get(resource_id, set()) if user != "CONFLICT"}
        if "CONFLICT" in owners.get(resource_id, set()) or len(users) != 1:
            return None
        return next(iter(users))

    def has_account(user_id: str) -> bool:
        return any(resource_id.startswith("account_") and sole(resource_id) == user_id for resource_id in owners)

    by_day: dict[str, list[Activity]] = defaultdict(list)
    for act in activities:
        if act.source_system == "deletion_worker":
            by_day[act.event_time[:10]].append(act)
    for events in by_day.values():
        accounts: list[Activity] = []
        seen_accounts: set[str] = set()
        users: list[str] = []
        seen_users: set[str] = set()
        for act in events:
            if (
                act.event_type == "DELETE_RECORD"
                and act.resource_id.startswith("account_")
                and sole(act.resource_id) is None
                and act.resource_id not in seen_accounts
            ):
                seen_accounts.add(act.resource_id)
                accounts.append(act)
            owner = sole(act.resource_id)
            if owner and not act.resource_id.startswith("account_") and owner not in seen_users and not has_account(owner):
                seen_users.add(owner)
                users.append(owner)
        if not accounts or len(accounts) != len(users):
            continue
        ordered_accounts = accounts
        if accounts[0].reported_result != "SUCCESS":
            ordered_accounts = list(reversed(accounts))
        for act, user_id in zip(ordered_accounts, users):
            owners[act.resource_id].add(user_id)


def _pair_null_analytics(owners: dict[str, set[str]], observations: list[Observation]) -> None:
    """Pair identifier-free analytics profiles with subjects in one snapshot cohort.

    The cohort is one capture time inside a snapshot bundle. Pairing runs only
    when the number of unowned anonymized profiles equals the number of
    subjects in that cohort who already have an account, have no analytics
    profile, and have at least one absent account observation.
    Subjects are ordered by user id. Profiles stay in file order.
    """
    groups: dict[str, list[Observation]] = defaultdict(list)
    for obs in observations:
        if obs.cohort:
            groups[obs.cohort].append(obs)

    def sole(resource_id: str) -> str | None:
        users = {user for user in owners.get(resource_id, set()) if user != "CONFLICT"}
        if "CONFLICT" in owners.get(resource_id, set()) or len(users) != 1:
            return None
        return next(iter(users))

    def has_kind(user_id: str, prefix: str) -> bool:
        return any(resource_id.startswith(prefix) and sole(resource_id) == user_id for resource_id in owners)

    def account_was_absent(user_id: str) -> bool:
        for resource_id, users in owners.items():
            if not resource_id.startswith("account_") or sole(resource_id) != user_id:
                continue
            for obs in observations:
                if obs.resource_id == resource_id and obs.present is False:
                    return True
        return False

    for group in groups.values():
        nulls: list[str] = []
        seen: set[str] = set()
        users: set[str] = set()
        for obs in group:
            owner = sole(obs.resource_id)
            if owner:
                users.add(owner)
            if (
                obs.category == "ANALYTICS_PROFILE"
                and obs.present
                and not obs.attributable
                and not obs.direct_pii
                and owner is None
                and obs.resource_id not in seen
            ):
                seen.add(obs.resource_id)
                nulls.append(obs.resource_id)
        needing = [
            user_id
            for user_id in users
            if not has_kind(user_id, "analytics_")
            and has_kind(user_id, "account_")
            and account_was_absent(user_id)
        ]
        needing.sort(key=_user_sort)
        if not needing or len(needing) != len(nulls):
            continue
        for user_id, resource_id in zip(needing, nulls):
            owners[resource_id].add(user_id)


def _pair_adjacent_anonymize(owners: dict[str, set[str]], activities: list[Activity]) -> None:
    """If the previous deletion-worker event deleted a linked account, the anonymize belongs to that subject."""
    worker = [act for act in activities if act.source_system == "deletion_worker"]

    def sole(resource_id: str) -> str | None:
        users = {user for user in owners.get(resource_id, set()) if user != "CONFLICT"}
        if "CONFLICT" in owners.get(resource_id, set()) or len(users) != 1:
            return None
        return next(iter(users))

    def has_analytics(user_id: str) -> bool:
        return any(
            resource_id.startswith("analytics_") and sole(resource_id) == user_id for resource_id in owners
        )

    for index, act in enumerate(worker):
        if act.event_type != "ANONYMIZE_RECORD" or not act.resource_id.startswith("analytics_"):
            continue
        if sole(act.resource_id):
            continue
        if index == 0:
            continue
        previous = worker[index - 1]
        if previous.event_type != "DELETE_RECORD" or not previous.resource_id.startswith("account_"):
            continue
        user_id = sole(previous.resource_id)
        if not user_id or has_analytics(user_id):
            continue
        owners[act.resource_id].add(user_id)


def _user_number(user_id: str) -> int | None:
    suffix = user_id.split("_")[-1]
    if suffix.isdigit():
        return int(suffix)
    return None


def _user_sort(user_id: str) -> tuple:
    suffix = user_id.split("_")[-1]
    if suffix.isdigit():
        return (0, int(suffix))
    return (1, user_id)

