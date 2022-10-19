from sqlalchemy.dialects.postgresql.base import PGDialect

class RisingWaveDialect(PGDialect):
    name = "risingwave"

    # Do not override connect
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def dbapi(cls):
        raise NotImplementedError

    def initialize(self, connection):
        super(PGDialect, self).initialize(connection)

    def _get_server_version_info(self, conn):
        return (9, 5, 0)

    def get_table_names(self, conn, schema=None, **kw):
        raise NotImplementedError

    def has_table(self, conn, table, schema=None):
        return any(t == table for t in self.get_table_names(conn, schema=schema))

    def get_columns(self, conn, table_name, schema=None, **kw):
        raise NotImplementedError

    def get_indexes(self, conn, table_name, schema=None, **kw):
        raise NotImplementedError

    def get_foreign_keys_v1(self, conn, table_name, schema=None, **kw):
        raise NotImplementedError

    def get_foreign_keys(
        self, connection, table_name, schema=None, postgresql_ignore_search_path=False, **kw
    ):
        raise NotImplementedError

    def get_pk_constraint(self, conn, table_name, schema=None, **kw):
        raise NotImplementedError

    def get_unique_constraints(self, conn, table_name, schema=None, **kw):
        raise NotImplementedError

    def get_check_constraints(self, conn, table_name, schema=None, **kw):
        raise NotImplementedError

    def do_rollback_to_savepoint(self, connection, name):
        raise NotImplementedError

    def do_release_savepoint(self, connection, name):
        raise NotImplementedError

    def get_isolation_level(self, connection):
        return {"default": "SERIALIZABLE", "supported": ["SERIALIZABLE"]}

    def get_isolation_level_values(self, dbapi_conn):
        return (
            "SERIALIZABLE",
            "READ UNCOMMITTED",
            "READ COMMITTED",
            "REPEATABLE READ",
        )

    def get_default_isolation_level(self, dbapi_conn):
        return self.get_isolation_level(dbapi_conn)