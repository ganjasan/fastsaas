"""Pydantic response shapes for the search foundation.

`SearchHit` is the universal row type returned by every `SearchProvider`.
`SearchGroup` wraps a per-entity-type list of hits with a UI label.
`SearchResponse` is the aggregate envelope returned by `GET /search`.

The shapes are deliberately flat — entity-specific metadata travels in
`title` / `subtitle` / `href` rather than a per-entity discriminated
union. This keeps the orval-generated TypeScript ergonomic (one type
across all providers) and matches the renderer-registry pattern on the
frontend (one renderer per entity_type, picked by lookup, not switch).
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SearchHit(BaseModel):
    """One result row, produced by exactly one `SearchProvider`."""

    model_config = ConfigDict(from_attributes=True)

    entity_type: str
    entity_id: UUID
    title: str
    subtitle: str | None = None
    href: str


class SearchGroup(BaseModel):
    """Group of hits sharing an entity_type, labelled for UI."""

    entity_type: str
    label: str
    hits: list[SearchHit]


class SearchResponse(BaseModel):
    """Aggregate envelope returned by `GET /search`."""

    query: str
    groups: list[SearchGroup]
