"""RisingWave dialect for the psycopg3 driver.

This module binds the driver-agnostic ``_RisingWaveCommon`` mixin to
SQLAlchemy's PostgreSQL ``psycopg`` dialect, registering the dialect under
the ``risingwave+psycopg://`` URL prefix. The same class supports both the
synchronous ``create_engine`` entry point and the asynchronous
``create_async_engine`` entry point because SQLAlchemy's ``PGDialect_psycopg``
dispatches to ``psycopg``'s sync or async path based on the engine factory.

Note that PR α only exercises the synchronous path; the async fixtures and
the concurrency / cross-driver / type-matrix acceptance tests land with PR β
on the same module.
"""

from sqlalchemy.dialects.postgresql.psycopg import PGDialect_psycopg

from .base import _RisingWaveCommon


class RisingWaveDialect_psycopg(_RisingWaveCommon, PGDialect_psycopg):
    driver = "psycopg"
    # ``supports_statement_cache`` must be set on the concrete dialect class
    # because SQLAlchemy reads it via ``self.__class__.__dict__.get(...)`` and
    # ignores inherited values; without this redeclaration SQLAlchemy emits a
    # warning and disables the statement cache for ``risingwave+psycopg://``.
    supports_statement_cache = True
