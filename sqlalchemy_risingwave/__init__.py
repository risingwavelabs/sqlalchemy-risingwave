from sqlalchemy.dialects import registry as _registry

__version__ = "2.0.0"

_registry.register(
    "risingwave.psycopg2",
    "sqlalchemy_risingwave.psycopg2",
    "RisingWaveDialect_psycopg2",
)

# psycopg3 driver, synchronous only in this release.
# ``create_engine("risingwave+psycopg://...")`` is supported.
# ``create_async_engine("risingwave+psycopg://...")`` is intentionally
# rejected at the dialect layer because SQLAlchemy's upstream
# ``PGDialect_psycopg.get_async_dialect_cls`` returns an async class with
# no RisingWave overrides; the async dialect is tracked in
# https://github.com/risingwavelabs/sqlalchemy-risingwave/issues/57.
_registry.register(
    "risingwave.psycopg",
    "sqlalchemy_risingwave.psycopg",
    "RisingWaveDialect_psycopg",
)

# asyncpg driver is not implemented; see the same issue #57 for the
# async support roadmap.
