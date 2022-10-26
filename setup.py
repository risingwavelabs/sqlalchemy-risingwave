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
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ],
    keywords="SQLAlchemy RisingWave",
    project_urls={
        "Source": "https://github.com/risingwavelabs/sqlalchemy-risingwave",
        "Tracker": "https://github.com/risingwavelabs/sqlalchemy-risingwave/issues",
    },
    packages=find_packages(include=["sqlalchemy_risingwave"]),
    include_package_data=True,
    install_requires=["SQLAlchemy"],
    zip_safe=False,
    # # Do not support dialects now.
    entry_points={
        "sqlalchemy.dialects": [
            "risingwave = sqlalchemy_risingwave.psycopg2:RisingWaveDialect_psycopg2",
            "risingwave.psycopg2 = sqlalchemy_risingwave.psycopg2:RisingWaveDialect_psycopg2",
        ],
    },
)
