# Async SQLAlchemy with RisingWave

`sqlalchemy-risingwave` ships an async dialect that lets applications drive
RisingWave from `asyncio` event loops via SQLAlchemy 2.0's async engine
API. This page describes what the async path solves, what it does **not**
solve, and how to wire it up against the underlying psycopg3 driver.

## What async actually changes

Python's `async` / `await` syntax is a concurrency model: at every
`await` point a coroutine can be suspended and the event loop can run a
different coroutine while the I/O is in flight. The dialect side of that
deal is that `await connection.execute(...)` returns the thread to the
event loop while the network round-trip to RisingWave is pending, so a
single-threaded process can have many SELECTs in flight at once.

This is the property that lets a FastAPI / Starlette / Tornado /
Quart-style web server serve hundreds or thousands of concurrent
requests on one OS thread.

Async **does not** change:

* RisingWave server-side latency. A query that takes 50 ms synchronously
  still takes 50 ms when awaited; you're just not blocking the event
  loop while it runs.
* RisingWave streaming visibility. `INSERT` into RisingWave is not
  immediately visible to a subsequent `SELECT` (see
  [`docs/streaming.md`](streaming.md)). That property is intrinsic to
  RisingWave's streaming pipeline, not to whether the client is sync or
  async. Async clients see exactly the same window as sync clients.
* Enforcement of `CHECK` / `UNIQUE` / `FOREIGN KEY` constraints. Those
  are not enforced by RisingWave in either driver mode.

## Driver requirements

The async path is implemented on top of [psycopg3]; install the dialect
with the `psycopg3` extra:

```
pip install -U "sqlalchemy-risingwave[psycopg3]"
```

The legacy `risingwave+psycopg2://` URL is sync-only. The async dialect
only resolves through the `risingwave+psycopg://` URL family.

[psycopg3]: https://www.psycopg.org/psycopg3/docs/

## Basic usage

```python
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    engine = create_async_engine(
        "risingwave+psycopg://root@localhost:4566/dev"
    )
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            print(result.scalar_one())
    finally:
        await engine.dispose()


asyncio.run(main())
```

`engine.dialect.driver` reports `"psycopg"` for both the sync and the
async engine; `engine.dialect.is_async` is `True` only on the async
engine. The driver name follows SQLAlchemy convention — it identifies
the DBAPI, not the sync-vs-async mode.

## ORM `AsyncSession`

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]


async_session = async_sessionmaker(engine, expire_on_commit=False)


async def fetch_alpha():
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.name == "alpha")
        )
        return result.scalars().all()
```

## Reflection

SQLAlchemy's `inspect(...)` API is synchronous because it walks the
catalog through one connection. Wrap it via `conn.run_sync` to use it
from an async connection:

```python
async with engine.connect() as conn:
    has_users = await conn.run_sync(
        lambda sync_conn: inspect(sync_conn).has_table("users")
    )
    columns = await conn.run_sync(
        lambda sync_conn: inspect(sync_conn).get_columns("users")
    )
```

This is the standard SQLAlchemy 2.0 pattern and is not RisingWave
specific. The dialect's reflection methods (`get_pk_constraint`,
`get_columns`, `get_table_names`, etc.) are reused as-is.

## FastAPI sketch

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def make_app() -> FastAPI:
    engine = create_async_engine(
        "risingwave+psycopg://root@localhost:4566/dev"
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield {"session_factory": session_factory}
        finally:
            await engine.dispose()

    app = FastAPI(lifespan=lifespan)

    @app.get("/healthz")
    async def healthz():
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app
```

## Read-after-write reminder

If your application code follows a write with an immediate read in the
same async block:

```python
async with session.begin():
    session.add(User(id=1, name="alpha"))
    # This SELECT can return zero rows on RisingWave, regardless of
    # whether the engine is sync or async.
    rows = (await session.execute(select(User))).all()
```

…the second statement can return empty data. This is RisingWave's
streaming-visibility behaviour, documented in
[`docs/streaming.md`](streaming.md), not a defect of the async dialect.
The patterns recommended there — treat RisingWave as a sink, avoid
write-then-read in the same transaction, supply application-allocated
ids — apply to async code identically.

`FLUSH;` is still the explicit knob if you really need synchronous
visibility:

```python
async with engine.begin() as conn:
    await conn.execute(text("INSERT INTO users (id, name) VALUES (1, 'alpha')"))
    await conn.execute(text("FLUSH"))

async with engine.connect() as conn:
    rows = (await conn.execute(text("SELECT id FROM users"))).all()
```

Whether the dialect should issue `FLUSH` automatically on every commit
(a `FLUSH`-on-commit mode) is an open product trade-off discussed in
the streaming-visibility document; it is not enabled by default.

## What is and is not covered by CI

Every `sqlalchemy-risingwave` pull request that touches the dialect
runs `test/test_async_psycopg_usage.py` against a real RisingWave
instance. The async tests cover:

* `create_async_engine("risingwave+psycopg://...")` dispatch and that
  the resolved class has `name == "risingwave"`, `driver == "psycopg"`,
  and `is_async is True`.
* `SELECT` round-trip and a parameterised `INSERT` then `SELECT` (the
  latter is what proves the async bind-parameter adapter works).
* The Superset cancel-query shim through the async dialect.
* Wall-clock proof that `asyncio.gather` actually parallelises I/O —
  the test asserts the batch of N independent queries finishes in
  meaningfully less time than running them sequentially.
* Cross-driver consistency: data inserted via psycopg2 sync is read
  back identically through psycopg3 sync and psycopg3 async (with an
  explicit `FLUSH`).
* A parametrised type round-trip matrix across all supported drivers
  and SQLAlchemy types (Integer, BigInteger, Float, String ASCII /
  unicode, UUID, Boolean, LargeBinary).

If your async code path exercises behaviour outside this list, please
open an issue — there is no E2E coverage for arbitrary frameworks yet,
just the dialect-level contracts above.
