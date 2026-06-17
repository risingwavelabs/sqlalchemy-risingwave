"""Conftest for the SQLAlchemy compliance suite directory.

The compliance suite lives in its own directory so the existing happy-path
``test/`` suite (always-green smoke tests for PR review) and the upstream
dialect conformance suite (advisory, larger, currently expected to surface
RisingWave streaming-semantics divergences) stay independently runnable.

``setup.cfg``'s ``[db]`` and ``[sqla_testing]`` blocks plus the dialect
registration in ``test/conftest.py`` are also needed here, so this file
mirrors that minimal bootstrap before importing SQLAlchemy's pytest plugin.
"""

from sqlalchemy.dialects import registry
import pytest

registry.register(
    "risingwave",
    "sqlalchemy_risingwave.psycopg2",
    "RisingWaveDialect_psycopg2",
)

registry.register(
    "risingwave.psycopg2",
    "sqlalchemy_risingwave.psycopg2",
    "RisingWaveDialect_psycopg2",
)

pytest.register_assert_rewrite("sqlalchemy.testing.assertions")

from sqlalchemy.testing.plugin.pytestplugin import *  # noqa: F401,F403
