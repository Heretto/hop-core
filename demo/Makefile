.PHONY: setup backend-deps frontend-deps start start-backend start-frontend docker-up docker-down docker-build help

# ── Local dev ────────────────────────────────────────────────────────────────

setup: .env backend-deps frontend-deps  ## Generate .env and install all dependencies

.env:
	./scripts/setup.sh

backend-deps:  ## Install Python dependencies (hop-core + uvicorn)
	cd backend && pip install -e ../../ && pip install -r requirements.txt

frontend-deps:  ## Install Node dependencies
	cd frontend && npm install

start:  ## Start backend and frontend together (auto-detects free ports, opens browser)
	./run.sh

start-backend:  ## Start the FastAPI backend on :8000
	cd backend && uvicorn main:app --reload --host 0.0.0.0 --port 8000

start-frontend:  ## Start the Angular dev server on :4200 (proxies /api → :8000)
	cd frontend && npm start

# ── Docker ───────────────────────────────────────────────────────────────────

docker-build:  ## Build Docker images without starting containers
	docker compose build

docker-up:  ## Build and start the full stack with Docker Compose (backend :8000, frontend :80)
	docker compose up --build

docker-down:  ## Stop and remove Docker Compose containers
	docker compose down

# ── Help ─────────────────────────────────────────────────────────────────────

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
