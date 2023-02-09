import re

from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
from sqlalchemy import text
from sqlalchemy.util import warn
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID

import sqlalchemy.types as sqltypes
_type_map = {
    "boolean": sqltypes.BOOLEAN,  # DataType::Boolean
    "smallint": sqltypes.SMALLINT,  # DataType::Int16
    "integer": sqltypes.INT,  # DataType::Int32
    "bigint": sqltypes.BIGINT,  # DataType::Int64
    "real": sqltypes.FLOAT,  # DataType::Float32
    "double precision": sqltypes.FLOAT,  # DataType::Float64
    "numeric": sqltypes.DECIMAL,  # DataType::Decimal
    "date": sqltypes.DATE,  # DataType::Date
    "varchar": sqltypes.VARCHAR,  # DataType::Varchar
    "time without time zone": sqltypes.Time,  # DataType::Time
    "timestamp without time zone": sqltypes.TIMESTAMP,  # DataType::Timestamp
    "timestamp with time zone": sqltypes.TIMESTAMP,  # DataType::Timestampz
    "interval": sqltypes.Interval,  # DataType::Interval
}


class RisingWaveDialect(PGDialect_psycopg2):
    name = "risingwave"

    # Do not override connect
    def __init__(self, *args, **kwargs):
        if kwargs.get("use_native_hstore", False):
            raise NotImplementedError("use_native_hstore is not supported")
        if kwargs.get("server_side_cursors", False):
            raise NotImplementedError("server_side_cursors is not supported")
        kwargs["use_native_hstore"] = False
        kwargs["server_side_cursors"] = False
        super().__init__(*args, **kwargs)

    def initialize(self, connection):
        super(PGDialect, self).initialize(connection)

    def _get_server_version_info(self, conn):
        return (9, 5, 0)

    def get_table_names(self, conn, schema=None, **kw):
        sql = (
            "SELECT table_name FROM information_schema.tables WHERE "
            "table_schema = :table_schema"
        )
        rows = conn.execute(
            text(sql),
            {"table_schema": schema or self.default_schema_name},
        )
        return [row.table_name for row in rows]

    def get_view_names(self, conn, schema=None, **kw):
        sql = (
            "select * from pg_catalog.pg_views"
        )
        rows = conn.execute(
            text(sql),
            {"table_schema": schema or self.default_schema_name},
        )

        return [row.viewname for row in rows]

    def has_table(self, conn, table, schema=None):
        return any(t == table for t in self.get_table_names(conn, schema=schema))

    def get_columns(self, conn, table_name, schema=None, **kw):
        sql = (
            "SELECT column_name, data_type FROM information_schema.columns WHERE "
            "table_schema = :table_schema AND table_name = :table_name"
        )
        rows = conn.execute(
            text(sql),
            {"table_schema": schema or self.default_schema_name, "table_name": table_name},
        )

        res = []
        for row in rows:
            name, type_str = row.column_name, row.data_type
            # When there are type parameters, attach them to the
            # returned type object.
            m = re.match(r"^struct<.*>$", type_str)
            if m:
                warn("Struct is not supported")
                type_class = sqltypes.NULLTYPE
            else:
                m = re.match(r"^([a-z ]+)((\[\])*)$", type_str)
                kwargs = {}
                if m:
                    groups = m.groups()
                    type_name = groups[0]

                    if type_name in _type_map:
                        data_type = _type_map[type_name]
                    else:
                        data_type = None

                    if type_name == "timestamp with time zone":
                        kwargs["timezone"] = True
                else:
                    data_type = None

                if data_type:
                    type_class = data_type(**kwargs)
                    if len(groups) > 1:
                        array_suffixs = re.findall(r"\[\]", groups[1])
                        for i in range(0, len(array_suffixs)):
                            type_class = sqltypes.ARRAY(type_class)
                else:
                    warn(f"Did not recognize type '{type_str}' of column '{name}'")
                    type_class = sqltypes.NULLTYPE

            column_info = dict(
                name=name,
                type=type_class,
            )

            res.append(column_info)
        return res

    def get_indexes(self, conn, table_name, schema=None, **kw):
        table_oid = self.get_table_oid(
            conn, table_name, schema, info_cache=kw.get("info_cache")
        )

        sql = (
            "select i.relname, a.attname from pg_catalog.pg_class t "
            "join pg_catalog.pg_index ix on t.oid = ix.indrelid "
            "join pg_catalog.pg_class i on i.oid = ix.indexrelid "
            "join pg_catalog.pg_attribute a on t.oid = a.attrelid and a.attnum = ANY(ix.indkey)"
            "where t.oid = :table_oid"
        )
        rows = conn.execute(
            text(sql),
            {"table_oid": table_oid},
        )

        indexes = {}
        for row in rows:
            if not row.relname in indexes:
                indexes[row.relname] = []
            indexes[row.relname].append(row.attname)

        res = []
        for index in indexes:
            res.append(
                {
                    "name": index,
                    "column_names": indexes[index],
                    "unique": False,
                }
            )
        return res

    def get_foreign_keys_v1(self, conn, table_name, schema=None, **kw):
        raise []

    def get_foreign_keys(
        self, connection, table_name, schema=None, postgresql_ignore_search_path=False, **kw
    ):
        return []

    def get_pk_constraint(self, conn, table_name, schema=None, **kw):
        # TODO: Fill in real implementation to make get pk constraint work.
        return dict()

    def get_unique_constraints(self, conn, table_name, schema=None, **kw):
        return []

    def get_check_constraints(self, conn, table_name, schema=None, **kw):
        return []

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

    def get_table_comment(self, connection, table_name, schema=None, **kw):
        # TODO: Support table comment
        return dict()

    def get_default_isolation_level(self, dbapi_conn):
        return self.get_isolation_level(dbapi_conn)
