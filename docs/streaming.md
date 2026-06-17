# Streaming visibility and `INSERT` → `SELECT`

The `sqlalchemy-risingwave` README's *SQLAlchemy compatibility* section
mentions that an `INSERT` is not necessarily visible to a subsequent
`SELECT` in the same connection. This page expands on that.

This is not a defect in the dialect, and the dialect does not currently work
around it. Whether to work around it in the future is a product decision
under discussion separately; this document is the user-facing version of the
problem so that application authors can plan accordingly.

## What's actually happening

RisingWave is a streaming database. A write transaction does not commit by
synchronously updating a base table on disk in the way PostgreSQL would.
Instead the write enters a streaming pipeline, and the row becomes visible
once the pipeline crosses a checkpoint barrier. Until that barrier passes,
`SELECT` from the same connection (and from any other connection) returns the
pre-`INSERT` state.

In PostgreSQL, the canonical pattern below "just works":

```python
with engine.begin() as conn:
    conn.execute(t.insert().values(id=1, name="alpha"))
    rows = conn.execute(select(t)).all()
    # rows == [(1, "alpha")]
```

On RisingWave the same code can produce:

```python
    # rows == []   # the INSERT is still in the streaming pipeline
```

There is no error from RisingWave. The `INSERT` succeeded. The data will
become visible to subsequent reads, just not immediately.

This is the root cause of nearly all of the 281 advisory failures the
SQLAlchemy compliance suite reports against RisingWave on `main`: every
type round-trip test (`BinaryTest`, `BooleanTest`, `IntegerTest`, `NumericTest`,
`StringTest`, `UnicodeTextTest`, …) writes a row, reads it back, and asserts
the value matches. RisingWave's eventual visibility breaks the assertion
without breaking the SQL.

## What this means for application code

If your application reads back what it just wrote in the same code path —
ORM-style "create then return", BI tools that show the row after an SQL Lab
insert, test fixtures, migrations that verify themselves — you need to plan
for the visibility gap explicitly:

* **Treat RisingWave as a sink.** The cleanest pattern is to let your
  upstream ingest pipeline land data into RisingWave and only read from
  RisingWave for analysis. Don't write-then-read inside the same request.

* **Don't rely on `SELECT` in the same transaction.** A `BEGIN; INSERT;
  SELECT; COMMIT;` block can return empty for the `SELECT` step. SQLAlchemy
  ORM patterns like `session.add(obj); session.flush(); session.refresh(obj)`
  fall into this trap.

* **Avoid unique-by-read-back idioms.** Patterns that depend on reading the
  row right after insert to allocate an id, then writing again, will not see
  the row reliably. Use application-supplied ids (the dialect rewrites
  `SERIAL` away in DDL anyway, so the application is already responsible for
  ids).

If your application needs synchronous read-after-write — for example,
Superset users who insert a row in SQL Lab and immediately want to see it —
you have two options today:

1. **Wait for the next checkpoint barrier.** RisingWave's checkpoint
   interval is configurable; once the barrier passes, the row is visible to
   every subsequent reader.
2. **Issue `FLUSH;` after the writing connection commits.** RisingWave's
   `FLUSH` command forces the pipeline to materialise everything in flight.
   This is a real cluster-wide operation and has a measurable performance
   cost, so it is not appropriate to do automatically inside the dialect on
   every commit; it is a deliberate choice the application makes.

Whether the dialect should issue `FLUSH` for users automatically — a
"`FLUSH`-on-commit" mode — is the open product decision the project is
currently evaluating. Until that lands, treat the visibility gap as an
explicit property of the database.

## What this is NOT

* **Not a transactional isolation bug.** PostgreSQL `READ COMMITTED` does not
  describe what RisingWave does. The right mental model is "writes commit
  successfully and become visible eventually," not "writes are visible
  immediately and isolation level controls who sees them."
* **Not something the dialect can transparently fix.** Any workaround
  (`FLUSH`-on-commit, polling-and-retrying reads, etc.) changes the database
  semantics or the performance profile in a way users should opt in to, not
  inherit.
* **Not a reason to claim the test fails are dialect bugs.** The compliance
  suite is doing exactly what it should — encoding PG OLTP expectations — and
  RisingWave's streaming model is doing exactly what it should — eventually
  materialising writes. The two designs disagree, and this document is where
  that disagreement is recorded.
* **Not fixed by switching to the async dialect.** The async path added in
  v2.1.0 lets a single Python process keep many queries in flight on one
  thread, which is purely a client-side concurrency story. RisingWave's
  server-side streaming barriers are unchanged, so an async
  `INSERT` → `SELECT` block has the same visibility window as a sync
  one. See [`docs/async.md`](async.md).

## Related code paths

* [`.github/workflows/compliance.yml`](../.github/workflows/compliance.yml) —
  the advisory compliance harness that produces the failure counts cited in
  the README.
* [`compliance/test_suite.py`](../compliance/test_suite.py) — re-export of the
  upstream `sqlalchemy.testing.suite` that the workflow runs.
* [`sqlalchemy_risingwave/requirements.py`](../sqlalchemy_risingwave/requirements.py) —
  feature flags declared closed because RisingWave does not implement them.
