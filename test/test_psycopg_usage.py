"""Real-RisingWave sync smoke tests for the psycopg3 driver.

This mirrors ``test/test_usage.py`` (which exercises the dialect through
psycopg2) against the new ``risingwave+psycopg://`` URL so the per-driver
behaviour stays in lockstep. PR α only covers the synchronous path; the
async smoke, concurrency proof, cross-driver consistency and type matrix
land in PR β on the same module.

These tests are skipped when the psycopg3 driver isn't installed so the
existing psycopg2-only CI matrix cell stays green when ``[psycopg3]``
extra hasn't been pulled in.
"""

import pytest

psycopg = pytest.importorskip("psycopg")  # noqa: F401

from sqlalchemy import (
    Column,
    Enum,
    Integer,
    MetaData,
    String,
    Table,
    inspect,
    literal,
    select,
    text,
)
from sqlalchemy.schema import CreateTable
from sqlalchemy import create_engine
from sqlalchemy import testing
from sqlalchemy.testing import fixtures
from sqlalchemy.types import Uuid

from sqlalchemy_risingwave.psycopg import RisingWaveDialect_psycopg


def _psycopg_url():
    """Return the test DB URL switched to the psycopg3 driver.

    ``setup.cfg`` pins the default DB URL to ``risingwave://`` (psycopg2);
    re-using the same host/port/database via the psycopg3 driver is the
    cleanest way to test cross-driver parity without a second CI fixture.
    """

    url = testing.db.url
    return url.set(drivername="risingwave+psycopg")


class PsycopgUsageTest(fixtures.TestBase):
    def teardown_method(self, method):
        engine = create_engine(_psycopg_url())
        try:
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS sqlalchemy_rw_psycopg"))
        finally:
            engine.dispose()

    def test_psycopg_core_query_round_trip(self):
        engine = create_engine(_psycopg_url())
        try:
            with engine.connect() as conn:
                row = conn.execute(
                    select(
                        literal(1).label("id"),
                        literal("alpha").label("name"),
                    )
                ).one()
            assert (row.id, row.name) == (1, "alpha")
        finally:
            engine.dispose()

    def test_psycopg_postgres_cancel_probe_degrades_to_noop(self):
        # The Superset cancel-query shim in ``do_execute`` is shared via the
        # ``_RisingWaveCommon`` mixin, so it must fire on the psycopg3 path
        # too; without this gate the dialect would raise "function not
        # supported" the moment Superset SQL Lab inherits the PostgreSQL
        # cancel probe over a psycopg3 connection.
        engine = create_engine(_psycopg_url())
        try:
            with engine.connect() as conn:
                backend_pid = conn.execute(text("SELECT pg_backend_pid()")).scalar()
                terminated = conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) "
                        "FROM pg_stat_activity WHERE pid='0'"
                    )
                ).scalar()
            assert backend_pid == 0
            assert terminated is False
        finally:
            engine.dispose()

    def test_psycopg_core_ddl_and_reflection_round_trip(self):
        engine = create_engine(_psycopg_url())
        try:
            metadata = MetaData()
            Table(
                "sqlalchemy_rw_psycopg",
                metadata,
                Column("id", Integer, primary_key=True, autoincrement=False),
                Column("name", String),
            )

            metadata.create_all(engine)

            inspector = inspect(engine)
            assert inspector.has_table("sqlalchemy_rw_psycopg")
            columns = inspector.get_columns("sqlalchemy_rw_psycopg")
            assert [column["name"] for column in columns] == ["id", "name"]
        finally:
            engine.dispose()

    def test_psycopg_reflects_table_created_by_core(self):
        engine = create_engine(_psycopg_url())
        try:
            metadata = MetaData()
            Table(
                "sqlalchemy_rw_psycopg",
                metadata,
                Column("id", Integer, primary_key=True, autoincrement=False),
                Column("name", String),
            )
            metadata.create_all(engine)

            reflected_metadata = MetaData()
            reflected = Table(
                "sqlalchemy_rw_psycopg",
                reflected_metadata,
                autoload_with=engine,
            )

            assert [column.name for column in reflected.columns] == ["id", "name"]
            inspector = inspect(engine)
            assert inspector.has_table("sqlalchemy_rw_psycopg")
        finally:
            engine.dispose()

    def test_psycopg_serial_keyword_rewritten_to_integer(self):
        # The DDL rewrite for default-autoincrement integer primary keys is
        # in the mixin's ``ddl_compiler``; this re-exercises it through the
        # psycopg3 path to prove the mixin actually wins MRO ordering.
        engine = create_engine(_psycopg_url())
        try:
            metadata = MetaData()
            Table(
                "sqlalchemy_rw_psycopg",
                metadata,
                Column("id", Integer, primary_key=True),  # implicit autoincrement
                Column("name", String),
            )

            metadata.create_all(engine)

            inspector = inspect(engine)
            assert inspector.has_table("sqlalchemy_rw_psycopg")
        finally:
            engine.dispose()

    def test_psycopg_type_compiler_strips_pg_length_and_precision_parameters(self):
        from sqlalchemy import CHAR, DECIMAL, NUMERIC

        metadata = MetaData()
        table = Table(
            "sqlalchemy_rw_psycopg_type_params",
            metadata,
            Column("varchar_sized", String(50)),
            Column("char_sized", CHAR(3)),
            Column("numeric_sized", NUMERIC(10, 2)),
            Column("decimal_sized", DECIMAL(8, 4)),
            Column("varchar_default", String),
        )

        ddl = str(
            CreateTable(table).compile(dialect=RisingWaveDialect_psycopg())
        )

        for forbidden in ("VARCHAR(50)", "CHAR(3)", "NUMERIC(10, 2)", "DECIMAL(8, 4)"):
            assert forbidden not in ddl, (
                f"emitted {forbidden!r}, which RisingWave's DDL parser rejects"
            )
        assert ddl.count("VARCHAR") >= 3
        assert "NUMERIC" in ddl
        assert "DECIMAL" in ddl

    def test_psycopg_create_table_with_parameterized_pg_types_runs_on_risingwave(self):
        engine = create_engine(_psycopg_url())
        try:
            metadata = MetaData()
            Table(
                "sqlalchemy_rw_psycopg",
                metadata,
                Column("id", Integer, primary_key=True),
                Column("varchar_sized", String(50)),
                Column("name", String),
            )

            metadata.create_all(engine)

            inspector = inspect(engine)
            assert inspector.has_table("sqlalchemy_rw_psycopg")
        finally:
            engine.dispose()

    def test_psycopg_enum_and_uuid_compile_to_varchar(self):
        metadata = MetaData()
        table = Table(
            "sqlalchemy_rw_psycopg_logical_types",
            metadata,
            Column("status", Enum("ready", "failed", name="status_enum")),
            Column("external_id", Uuid()),
        )

        ddl = str(
            CreateTable(table).compile(dialect=RisingWaveDialect_psycopg())
        )

        assert "CREATE TYPE" not in ddl
        assert "status_enum" not in ddl
        assert " UUID" not in ddl
        assert ddl.count("VARCHAR") >= 2

    def test_psycopg_create_table_with_enum_and_uuid_runs_on_risingwave(self):
        engine = create_engine(_psycopg_url())
        try:
            metadata = MetaData()
            Table(
                "sqlalchemy_rw_psycopg",
                metadata,
                Column("id", Integer, primary_key=True),
                Column("status", Enum("ready", "failed", name="status_enum")),
                Column("external_id", Uuid()),
            )

            metadata.create_all(engine)

            inspector = inspect(engine)
            assert inspector.has_table("sqlalchemy_rw_psycopg")
        finally:
            engine.dispose()
