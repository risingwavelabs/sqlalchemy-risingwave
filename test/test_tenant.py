"""Tests for RisingWave Cloud tenant parameter handling."""

from sqlalchemy import create_engine
from sqlalchemy_risingwave.base import RisingWaveDialect


class TestTenantParameter:
    """Test cases for tenant parameter conversion."""

    def test_tenant_parameter_converted_to_options(self):
        """Test that tenant parameter is converted to --tenant option."""
        dialect = RisingWaveDialect()
        url = create_engine(
            "risingwave://user:pass@host:4566/db?tenant=my-tenant"
        ).url

        cargs, cparams = dialect.create_connect_args(url)

        assert "tenant" not in cparams
        assert "options" in cparams
        assert cparams["options"] == "--tenant=my-tenant"

    def test_tenant_merged_with_existing_options(self):
        """Test that tenant is merged with existing options parameter."""
        dialect = RisingWaveDialect()
        url = create_engine(
            "risingwave://user:pass@host:4566/db?tenant=my-tenant&options=-c%20statement_timeout%3D30000"
        ).url

        cargs, cparams = dialect.create_connect_args(url)

        assert "tenant" not in cparams
        assert "options" in cparams
        assert "--tenant=my-tenant" in cparams["options"]
        assert "-c statement_timeout=30000" in cparams["options"]

    def test_no_tenant_parameter(self):
        """Test that connections without tenant work normally."""
        dialect = RisingWaveDialect()
        url = create_engine("risingwave://user:pass@host:4566/db").url

        cargs, cparams = dialect.create_connect_args(url)

        assert "tenant" not in cparams
        # options should not be added if not present
        assert cparams.get("options") is None or "--tenant" not in cparams.get(
            "options", ""
        )

    def test_sslmode_preserved(self):
        """Test that sslmode parameter is preserved alongside tenant."""
        dialect = RisingWaveDialect()
        url = create_engine(
            "risingwave://user:pass@host:4566/db?sslmode=require&tenant=my-tenant"
        ).url

        cargs, cparams = dialect.create_connect_args(url)

        assert cparams.get("sslmode") == "require"
        assert cparams["options"] == "--tenant=my-tenant"
