# RisingWave dialect for SQLAlchemy

## Prerequisites

For psycopg2 support you must install either:

* [psycopg2](https://pypi.org/project/psycopg2/), which has some
  [prerequisites](https://www.psycopg.org/docs/install.html#prerequisites) of
  its own.

* [psycopg2-binary](https://pypi.org/project/psycopg2-binary/)

(The binary package is a practical choice for development and testing but in
production it is advised to use the package built from sources.)
 
## Install and usage
Now the sqlalchemy-risingwave do not published to PyPi, so install this packages locally.

```
python setup.py sdist bdist_wheel # generate dist
pip install -e . # install this package
```

As in demo.py, use a `risingwave` connection string when creating the `Engine`.
```
./risedev p # start local risingwave cluster listening at 4566. 
python demo.py # connect to risedev use sqlalchemy
```

`sqlalchemy-risingwave` will work like a plugin to be placed into runtime sqlalchemy lib, so that we can overrides some code path to change the behaviour to better fits these python clients with RisingWave. 

## Ref
[Sqlalchemy dialects doc](https://github.com/sqlalchemy/sqlalchemy/blob/main/README.dialects.rst)

[CocoroachDB sqlalchemy](https://github.com/cockroachdb/sqlalchemy-cockroachdb)

