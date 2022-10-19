from sqlalchemy.dialects.postgresql.psycopg2 import PGDialect_psycopg2
from .base import RisingWaveDialect

class RisingWaveDialect_psycopg2(PGDialect_psycopg2, RisingWaveDialect):
    driver = "psycopg2"  # driver name