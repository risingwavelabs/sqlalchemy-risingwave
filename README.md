# RisingWave dialect for SQLAlchemy

SQLAlchemy is the Python SQL toolkit and Object Relational Mapper that gives application developers the full power and flexibility of SQL. https://www.sqlalchemy.org/

RisingWave is a cloud-native streaming database that uses SQL as the interface language. It is designed to reduce the complexity and cost of building real-time applications. https://www.risingwave.com

## Prerequisites

For psycopg2 support you must install either:

* [psycopg2](https://pypi.org/project/psycopg2/), which has some
  [prerequisites](https://www.psycopg.org/docs/install.html#prerequisites) of
  its own.

* [psycopg2-binary](https://pypi.org/project/psycopg2-binary/)

(The binary package is a practical choice for development and testing but in
production it is advised to use the package built from sources.)

## Install
Install via [PyPI](https://pypi.org/project/sqlalchemy-risingwave/)
```
pip install sqlalchemy-risingwave
```

Recommend install packages locally like below. If directly from PyPI, the version may not be the most updated.

```
python setup.py sdist bdist_wheel # generate dist
pip install -e . # install this package
```

## Usage
`sqlalchemy-risingwave` will work like a plugin to be placed into runtime sqlalchemy lib, so that we can overrides some code path to change the behaviour to better fits these python clients with RisingWave.

See how to use with Superset: [doc](./doc/integrate_with_superset.md)

## Async support

Released in v2.1.0. RisingWave can now be driven from SQLAlchemy 2.0's
async engine API via the psycopg3 driver. Install the dialect with the
optional `psycopg3` extra:

```sh
pip install -U "sqlalchemy-risingwave[psycopg3]"
```

Sync and async both go through the same `risingwave+psycopg://` URL —
SQLAlchemy picks the right dialect class from the engine factory:

```python
import asyncio

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import create_async_engine


# Sync
sync_engine = create_engine("risingwave+psycopg://root@localhost:4566/dev")
with sync_engine.connect() as conn:
    print(conn.execute(text("SELECT 1")).scalar_one())


# Async
async def main():
    async_engine = create_async_engine(
        "risingwave+psycopg://root@localhost:4566/dev"
    )
    try:
        async with async_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            print(result.scalar_one())
    finally:
        await async_engine.dispose()


asyncio.run(main())
```

The legacy `risingwave+psycopg2://` URL is sync only — psycopg2 itself
has no async mode. async-only drivers such as `asyncpg` are not
implemented; the supported async path is psycopg3.

See [`docs/async.md`](docs/async.md) for the full usage guide, the
FastAPI sketch, the read-after-write reminder (RisingWave streaming
visibility still applies — async does not change it), and the list of
behaviour each PR is required to validate against a real RisingWave
instance in CI.

## SQLAlchemy compatibility

This dialect targets SQLAlchemy 2.0+. RisingWave's SQL surface is
PostgreSQL-compatible for *querying*, but diverges from PostgreSQL OLTP
semantics for several features the SQLAlchemy ORM and most non-streaming
tooling assume. This section documents that gap honestly rather than papering
over it.

The upstream `sqlalchemy.testing.suite` dialect compliance suite runs against
a real RisingWave instance via
[`.github/workflows/compliance.yml`](.github/workflows/compliance.yml). It is
**advisory** (`continue-on-error: true`) — its job is to quantify the gap, not
to gate merges. The current baseline on `main` is:

| Result | Count | Meaning |
|---|---|---|
| Pass | 90 | Behaviour the dialect implements as PG-compatible |
| Fail | 281 | RisingWave streaming semantics diverge from the assertion (see below) |
| Skip | 946 | Features RisingWave does not implement; declared unsupported via `Requirements` and the advisory harness |
| Error | 0 | Fixture or collection errors (none expected on `main`) |

That is `90 / (90 + 281) ≈ 24%` of tests whose assertion RisingWave can
express, and `90 / 1317 ≈ 6.8%` of the suite overall. The 946 skips are
honest "the database does not support this" signals, not silent passes.

### Safe fallbacks the dialect applies

These rewrites change how SQLAlchemy renders DDL so the RisingWave parser
accepts it. Importantly they only re-shape syntax that RisingWave **already
does not enforce in PostgreSQL semantics either**, so the rewrite is a no-op
at the data layer — not a silent change to a user-declared invariant:

* `SERIAL` / `BIGSERIAL` / `SMALLSERIAL` → `INTEGER` / `BIGINT` / `SMALLINT`
  ([PR #49](https://github.com/risingwavelabs/sqlalchemy-risingwave/pull/49)).
  RisingWave does not implement PostgreSQL per-row autoincrement, so inserts
  must supply explicit ids.
* `CHAR(n)` / `VARCHAR(n)` / `NUMERIC(p, s)` / `DECIMAL(p, s)` →
  unparameterised forms
  ([PR #50](https://github.com/risingwavelabs/sqlalchemy-risingwave/pull/50)).
  RisingWave does not enforce length / precision caps.
* `Uuid()` / `UUID` → `VARCHAR` with SQLAlchemy non-native UUID round-trip
  ([PR #51](https://github.com/risingwavelabs/sqlalchemy-risingwave/pull/51)).
  Format validation moves to the application layer.
* `Enum(...)` → `VARCHAR` (`supports_native_enum = False`)
  ([PR #51](https://github.com/risingwavelabs/sqlalchemy-risingwave/pull/51)).
  Note that the optional `CHECK` constraint SQLAlchemy generates for
  non-native enums is also not enforced by RisingWave (see below).

### User-declared invariants the dialect does NOT silently drop

Silently rewriting these would let an application's data model assumptions
break without anyone noticing, so the dialect does not strip, emulate, or
pretend to enforce them. Depending on the RisingWave version and construct,
RisingWave may reject the DDL or accept metadata that is not enforced at
runtime; in either case, the application must not rely on the dialect to
provide the invariant:

* `CHECK` constraints — not enforced by RisingWave.
* `UNIQUE` constraints — not enforced.
* `FOREIGN KEY` constraints — declared but not enforced at runtime.

If your application depends on any of these invariants today, enforce them at
the application layer or in the ingest pipeline before data lands in
RisingWave.

### Read-after-write

An `INSERT` enters the streaming pipeline and is not necessarily visible to a
subsequent `SELECT` in the same connection until the change crosses a
checkpoint barrier. This is a property of RisingWave's streaming model, not a
bug in the dialect. SQLAlchemy's ORM and the upstream compliance suite assume
PostgreSQL OLTP semantics (`INSERT` then `SELECT` returns the row), and that
assumption is the root cause of nearly all of the 281 advisory failures.

See [`docs/streaming.md`](docs/streaming.md) for the trade-offs and how to
think about this in application code.

### Where this fits in CI

* Every pull request runs the dialect's own `test/` suite against a real
  RisingWave instance across Python 3.10 / 3.11 / 3.12 / 3.13. This suite is
  merge-gating: a green build means the documented dialect behaviour above
  still holds.
* Pull requests that touch the dialect or the compliance harness also run the
  upstream SQLAlchemy compliance suite via `compliance.yml`. That run is
  advisory and produces a `compliance-log` artifact for triage.

## Develop
Install pre-req.
```
pip install sqlalchemy alembic pytest psycopg2-binary
```

### Test
We use pytest for unittest.
```
pytest # to run the test
```

## Ref

- [Sqlalchemy dialects doc](https://github.com/sqlalchemy/sqlalchemy/blob/main/README.dialects.rst)
- [CocoroachDB sqlalchemy](https://github.com/cockroachdb/sqlalchemy-cockroachdb)
- [RisingWave: Open-Source Streaming Database](https://www.risingwave.com/database/)
- [RisingWave Cloud](https://www.risingwave.com/cloud/)
- [What is RisingWave?](https://docs.risingwave.com/docs/current/intro/)
