"""Resolve the regional scope of a production-support request."""

from __future__ import annotations

import re
from dataclasses import dataclass

from workspaces.data_engineering.workflows.prod_support.models import Region

US_PATTERN = re.compile(r"\b(?:us|us-01|united states)\b", re.IGNORECASE)
CA_PATTERN = re.compile(r"\b(?:ca|ca-02|canada)\b", re.IGNORECASE)
ALL_REGIONS = (Region.US_01, Region.CA_02)


class ProdSupportScopeError(ValueError):
    """Raised when a production-support regional scope is invalid."""

    @classmethod
    def empty_regions(cls) -> ProdSupportScopeError:
        """Return an error for an empty scope."""
        return cls("production-support scope must include a region")

    @classmethod
    def duplicate_regions(cls) -> ProdSupportScopeError:
        """Return an error for duplicate regions."""
        return cls("production-support scope contains duplicate regions")


@dataclass(frozen=True, slots=True)
class ProdSupportScope:
    """Selected production regions for one request."""

    regions: tuple[Region, ...] = ALL_REGIONS

    def __post_init__(self) -> None:
        """Reject empty, duplicate, or unsupported regional scopes."""
        if not self.regions:
            raise ProdSupportScopeError.empty_regions()
        if len(set(self.regions)) != len(self.regions):
            raise ProdSupportScopeError.duplicate_regions()


def resolve_scope(prompt: str) -> ProdSupportScope:
    """Resolve US, CA, or both regions; generic requests default to both."""
    us_requested = US_PATTERN.search(prompt) is not None
    ca_requested = CA_PATTERN.search(prompt) is not None
    if us_requested and not ca_requested:
        return ProdSupportScope((Region.US_01,))
    if ca_requested and not us_requested:
        return ProdSupportScope((Region.CA_02,))
    return ProdSupportScope()
