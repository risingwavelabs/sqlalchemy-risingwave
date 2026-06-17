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
from sqlalchemy import testing
from sqlalchemy.testing import fixtures


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
