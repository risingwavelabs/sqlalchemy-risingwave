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
from sqlalchemy.testing.plugin.pytestplugin import (
    pytest_collection_modifyitems as _sqla_pytest_collection_modifyitems,
)


_UNSUPPORTED_CONSTRAINT_FIXTURE_CLASSES = {
    "ComponentReflectionTest",
    "CompositeKeyReflectionTest",
    "JoinTest",
    "QuotedNameArgumentTest",
}


def pytest_collection_modifyitems(session, config, items):
    _sqla_pytest_collection_modifyitems(session, config, items)

    skip_constraint_fixtures = pytest.mark.skip(
        reason=(
            "RisingWave does not support table-level CHECK / UNIQUE / FK "
            "constraints. These upstream suite classes require unsupported "
            "constraint-backed fixtures, so the advisory compliance run skips "
            "them instead of silently stripping user constraints."
        )
    )
    for item in items:
        if any(
            item.nodeid.startswith(f"compliance/test_suite.py::{class_name}_")
            for class_name in _UNSUPPORTED_CONSTRAINT_FIXTURE_CLASSES
        ):
            item.add_marker(skip_constraint_fixtures)
