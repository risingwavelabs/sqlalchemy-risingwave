"""Runnable SQLAlchemy asyncio examples for RisingWave.

Prerequisites:

    pip install -U "sqlalchemy-risingwave[psycopg3]"

Run against local RisingWave:

    python examples/async_usage.py

Or point at another cluster:

    RISINGWAVE_ASYNC_URL="risingwave+psycopg://user:pass@host:4566/dev" \
        python examples/async_usage.py

The examples intentionally include an explicit FLUSH after INSERT. RisingWave
is a streaming database, so an INSERT is not guaranteed to be visible to a
subsequent SELECT until a barrier has passed or the application runs FLUSH.
"""

from __future__ import annotations

import asyncio
import os
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


DEFAULT_URL = "risingwave+psycopg://root@localhost:4566/dev"


async def minimal_select(engine) -> None:
    async with engine.connect() as conn:
        value = (await conn.execute(text("SELECT 1"))).scalar_one()
    print(f"minimal SELECT -> {value}")


async def insert_flush_select(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS sqlalchemy_async_demo"))
        await conn.execute(
            text(
                "CREATE TABLE sqlalchemy_async_demo ("
                "id INTEGER PRIMARY KEY, "
                "name VARCHAR"
                ")"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO sqlalchemy_async_demo (id, name) "
                "VALUES (:id, :name)"
            ),
            {"id": 1, "name": "alpha"},
        )
        await conn.execute(text("FLUSH"))

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT id, name FROM sqlalchemy_async_demo ORDER BY id")
            )
        ).all()
    print(f"INSERT + FLUSH + SELECT -> {rows}")


async def concurrency_demo(engine) -> None:
    """Show async client-side concurrency with several independent queries."""

    # pg_sleep gives the clearest wall-clock demo when the connected
    # RisingWave version supports it: five one-second sleeps should finish in
    # roughly one second, not five. Older versions may not expose pg_sleep, so
    # fall back to a CPU-bound query that still exercises asyncio.gather, but
    # may not show the same clean timing if the server is CPU-saturated.
    async with engine.connect() as conn:
        try:
            await conn.execute(text("SELECT pg_sleep(0.01)"))
            slow_query = "SELECT pg_sleep(1)"
            timing_note = "pg_sleep demo"
        except Exception:
            slow_query = "SELECT count(*) FROM generate_series(1, 10000000)"
            timing_note = "generate_series fallback"

    query_count = 5

    async def one_query(i: int) -> None:
        async with engine.connect() as conn:
            await conn.execute(text(slow_query))
        print(f"concurrent query {i} finished")

    start = time.monotonic()
    await asyncio.gather(*(one_query(i) for i in range(query_count)))
    elapsed = time.monotonic() - start
    print(f"{query_count} independent queries ({timing_note}) finished in {elapsed:.2f}s")


async def main() -> None:
    url = os.environ.get("RISINGWAVE_ASYNC_URL", DEFAULT_URL)
    engine = create_async_engine(url)
    try:
        await minimal_select(engine)
        await insert_flush_select(engine)
        await concurrency_demo(engine)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
