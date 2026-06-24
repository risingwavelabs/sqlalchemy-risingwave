import logging
import re

from sqlalchemy.dialects.postgresql.base import (
    PGDDLCompiler,
    PGDialect,
    PGTypeCompiler,
)
from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
from sqlalchemy import schema, text
from sqlalchemy.engine import reflection
from sqlalchemy.util import warn

import sqlalchemy.types as sqltypes
import sqlalchemy.exc as exc


class RisingWaveDDLCompiler(PGDDLCompiler):
    """DDL compiler that rewrites PostgreSQL autoincrement keywords.

    RisingWave's DDL parser rejects ``SERIAL`` / ``BIGSERIAL`` /
    ``SMALLSERIAL`` with ``Not supported: Column type SERIAL is not
    supported. HINT: Please remove the SERIAL column``. The PG parent
    emits those keywords for any primary-key integer column that the ORM
    flags as autoincrement, including the implicit autoincrement that
    ``Table(... Column("id", Integer, primary_key=True) ...)`` picks up.

    RisingWave does not provide PostgreSQL's per-row autoincrement
    semantics anyway, so rewrite the keyword back to the underlying
    integer type and let inserts supply explicit values. This makes the
    upstream ``sqlalchemy.testing.suite`` fixtures actually create their
    tables instead of erroring during setup, which is what surfaces the
    real per-feature behaviour underneath.
    """

    _SERIAL_KEYWORDS = (
        (" BIGSERIAL", " BIGINT"),
        (" SMALLSERIAL", " SMALLINT"),
        (" SERIAL", " INTEGER"),
    )

    def get_column_specification(self, column, **kwargs):
        spec = super().get_column_specification(column, **kwargs)
        if not self._has_pg_serial_autoincrement(column):
            return spec

        for serial_kw, concrete_kw in self._SERIAL_KEYWORDS:
            if serial_kw in spec:
                spec = spec.replace(serial_kw, concrete_kw)
        return spec

    def _has_pg_serial_autoincrement(self, column):
        impl_type = column.type.dialect_impl(self.dialect)
        if isinstance(impl_type, sqltypes.TypeDecorator):
            impl_type = impl_type.impl

        has_identity = (
            column.identity is not None and self.dialect.supports_identity_columns
        )
        return (
            column.primary_key
            and column is column.table._autoincrement_column
            and (
                self.dialect.supports_smallserial
                or not isinstance(impl_type, sqltypes.SmallInteger)
            )
            and not has_identity
            and (
                column.default is None
                or (
                    isinstance(column.default, schema.Sequence)
                    and column.default.optional
                )
            )
        )


class RisingWaveTypeCompiler(PGTypeCompiler):
    """Type compiler that drops PostgreSQL-style length / precision arguments.

    RisingWave's DDL parser rejects every PostgreSQL string and numeric type
    that carries a parenthesised parameter:

    - ``CHAR`` / ``CHAR(n)`` → ``Feature is not yet implemented: CHAR is not
      supported, please use VARCHAR instead``.
    - ``VARCHAR(n)`` → ``sql parser error: expected ',' or ')' after column
      definition, found: '('``.
    - ``NUMERIC(p, s)`` / ``DECIMAL(p, s)`` → ``unsupported data type:
      NUMERIC(8,4)``.

    The PostgreSQL parent emits those forms whenever the SQLAlchemy column
    type carries ``.length`` / ``.precision`` / ``.scale``. That is the
    default for ``String(50)`` / ``DECIMAL(10, 2)`` / ``Column(CHAR(3))``
    fixtures the upstream compliance suite uses, so leaving the parent
    behaviour intact makes hundreds of suite fixtures fail at CREATE TABLE.

    Strip the parameters here. RisingWave does not enforce length / precision
    caps anyway, so this is a DDL-acceptance fix rather than a semantic loss
    — same shape as the SERIAL rewrite in ``RisingWaveDDLCompiler``.
    """

    def visit_CHAR(self, type_, **kw):
        return "VARCHAR"

    def visit_NCHAR(self, type_, **kw):
        return "VARCHAR"

    def visit_VARCHAR(self, type_, **kw):
        return "VARCHAR"

    def visit_NVARCHAR(self, type_, **kw):
        return "VARCHAR"

    def visit_NUMERIC(self, type_, **kw):
        return "NUMERIC"

    def visit_DECIMAL(self, type_, **kw):
        return "DECIMAL"

    def visit_uuid(self, type_, **kw):
        return "VARCHAR"

    def visit_UUID(self, type_, **kw):
        return "VARCHAR"


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
    "text": sqltypes.TEXT,
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

def _get_column_type_from_information_schema(
    type_str,
    column_name,
    character_maximum_length=None,
    numeric_precision=None,
    numeric_scale=None,
):
    # RisingWave VARCHAR is unbounded, and current RisingWave rejects
    # PostgreSQL-style VARCHAR(n) DDL. Do not synthesize a length that the
    # database does not enforce.
    del character_maximum_length

    m = re.match(r"^struct<.*>$", type_str)
    if m:
        warn("Struct is not supported")
        return sqltypes.NULLTYPE

    m = re.match(
        r"^([a-z ]+)(?:\(([^)]*)\))?((\[\])*)$",
        type_str,
    )
    kwargs = {}
    if m:
        groups = m.groups()
        type_name = groups[0]
        type_args = groups[1]

        if type_name in _type_map:
            data_type = _type_map[type_name]
        else:
            data_type = None

        if type_name == "timestamp with time zone":
            kwargs["timezone"] = True
        if type_name in ("numeric", "decimal"):
            if numeric_precision is not None:
                kwargs["precision"] = int(numeric_precision)
            if numeric_scale is not None:
                kwargs["scale"] = int(numeric_scale)
            if type_args and numeric_precision is None and numeric_scale is None:
                numeric_args = [
                    int(arg.strip()) for arg in type_args.split(",") if arg.strip()
                ]
                if len(numeric_args) >= 1:
                    kwargs["precision"] = numeric_args[0]
                if len(numeric_args) >= 2:
                    kwargs["scale"] = numeric_args[1]
    else:
        data_type = None
        groups = None

    if data_type:
        type_class = data_type(**kwargs)
        if groups[2]:
            array_suffixes = re.findall(r"\[\]", groups[2])
            for _ in array_suffixes:
                type_class = sqltypes.ARRAY(type_class)
        return type_class

    warn(f"Did not recognize type '{type_str}' of column '{column_name}'")
    return sqltypes.NULLTYPE


logger = logging.getLogger(__name__)
_warned_pg_cancel_probe = False


class _RisingWaveCommon:
    """Driver-agnostic RisingWave dialect overrides.

    Composed with both ``PGDialect_psycopg2`` (sync, psycopg2) and
    ``PGDialect_psycopg`` (sync + async, psycopg3) via MRO so the
    RisingWave-specific behaviour (compilers, capability flags, reflection
    methods, Superset shim) is shared across drivers. Concrete driver
    bindings stay in the per-driver subclasses below or in sibling modules.
    """

    name = "risingwave"
    ddl_compiler = RisingWaveDDLCompiler
    type_compiler = RisingWaveTypeCompiler
    supports_native_enum = False
    supports_native_uuid = False
    supports_statement_cache = True

    _PG_BACKEND_PID_SQL = re.compile(
        r"^\s*SELECT\s+pg_backend_pid\(\)\s*;?\s*$",
        re.IGNORECASE,
    )
    _PG_TERMINATE_BACKEND_SQL = re.compile(
        r"^\s*SELECT\s+pg_terminate_backend\(\s*pid\s*\)\s+"
        r"FROM\s+pg_stat_activity\s+WHERE\s+pid\s*=\s*['\"]?\d+['\"]?\s*;?\s*$",
        re.IGNORECASE,
    )

    def do_execute(self, cursor, statement, parameters, context=None):
        global _warned_pg_cancel_probe
        # Superset's RisingWave spec inherits PostgreSQL cancel-query logic,
        # which probes pg_backend_pid() and pg_terminate_backend(...). RisingWave
        # does not expose PostgreSQL backend processes, so report a stable dummy
        # PID and a failed termination instead of raising "function not found".
        # This keeps query cancellation explicitly unsupported while avoiding a
        # hard error in clients that merely inherit PostgreSQL probes.
        if self._PG_BACKEND_PID_SQL.match(statement):
            if not _warned_pg_cancel_probe:
                logger.warning(
                    "RisingWave dialect intercepted PostgreSQL cancellation "
                    "probe pg_backend_pid(). Returning dummy PID 0; query "
                    "cancellation is not supported."
                )
                _warned_pg_cancel_probe = True
            cursor.execute("SELECT 0")
            return
        if self._PG_TERMINATE_BACKEND_SQL.match(statement):
            cursor.execute("SELECT false")
            return
        super().do_execute(cursor, statement, parameters, context=context)

    def create_connect_args(self, url):
        """Create connection arguments, handling RisingWave Cloud tenant parameter.

        RisingWave Cloud requires a tenant identifier for routing connections.
        This can be specified as a `tenant` query parameter in the connection URL,
        which will be automatically converted to the PostgreSQL `options` format
        that RisingWave Cloud expects.

        Example:
            risingwave://user:pass@host:4566/db?tenant=rwc-xxx

        This will be converted to:
            options=--tenant=rwc-xxx

        See https://docs.risingwave.com/cloud/connection-errors for more details
        on RisingWave Cloud connection methods.
        """
        # Get the default connection args from parent
        cargs, cparams = super().create_connect_args(url)

        # Handle tenant parameter if present
        if "tenant" in cparams:
            tenant = cparams.pop("tenant")
            # Merge tenant into options parameter
            existing_options = cparams.get("options", "")
            if existing_options:
                cparams["options"] = f"{existing_options} --tenant={tenant}"
            else:
                cparams["options"] = f"--tenant={tenant}"

        return cargs, cparams

    def initialize(self, connection):
        super(PGDialect, self).initialize(connection)

    def _get_server_version_info(self, conn):
        return (9, 5, 0)

    @reflection.cache
    def get_table_names(self, conn, schema=None, **kw):
        sql = "SELECT tablename FROM pg_tables"
        if schema is not None:
            sql += f" WHERE schemaname = '{schema or self.default_schema_name}'"
        else:
            sql += (
                " WHERE schemaname <> 'rw_catalog'"
                " and schemaname <> 'pg_catalog'"
                " and schemaname <> 'information_schema'"
            )
        rows = conn.execute(text(sql))
        return [row.tablename for row in rows]

    @reflection.cache
    def get_view_names(self, conn, schema=None, **kw):
        base_queries = [
            "SELECT viewname FROM pg_views",
        ]
        queries = []
        for sql in base_queries:
            if schema is not None:
                sql += f" WHERE schemaname = '{schema or self.default_schema_name}'"
            else:
                sql += (
                    " WHERE schemaname <> 'rw_catalog'"
                    " and schemaname <> 'pg_catalog'"
                    " and schemaname <> 'information_schema'"
                )
            queries.append(sql)
        views = conn.execute(text(" UNION ".join(queries)))

        # As sqlalchmey has no support for Sources, we categorize as view temporarily.
        source_sql = (
            "SELECT rw_catalog.rw_sources.name as source_name"
            " FROM rw_catalog.rw_sources"
            " JOIN rw_catalog.rw_schemas"
            " ON rw_catalog.rw_sources.schema_id = rw_catalog.rw_schemas.id"
        )
        if schema is not None:
            source_sql += (
                " WHERE rw_catalog.rw_schemas.name = "
                f"'{schema or self.default_schema_name}'"
            )
        else:
            source_sql += (
                " WHERE rw_catalog.rw_schemas.name <> 'rw_catalog'"
                " and rw_catalog.rw_schemas.name <> 'pg_catalog'"
                " and rw_catalog.rw_schemas.name <> 'information_schema'"
            )
        sources = conn.execute(text(source_sql))

        return [view.viewname for view in views] + [
            source.source_name for source in sources
        ]

    @reflection.cache
    def get_materialized_view_names(self, conn, schema=None, **kw):
        sql = "SELECT matviewname FROM pg_matviews"
        if schema is not None:
            sql += f" WHERE schemaname = '{schema or self.default_schema_name}'"
        else:
            sql += (
                " WHERE schemaname <> 'rw_catalog'"
                " and schemaname <> 'pg_catalog'"
                " and schemaname <> 'information_schema'"
            )
        rows = conn.execute(text(sql))
        return [row.matviewname for row in rows]

    @reflection.cache
    def has_table(self, conn, table_name, schema=None, **kw):
        return any(t == table_name for t in self.get_table_names(conn, schema=schema))

    @reflection.cache
    def get_columns(self, conn, table_name, schema=None, **kw):
        sql = (
            "SELECT column_name, data_type, is_nullable, column_default,"
            " character_maximum_length, numeric_precision, numeric_scale"
            " FROM information_schema.columns WHERE "
            "table_schema = :table_schema AND table_name = :table_name"
        )
        rows = conn.execute(
            text(sql),
            {
                "table_schema": schema or self.default_schema_name,
                "table_name": table_name,
            },
        )

        res = []
        for row in rows:
            name, type_str = row.column_name, row.data_type
            type_class = _get_column_type_from_information_schema(
                type_str,
                name,
                character_maximum_length=row.character_maximum_length,
                numeric_precision=row.numeric_precision,
                numeric_scale=row.numeric_scale,
            )

            column_info = dict(
                name=name,
                type=type_class,
                nullable=row.is_nullable == "YES",
                default=row.column_default,
                autoincrement=False,
                comment=None,
            )

            res.append(column_info)
        return res

    def get_table_oid(self, connection, table_name, schema=None, **kw):
        table_oid = None
        if schema is not None:
            schema_where_clause = "n.nspname = :schema"
        else:
            schema_where_clause = "pg_catalog.pg_table_is_visible(r.id)"
        sql = (
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
        s = text(sql).columns(oid=sqltypes.Integer)
        c = connection.execute(
            s, {"table_name": str(table_name), "schema": str(schema)}
        )
        table_oid = c.scalar()
        if table_oid is None:
            raise exc.NoSuchTableError(table_name)
        return table_oid

    @reflection.cache
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

    def get_multi_columns(self, connection, schema, filter_names, scope, kind, **kw):
        return self._default_multi_reflect(
            self.get_columns,
            connection,
            kind=kind,
            schema=schema,
            filter_names=filter_names,
            scope=scope,
            **kw,
        )

    def get_multi_indexes(self, connection, schema, filter_names, scope, kind, **kw):
        return self._default_multi_reflect(
            self.get_indexes,
            connection,
            kind=kind,
            schema=schema,
            filter_names=filter_names,
            scope=scope,
            **kw,
        )

    def get_multi_pk_constraint(
        self, connection, schema, filter_names, scope, kind, **kw
    ):
        return self._default_multi_reflect(
            self.get_pk_constraint,
            connection,
            kind=kind,
            schema=schema,
            filter_names=filter_names,
            scope=scope,
            **kw,
        )

    def get_multi_foreign_keys(
        self,
        connection,
        schema,
        filter_names,
        scope,
        kind,
        postgresql_ignore_search_path=False,
        **kw,
    ):
        return self._default_multi_reflect(
            self.get_foreign_keys,
            connection,
            kind=kind,
            schema=schema,
            filter_names=filter_names,
            scope=scope,
            postgresql_ignore_search_path=postgresql_ignore_search_path,
            **kw,
        )

    def get_multi_unique_constraints(
        self, connection, schema, filter_names, scope, kind, **kw
    ):
        return self._default_multi_reflect(
            self.get_unique_constraints,
            connection,
            kind=kind,
            schema=schema,
            filter_names=filter_names,
            scope=scope,
            **kw,
        )

    def get_multi_check_constraints(
        self, connection, schema, filter_names, scope, kind, **kw
    ):
        return self._default_multi_reflect(
            self.get_check_constraints,
            connection,
            kind=kind,
            schema=schema,
            filter_names=filter_names,
            scope=scope,
            **kw,
        )

    def get_multi_table_comment(
        self, connection, schema, filter_names, scope, kind, **kw
    ):
        return self._default_multi_reflect(
            self.get_table_comment,
            connection,
            kind=kind,
            schema=schema,
            filter_names=filter_names,
            scope=scope,
            **kw,
        )

    @reflection.cache
    def get_foreign_keys_v1(self, conn, table_name, schema=None, **kw):
        return []

    @reflection.cache
    def get_foreign_keys(
        self,
        connection,
        table_name,
        schema=None,
        postgresql_ignore_search_path=False,
        **kw,
    ):
        return []

    @reflection.cache
    def get_pk_constraint(self, conn, table_name, schema=None, **kw):
        sql = """
            SELECT
                tc.constraint_name,
                kcu.column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_catalog = kcu.constraint_catalog
             AND tc.constraint_schema = kcu.constraint_schema
             AND tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
             AND tc.table_name = kcu.table_name
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = :table_schema
              AND tc.table_name = :table_name
            ORDER BY kcu.ordinal_position
        """
        rows = conn.execute(
            text(sql),
            {
                "table_schema": schema or self.default_schema_name,
                "table_name": table_name,
            },
        ).fetchall()

        rows = [row for row in rows if row.column_name != "_row_id"]

        if not rows:
            return {"constrained_columns": [], "name": None}

        return {
            "constrained_columns": [row.column_name for row in rows],
            "name": rows[0].constraint_name,
        }

    @reflection.cache
    def get_unique_constraints(self, conn, table_name, schema=None, **kw):
        return []

    @reflection.cache
    def get_check_constraints(self, conn, table_name, schema=None, **kw):
        return []

    def do_rollback_to_savepoint(self, connection, name):
        raise NotImplementedError

    def do_release_savepoint(self, connection, name):
        raise NotImplementedError

    def get_isolation_level(self, connection):
        return "SERIALIZABLE"

    def get_isolation_level_values(self, dbapi_conn):
        return (
            "SERIALIZABLE",
            "READ UNCOMMITTED",
            "READ COMMITTED",
            "REPEATABLE READ",
        )

    @reflection.cache
    def get_table_comment(self, connection, table_name, schema=None, **kw):
        # TODO: Support table comment
        return {"text": None}

    def get_default_isolation_level(self, dbapi_conn):
        return self.get_isolation_level(dbapi_conn)


class RisingWaveDialect(_RisingWaveCommon, PGDialect_psycopg2):
    """psycopg2 sync RisingWave dialect.

    This is the original concrete dialect class exposed via the
    ``risingwave+psycopg2://`` URL, and the import name ``RisingWaveDialect``
    that ``sqlalchemy_risingwave.psycopg2`` and external code already rely on.
    The driver-specific kwargs guarded in ``__init__`` are psycopg2 features
    RisingWave does not implement; the psycopg3 dialect lives in a sibling
    module and does not share those kwargs.
    """

    def __init__(self, *args, **kwargs):
        if kwargs.get("use_native_hstore", False):
            raise NotImplementedError("use_native_hstore is not supported")
        if kwargs.get("server_side_cursors", False):
            raise NotImplementedError("server_side_cursors is not supported")
        kwargs["use_native_hstore"] = False
        kwargs["server_side_cursors"] = False
        super().__init__(*args, **kwargs)
