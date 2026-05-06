"""Foundation search providers — project + member.

Imported by `fastsaas.search.__init__` which performs the registration
calls. Downstream products implement their own providers and call
`register_provider(...)` from their own module imports.
"""

from fastsaas.search.providers.members import MemberSearchProvider
from fastsaas.search.providers.projects import ProjectSearchProvider

__all__ = ["MemberSearchProvider", "ProjectSearchProvider"]
