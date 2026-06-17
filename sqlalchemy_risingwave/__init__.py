from sqlalchemy.dialects import registry as _registry

__version__ = "2.0.0"

_registry.register(
    "risingwave.psycopg2",
    "sqlalchemy_risingwave.psycopg2",
    "RisingWaveDialect_psycopg2",
)

# psycopg3 driver. Same dialect class is dispatched for both
# ``create_engine("risingwave+psycopg://...")`` and the async
# ``create_async_engine("risingwave+psycopg://...")`` because SQLAlchemy's
# ``PGDialect_psycopg`` parent provides both code paths internally.
_registry.register(
    "risingwave.psycopg",
    "sqlalchemy_risingwave.psycopg",
    "RisingWaveDialect_psycopg",
)

# asyncpg driver is not implemented; see issue
# https://github.com/risingwavelabs/sqlalchemy-risingwave/issues/57 for the
# current async support roadmap, which lands the async path via the psycopg3
# dialect registered above.
