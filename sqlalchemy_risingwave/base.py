import re

from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
from sqlalchemy import text
from sqlalchemy.util import warn
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.dialects.postgresql import UUID

import sqlalchemy.types as sqltypes
_type_map = {
    "bool": sqltypes.BOOLEAN,  # introspection returns "BOOL" not boolean
    "boolean": sqltypes.BOOLEAN,
    "bigint": sqltypes.BIGINT,
    "int": sqltypes.INT,
    "int2": sqltypes.SMALLINT,
    "int4": sqltypes.INT,
    "int8": sqltypes.BIGINT,
    "int32": sqltypes.INT,
    "int64": sqltypes.BIGINT,
    "integer": sqltypes.INT,
    "smallint": sqltypes.INT,
    "double precision": sqltypes.FLOAT,
    "float": sqltypes.FLOAT,
    "float4": sqltypes.FLOAT,
    "float8": sqltypes.FLOAT,
    "real": sqltypes.FLOAT,
    "dec": sqltypes.DECIMAL,
    "decimal": sqltypes.DECIMAL,
    "numeric": sqltypes.DECIMAL,
    "date": sqltypes.DATE,
    "time": sqltypes.Time,
    "time without time zone": sqltypes.Time,
    "timestamp": sqltypes.TIMESTAMP,
    "timestamptz": sqltypes.TIMESTAMP,
    "timestamp with time zone": sqltypes.TIMESTAMP,
    "timestamp without time zone": sqltypes.TIMESTAMP,
    "interval": sqltypes.Interval,
    "char": sqltypes.VARCHAR,
    "char varying": sqltypes.VARCHAR,
    "character": sqltypes.VARCHAR,
    "character varying": sqltypes.VARCHAR,
    "string": sqltypes.VARCHAR,
    "text": sqltypes.VARCHAR,
    "varchar": sqltypes.VARCHAR,
    "blob": sqltypes.BLOB,
    "bytea": sqltypes.BLOB,
    "bytes": sqltypes.BLOB,
    "json": sqltypes.JSON,
    "jsonb": sqltypes.JSON,
    "uuid": UUID,
    "inet": INET,
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
        # TODO: use \dt instead. Oddly there seems some escape words issue...
        return [row.Name for row in conn.execute("show tables")]

    def has_table(self, conn, table, schema=None):
        return any(t == table for t in self.get_table_names(conn, schema=schema))

    def get_columns(self, conn, table_name, schema=None, **kw):
        sql = (
            "DESCRIBE {}".format(table_name)
        )
        rows = conn.execute(
            text(sql),
            {"table_schema": schema or self.default_schema_name, "table_name": table_name},
        )

        res = []
        for row in rows:
            name, type_str = row[:2]
            # When there are type parameters, attach them to the
            # returned type object.
            m = re.match(r"^(\w+(?: \w+)*)(?:\(([0-9, ]*)\))?$", type_str)
            if m is None:
                warn("Could not parse type name '%s'" % type_str)
                typ = sqltypes.NULLTYPE
            else:
                type_name, type_args = m.groups()
                try:
                    type_class = _type_map[type_name.lower()]
                except KeyError:
                    warn(f"Did not recognize type '{type_name}' of column '{name}'")
                    type_class = sqltypes.NULLTYPE
                if type_args:
                    typ = type_class(*[int(s.strip()) for s in type_args.split(",")])
                else:
                    typ = type_class

            column_info = dict(
                name=name,
                type=typ,
            )

            res.append(column_info)
        return res

    def get_indexes(self, conn, table_name, schema=None, **kw):
        return dict()

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

    def get_table_comment(self, connection, table_name, schema=None, **kw):
        # TODO: Support table comment
        return dict()

    def get_default_isolation_level(self, dbapi_conn):
        return self.get_isolation_level(dbapi_conn)
