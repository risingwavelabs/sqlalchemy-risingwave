# RisingWave dialect for SQLAlchemy

SQLAlchemy is the Python SQL toolkit and Object Relational Mapper that gives application developers the full power and flexibility of SQL. https://www.sqlalchemy.org/

RisingWave is a cloud-native streaming database that uses SQL as the interface language. It is designed to reduce the complexity and cost of building real-time applications. https://www.risingwave.com

## Prerequisites

For psycopg2 support you must install either:

* [psycopg2](https://pypi.org/project/psycopg2/), which has some
  [prerequisites](https://www.psycopg.org/docs/install.html#prerequisites) of
  its own.

* [psycopg2-binary](https://pypi.org/project/psycopg2-binary/)

(The binary package is a practical choice for development and testing but in
production it is advised to use the package built from sources.)
 
## Install
Install via [PyPI](https://pypi.org/project/sqlalchemy-risingwave/)
```
pip install sqlalchemy-risingwave
```

Recommend install packages locally like below. If directly from PyPI, the version may not be the most updated.

```
python setup.py sdist bdist_wheel # generate dist
pip install -e . # install this package
```

## Usage
`sqlalchemy-risingwave` will work like a plugin to be placed into runtime sqlalchemy lib, so that we can overrides some code path to change the behaviour to better fits these python clients with RisingWave.

See how to use with Superset: [doc](./doc/integrate_with_superset.md)

## Develop
Install pre-req.
```
pip install sqlalchemy alembic pytest psycopg2-binary
```

### Test
We use pytest for unittest.
```
pytest # to run the test
```

## Ref

- [Sqlalchemy dialects doc](https://github.com/sqlalchemy/sqlalchemy/blob/main/README.dialects.rst)

- [CocoroachDB sqlalchemy](https://github.com/cockroachdb/sqlalchemy-cockroachdb)

- [RisingWave: Open-Source Streaming Database](https://www.risingwave.com/database/)

- [RisingWave Cloud](https://www.risingwave.com/cloud/)

- [What is RisingWave?](https://docs.risingwave.com/docs/current/intro/)
