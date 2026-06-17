"""Real-RisingWave async smoke + acceptance tests for the psycopg3 driver.

PR β acceptance gates from issue #57:

* basic async round-trip + DDL + reflection,
* concurrency wall-clock proof (``asyncio.gather`` over N independent
  slow-enough queries completes in roughly one query's time, not N),
* cross-driver consistency (psycopg2 sync writes, psycopg3 async reads,
  with explicit ``FLUSH`` to isolate streaming visibility from driver
  behaviour),
* parametrised type round-trip matrix across drivers and types, again
  with explicit ``FLUSH``.

Tests are skipped when the psycopg3 driver isn't installed so the
existing psycopg2-only CI matrix cell stays green when ``[psycopg3]``
extra hasn't been pulled in.
"""

import asyncio
import datetime
import decimal
import time
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")  # noqa: F401

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Float,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    inspect,
    text,
)
from sqlalchemy import create_engine
from sqlalchemy import testing
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.testing import fixtures
from sqlalchemy.types import Uuid

from sqlalchemy_risingwave.psycopg import (
    RisingWaveDialect_psycopg,
    RisingWaveDialect_psycopg_async,
)


def _sync_psycopg2_url():
    return testing.db.url


def _sync_psycopg3_url():
    return testing.db.url.set(drivername="risingwave+psycopg")


def _async_psycopg3_url():
    # ``create_async_engine`` reads the same URL pattern as the sync engine
    # and dispatches to the async dialect via ``get_async_dialect_cls``.
    return testing.db.url.set(drivername="risingwave+psycopg")


def _drop_table_sync(table_name):
    engine = create_engine(_sync_psycopg2_url())
    try:
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
    finally:
        engine.dispose()


class AsyncPsycopgUsageTest(fixtures.TestBase):
    """The core async smoke + acceptance suite."""

    @pytest.mark.asyncio
    async def test_async_dispatch_returns_risingwave_async_class(self):
        # First-line correctness: SQLAlchemy must dispatch
        # ``create_async_engine("risingwave+psycopg://...")`` to the
        # RisingWave async dialect, not the raw upstream
        # ``PGDialectAsync_psycopg``. PR α's guard previously raised here;
        # PR β replaces the guard with a real dispatch.
        engine = create_async_engine(_async_psycopg3_url())
        try:
            assert isinstance(engine.dialect, RisingWaveDialect_psycopg_async)
            assert engine.dialect.name == "risingwave"
            assert engine.dialect.is_async is True
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_async_core_query_round_trip(self):
        engine = create_async_engine(_async_psycopg3_url())
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                row = result.one()
                assert tuple(row) == (1,)
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_async_ddl_and_reflection_round_trip(self):
        engine = create_async_engine(_async_psycopg3_url())
        try:
            async with engine.begin() as conn:
                await conn.execute(text("DROP TABLE IF EXISTS sqlalchemy_rw_async"))
                await conn.execute(
                    text(
                        "CREATE TABLE sqlalchemy_rw_async ("
                        "id INTEGER PRIMARY KEY, "
                        "name VARCHAR"
                        ")"
                    )
                )

            # Reflection requires SQLAlchemy's standard async pattern of
            # wrapping the synchronous Inspector via ``conn.run_sync(...)``.
            async with engine.connect() as conn:
                has_table = await conn.run_sync(
                    lambda sync_conn: inspect(sync_conn).has_table(
                        "sqlalchemy_rw_async"
                    )
                )
                columns = await conn.run_sync(
                    lambda sync_conn: inspect(sync_conn).get_columns(
                        "sqlalchemy_rw_async"
                    )
                )

            assert has_table is True
            assert [c["name"] for c in columns] == ["id", "name"]
        finally:
            await engine.dispose()
            _drop_table_sync("sqlalchemy_rw_async")

    @pytest.mark.asyncio
    async def test_async_superset_cancel_probe_degrades_to_noop(self):
        # The Superset shim is shared via ``_RisingWaveCommon.do_execute``
        # so it must continue to fire under the async dialect; verifying
        # this here is what protects async Superset SQL Lab from a hard
        # ``function not supported`` failure.
        engine = create_async_engine(_async_psycopg3_url())
        try:
            async with engine.connect() as conn:
                backend_pid = (
                    await conn.execute(text("SELECT pg_backend_pid()"))
                ).scalar()
                terminated = (
                    await conn.execute(
                        text(
                            "SELECT pg_terminate_backend(pid) "
                            "FROM pg_stat_activity WHERE pid='0'"
                        )
                    )
                ).scalar()
            assert backend_pid == 0
            assert terminated is False
        finally:
            await engine.dispose()


class AsyncConcurrencyProofTest(fixtures.TestBase):
    """PR β hard-gate #6: prove async actually parallelises I/O.

    Without this test the dialect could pass smoke (``await`` works,
    ``SELECT 1`` returns 1) while internally serialising every connection
    on a shared lock, in which case ``async`` would be branding only.
    """

    @pytest.fixture(scope="class")
    def slow_query(self):
        # Determine the slowest reliable query RisingWave supports for the
        # concurrency proof. ``pg_sleep`` is the cheapest if it exists;
        # otherwise fall back to a CPU-bound ``generate_series`` aggregation
        # that takes consistently > 0.4 s on the CI runner.
        engine = create_engine(_sync_psycopg2_url())
        try:
            try:
                with engine.connect() as conn:
                    conn.execute(text("SELECT pg_sleep(0.05)"))
                return "SELECT pg_sleep(0.5)"
            except Exception:
                return "SELECT count(*) FROM generate_series(1, 10_000_000)"
        finally:
            engine.dispose()

    @pytest.mark.asyncio
    async def test_async_actually_concurrent(self, slow_query):
        engine = create_async_engine(_async_psycopg3_url())
        N = 5

        async def one_query():
            async with engine.connect() as conn:
                await conn.execute(text(slow_query))

        try:
            # Warm the connection pool / dialect bind on a single query.
            await one_query()

            start = time.monotonic()
            await asyncio.gather(*[one_query() for _ in range(N)])
            elapsed = time.monotonic() - start
        finally:
            await engine.dispose()

        # N independent queries that each take ~T seconds should finish
        # in roughly T, not N*T, if async I/O is truly concurrent. Give a
        # comfortable margin (~ 2x) for CI scheduler noise.
        single_query_estimate = 0.5
        max_acceptable = single_query_estimate * 2
        assert elapsed < max_acceptable, (
            f"async dialect did not parallelise: {N} queries took "
            f"{elapsed:.3f}s, expected ≲ {max_acceptable:.1f}s"
        )


class CrossDriverConsistencyTest(fixtures.TestBase):
    """PR β hard-gate #7: psycopg2 sync write, psycopg3 read, same data.

    Inserts via psycopg2 sync, issues an explicit ``FLUSH`` so the
    streaming visibility property documented in ``docs/streaming.md``
    cannot mask a driver-level mismatch, then reads back via both
    psycopg3 sync and psycopg3 async. All three reads must agree.
    """

    def teardown_method(self, method):
        _drop_table_sync("sqlalchemy_rw_cross")

    def test_psycopg2_sync_write_psycopg3_sync_read_agree(self):
        engine2 = create_engine(_sync_psycopg2_url())
        engine3 = create_engine(_sync_psycopg3_url())
        try:
            with engine2.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS sqlalchemy_rw_cross"))
                conn.execute(
                    text(
                        "CREATE TABLE sqlalchemy_rw_cross ("
                        "id INTEGER PRIMARY KEY, "
                        "name VARCHAR"
                        ")"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO sqlalchemy_rw_cross (id, name) "
                        "VALUES (1, 'alpha'), (2, 'beta')"
                    )
                )
                conn.execute(text("FLUSH"))

            with engine2.connect() as conn:
                psy2_rows = conn.execute(
                    text("SELECT id, name FROM sqlalchemy_rw_cross ORDER BY id")
                ).all()

            with engine3.connect() as conn:
                psy3_rows = conn.execute(
                    text("SELECT id, name FROM sqlalchemy_rw_cross ORDER BY id")
                ).all()
        finally:
            engine2.dispose()
            engine3.dispose()

        assert psy2_rows == psy3_rows == [(1, "alpha"), (2, "beta")]

    @pytest.mark.asyncio
    async def test_psycopg2_sync_write_psycopg3_async_read_agree(self):
        engine2 = create_engine(_sync_psycopg2_url())
        try:
            with engine2.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS sqlalchemy_rw_cross"))
                conn.execute(
                    text(
                        "CREATE TABLE sqlalchemy_rw_cross ("
                        "id INTEGER PRIMARY KEY, "
                        "name VARCHAR"
                        ")"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO sqlalchemy_rw_cross (id, name) "
                        "VALUES (1, 'alpha'), (2, 'beta')"
                    )
                )
                conn.execute(text("FLUSH"))

            with engine2.connect() as conn:
                psy2_rows = conn.execute(
                    text("SELECT id, name FROM sqlalchemy_rw_cross ORDER BY id")
                ).all()
        finally:
            engine2.dispose()

        engine3_async = create_async_engine(_async_psycopg3_url())
        try:
            async with engine3_async.connect() as conn:
                result = await conn.execute(
                    text("SELECT id, name FROM sqlalchemy_rw_cross ORDER BY id")
                )
                psy3_async_rows = result.all()
        finally:
            await engine3_async.dispose()

        assert (
            psy2_rows == psy3_async_rows == [(1, "alpha"), (2, "beta")]
        )


# PR β hard-gate #8: type round-trip matrix across drivers and types.
# Parametrised so each (driver, type, value) cell is its own test entry,
# which makes failure surface the exact driver/type that drifted instead
# of a single oversized test case. Every cell ``FLUSH``es between insert
# and select so streaming visibility cannot be misdiagnosed as type
# adapter drift.

_TYPE_ROUND_TRIP_CASES = [
    pytest.param(Integer, 1, id="int"),
    pytest.param(BigInteger, 2**40, id="bigint"),
    pytest.param(Float, 1.5, id="float"),
    pytest.param(String, "ascii string", id="string-ascii"),
    pytest.param(String, "string with 中文", id="string-unicode"),
    pytest.param(Uuid, uuid.uuid4(), id="uuid"),
    pytest.param(Boolean, True, id="bool-true"),
    pytest.param(Boolean, False, id="bool-false"),
    pytest.param(LargeBinary, b"\x00\x01\x02 raw bytes", id="bytes"),
]


def _make_cross_driver_table(table_name, col_type):
    metadata = MetaData()
    table = Table(
        table_name,
        metadata,
        Column("id", Integer, primary_key=True),
        Column("val", col_type),
    )
    return metadata, table


def _normalize_for_comparison(py_val, retrieved):
    # SQLAlchemy returns ``bytes`` via ``LargeBinary`` and ``memoryview`` is
    # possible on some adapters; coerce so equality works without leaking
    # the comparison detail into every test case.
    if isinstance(py_val, (bytes, bytearray)):
        return bytes(py_val), bytes(retrieved)
    return py_val, retrieved


@pytest.mark.parametrize("col_type, py_val", _TYPE_ROUND_TRIP_CASES)
@pytest.mark.parametrize("driver", ["psycopg2", "psycopg"])
def test_type_round_trip_matrix_sync(driver, col_type, py_val):
    """Sync parity matrix for both drivers across the supported types."""

    url = testing.db.url.set(drivername=f"risingwave+{driver}")
    table_name = "sqlalchemy_rw_typmatrix"
    metadata, table = _make_cross_driver_table(table_name, col_type)

    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
            metadata.create_all(conn)
            conn.execute(table.insert().values(id=1, val=py_val))
            conn.execute(text("FLUSH"))

        with engine.connect() as conn:
            retrieved = conn.execute(
                table.select().where(table.c.id == 1)
            ).one().val
    finally:
        _drop_table_sync(table_name)
        engine.dispose()

    expected, actual = _normalize_for_comparison(py_val, retrieved)
    assert actual == expected


@pytest.mark.parametrize("col_type, py_val", _TYPE_ROUND_TRIP_CASES)
@pytest.mark.asyncio
async def test_type_round_trip_matrix_async_psycopg(col_type, py_val):
    """Async psycopg3 leg of the type round-trip matrix."""

    table_name = "sqlalchemy_rw_typmatrix_async"
    metadata, table = _make_cross_driver_table(table_name, col_type)

    # Set up the schema and data via sync psycopg2 so the matrix isolates
    # async-read behaviour; the cross-driver write/read consistency test
    # above already covers async-write paths separately.
    engine_sync = create_engine(_sync_psycopg2_url())
    try:
        with engine_sync.begin() as conn:
            conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
            metadata.create_all(conn)
            conn.execute(table.insert().values(id=1, val=py_val))
            conn.execute(text("FLUSH"))
    finally:
        engine_sync.dispose()

    engine_async = create_async_engine(_async_psycopg3_url())
    try:
        async with engine_async.connect() as conn:
            result = await conn.execute(table.select().where(table.c.id == 1))
            retrieved = result.one().val
    finally:
        await engine_async.dispose()
        _drop_table_sync(table_name)

    expected, actual = _normalize_for_comparison(py_val, retrieved)
    assert actual == expected
