"""Search foundation — single `/search` endpoint + extensible provider registry.

Public surface for downstream products and AI agents:

- `SearchProvider` — Protocol class to implement per entity type.
- `register_provider(p)` — call at module-load time to register.
- `SearchHit`, `SearchGroup`, `SearchResponse` — wire shapes.
- `search_all` — orchestrator (rare external use; the route already
  invokes it).

See `search/CLAUDE.md` for the extension contract + recipe + naming
convention.
"""

from fastsaas.search.models import SearchGroup, SearchHit, SearchResponse
from fastsaas.search.providers import MemberSearchProvider, ProjectSearchProvider
from fastsaas.search.registry import (
    SearchProvider,
    SearchProviderConflictError,
    providers,
    register_provider,
)
from fastsaas.search.service import search_all

# Foundation providers register on import. Downstream products call
# `register_provider(...)` from their own module imports — same pattern
# as the Settings / Branding pages registering their feature surfaces.
register_provider(ProjectSearchProvider())
register_provider(MemberSearchProvider())

__all__ = [
    "MemberSearchProvider",
    "ProjectSearchProvider",
    "SearchGroup",
    "SearchHit",
    "SearchProvider",
    "SearchProviderConflictError",
    "SearchResponse",
    "providers",
    "register_provider",
    "search_all",
]
