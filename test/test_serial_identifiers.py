"""Offline compilation regressions; no RisingWave server is required."""

import pytest
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table
from sqlalchemy.schema import CreateTable

from sqlalchemy_risingwave.psycopg import (
    RisingWaveDialect_psycopg,
    RisingWaveDialect_psycopg_async,
)
from sqlalchemy_risingwave.psycopg2 import RisingWaveDialect_psycopg2


@pytest.mark.parametrize("dialect_cls", [
    RisingWaveDialect_psycopg2,
    RisingWaveDialect_psycopg,
    RisingWaveDialect_psycopg_async,
])
@pytest.mark.parametrize("type_, expected_type", [
    (Integer, "INTEGER"),
    (BigInteger, "BIGINT"),
])
@pytest.mark.parametrize("name", [
    " SERIAL", " BIGSERIAL", " SMALLSERIAL", "ordinary_id",
])
def test_serial_rewrite_preserves_column_name(dialect_cls, type_, expected_type, name):
    table = Table("items", MetaData(), Column(name, type_, primary_key=True))
    ddl = str(CreateTable(table).compile(dialect=dialect_cls()))
    quoted_name = f'"{name}"' if name.startswith(" ") else name
    assert f"{quoted_name} {expected_type} NOT NULL" in ddl
    assert f"PRIMARY KEY ({quoted_name})" in ddl
