"""RisingWave dialect for the psycopg3 driver, sync and async.

Two concrete classes live here:

* ``RisingWaveDialect_psycopg`` is the synchronous dialect dispatched by
  ``create_engine("risingwave+psycopg://...")``.
* ``RisingWaveDialect_psycopg_async`` is the asynchronous dialect SQLAlchemy
  reaches via ``RisingWaveDialect_psycopg.get_async_dialect_cls(...)`` when
  the application calls ``create_async_engine("risingwave+psycopg://...")``.

Both compose the driver-agnostic ``_RisingWaveCommon`` mixin first in MRO so
the RisingWave behaviour (SERIAL rewrite, parameterised-type strip,
Enum/UUID fallback, Superset cancel-query shim, RisingWave reflection
paths) wins over the upstream PG defaults. ``supports_statement_cache``
is redeclared on both concrete classes because SQLAlchemy reads it from
``self.__class__.__dict__`` rather than walking the MRO.

Overriding ``get_async_dialect_cls`` on the sync class is the gate that
prevents SQLAlchemy from silently dispatching ``create_async_engine`` to
the raw upstream ``PGDialectAsync_psycopg``, which has none of these
overrides and would surface as confusing behaviour (e.g. ``name`` reports
``"postgresql"``, SERIAL DDL errors against RisingWave's parser, no
Superset shim).
"""

from sqlalchemy.dialects.postgresql.psycopg import (
    PGDialectAsync_psycopg,
    PGDialect_psycopg,
)

from .base import _RisingWaveCommon


class RisingWaveDialect_psycopg_async(_RisingWaveCommon, PGDialectAsync_psycopg):
    """Asynchronous RisingWave dialect over psycopg3.

    Used by ``create_async_engine("risingwave+psycopg://...")``. The class
    body is intentionally minimal: every RisingWave override is contributed
    by ``_RisingWaveCommon`` so async and sync stay in lockstep,
    ``is_async`` comes from ``PGDialectAsync_psycopg``, the inherited
    ``driver`` stays ``"psycopg"`` to match the SQLAlchemy convention and
    the ``risingwave+psycopg://`` URL form (the driver name is the DBAPI,
    not the sync-vs-async mode), and ``supports_statement_cache`` is set
    explicitly because SQLAlchemy reads it from ``self.__class__.__dict__``.
    """

    supports_statement_cache = True


class RisingWaveDialect_psycopg(_RisingWaveCommon, PGDialect_psycopg):
    driver = "psycopg"
    # ``supports_statement_cache`` must be set on the concrete dialect class
    # because SQLAlchemy reads it via ``self.__class__.__dict__.get(...)`` and
    # ignores inherited values; without this redeclaration SQLAlchemy emits a
    # warning and disables the statement cache for ``risingwave+psycopg://``.
    supports_statement_cache = True

    @classmethod
    def get_async_dialect_cls(cls, url):
        # Replace the PR α guard with a RisingWave-aware async class. The
        # upstream default would return ``PGDialectAsync_psycopg`` directly,
        # which strips every RisingWave override; the override below ensures
        # ``create_async_engine("risingwave+psycopg://...")`` lands on a
        # dialect whose ``name`` is ``"risingwave"`` and whose compiler /
        # reflection / Superset behaviour matches the synchronous path.
        return RisingWaveDialect_psycopg_async
