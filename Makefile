.PHONY: up down dev panel test lint schema install

up:            ## start infra (rabbitmq, postgres, prometheus, grafana)
	docker compose -f infra/docker-compose.yml up -d

down:          ## stop infra
	docker compose -f infra/docker-compose.yml down

install:       ## sync python workspace deps
	uv sync

dev:           ## run the orchestrator (FastAPI + consumer) on :8000
	cd apps/orchestrator && uv run uvicorn app.main:app --reload --port 8000

panel:         ## run the control panel (Vite) on :5173
	cd apps/control-panel && pnpm install && pnpm dev

test:          ## run orchestrator tests (no infra needed)
	cd apps/orchestrator && uv run pytest -q

lint:          ## ruff check
	uv run ruff check .

schema:        ## export the contract JSON Schema (for the frontend types)
	cd packages/contract && uv run python -m fieldflow_contract.export_schema
