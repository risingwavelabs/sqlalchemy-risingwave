ENV_BASE=${CURDIR}
ENV=${ENV_BASE}/sqlalchemy-risingwave/venv
TOX=${ENV}/bin/tox

.PHONY: all
all: test lint

.PHONY: bootstrap
bootstrap:
	@mkdir -p ${ENV}
	virtualenv ${ENV}
	${ENV}/bin/pip install sqlalchemy alembic pytest psycopg2-binary pip-tools tox
	# ${ENV}/bin/pip install -r dev-requirements.txt

.PHONY: clean-bootstrap-env
clean-bootstrap-env:
	rm -rf ${ENV}

.PHONY: test
test:
	${TOX} -e py39

.PHONY: lint
lint:
	${TOX} -e lint

.PHONY: update-requirements
update-requirements:
	${TOX} -e pip-compile

.PHONY: build
build: clean
	${ENV}/bin/python setup.py sdist

.PHONY: clean
clean:
	rm -rf dist build

.PHONY: detox
detox: clean
	rm -rf .tox
