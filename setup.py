import os
import re

from setuptools import setup, find_packages

with open(os.path.join(os.path.dirname(__file__), "sqlalchemy_risingwave", "__init__.py")) as v:
    VERSION = re.compile(r'.*__version__ = "(.*?)"', re.S).match(v.read()).group(1)

with open(os.path.join(os.path.dirname(__file__), "README.md")) as f:
    README = f.read()

setup(
    name="sqlalchemy-risingwave",
    version=VERSION,
    author="RisingWave Labs",
    author_email="risingwave@dev.com",
    url="https://github.com/risingwavelabs/risingwave",
    description="RisingWave dialect for SQLAlchemy",
    long_description=README,
    long_description_content_type="text/markdown",
    license="http://www.apache.org/licenses/LICENSE-2.0",
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    keywords="SQLAlchemy RisingWave",
    project_urls={
        "Source": "https://github.com/risingwavelabs/sqlalchemy-risingwave",
        "Tracker": "https://github.com/risingwavelabs/sqlalchemy-risingwave/issues",
    },
    packages=find_packages(include=["sqlalchemy_risingwave"]),
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=["SQLAlchemy>=2.0,<2.1"],
    extras_require={
        # psycopg3 is the upstream-recommended PostgreSQL driver and the
        # path that lets applications opt into SQLAlchemy's async engine for
        # RisingWave via ``risingwave+psycopg://`` URLs. The dialect itself
        # imports psycopg lazily, so this dependency stays optional —
        # existing psycopg2-only users are unaffected.
        "psycopg3": ["psycopg[binary]>=3.1"],
    },
    zip_safe=False,
    entry_points={
        "sqlalchemy.dialects": [
            "risingwave = sqlalchemy_risingwave.psycopg2:RisingWaveDialect_psycopg2",
            "risingwave.psycopg2 = sqlalchemy_risingwave.psycopg2:RisingWaveDialect_psycopg2",
            "risingwave.psycopg = sqlalchemy_risingwave.psycopg:RisingWaveDialect_psycopg",
        ],
    },
)
