"""GDPR Art.17 right-to-erasure for `audit_log.intent_metadata`.

Per ADR-010 §"Second amendment — PII scrub contract", the audit table is
immortal and `app_user` cannot mutate it. This module is the one sanctioned
mutation path: a DPO with `Operation.SCRUB` on `audit_log` calls
`AuditScrubService.scrub(...)`, which runs an UPDATE through the migrator
(BYPASSRLS) session to replace `intent_metadata.{ip, user_agent,
original_prompt, path}` with the literal `"<scrubbed:gdpr>"`. Structural
columns (`actor_id`, `entity_type`, `entity_id`, `action`, `timestamp`,
`intent_hash`, `diff`, `organisation_id`) are NEVER touched — the scrub
preserves the audit trail and only zeroes client-controlled PII fields.

The scrub itself writes a meta-audit row (`entity_type="audit_scrub"`) in
the same transaction so the act of scrubbing is provable.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from fastsaas.audit.intent import PII_INTENT_KEYS
from fastsaas.audit.service import record
from fastsaas.db import migrator_session_scope
from fastsaas.identity.schemas import CurrentActor

SCRUBBED_GDPR_LITERAL = "<scrubbed:gdpr>"

# Set of `intent_metadata` keys the scrub erases. Mirrors `intent.py::
# PII_INTENT_KEYS` — the assert below fails loud if the two drift. New
# client-controlled keys added to intent.py must either join this set or
# be deliberately excluded with a written reason in ADR-010.
SCRUBBED_FIELDS: tuple[str, ...] = ("ip", "user_agent", "original_prompt", "path")

assert tuple(SCRUBBED_FIELDS) == PII_INTENT_KEYS, (
    f"SCRUBBED_FIELDS={SCRUBBED_FIELDS} drifted from "
    f"intent.PII_INTENT_KEYS={PII_INTENT_KEYS}; extend the scrub set or "
    "exclude the new key in ADR-010 second amendment"
)


class ScrubFilterError(ValueError):
    """Filter validation error. `code` maps to the API error code."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class ScrubFilter(BaseModel):
    """At least one field must be set; unknown keys reject (extra=forbid).

    All four fields are AND-combined inside the SQL — narrow scope wins on
    a destructive endpoint (a DPO needing OR composes two calls)."""

    model_config = ConfigDict(extra="forbid")

    actor_id: UUID | None = None
    ip: str | None = None
    since: datetime | None = None
    until: datetime | None = None

    def is_empty(self) -> bool:
        return not any(
            (self.actor_id, self.ip, self.since, self.until)
        )


class ScrubRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filter: ScrubFilter
    dry_run: bool = False


class ScrubResult(BaseModel):
    rows_scrubbed: int
    dry_run: bool


def _filter_clauses(f: ScrubFilter) -> tuple[str, dict[str, object]]:
    """Build the AND-joined WHERE fragment for the supplied filter."""
    clauses: list[str] = []
    params: dict[str, object] = {}
    if f.actor_id is not None:
        clauses.append("actor_id = :actor_id")
        params["actor_id"] = str(f.actor_id)
    if f.ip is not None:
        clauses.append("intent_metadata->>'ip' = :ip")
        params["ip"] = f.ip
    if f.since is not None:
        clauses.append("timestamp >= :since")
        params["since"] = f.since
    if f.until is not None:
        clauses.append("timestamp <= :until")
        params["until"] = f.until
    return " AND ".join(clauses), params


# Row needs scrubbing if at least one of the four PII keys is present and
# not yet equal to the sentinel — this both excludes already-scrubbed rows
# from the matched set (so re-runs naturally return 0) and avoids issuing
# UPDATEs on rows that wouldn't change anyway.
_UNSCRUBBED_CONDITION = " OR ".join(
    f"(intent_metadata ? '{field}' "
    f"AND intent_metadata->>'{field}' != '{SCRUBBED_GDPR_LITERAL}')"
    for field in SCRUBBED_FIELDS
)


def _build_jsonb_set_expr() -> str:
    """Wrap `jsonb_set` four times — one per scrubbable field. Uses
    `create_missing => false` so absent keys stay absent (presence-of-key
    is signal: the compliance officer should still be able to tell that
    this row never carried e.g. an `original_prompt`)."""
    expr = "intent_metadata"
    for field in SCRUBBED_FIELDS:
        expr = (
            f"jsonb_set({expr}, '{{{field}}}', "
            f"'\"{SCRUBBED_GDPR_LITERAL}\"'::jsonb, false)"
        )
    return expr


_JSONB_SET_EXPR = _build_jsonb_set_expr()


class AuditScrubService:
    @staticmethod
    async def scrub(
        *,
        org_id: UUID,
        dpo: CurrentActor,
        scrub_filter: ScrubFilter,
        dry_run: bool,
    ) -> ScrubResult:
        """Run the scrub UPDATE (or its dry-run count). Always org-scoped.

        Wet path writes one `audit_scrub` meta row in the same transaction
        as the UPDATE, so the scrub itself is auditable. Dry-run only
        counts; no UPDATE, no meta row.
        """
        if scrub_filter.is_empty():
            raise ScrubFilterError(
                "Filter must include at least one of: actor_id, ip, since, until",
                code="audit.scrub.empty_filter",
            )

        filter_sql, filter_params = _filter_clauses(scrub_filter)
        where = (
            "organisation_id = :org_id "
            f"AND {filter_sql} "
            f"AND ({_UNSCRUBBED_CONDITION})"
        )
        base_params = {"org_id": str(org_id), **filter_params}

        async with migrator_session_scope() as db:
            if dry_run:
                count_row = await db.execute(
                    text(f"SELECT count(*) FROM audit_log WHERE {where}"),
                    base_params,
                )
                count = int(count_row.scalar() or 0)
                return ScrubResult(rows_scrubbed=count, dry_run=True)

            update_result = await db.execute(
                text(
                    "UPDATE audit_log "
                    f"SET intent_metadata = {_JSONB_SET_EXPR} "
                    f"WHERE {where}"
                ),
                base_params,
            )
            rows_scrubbed = update_result.rowcount or 0

            await record(
                db,
                action="scrub",
                entity_type="audit_scrub",
                entity_id=uuid4(),
                actor=dpo,
                organisation_id=org_id,
                diff={
                    "before": {},
                    "after": {
                        "filter": scrub_filter.model_dump(
                            mode="json", exclude_none=True
                        ),
                        "rows_scrubbed": rows_scrubbed,
                    },
                },
            )
            return ScrubResult(rows_scrubbed=rows_scrubbed, dry_run=False)
