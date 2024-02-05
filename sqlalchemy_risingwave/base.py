import re

from sqlalchemy.dialects.postgresql.base import PGDialect
from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
from sqlalchemy import text
from sqlalchemy.util import warn

from sqlalchemy import util
import sqlalchemy.types as sqltypes

_type_map = {
    "bool": sqltypes.BOOLEAN,  # DataType::Boolean
    "boolean": sqltypes.BOOLEAN,  # DataType::Boolean
    "smallint": sqltypes.SMALLINT,  # DataType::Int16
    "int2": sqltypes.SMALLINT,  # DataType::Int16
    "integer": sqltypes.INT,  # DataType::Int32
    "int4": sqltypes.INT,  # DataType::Int32
    "bigint": sqltypes.BIGINT,  # DataType::Int64
    "int8": sqltypes.BIGINT,  # DataType::Int64
    "real": sqltypes.FLOAT,  # DataType::Float32
    "float4": sqltypes.FLOAT,  # DataType::Float32
    "double precision": sqltypes.FLOAT,  # DataType::Float64
    "float8": sqltypes.FLOAT,  # DataType::Float64
    "numeric": sqltypes.DECIMAL,  # DataType::Decimal
    "decimal": sqltypes.DECIMAL,  # DataType::Decimal
    "date": sqltypes.DATE,  # DataType::Date
    "varchar": sqltypes.VARCHAR,  # DataType::Varchar
    "character varying": sqltypes.VARCHAR,  # DataType::Varchar
    "time": sqltypes.Time,  # DataType::Time
    "time without time zone": sqltypes.Time,  # DataType::Time
    "timestamp": sqltypes.TIMESTAMP,  # DataType::Timestamp
    "timestamp without time zone": sqltypes.TIMESTAMP,  # DataType::Timestamp
    "timestamptz": sqltypes.TIMESTAMP,  # DataType::Timestampz
    "timestamp with time zone": sqltypes.TIMESTAMP,  # DataType::Timestampz
    "interval": sqltypes.Interval,  # DataType::Interval
    "bytea": sqltypes.BLOB,
    "jsonb": sqltypes.JSON,
}


# Unsupported: Int256, Serial, Struct, List


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
        sql = "SELECT tablename FROM pg_tables"
        if schema is not None:
            sql += f" WHERE schemaname = '{schema or self.default_schema_name}'"
        else:
            sql += " WHERE schemaname <> 'rw_catalog' and schemaname <> 'pg_catalog' and schemaname <> 'information_schema'"
        rows = conn.execute(text(sql))
        return [row.tablename for row in rows]

    def get_view_names(self, conn, schema=None, **kw):
        sql = "SELECT viewname FROM pg_views"
        if schema is not None:
            sql += f" WHERE schemaname = '{schema or self.default_schema_name}'"
        else:
            sql += " WHERE schemaname <> 'rw_catalog' and schemaname <> 'pg_catalog' and schemaname <> 'information_schema'"
        views = conn.execute(text(sql))

        # As sqlalchmey has no support for Sources, we categorize as view temporarily.
        source_sql = f"SELECT rw_catalog.rw_sources.name as source_name FROM rw_catalog.rw_sources JOIN rw_catalog.rw_schemas ON rw_catalog.rw_sources.schema_id = rw_catalog.rw_schemas.id"
        if schema is not None:
            source_sql += f" WHERE rw_catalog.rw_schemas.name = '{schema or self.default_schema_name}'"
        else:
            source_sql += " WHERE rw_catalog.rw_schemas.name <> 'rw_catalog' and rw_catalog.rw_schemas.name <> 'pg_catalog' and rw_catalog.rw_schemas.name <> 'information_schema'"
        sources = conn.execute(text(source_sql))
        return [view.viewname for view in views] + [source.source_name for source in sources]

    def has_table(self, conn, table, schema=None, **kw):
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

    def get_table_oid(self, connection, table_name, schema=None, **kw):
        table_oid = None
        if schema is not None:
            schema_where_clause = "n.nspname = :schema"
        else:
            schema_where_clause = "pg_catalog.pg_table_is_visible(r.id)"
        query = (
                """
                SELECT r.id as oid
                FROM rw_catalog.rw_relations r
                LEFT JOIN pg_catalog.pg_namespace n ON n.oid = r.schema_id
                WHERE (%s)
                AND r.name = :table_name AND r.relation_type in
                ('table', 'system table', 'view', 'materialized view', 'source', 'sink')
            """
                % schema_where_clause
        )
        # Since we're binding to unicode, table_name and schema_name must be
        # unicode.
        table_name = util.text_type(table_name)
        if schema is not None:
            schema = util.text_type(schema)
        s = text(query).bindparams(table_name=sqltypes.Unicode)
        s = s.columns(oid=sqltypes.Integer)
        if schema:
            s = s.bindparams(sql.bindparam("schema", type_=sqltypes.Unicode))
        c = connection.execute(s, dict(table_name=table_name, schema=schema))
        table_oid = c.scalar()
        if table_oid is None:
            raise exc.NoSuchTableError(table_name)
        return table_oid

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
            if row.relname not in indexes:
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
