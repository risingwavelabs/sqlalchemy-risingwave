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

from sqlalchemy.testing.plugin.pytestplugin import *  # noqa