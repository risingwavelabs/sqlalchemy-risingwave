from sqlalchemy import distinct, func, MetaData, Table, testing, text
from sqlalchemy import MetaData, Table, Column, Integer, String, testing, inspect
from sqlalchemy.testing import fixtures, eq_

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
        self.meta = MetaData(schema="public")

    def test_get_columns_indexes_across_schema(self):
        # get_columns and get_indexes use default db uri schema.
        # across schema table must use schema.table
        Table("users", self.meta, autoload_with=testing.db, schema="public")

    def test_returning_clause(self):
        with testing.db.begin() as conn:
            insp = inspect(testing.db)
            col_info = insp.get_table_names(conn)

            for row in col_info:
                assert row == str("users")
