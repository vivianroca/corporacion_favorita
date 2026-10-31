PYTHON := .venv/bin/python
COMPOSE := docker compose --env-file .env -f docker/compose.yaml

.PHONY: test lint infra-prepare infra-build infra-up infra-stop infra-down infra-status inbox-init publish-next
COUNT ?= 1

test:
	$(PYTHON) -m pytest -q

lint:
	.venv/bin/ruff check src tests scripts dags docker/init_airflow.py
	.venv/bin/ruff format --check src tests scripts dags docker/init_airflow.py

infra-prepare:
	$(PYTHON) scripts/preparar_infra.py
	$(COMPOSE) config --quiet

infra-build:
	$(COMPOSE) build --pull=false airflow-init

infra-up:
	$(COMPOSE) up -d --no-build --pull never

infra-stop:
	$(COMPOSE) stop

infra-down:
	$(COMPOSE) down

infra-status:
	$(COMPOSE) ps

inbox-init:
	$(PYTHON) -m reposicion.cli initialize-inbox

publish-next:
	$(PYTHON) -m reposicion.cli publish-next --count $(COUNT)
