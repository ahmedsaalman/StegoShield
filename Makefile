# Common tasks. Python commands use the project virtualenv (.venv).
PYTHON := .venv/bin/python
NPM := npm --prefix frontend

.PHONY: install dev-api dev-web test lint build serve check

install:  ## Install Python and front-end dependencies
	$(PYTHON) -m pip install -r requirements-dev.txt
	$(NPM) ci

dev-api:  ## API with auto-reload on http://127.0.0.1:8000
	$(PYTHON) -m uvicorn api.main:app --reload --port 8000

dev-web:  ## React dev server on http://localhost:5173 (proxies /api to :8000)
	$(NPM) run dev

test:  ## All tests: Python, then front end
	$(PYTHON) -m pytest -q
	$(NPM) test

lint:  ## Ruff + ESLint + TypeScript
	$(PYTHON) -m ruff check . && $(PYTHON) -m ruff format --check .
	$(NPM) run lint && $(NPM) run typecheck

build:  ## Production build of the front end into frontend/dist
	$(NPM) run build

serve: build  ## Production-style server: API + built front end on http://127.0.0.1:8000
	$(PYTHON) -m uvicorn api.main:app --port 8000 --workers 2 --no-access-log

check: lint test  ## Everything CI should run
