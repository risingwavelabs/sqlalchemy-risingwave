from sqlalchemy.dialects import registry as _registry

__version__ = "2.0.0"

_registry.register(
    "risingwave.psycopg2",
    "sqlalchemy_risingwave.psycopg2",
    "RisingWaveDialect_psycopg2",
)

# psycopg3 driver, synchronous and asynchronous.
# ``create_engine("risingwave+psycopg://...")`` resolves to the sync
# ``RisingWaveDialect_psycopg`` class, while
# ``create_async_engine("risingwave+psycopg://...")`` is routed to the
# async ``RisingWaveDialect_psycopg_async`` class via the sync class's
# ``get_async_dialect_cls`` override so both paths inherit the
# ``_RisingWaveCommon`` mixin instead of falling back to upstream
# ``PGDialectAsync_psycopg``.
_registry.register(
    "risingwave.psycopg",
    "sqlalchemy_risingwave.psycopg",
    "RisingWaveDialect_psycopg",
)

# asyncpg driver is not implemented; the supported async path is the
# psycopg3 dialect registered above. See
# https://github.com/risingwavelabs/sqlalchemy-risingwave/issues/57
# for additional context.
