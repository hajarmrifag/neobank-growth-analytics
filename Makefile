.PHONY: install lint format test dashboard api-up api-down

install:
	python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

lint:
	ruff check .
	ruff format --check .

format:
	ruff check --fix .
	ruff format .

test:
	python -m pytest tests/analytics

dashboard:
	streamlit run dashboard/app.py

api-up:
	python3 scripts/init-api-env.py
	docker compose --env-file .env.api -f compose.api.yml up -d --build

api-down:
	docker compose --env-file .env.api -f compose.api.yml stop
