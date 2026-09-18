.PHONY: help gen test dbt-build docker-init docker-app replay docker-down docker-logs clean

PROFILE ?= dev
SPEED ?= 10x

help:
	@echo "motor-health-lab — Local condition monitoring (DuckDB + dbt + Streamlit)"
	@echo ""
	@echo "Live Demo (3 terminals):"
	@echo "  Terminal 1: make docker-init         (init pipeline: gen + ingest + dbt)"
	@echo "  Terminal 2: make docker-app          (start dashboard @ http://localhost:8501)"
	@echo "  Terminal 3: make replay PROFILE=dev  (inject live data, updates every 5s)"
	@echo ""
	@echo "Quick start (Docker):"
	@echo "  make docker-init        Init: generate + ingest + dbt"
	@echo "  make docker-app         Run Streamlit dashboard"
	@echo "  make docker-down        Stop all services"
	@echo ""
	@echo "Manual (dev without Docker):"
	@echo "  make gen                Generate synthetic data (PROFILE=dev|demo|full)"
	@echo "  make test               Run pytest on generator & ingest"
	@echo "  make dbt-build          Build dbt models"
	@echo "  make app                Run Streamlit locally"
	@echo "  make replay             Replay data (live demo)"
	@echo ""
	@echo "Options:"
	@echo "  PROFILE=dev|demo|full   Generator profile (default: dev)"
	@echo "  SPEED=1x|10x|100x       Replay speed (default: 10x)"

gen:
	@echo "[gen] Generating synthetic data (PROFILE=$(PROFILE))..."
	python3 -m generator.main --profile $(PROFILE)
	@echo "[gen] ✓ Data in data/"

test:
	@echo "[test] Running pytest..."
	python3 -m pytest generator/ ingest/ -v

dbt-build:
	@echo "[dbt] Building models..."
	cd dbt && uv run dbt build
	@echo "[dbt] ✓ All models built"

docker-init:
	@echo "[docker] Init pipeline (gen + ingest + dbt)..."
	docker-compose --profile init up --remove-orphans
	@echo "[docker] ✓ Pipeline complete. Run 'make docker-app' to view dashboard."

docker-app:
	@echo "[docker] Starting Streamlit dashboard (http://localhost:8501)..."
	docker-compose --profile app up

replay:
	@echo "[replay] Injecting live data into dashboard (SPEED=$(SPEED))..."
	@echo "  Dashboard metrics will update every 5 seconds as data flows in"
	python3 app/replay.py --data-dir data/$(PROFILE) --speed $(SPEED) --pause 3

replay-demo:
	@echo "[demo] LIVE DEMO: Data updates every 5 seconds"
	@echo ""
	@echo "1. Terminal 1 (pipeline): make docker-init"
	@echo "2. Terminal 2 (dashboard): make docker-app"
	@echo "3. Terminal 3 (replay):    make replay PROFILE=dev"
	@echo ""
	@echo "Watch dashboard → metrics grow every 5 seconds as replay injects data"
	@echo ""

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

app:
	@echo "[app] Running Streamlit locally..."
	streamlit run app/streamlit_app.py

clean:
	@echo "[clean] Removing data, .duckdb, containers..."
	rm -rf data/ .duckdb .duckdb.wal
	docker-compose down -v
	@echo "[clean] ✓ Done."
