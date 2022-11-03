from .base import RisingWaveDialect


class RisingWaveDialect_psycopg2(RisingWaveDialect):
    driver = "psycopg2"  # driver name

    supports_statement_cache = True
