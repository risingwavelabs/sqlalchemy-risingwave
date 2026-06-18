# Changelog

## 2.1.0 - 2026-06-18

Adds the psycopg3 driver path — synchronous and asynchronous — to the
existing psycopg2 sync dialect. No behaviour on the existing
`risingwave+psycopg2://` URL changes; 2.1.0 is a backwards-compatible
addition.

### Added

- psycopg3 driver support via `risingwave+psycopg://` URLs. Sync engines
  resolve to `RisingWaveDialect_psycopg`; async engines resolve to
  `RisingWaveDialect_psycopg_async` via the sync class's
  `get_async_dialect_cls` override, keeping every RisingWave behaviour
  (compilers, capability flags, reflection, Superset cancel-query shim)
  consistent across both paths.
- SQLAlchemy `create_async_engine("risingwave+psycopg://...")` is now
  supported. The sync `RisingWaveDialect_psycopg.get_async_dialect_cls(...)`
  dispatches to `RisingWaveDialect_psycopg_async` so both sync and async
  paths share the `_RisingWaveCommon` overrides.
- Optional `psycopg3` extras: `pip install "sqlalchemy-risingwave[psycopg3]"`.
- A documentation page at `docs/async.md` covering the async usage
  pattern, FastAPI sketch, the streaming visibility reminder, and the
  exact set of behaviours every PR validates against a real RisingWave
  instance in CI.
- A runnable `examples/async_usage.py` script covering minimal SELECT,
  write → explicit FLUSH → read, and `asyncio.gather` concurrency.
- README "Async support" section.

### Changed

- The driver-agnostic RisingWave behaviour has moved from the
  `RisingWaveDialect` class into a new `_RisingWaveCommon` mixin. The
  `RisingWaveDialect` name is preserved as an import alias on the
  psycopg2 path; downstream code that imports it from
  `sqlalchemy_risingwave.base` continues to work without modification.

### Tests

The new merge-gating integration tests land alongside the dialect.
They run against a real RisingWave instance via
``.github/workflows/test.yml`` and a failure blocks merge. The
``compliance.yml`` workflow remains advisory and is unchanged.

- Cross-driver round trip: data written via psycopg2 sync is read back
  identically through psycopg3 sync and psycopg3 async, with an
  explicit `FLUSH` so RisingWave's streaming visibility window can't
  mask a driver-level mismatch.
- Parametrised type round-trip matrix across driver
  (psycopg2, psycopg) × type (Integer, BigInteger, Float, String
  ASCII / unicode, UUID, Boolean true/false, LargeBinary).
- Async wall-clock proof that `asyncio.gather` actually parallelises
  I/O — the test measures one query's elapsed time and asserts the
  batch of N queries completes in noticeably less than that, so a
  dialect that secretly serialised every connection would fail loudly.

### Known limitations

- The asyncpg driver is still not implemented; the supported async
  path is psycopg3 via `risingwave+psycopg://`.
- Read-after-write visibility is unchanged in either driver: an
  `INSERT` is not guaranteed to be visible to a subsequent `SELECT`
  until a checkpoint barrier has passed or the user explicitly runs
  `FLUSH;`. async does not change this. See `docs/streaming.md`.

## 2.0.0 - 2026-06-17

This release updates `sqlalchemy-risingwave` for SQLAlchemy 2.0.x and documents the dialect's current compatibility boundary against real RisingWave.

### Breaking changes

- Drop Python 3.8 and 3.9. The package now requires Python 3.10+.
- Drop SQLAlchemy 1.4 support. The package now requires `SQLAlchemy>=2.0,<2.1`.
- Update dialect capability flags to match RisingWave's actual feature set:
  - native UUID is disabled and SQLAlchemy UUID values are stored through a `VARCHAR` fallback;
  - native ENUM is disabled and SQLAlchemy enum values are stored through a `VARCHAR` fallback;
  - foreign-key support and foreign-key reflection are declared unsupported.
- Reflection now returns real primary-key metadata where available. Code that treated an empty `get_pk_constraint()` result as "no primary key" should inspect `constrained_columns` instead.

### Added

- SQLAlchemy 2.0 dialect API compatibility for reflection and connection metadata paths.
- Real RisingWave integration tests across Python 3.10, 3.11, 3.12, and 3.13.
- Advisory SQLAlchemy upstream compliance workflow against a real RisingWave instance.
- Primary-key reflection support.
- Hardened column/type reflection for RisingWave scalar types.
- Superset SQL Lab cancel-query compatibility shim for `pg_backend_pid()` and `pg_terminate_backend(...)` probes.
- Documentation for SQLAlchemy compatibility boundaries and RisingWave streaming visibility in `README.md` and `docs/streaming.md`.

### Changed

- PostgreSQL `SERIAL`, `BIGSERIAL`, and `SMALLSERIAL` DDL emitted by SQLAlchemy is rewritten to `INTEGER`, `BIGINT`, and `SMALLINT`, respectively. RisingWave does not provide PostgreSQL autoincrement semantics, so applications should provide explicit IDs.
- Parameterized `CHAR(n)`, `VARCHAR(n)`, `NUMERIC(p, s)`, and `DECIMAL(p, s)` DDL emitted by SQLAlchemy is rendered as unparameterized RisingWave-accepted types.
- UUID and enum SQLAlchemy types use non-native `VARCHAR` storage instead of claiming native RisingWave support.

### Known limitations

- RisingWave is a streaming database, not a PostgreSQL OLTP database. An `INSERT` is not guaranteed to be immediately visible to a following `SELECT` until a checkpoint/barrier has passed or the user explicitly runs `FLUSH;`.
- `CHECK`, `UNIQUE`, and `FOREIGN KEY` constraints should not be relied on for runtime enforcement in RisingWave. The dialect does not silently strip, emulate, or pretend to enforce these invariants.
- The advisory SQLAlchemy compliance baseline on `main` is `90 passed / 281 failed / 946 skipped / 0 errors`. The remaining failures primarily reflect PostgreSQL OLTP assumptions that do not match RisingWave streaming semantics.
- Async SQLAlchemy drivers such as `asyncpg` are not supported by this release.
