from sqlalchemy import (
    Column,
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

from sqlalchemy_risingwave.psycopg2 import RisingWaveDialect_psycopg2


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
