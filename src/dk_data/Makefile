# TAVR Data Infrastructure Platform
# Makefile for development and operations
#
# PostgreSQL runs separately on localhost:5433 (container: system-postgres)
# This Makefile manages the application, API, and data operations

.PHONY: help dev up down logs status db-shell api-shell init-db load-fixtures \
        fetch fetch-all fetch-cms-inpatient fetch-cms-hospitals fetch-hrsa \
        fetch-acc-tvc fetch-cost-reports ingest-all \
        refresh-all sqlmesh-plan sqlmesh-run sqlmesh-info \
        test validate clean progress

# Load environment variables
ifneq (,$(wildcard .env.local))
    include .env.local
    export
endif

# Default values (from .env.local)
POSTGRES_HOST ?= localhost
POSTGRES_PORT ?= 5433
POSTGRES_USER ?= postgres
POSTGRES_PASSWORD ?= postgres
POSTGRES_DB ?= edwards_tavr
POSTGREST_PORT ?= 3030
POSTGREST_PASSWORD ?= postgrest_secret_change_me

# Docker container names
POSTGRES_CONTAINER ?= system-postgres
POSTGREST_CONTAINER ?= postgrest

# Paths
VENV := ../.venv
DATA_DIR := ./data/raw
LOGS_DIR := ./logs

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
CYAN := \033[0;36m
NC := \033[0m

#==============================================================================
# HELP
#==============================================================================

help: ## Show this help message
	@echo "$(CYAN)TAVR Data Infrastructure Platform$(NC)"
	@echo "================================="
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(GREEN)%-22s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST) | sort

#==============================================================================
# DEVELOPMENT ENVIRONMENT
#==============================================================================

dev: api-start ## Start development environment (PostgREST API)
	@echo "$(GREEN)Development environment ready$(NC)"
	@echo "  PostgreSQL: $(POSTGRES_HOST):$(POSTGRES_PORT) (external)"
	@echo "  PostgREST:  http://localhost:$(POSTGREST_PORT)"
	@echo ""
	@echo "Try: curl 'http://localhost:$(POSTGREST_PORT)/targets?limit=3'"

up: api-start ## Start PostgREST API

down: api-stop ## Stop PostgREST API
	@echo "$(GREEN)Services stopped$(NC)"

#==============================================================================
# POSTGREST API
#==============================================================================

api-start: ## Start PostgREST API container
	@if docker ps -q -f name=$(POSTGREST_CONTAINER) | grep -q .; then \
		echo "$(YELLOW)PostgREST already running$(NC)"; \
	else \
		echo "$(YELLOW)Starting PostgREST...$(NC)"; \
		docker rm $(POSTGREST_CONTAINER) 2>/dev/null || true; \
		docker run --name $(POSTGREST_CONTAINER) --rm -d \
			-p $(POSTGREST_PORT):$(POSTGREST_PORT) \
			-e PGRST_DB_URI="postgres://authenticator:$(POSTGREST_PASSWORD)@host.docker.internal:$(POSTGRES_PORT)/$(POSTGRES_DB)" \
			-e PGRST_DB_SCHEMAS="api" \
			-e PGRST_DB_ANON_ROLE="web_anon" \
			-e PGRST_SERVER_PORT=$(POSTGREST_PORT) \
			-e PGRST_LOG_LEVEL="info" \
			postgrest/postgrest; \
		sleep 2; \
	fi
	@echo "$(GREEN)PostgREST running on http://localhost:$(POSTGREST_PORT)$(NC)"

api-stop: ## Stop PostgREST API container
	@docker stop $(POSTGREST_CONTAINER) 2>/dev/null || true
	@echo "$(YELLOW)PostgREST stopped$(NC)"

api-test: ## Test API endpoints
	@echo "$(GREEN)API Endpoints$(NC)"
	@echo "============="
	@echo "Targets:   curl 'http://localhost:$(POSTGREST_PORT)/targets'"
	@echo "Hospitals: curl 'http://localhost:$(POSTGREST_PORT)/hospitals'"
	@echo "Scores:    curl 'http://localhost:$(POSTGREST_PORT)/scoring_details'"
	@echo "Catalog:   curl 'http://localhost:$(POSTGREST_PORT)/data_catalog'"
	@echo ""
	@echo "$(YELLOW)Sample request:$(NC)"
	@curl -s 'http://localhost:$(POSTGREST_PORT)/targets?limit=3' | python3 -m json.tool 2>/dev/null || echo "$(RED)API not running$(NC)"

#==============================================================================
# DATABASE OPERATIONS
#==============================================================================

db-shell: ## Open PostgreSQL shell
	@docker exec -it $(POSTGRES_CONTAINER) psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

db-status: ## Check database status and record counts
	@echo "$(GREEN)Database Status$(NC)"
	@echo "==============="
	@docker exec $(POSTGRES_CONTAINER) psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -c "\
		SELECT 'raw.cms_hospital_info' as table_name, COUNT(*) as records FROM raw.cms_hospital_info \
		UNION ALL SELECT 'raw.cms_medicare_inpatient', COUNT(*) FROM raw.cms_medicare_inpatient \
		UNION ALL SELECT 'staging.hospitals', COUNT(*) FROM staging.hospitals \
		UNION ALL SELECT 'staging.tavr_volumes', COUNT(*) FROM staging.tavr_volumes \
		UNION ALL SELECT 'mart.dim_hospital', COUNT(*) FROM mart.dim_hospital \
		UNION ALL SELECT 'scoring.target_scores', COUNT(*) FROM scoring.target_scores \
		ORDER BY table_name;" 2>/dev/null || echo "$(RED)Database not accessible$(NC)"

init-db: ## Initialize database schema
	@echo "$(YELLOW)Initializing database schema...$(NC)"
	@docker exec $(POSTGRES_CONTAINER) psql -U $(POSTGRES_USER) -c "CREATE DATABASE $(POSTGRES_DB);" 2>/dev/null || true
	@docker exec -i $(POSTGRES_CONTAINER) psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) < sql/init_database.sql
	@docker exec -i $(POSTGRES_CONTAINER) psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) < sql/seed_data_sources.sql
	@docker exec -i $(POSTGRES_CONTAINER) psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) < sql/score_history_trigger.sql 2>/dev/null || true
	@echo "$(GREEN)Database initialized$(NC)"

load-fixtures: ## Load test fixture data
	@echo "$(YELLOW)Loading test fixtures...$(NC)"
	@. $(VENV)/bin/activate && cd .. && \
		python -c "from edwards.ingestion.sources.cms_hospital_info import load_cms_hospital_info; print(load_cms_hospital_info('tests/fixtures/sample_hospitals.csv'))"
	@. $(VENV)/bin/activate && cd .. && \
		python -c "from edwards.ingestion.sources.cms_inpatient import load_cms_inpatient_file; print(load_cms_inpatient_file('tests/fixtures/sample_cms_inpatient.csv', 2024))"
	@echo "$(GREEN)Fixtures loaded$(NC)"

#==============================================================================
# DATA FETCHING (External APIs)
#==============================================================================

fetch: ## Show fetch commands
	@echo "$(CYAN)Data Fetch Commands$(NC)"
	@echo "==================="
	@echo ""
	@echo "Fetch individual sources:"
	@echo "  make fetch-cms-hospitals   - CMS Hospital General Info"
	@echo "  make fetch-cms-inpatient   - CMS Medicare Inpatient (TAVR DRG 266/267)"
	@echo "  make fetch-cost-reports    - CMS Hospital Cost Reports"
	@echo "  make fetch-acc-tvc         - ACC TVC Certification"
	@echo "  make fetch-hrsa            - HRSA Shortage Areas"
	@echo ""
	@echo "  make fetch-all             - Fetch ALL sources"
	@echo ""
	@echo "Options:"
	@echo "  YEAR=2023 make fetch-cms-inpatient  - Specific fiscal year"

fetch-all: _ensure-dirs ## Fetch data from ALL external sources
	@echo "$(YELLOW)Fetching ALL data sources...$(NC)"
	@. $(VENV)/bin/activate && python -m ingestion.fetch_data --source all --data-dir $(DATA_DIR) 2>&1 | tee -a $(LOGS_DIR)/fetch.log
	@echo "$(GREEN)Fetch complete - see $(LOGS_DIR)/fetch.log$(NC)"

fetch-cms-hospitals: _ensure-dirs ## Fetch CMS Hospital General Information
	@echo "$(YELLOW)Fetching CMS Hospital Info...$(NC)"
	@. $(VENV)/bin/activate && python -m ingestion.fetch_data --source cms_hospital_info --data-dir $(DATA_DIR) 2>&1 | tee -a $(LOGS_DIR)/fetch.log

fetch-cms-inpatient: _ensure-dirs ## Fetch CMS Medicare Inpatient data (TAVR volumes)
	@echo "$(YELLOW)Fetching CMS Medicare Inpatient...$(NC)"
	@if [ -n "$(YEAR)" ]; then \
		. $(VENV)/bin/activate && python -m ingestion.fetch_data --source cms_inpatient --year $(YEAR) --data-dir $(DATA_DIR) 2>&1 | tee -a $(LOGS_DIR)/fetch.log; \
	else \
		. $(VENV)/bin/activate && python -m ingestion.fetch_data --source cms_inpatient --data-dir $(DATA_DIR) 2>&1 | tee -a $(LOGS_DIR)/fetch.log; \
	fi

fetch-cost-reports: _ensure-dirs ## Fetch CMS Hospital Cost Reports
	@echo "$(YELLOW)Fetching CMS Cost Reports...$(NC)"
	@if [ -n "$(YEAR)" ]; then \
		. $(VENV)/bin/activate && python -m ingestion.fetch_data --source cms_cost_reports --year $(YEAR) --data-dir $(DATA_DIR) 2>&1 | tee -a $(LOGS_DIR)/fetch.log; \
	else \
		. $(VENV)/bin/activate && python -m ingestion.fetch_data --source cms_cost_reports --data-dir $(DATA_DIR) 2>&1 | tee -a $(LOGS_DIR)/fetch.log; \
	fi

fetch-acc-tvc: _ensure-dirs ## Fetch ACC TVC Certification data
	@echo "$(YELLOW)Fetching ACC TVC Certification...$(NC)"
	@. $(VENV)/bin/activate && python -m ingestion.fetch_data --source acc_tvc --data-dir $(DATA_DIR) 2>&1 | tee -a $(LOGS_DIR)/fetch.log

fetch-hrsa: _ensure-dirs ## Fetch HRSA Shortage Area data
	@echo "$(YELLOW)Fetching HRSA Shortage Areas...$(NC)"
	@. $(VENV)/bin/activate && python -m ingestion.fetch_data --source hrsa --data-dir $(DATA_DIR) 2>&1 | tee -a $(LOGS_DIR)/fetch.log

#==============================================================================
# DATA INGESTION (Load to Database)
#==============================================================================

ingest-all: ## Ingest all fetched data into database
	@echo "$(YELLOW)Ingesting fetched data into database...$(NC)"
	@echo "$(RED)TODO: Implement ingest-all command$(NC)"
	@echo "For now, use individual ingestors or load-fixtures"

ingest-cms-hospitals: ## Ingest CMS Hospital Info (requires FILE=path)
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)Usage: make ingest-cms-hospitals FILE=/path/to/file.csv$(NC)"; \
		exit 1; \
	fi
	@. $(VENV)/bin/activate && python -m ingestion.sources.cms_hospital_info $(FILE)

ingest-cms-inpatient: ## Ingest CMS Inpatient data (requires FILE=path YEAR=nnnn)
	@if [ -z "$(FILE)" ] || [ -z "$(YEAR)" ]; then \
		echo "$(RED)Usage: make ingest-cms-inpatient FILE=/path/to/file.csv YEAR=2024$(NC)"; \
		exit 1; \
	fi
	@. $(VENV)/bin/activate && python -m ingestion.sources.cms_inpatient $(FILE) --fiscal-year $(YEAR)

#==============================================================================
# SQLMESH TRANSFORMATIONS
#==============================================================================

sqlmesh-info: ## Show SQLMesh project info
	@. $(VENV)/bin/activate && cd sqlmesh && sqlmesh info

sqlmesh-plan: ## Preview SQLMesh changes (dry-run)
	@echo "$(YELLOW)Planning SQLMesh changes...$(NC)"
	@. $(VENV)/bin/activate && cd sqlmesh && sqlmesh plan --no-prompts

sqlmesh-run: ## Apply SQLMesh transformations
	@echo "$(YELLOW)Running SQLMesh transformations...$(NC)"
	@mkdir -p $(LOGS_DIR)
	@. $(VENV)/bin/activate && cd sqlmesh && echo "y" | sqlmesh plan --auto-apply 2>&1 | tee -a ../$(LOGS_DIR)/sqlmesh.log
	@echo "$(GREEN)Transformations complete$(NC)"

sqlmesh-diff: ## Show diff of pending model changes
	@. $(VENV)/bin/activate && cd sqlmesh && sqlmesh diff

#==============================================================================
# FULL PIPELINE
#==============================================================================

refresh-all: fetch-all sqlmesh-run ## Full refresh: fetch all data + run transformations
	@echo "$(GREEN)Full data refresh complete$(NC)"

pipeline: fetch-all ingest-all sqlmesh-run ## Run complete data pipeline
	@echo "$(GREEN)Pipeline complete$(NC)"

#==============================================================================
# MONITORING & LOGGING
#==============================================================================

logs: ## Show recent logs
	@echo "$(GREEN)=== PostgREST Logs ===$(NC)"
	@docker logs --tail 20 $(POSTGREST_CONTAINER) 2>/dev/null || echo "PostgREST not running"
	@echo ""
	@echo "$(GREEN)=== Fetch Logs ===$(NC)"
	@tail -30 $(LOGS_DIR)/fetch.log 2>/dev/null || echo "No fetch logs yet"
	@echo ""
	@echo "$(GREEN)=== SQLMesh Logs ===$(NC)"
	@tail -20 $(LOGS_DIR)/sqlmesh.log 2>/dev/null || echo "No SQLMesh logs yet"

logs-api: ## Follow PostgREST logs
	@docker logs -f $(POSTGREST_CONTAINER)

logs-fetch: ## Show data fetch logs
	@tail -f $(LOGS_DIR)/fetch.log 2>/dev/null || echo "No fetch logs yet"

logs-sqlmesh: ## Show SQLMesh transformation logs
	@tail -f $(LOGS_DIR)/sqlmesh.log 2>/dev/null || echo "No SQLMesh logs yet"

status: ## Show system status
	@echo "$(CYAN)TAVR Data Infrastructure Status$(NC)"
	@echo "================================"
	@echo ""
	@echo "$(YELLOW)Services:$(NC)"
	@printf "  PostgreSQL:  "; docker exec $(POSTGRES_CONTAINER) pg_isready -q && echo "$(GREEN)running$(NC) ($(POSTGRES_HOST):$(POSTGRES_PORT))" || echo "$(RED)not accessible$(NC)"
	@printf "  PostgREST:   "; docker ps -q -f name=$(POSTGREST_CONTAINER) | grep -q . && echo "$(GREEN)running$(NC) (http://localhost:$(POSTGREST_PORT))" || echo "$(RED)stopped$(NC)"
	@echo ""
	@echo "$(YELLOW)Endpoints:$(NC)"
	@echo "  Database: $(POSTGRES_HOST):$(POSTGRES_PORT)/$(POSTGRES_DB)"
	@echo "  API:      http://localhost:$(POSTGREST_PORT)"
	@echo ""
	@$(MAKE) -s db-status 2>/dev/null || true

progress: ## Show data pipeline progress
	@echo "$(CYAN)Data Pipeline Progress$(NC)"
	@echo "======================"
	@echo ""
	@echo "$(YELLOW)Raw Data (fetched):$(NC)"
	@ls -la $(DATA_DIR)/*.csv $(DATA_DIR)/*.json 2>/dev/null | awk '{print "  " $$NF ": " $$5 " bytes"}' || echo "  No files fetched yet"
	@echo ""
	@echo "$(YELLOW)Database Records:$(NC)"
	@docker exec $(POSTGRES_CONTAINER) psql -U $(POSTGRES_USER) -d $(POSTGRES_DB) -t -c "\
		SELECT '  raw.cms_hospital_info: ' || COUNT(*) FROM raw.cms_hospital_info \
		UNION ALL SELECT '  raw.cms_medicare_inpatient: ' || COUNT(*) FROM raw.cms_medicare_inpatient \
		UNION ALL SELECT '  staging.hospitals: ' || COUNT(*) FROM staging.hospitals \
		UNION ALL SELECT '  staging.tavr_volumes: ' || COUNT(*) FROM staging.tavr_volumes \
		UNION ALL SELECT '  mart.dim_hospital: ' || COUNT(*) FROM mart.dim_hospital \
		UNION ALL SELECT '  scoring.target_scores: ' || COUNT(*) FROM scoring.target_scores;" 2>/dev/null || echo "  Database not accessible"
	@echo ""
	@echo "$(YELLOW)Last Operations:$(NC)"
	@echo "  Fetch: $$(tail -1 $(LOGS_DIR)/fetch.log 2>/dev/null || echo 'No fetch logs')"
	@echo "  SQLMesh: $$(tail -1 $(LOGS_DIR)/sqlmesh.log 2>/dev/null || echo 'No SQLMesh logs')"

#==============================================================================
# TESTING & VALIDATION
#==============================================================================

test: ## Run test suite
	@echo "$(YELLOW)Running tests...$(NC)"
	@. $(VENV)/bin/activate && pytest ../tests/ -v

validate: ## Validate API responses
	@echo "$(YELLOW)Validating API...$(NC)"
	@. $(VENV)/bin/activate && python scripts/validate_api.py
	@echo "$(GREEN)Validation complete$(NC)"

check-freshness: ## Check data freshness
	@echo "$(YELLOW)Checking data freshness...$(NC)"
	@. $(VENV)/bin/activate && python scripts/check_freshness.py 2>/dev/null || echo "Freshness check not configured"

#==============================================================================
# CLEANUP
#==============================================================================

clean: ## Clean up logs and cache files
	@echo "$(YELLOW)Cleaning up...$(NC)"
	@rm -rf $(LOGS_DIR)/*.log
	@rm -rf __pycache__ */__pycache__ */*/__pycache__
	@rm -rf .pytest_cache ../.pytest_cache
	@echo "$(GREEN)Cleanup complete$(NC)"

clean-data: ## Clean downloaded data files (keeps database)
	@echo "$(RED)WARNING: This will delete all downloaded data files!$(NC)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	@rm -rf $(DATA_DIR)/*
	@echo "$(GREEN)Data files cleaned$(NC)"

clean-all: clean api-stop ## Full cleanup (logs + stop services)
	@echo "$(GREEN)Full cleanup complete$(NC)"

reset-db: ## Reset database (WARNING: destroys all data)
	@echo "$(RED)WARNING: This will destroy all data in the database!$(NC)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	@docker exec $(POSTGRES_CONTAINER) psql -U $(POSTGRES_USER) -c "DROP DATABASE IF EXISTS $(POSTGRES_DB);"
	@$(MAKE) init-db
	@echo "$(GREEN)Database reset complete$(NC)"

#==============================================================================
# INTERNAL TARGETS
#==============================================================================

_ensure-dirs:
	@mkdir -p $(DATA_DIR) $(LOGS_DIR)
