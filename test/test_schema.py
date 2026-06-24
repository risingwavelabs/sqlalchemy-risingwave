from sqlalchemy import text
from sqlalchemy import MetaData, Table, testing, inspect
from sqlalchemy.testing import fixtures
import sqlalchemy.types as sqltypes

from sqlalchemy_risingwave.base import _get_column_type_from_information_schema


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
        with testing.db.begin():
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

    def test_get_pk_constraint(self):
        insp = inspect(testing.db)
        pk = insp.get_pk_constraint("users")

        assert pk["constrained_columns"] == ["name"]
        assert pk["name"] is not None

    def test_reflected_primary_key_column(self):
        reflected_meta = MetaData()
        users = Table("users", reflected_meta, autoload_with=testing.db)

        assert users.c.name.primary_key
        assert [column.name for column in users.primary_key.columns] == ["name"]

    def test_get_pk_constraint_composite_uses_catalog_order(self):
        with testing.db.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE composite_pk ("
                    "a INT,"
                    "b INT,"
                    "c INT,"
                    "PRIMARY KEY (b, a)"
                    ")"
                )
            )

            insp = inspect(testing.db)
            pk = insp.get_pk_constraint("composite_pk")

            # RisingWave v3.0 reports composite primary keys in table-column
            # order, even when the DDL declared PRIMARY KEY (b, a).
            assert pk["constrained_columns"] == ["a", "b"]
            assert pk["name"] is not None

            conn.execute(text("DROP TABLE composite_pk"))

    def test_get_pk_constraint_no_pk(self):
        with testing.db.begin() as conn:
            conn.execute(text("CREATE TABLE no_pk (x INT)"))

            insp = inspect(testing.db)
            pk = insp.get_pk_constraint("no_pk")

            assert pk == {"constrained_columns": [], "name": None}

            conn.execute(text("DROP TABLE no_pk"))

    def test_get_pk_constraint_named_schema(self):
        with testing.db.begin() as conn:
            conn.execute(text("CREATE SCHEMA pk_schema"))
            conn.execute(
                text("CREATE TABLE pk_schema.schema_pk (id INT PRIMARY KEY)")
            )

            insp = inspect(testing.db)
            pk = insp.get_pk_constraint("schema_pk", schema="pk_schema")

            assert pk["constrained_columns"] == ["id"]
            assert pk["name"] is not None

            conn.execute(text("DROP TABLE pk_schema.schema_pk"))
            conn.execute(text("DROP SCHEMA pk_schema"))

    def test_get_columns_reflects_text_and_alias_types(self):
        with testing.db.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE reflected_types ("
                    "txt TEXT,"
                    "short_name VARCHAR,"
                    "amount DECIMAL"
                    ")"
                )
            )

            insp = inspect(testing.db)
            columns = {
                column["name"]: column["type"]
                for column in insp.get_columns("reflected_types")
            }

            assert isinstance(columns["txt"], sqltypes.VARCHAR)
            assert isinstance(columns["short_name"], sqltypes.VARCHAR)
            assert isinstance(columns["amount"], sqltypes.DECIMAL)
            assert columns["short_name"].length is None
            assert columns["amount"].precision is None
            assert columns["amount"].scale is None

            conn.execute(text("DROP TABLE reflected_types"))

    def test_get_columns_preserves_catalog_numeric_metadata(self):
        column_type = _get_column_type_from_information_schema(
            "numeric",
            "amount",
            numeric_precision=10,
            numeric_scale=2,
        )

        assert isinstance(column_type, sqltypes.DECIMAL)
        assert column_type.precision == 10
        assert column_type.scale == 2

    def test_get_columns_does_not_fabricate_varchar_length(self):
        column_type = _get_column_type_from_information_schema(
            "character varying",
            "name",
            character_maximum_length=12,
        )

        assert isinstance(column_type, sqltypes.VARCHAR)
        assert column_type.length is None

    def test_get_view_names(self):
        with testing.db.begin() as conn:
            conn.execute(text("CREATE TABLE t (id1 INT, id2 INT, id3 INT)"))
            conn.execute(text("CREATE VIEW v AS SELECT * from t"))
            conn.execute(text("CREATE MATERIALIZED VIEW mv AS SELECT * FROM t"))

            insp = inspect(testing.db)
            views = insp.get_view_names()
            materialized_views = insp.get_materialized_view_names()

            assert len(views) == 1
            assert "v" in views
            assert materialized_views == ["mv"]

            conn.execute(text("DROP MATERIALIZED VIEW mv"))
            conn.execute(text("DROP VIEW v"))
            conn.execute(text("DROP TABLE t"))
