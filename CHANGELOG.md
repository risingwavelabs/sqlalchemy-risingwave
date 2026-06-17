# Changelog

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
