"""Secret lookup port."""

from typing import Protocol


class SecretProvider(Protocol):
    """Resolve secrets without exposing a concrete secret manager."""

    async def get_secret(self, name: str) -> str:
        """Return a secret value or raise when it is unavailable."""
        ...
