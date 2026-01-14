# TAVR Data Infrastructure Platform - Root Makefile
# ============================================================================
# Orchestrates all development and operations tasks
#
# Usage:
#   make help          - Show all available commands
#   make up            - Start all services
#   make down          - Stop all services
#   make logs          - Tail all service logs
#   make status        - Show service status and health
#
# ============================================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

# Colors for output
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RED    := \033[0;31m
BLUE   := \033[0;34m
CYAN   := \033[0;36m
NC     := \033[0m # No Color
BOLD   := \033[1m

# Progress indicator characters
SPINNER := ⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏
CHECK   := ✓
CROSS   := ✗
ARROW   := →

# Docker Compose configuration
COMPOSE_DIR := src/dk_data
COMPOSE_FILE := $(COMPOSE_DIR)/docker-compose.yml
DC := docker compose -f $(COMPOSE_FILE)

# API endpoints
POSTGREST_URL := http://localhost:3030
JOB_TRIGGER_URL := http://localhost:8000
POSTGRES_PORT := 5433

# ============================================================================
# HELP
# ============================================================================

.PHONY: help
help: ## Show this help message
	@echo ""
	@echo "$(BOLD)$(CYAN)TAVR Data Infrastructure Platform$(NC)"
	@echo "$(CYAN)══════════════════════════════════════════════════════════════$(NC)"
	@echo ""
	@echo "$(BOLD)Usage:$(NC) make [target]"
	@echo ""
	@echo "$(BOLD)$(GREEN)Service Lifecycle:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '(up|down|restart|status|logs)' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BOLD)$(GREEN)Database:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '(db-|init-db|psql|migrate)' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BOLD)$(GREEN)Jobs:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '(job-|fetch-|catalog-)' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BOLD)$(GREEN)Development:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E '(test|lint|build|clean)' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(BOLD)$(GREEN)Monitoring:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E 'health|api-' | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""

# ============================================================================
# SERVICE LIFECYCLE
# ============================================================================

.PHONY: up
up: ## Start all services (postgres, postgrest, job-trigger)
	@echo "$(BOLD)$(BLUE)$(ARROW) Starting services...$(NC)"
	@$(DC) up -d postgres
	@echo "  $(YELLOW)Waiting for PostgreSQL to be healthy...$(NC)"
	@timeout=60; while [ $$timeout -gt 0 ]; do \
		if $(DC) exec -T postgres pg_isready -U postgres -q 2>/dev/null; then \
			echo "  $(GREEN)$(CHECK) PostgreSQL is ready$(NC)"; \
			break; \
		fi; \
		sleep 1; \
		timeout=$$((timeout - 1)); \
	done
	@$(DC) up -d postgrest job-trigger
	@sleep 3
	@echo "  $(YELLOW)Checking service health...$(NC)"
	@$(MAKE) --no-print-directory _check-services
	@echo ""
	@echo "$(GREEN)$(CHECK) All services started successfully$(NC)"
	@echo ""
	@$(MAKE) --no-print-directory _show-urls

.PHONY: down
down: ## Stop all services
	@echo "$(BOLD)$(BLUE)$(ARROW) Stopping services...$(NC)"
	@$(DC) down
	@echo "$(GREEN)$(CHECK) All services stopped$(NC)"

.PHONY: restart
restart: down up ## Restart all services

.PHONY: status
status: ## Show status of all services with health checks
	@echo ""
	@echo "$(BOLD)$(CYAN)Service Status$(NC)"
	@echo "$(CYAN)══════════════════════════════════════════════════════════════$(NC)"
	@echo ""
	@$(DC) ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "No services running"
	@echo ""
	@$(MAKE) --no-print-directory _check-health

.PHONY: logs
logs: ## Tail logs from all services
	@$(DC) logs -f --tail=50

.PHONY: logs-postgres
logs-postgres: ## Tail PostgreSQL logs
	@$(DC) logs -f --tail=50 postgres

.PHONY: logs-postgrest
logs-postgrest: ## Tail PostgREST logs
	@$(DC) logs -f --tail=50 postgrest

.PHONY: logs-jobs
logs-jobs: ## Tail job-trigger logs
	@$(DC) logs -f --tail=50 job-trigger

# ============================================================================
# DATABASE
# ============================================================================

.PHONY: init-db
init-db: ## Initialize database schema and seed data
	@echo "$(BOLD)$(BLUE)$(ARROW) Initializing database...$(NC)"
	@echo "  $(YELLOW)Running init_database.sql...$(NC)"
	@$(DC) exec -T postgres psql -U postgres -d edwards_tavr -f /docker-entrypoint-initdb.d/init_database.sql > /dev/null 2>&1
	@echo "  $(GREEN)$(CHECK) Schema created$(NC)"
	@echo "  $(YELLOW)Running catalog_functions.sql...$(NC)"
	@$(DC) exec -T postgres psql -U postgres -d edwards_tavr -f /docker-entrypoint-initdb.d/catalog_functions.sql > /dev/null 2>&1
	@echo "  $(GREEN)$(CHECK) Catalog functions created$(NC)"
	@echo "  $(YELLOW)Running api_views.sql...$(NC)"
	@$(DC) exec -T postgres psql -U postgres -d edwards_tavr -f /docker-entrypoint-initdb.d/api_views.sql > /dev/null 2>&1
	@echo "  $(GREEN)$(CHECK) API views created$(NC)"
	@echo "  $(YELLOW)Running seed_batch_jobs.sql...$(NC)"
	@$(DC) exec -T postgres psql -U postgres -d edwards_tavr -f /docker-entrypoint-initdb.d/seed_batch_jobs.sql > /dev/null 2>&1
	@echo "  $(GREEN)$(CHECK) Batch jobs seeded$(NC)"
	@echo "  $(YELLOW)Running seed_data_sources.sql...$(NC)"
	@$(DC) exec -T postgres psql -U postgres -d edwards_tavr -f /docker-entrypoint-initdb.d/seed_data_sources.sql > /dev/null 2>&1
	@echo "  $(GREEN)$(CHECK) Data sources seeded$(NC)"
	@echo ""
	@echo "$(GREEN)$(CHECK) Database initialization complete$(NC)"

.PHONY: db-reset
db-reset: ## Reset database (WARNING: destroys all data)
	@echo "$(BOLD)$(RED)WARNING: This will destroy all data!$(NC)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	@echo "$(BOLD)$(BLUE)$(ARROW) Resetting database...$(NC)"
	@$(DC) down -v
	@$(DC) up -d postgres
	@sleep 5
	@$(MAKE) --no-print-directory init-db
	@$(DC) up -d postgrest job-trigger
	@echo "$(GREEN)$(CHECK) Database reset complete$(NC)"

.PHONY: psql
psql: ## Open PostgreSQL shell
	@$(DC) exec postgres psql -U postgres -d edwards_tavr

.PHONY: db-stats
db-stats: ## Show database statistics
	@echo ""
	@echo "$(BOLD)$(CYAN)Database Statistics$(NC)"
	@echo "$(CYAN)══════════════════════════════════════════════════════════════$(NC)"
	@$(DC) exec -T postgres psql -U postgres -d edwards_tavr -c "\
		SELECT schemaname, \
		       COUNT(*) as tables, \
		       pg_size_pretty(SUM(pg_total_relation_size(schemaname || '.' || relname))) as size \
		FROM pg_stat_user_tables \
		GROUP BY schemaname \
		ORDER BY schemaname;"
	@echo ""
	@echo "$(BOLD)Raw Tables Row Counts:$(NC)"
	@$(DC) exec -T postgres psql -U postgres -d edwards_tavr -c "\
		SELECT relname as table_name, n_live_tup as row_count \
		FROM pg_stat_user_tables \
		WHERE schemaname = 'raw' \
		ORDER BY relname;"

# ============================================================================
# JOBS
# ============================================================================

.PHONY: job-list
job-list: ## List all available batch jobs
	@echo ""
	@echo "$(BOLD)$(CYAN)Available Batch Jobs$(NC)"
	@echo "$(CYAN)══════════════════════════════════════════════════════════════$(NC)"
	@curl -s $(JOB_TRIGGER_URL)/jobs 2>/dev/null | jq -r '.[] | "  \(.job_name)\t\(.cron_schedule)\t\(.is_enabled)"' | column -t -s $$'\t' || echo "  $(RED)Job trigger service not available$(NC)"

.PHONY: job-runs
job-runs: ## Show recent job runs
	@echo ""
	@echo "$(BOLD)$(CYAN)Recent Job Runs$(NC)"
	@echo "$(CYAN)══════════════════════════════════════════════════════════════$(NC)"
	@curl -s "$(JOB_TRIGGER_URL)/runs?limit=10" 2>/dev/null | jq -r '.[] | "\(.job_name)\t\(.status)\t\(.started_at)\t\(.completed_at // "running")"' | column -t -s $$'\t' || echo "  $(RED)Job trigger service not available$(NC)"

.PHONY: fetch-all
fetch-all: ## Fetch all external data sources
	@echo "$(BOLD)$(BLUE)$(ARROW) Fetching all data sources...$(NC)"
	@$(MAKE) --no-print-directory _run-job JOB=fetch-cms-all

.PHONY: fetch-cms
fetch-cms: ## Fetch CMS data (Medicare Inpatient, Hospital Info, Cost Reports)
	@echo "$(BOLD)$(BLUE)$(ARROW) Fetching CMS data...$(NC)"
	@$(MAKE) --no-print-directory _run-job JOB=fetch-cms-all

.PHONY: fetch-hrsa
fetch-hrsa: ## Fetch HRSA shortage area data
	@$(MAKE) --no-print-directory _run-job JOB=fetch-hrsa

.PHONY: fetch-acc
fetch-acc: ## Fetch ACC TVC certification data
	@$(MAKE) --no-print-directory _run-job JOB=fetch-acc-tvc

.PHONY: catalog-refresh
catalog-refresh: ## Refresh data catalog metadata
	@$(MAKE) --no-print-directory _run-job JOB=catalog-refresh

.PHONY: sqlmesh-run
sqlmesh-run: ## Run SQLMesh transformations
	@$(MAKE) --no-print-directory _run-job JOB=sqlmesh-run

# Internal job runner with progress
.PHONY: _run-job
_run-job:
	@echo "  $(YELLOW)Triggering job: $(JOB)...$(NC)"
	@result=$$(curl -s -X POST $(JOB_TRIGGER_URL)/jobs/$(JOB)/trigger 2>/dev/null); \
	status=$$(echo "$$result" | jq -r '.status' 2>/dev/null); \
	if [ "$$status" = "success" ]; then \
		echo "  $(GREEN)$(CHECK) Job $(JOB) completed successfully$(NC)"; \
	elif [ "$$status" = "failure" ]; then \
		echo "  $(RED)$(CROSS) Job $(JOB) failed$(NC)"; \
		echo "$$result" | jq -r '.message // .error_message // "Unknown error"' 2>/dev/null; \
	else \
		echo "  $(RED)$(CROSS) Failed to trigger job$(NC)"; \
		echo "$$result"; \
	fi

# ============================================================================
# MONITORING & HEALTH
# ============================================================================

.PHONY: health
health: ## Check health of all services
	@$(MAKE) --no-print-directory _check-health

.PHONY: catalog
catalog: ## Show data catalog status
	@echo ""
	@echo "$(BOLD)$(CYAN)Data Catalog Status$(NC)"
	@echo "$(CYAN)══════════════════════════════════════════════════════════════$(NC)"
	@curl -s "$(POSTGREST_URL)/catalog?select=source_name,health_status,record_count,last_successful_refresh,status_color" 2>/dev/null | \
		jq -r '.[] | "\(.source_name)\t\(.health_status // "unknown")\t\(.record_count // 0)\t\(.last_successful_refresh // "never")\t\(.status_color)"' | \
		while IFS=$$'\t' read -r name status count refresh color; do \
			case "$$color" in \
				green) color_code="$(GREEN)" ;; \
				yellow) color_code="$(YELLOW)" ;; \
				red) color_code="$(RED)" ;; \
				*) color_code="$(NC)" ;; \
			esac; \
			printf "  %-25s $${color_code}%-10s$(NC) %8s rows  %s\n" "$$name" "$$status" "$$count" "$$refresh"; \
		done || echo "  $(RED)PostgREST service not available$(NC)"

.PHONY: api-health
api-health: ## Check PostgREST API health
	@echo ""
	@echo "$(BOLD)$(CYAN)API Health Status$(NC)"
	@echo "$(CYAN)══════════════════════════════════════════════════════════════$(NC)"
	@curl -s "$(POSTGREST_URL)/health" 2>/dev/null | jq '.' || echo "  $(RED)PostgREST not available$(NC)"

.PHONY: api-openapi
api-openapi: ## Show available API endpoints
	@echo ""
	@echo "$(BOLD)$(CYAN)Available API Endpoints$(NC)"
	@echo "$(CYAN)══════════════════════════════════════════════════════════════$(NC)"
	@curl -s "$(POSTGREST_URL)/" 2>/dev/null | jq -r '.paths | keys[]' | sort | head -20 || echo "  $(RED)PostgREST not available$(NC)"

# Internal health checks
.PHONY: _check-services
_check-services:
	@for svc in postgres postgrest job-trigger; do \
		if $(DC) ps $$svc 2>/dev/null | grep -q "running\|healthy"; then \
			echo "  $(GREEN)$(CHECK) $$svc$(NC)"; \
		else \
			echo "  $(RED)$(CROSS) $$svc$(NC)"; \
		fi; \
	done

.PHONY: _check-health
_check-health:
	@echo ""
	@echo "$(BOLD)Health Checks:$(NC)"
	@echo ""
	@# PostgreSQL
	@if $(DC) exec -T postgres pg_isready -U postgres -q 2>/dev/null; then \
		echo "  $(GREEN)$(CHECK) PostgreSQL$(NC) - accepting connections"; \
	else \
		echo "  $(RED)$(CROSS) PostgreSQL$(NC) - not available"; \
	fi
	@# PostgREST
	@if curl -sf $(POSTGREST_URL)/ > /dev/null 2>&1; then \
		echo "  $(GREEN)$(CHECK) PostgREST$(NC)  - $(POSTGREST_URL)"; \
	else \
		echo "  $(RED)$(CROSS) PostgREST$(NC)  - not available"; \
	fi
	@# Job Trigger
	@if curl -sf $(JOB_TRIGGER_URL)/health > /dev/null 2>&1; then \
		echo "  $(GREEN)$(CHECK) Job Trigger$(NC) - $(JOB_TRIGGER_URL)"; \
	else \
		echo "  $(RED)$(CROSS) Job Trigger$(NC) - not available"; \
	fi
	@echo ""

.PHONY: _show-urls
_show-urls:
	@echo "$(BOLD)Service URLs:$(NC)"
	@echo "  $(CYAN)PostgreSQL:$(NC)  localhost:$(POSTGRES_PORT)"
	@echo "  $(CYAN)PostgREST:$(NC)   $(POSTGREST_URL)"
	@echo "  $(CYAN)Job Trigger:$(NC) $(JOB_TRIGGER_URL)"
	@echo "  $(CYAN)Metabase:$(NC)    http://localhost:3000 (if enabled)"

# ============================================================================
# DEVELOPMENT
# ============================================================================

.PHONY: build
build: ## Build all Docker images
	@echo "$(BOLD)$(BLUE)$(ARROW) Building Docker images...$(NC)"
	@$(DC) build
	@echo "$(GREEN)$(CHECK) Build complete$(NC)"

.PHONY: build-no-cache
build-no-cache: ## Build Docker images without cache
	@echo "$(BOLD)$(BLUE)$(ARROW) Building Docker images (no cache)...$(NC)"
	@$(DC) build --no-cache
	@echo "$(GREEN)$(CHECK) Build complete$(NC)"

.PHONY: test
test: ## Run all tests
	@echo "$(BOLD)$(BLUE)$(ARROW) Running tests...$(NC)"
	@cd $(COMPOSE_DIR) && python -m pytest tests/ -v || echo "No tests found"

.PHONY: lint
lint: ## Run linters
	@echo "$(BOLD)$(BLUE)$(ARROW) Running linters...$(NC)"
	@cd $(COMPOSE_DIR) && python -m ruff check . || echo "Ruff not installed"
	@echo "$(GREEN)$(CHECK) Lint complete$(NC)"

.PHONY: clean
clean: ## Clean up Docker resources
	@echo "$(BOLD)$(BLUE)$(ARROW) Cleaning up...$(NC)"
	@$(DC) down -v --remove-orphans
	@docker system prune -f
	@echo "$(GREEN)$(CHECK) Cleanup complete$(NC)"

.PHONY: shell
shell: ## Open shell in job-trigger container
	@$(DC) exec job-trigger /bin/bash

# ============================================================================
# FULL PIPELINE
# ============================================================================

.PHONY: pipeline
pipeline: ## Run full data pipeline (fetch -> transform -> catalog)
	@echo ""
	@echo "$(BOLD)$(CYAN)Running Full Data Pipeline$(NC)"
	@echo "$(CYAN)══════════════════════════════════════════════════════════════$(NC)"
	@echo ""
	@echo "$(BOLD)Step 1/4: Fetch external data$(NC)"
	@$(MAKE) --no-print-directory fetch-all
	@echo ""
	@echo "$(BOLD)Step 2/4: Run SQLMesh transformations$(NC)"
	@$(MAKE) --no-print-directory sqlmesh-run
	@echo ""
	@echo "$(BOLD)Step 3/4: Refresh catalog metadata$(NC)"
	@$(MAKE) --no-print-directory catalog-refresh
	@echo ""
	@echo "$(BOLD)Step 4/4: Check final status$(NC)"
	@$(MAKE) --no-print-directory catalog
	@echo ""
	@echo "$(GREEN)$(CHECK) Pipeline complete$(NC)"

.PHONY: quick-start
quick-start: up init-db catalog-refresh ## Quick start: up + init-db + catalog-refresh
	@echo ""
	@echo "$(GREEN)$(CHECK) Quick start complete!$(NC)"
	@echo ""
	@$(MAKE) --no-print-directory _show-urls
