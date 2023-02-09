from sqlalchemy import text
from sqlalchemy import MetaData, Table, testing, inspect
from sqlalchemy.testing import fixtures


class SchemaTest(fixtures.TestBase):

    def teardown_method(self, method):
        with testing.db.begin() as conn:
            conn.execute("DROP TABLE IF EXISTS users")

    def setup_method(self):
        with testing.db.begin() as conn:
            conn.execute("CREATE TABLE users (name STRING PRIMARY KEY)")
        self.meta = MetaData(schema="public")

    def test_get_columns_indexes_across_schema(self):
        # get_columns and get_indexes use default db uri schema.
        # across schema table must use schema.table
        Table("users", self.meta, autoload_with=testing.db, schema="public")

    def test_returning_clause(self):
        with testing.db.begin() as conn:
            insp = inspect(testing.db)
            table_names = insp.get_table_names()

            for t in table_names:
                assert t == str("users")

    def test_get_indexes(self):
        with testing.db.begin() as conn:
            conn.execute("CREATE TABLE three_columns (id1 INT, id2 INT, id3 INT)")
            conn.execute("CREATE INDEX three_columns_idx ON three_columns(id2) INCLUDE(id1)")

            insp = inspect(testing.db)
            indexes = insp.get_indexes("three_columns")

            assert len(indexes) == 1
            assert indexes[0]["name"] == "three_columns_idx"
            assert indexes[0]["column_names"] == ["id2", "id1"]

            conn.execute("DROP TABLE three_columns")

    def test_get_view_names(self):
        with testing.db.begin() as conn:
            conn.execute("CREATE TABLE three_columns (id1 INT, id2 INT, id3 INT)")
            conn.execute("CREATE VIEW three_view AS SELECT * from three_columns")

            insp = inspect(testing.db)
            indexes = insp.get_view_names()

            assert len(indexes) == 1
            assert indexes[0] == "three_view"

            conn.execute("DROP VIEW three_view")
            conn.execute("DROP TABLE three_columns")
