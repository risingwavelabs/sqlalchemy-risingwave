from sqlalchemy import text
from sqlalchemy import MetaData, Table, testing, inspect
from sqlalchemy.testing import fixtures


class SchemaTest(fixtures.TestBase):

    def teardown_method(self, method):
        with testing.db.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS users"))

    def setup_method(self):
        with testing.db.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE users (
                        name STRING PRIMARY KEY
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "CREATE index users_idx on users(name)"
                )
            )
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
            insp = inspect(testing.db)
            indexes = insp.get_indexes("users")

            for index in indexes:
                assert index["name"] == str("users_idx")
                assert index["column_names"] == ["name"]
