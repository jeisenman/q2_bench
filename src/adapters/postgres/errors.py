"""PostgreSQL agent-memory adapter exceptions."""


class PostgresMemoryConfigurationError(RuntimeError):
    """Raised when PostgreSQL memory configuration is unavailable."""


class PostgresMemoryError(RuntimeError):
    """Raised when durable memory cannot be read or updated safely."""
