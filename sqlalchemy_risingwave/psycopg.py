"""RisingWave dialect for the psycopg3 driver.

This module binds the driver-agnostic ``_RisingWaveCommon`` mixin to
SQLAlchemy's PostgreSQL ``psycopg`` dialect, registering the dialect under
the ``risingwave+psycopg://`` URL prefix.

**Sync only in PR α.** The asynchronous path (``create_async_engine``) is
NOT covered here: SQLAlchemy resolves the async dialect by calling
``get_async_dialect_cls`` on the sync class, and the upstream
``PGDialect_psycopg`` implementation returns the raw
``PGDialectAsync_psycopg`` from ``sqlalchemy.dialects.postgresql.psycopg``,
which knows nothing about any of the RisingWave overrides (SERIAL rewrite,
parameterised-type strip, Enum/UUID fallback, Superset cancel shim,
RisingWave reflection paths, etc.). We override ``get_async_dialect_cls``
below so the async path fails loudly with a pointer to the tracking issue
instead of silently dispatching to upstream PG. The async dialect itself
lands in PR β of issue #57.
"""

from sqlalchemy import exc
from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg

from .base import _RisingWaveCommon


class RisingWaveDialect_psycopg(_RisingWaveCommon, PGDialect_psycopg):
    driver = "psycopg"
    # ``supports_statement_cache`` must be set on the concrete dialect class
    # because SQLAlchemy reads it via ``self.__class__.__dict__.get(...)`` and
    # ignores inherited values; without this redeclaration SQLAlchemy emits a
    # warning and disables the statement cache for ``risingwave+psycopg://``.
    supports_statement_cache = True

    @classmethod
    def get_async_dialect_cls(cls, url):
        raise exc.InvalidRequestError(
            "Asynchronous RisingWave support via "
            "'risingwave+psycopg://' is not implemented yet. "
            "Use create_engine(...) (synchronous) for now; the async "
            "dialect lands in PR β of "
            "https://github.com/risingwavelabs/sqlalchemy-risingwave/issues/57."
        )
