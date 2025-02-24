from sqlalchemy import text
from sqlalchemy import MetaData, Table, testing, inspect
from sqlalchemy.testing import fixtures


class SchemaTest(fixtures.TestBase):

    def teardown_method(self, method):
        with testing.db.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS users"))

    def setup_method(self):
        with testing.db.begin() as conn:
            conn.execute(text("CREATE TABLE users (name STRING PRIMARY KEY)"))
        self.meta = MetaData(schema="public")

    def test_get_columns_indexes_across_schema(self):
        # get_columns and get_indexes use default db uri schema.
        # across schema table must use schema.table
        Table("users", self.meta, autoload_with=testing.db, schema="public")

    def test_has_table(self):
        with testing.db.begin() as conn:
            insp = inspect(testing.db)
            assert insp.has_table(table_name="users", schema="public")

    def test_get_indexes(self):
        with testing.db.begin() as conn:
            conn.execute(text("CREATE TABLE t (id1 INT, id2 INT, id3 INT)"))
            conn.execute(text("CREATE INDEX idx ON t(id2) INCLUDE(id1)"))

            insp = inspect(testing.db)
            indexes = insp.get_indexes("t")

            assert len(indexes) == 1
            assert indexes[0]["name"] == "idx"
            assert indexes[0]["column_names"] == ["id2", "id1"]

            conn.execute(text("DROP TABLE t"))

    def test_get_view_names(self):
        with testing.db.begin() as conn:
            conn.execute(text("CREATE TABLE t (id1 INT, id2 INT, id3 INT)"))
            conn.execute(text("CREATE VIEW v AS SELECT * from t"))
            conn.execute(text("CREATE MATERIALIZED VIEW mv AS SELECT * FROM t"))

            insp = inspect(testing.db)
            views = insp.get_view_names()

            assert len(views) == 2
            assert "v" in views
            assert "mv" in views

            insp = inspect(testing.db)
            views = insp.get_view_names(include = ("plain"))

            assert len(views) == 1
            assert "v" in views

            insp = inspect(testing.db)
            views = insp.get_view_names(include = ("materialized"))

            assert len(views) == 1
            assert "mv" in views

            conn.execute(text("DROP MATERIALIZED VIEW mv"))
            conn.execute(text("DROP VIEW v"))
            conn.execute(text("DROP TABLE t"))
