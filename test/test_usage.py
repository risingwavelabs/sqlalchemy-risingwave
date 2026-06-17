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
from sqlalchemy import testing
from sqlalchemy.testing import fixtures
from sqlalchemy.types import Uuid

from sqlalchemy_risingwave.psycopg2 import RisingWaveDialect_psycopg2
from sqlalchemy_risingwave.requirements import Requirements


class UsageTest(fixtures.TestBase):
    def teardown_method(self, method):
        with testing.db.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS sqlalchemy_rw_usage"))

    def test_sqlalchemy_core_query_round_trip(self):
        with testing.db.connect() as conn:
            row = conn.execute(
                select(
                    literal(1).label("id"),
                    literal("alpha").label("name"),
                )
            ).one()

        assert (row.id, row.name) == (1, "alpha")

    def test_postgres_cancel_probe_degrades_to_noop(self):
        with testing.db.connect() as conn:
            backend_pid = conn.execute(text("SELECT pg_backend_pid()")).scalar()
            terminated = conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity WHERE pid='0'"
                )
            ).scalar()

        assert backend_pid == 0
        assert terminated is False

    def test_sqlalchemy_core_ddl_and_reflection_round_trip(self):
        metadata = MetaData()
        Table(
            "sqlalchemy_rw_usage",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=False),
            Column("name", String),
        )

        metadata.create_all(testing.db)

        inspector = inspect(testing.db)
        assert inspector.has_table("sqlalchemy_rw_usage")
        columns = inspector.get_columns("sqlalchemy_rw_usage")
        assert [column["name"] for column in columns] == ["id", "name"]

    def test_sqlalchemy_reflects_table_created_by_core(self):
        metadata = MetaData()
        Table(
            "sqlalchemy_rw_usage",
            metadata,
            Column("id", Integer, primary_key=True, autoincrement=False),
            Column("name", String),
        )
        metadata.create_all(testing.db)

        reflected_metadata = MetaData()
        reflected = Table(
            "sqlalchemy_rw_usage",
            reflected_metadata,
            autoload_with=testing.db,
        )

        assert [column.name for column in reflected.columns] == ["id", "name"]

        inspector = inspect(testing.db)
        assert inspector.has_table("sqlalchemy_rw_usage")
        columns = inspector.get_columns("sqlalchemy_rw_usage")
        assert [column["name"] for column in columns] == ["id", "name"]

    def test_serial_keyword_rewritten_to_integer(self):
        # When ``autoincrement`` is the SQLAlchemy default (i.e. an
        # ``Integer`` primary key without ``autoincrement=False``), the
        # PG parent compiler emits ``SERIAL``. RisingWave rejects that
        # DDL; the dialect must rewrite the keyword to ``INTEGER`` so
        # CREATE TABLE actually succeeds. Most of the upstream
        # ``sqlalchemy.testing.suite`` fixtures rely on this implicit
        # autoincrement shape, so this is the gate that lets the
        # compliance suite progress past fixture setup.
        metadata = MetaData()
        Table(
            "sqlalchemy_rw_usage",
            metadata,
            Column("id", Integer, primary_key=True),  # implicit autoincrement
            Column("name", String),
        )

        metadata.create_all(testing.db)

        inspector = inspect(testing.db)
        assert inspector.has_table("sqlalchemy_rw_usage")

    def test_serial_rewrite_does_not_mutate_default_literals(self):
        metadata = MetaData()
        table = Table(
            "sqlalchemy_rw_defaults",
            metadata,
            Column("note", String, server_default=text("' SERIAL'")),
        )

        ddl = str(
            CreateTable(table).compile(dialect=RisingWaveDialect_psycopg2())
        )

        assert "DEFAULT ' SERIAL'" in ddl
        assert "DEFAULT ' INTEGER'" not in ddl

    def test_type_compiler_strips_pg_length_and_precision_parameters(self):
        # RisingWave's DDL parser rejects every PG-style parameterised type:
        # ``CHAR(n)`` / ``VARCHAR(n)`` / ``NUMERIC(p,s)`` / ``DECIMAL(p,s)``.
        # The compliance suite's fixtures rely heavily on these shapes
        # (``String(50)``, ``DECIMAL(10, 2)`` etc.), so any test using them
        # used to fail during CREATE TABLE setup. Confirm at compile time
        # that the dialect emits the bare keyword form RisingWave accepts.
        from sqlalchemy import CHAR, DECIMAL, NUMERIC

        metadata = MetaData()
        table = Table(
            "sqlalchemy_rw_type_params",
            metadata,
            Column("varchar_sized", String(50)),
            Column("char_sized", CHAR(3)),
            Column("numeric_sized", NUMERIC(10, 2)),
            Column("decimal_sized", DECIMAL(8, 4)),
            Column("varchar_default", String),
        )

        ddl = str(
            CreateTable(table).compile(dialect=RisingWaveDialect_psycopg2())
        )

        for forbidden in ("VARCHAR(50)", "CHAR(3)", "NUMERIC(10, 2)", "DECIMAL(8, 4)"):
            assert forbidden not in ddl, (
                f"emitted {forbidden!r}, which RisingWave's DDL parser rejects"
            )
        # CHAR is rewritten to VARCHAR per the RisingWave hint message, not
        # carried through unchanged. Confirm both the bare VARCHAR and the
        # rewrite of CHAR are present.
        assert ddl.count("VARCHAR") >= 3
        assert "CHAR" not in ddl.replace("VARCHAR", "")
        assert "NUMERIC" in ddl
        assert "DECIMAL" in ddl

    def test_create_table_with_parameterized_pg_types_runs_on_risingwave(self):
        metadata = MetaData()
        Table(
            "sqlalchemy_rw_usage",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("varchar_sized", String(50)),
            Column("name", String),
        )

        # Real RisingWave round trip: with the type-compiler override the
        # emitted DDL must actually be runnable. Before this change the same
        # table definition fails with ``expected ',' or ')' after column
        # definition, found: '('``.
        metadata.create_all(testing.db)

        inspector = inspect(testing.db)
        assert inspector.has_table("sqlalchemy_rw_usage")

    def test_enum_and_uuid_compile_to_varchar(self):
        metadata = MetaData()
        table = Table(
            "sqlalchemy_rw_logical_types",
            metadata,
            Column("status", Enum("ready", "failed", name="status_enum")),
            Column("external_id", Uuid()),
        )

        ddl = str(
            CreateTable(table).compile(dialect=RisingWaveDialect_psycopg2())
        )

        assert "CREATE TYPE" not in ddl
        assert "status_enum" not in ddl
        assert " UUID" not in ddl
        assert ddl.count("VARCHAR") >= 2

    def test_create_table_with_enum_and_uuid_runs_on_risingwave(self):
        metadata = MetaData()
        Table(
            "sqlalchemy_rw_usage",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("status", Enum("ready", "failed", name="status_enum")),
            Column("external_id", Uuid()),
        )

        metadata.create_all(testing.db)

        inspector = inspect(testing.db)
        assert inspector.has_table("sqlalchemy_rw_usage")

    def test_compliance_requirements_disable_unsupported_fk_and_uuid_features(self):
        requirements = Requirements()

        assert not requirements.foreign_keys.enabled
        assert not requirements.foreign_key_ddl.enabled
        assert not requirements.self_referential_foreign_keys.enabled
        assert not requirements.foreign_key_constraint_reflection.enabled
        assert not requirements.uuid_data_type.enabled
