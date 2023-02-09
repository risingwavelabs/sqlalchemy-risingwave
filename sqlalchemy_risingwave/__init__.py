from sqlalchemy.dialects import registry as _registry

__version__ = "0.0.9"

_registry.register(
    "risingwave.psycopg2",
    "sqlalchemy_risingwave.psycopg2",
    "RisingWaveDialect_psycopg2",
)
_registry.register(
    "risingwave.asyncpg",
    "sqlalchemy_risingwave.asyncpg",
    "RisingWaveDialect_asyncpg",
)
