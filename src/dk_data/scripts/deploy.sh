#!/bin/bash
# Production Deployment Script for DK Data Platform
# Usage: ./scripts/deploy.sh [command]
#
# Commands:
#   setup     - Initial setup (SSL, env, directories)
#   start     - Start all services
#   stop      - Stop all services
#   restart   - Restart all services
#   logs      - View logs
#   status    - Check service status
#   backup    - Backup database
#   migrate   - Run database migrations

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.yml"
COMPOSE_PROD="$PROJECT_ROOT/docker-compose.prod.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check prerequisites
check_prereqs() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi

    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi

    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        log_error ".env file not found. Copy .env.production.example to .env and configure it."
        exit 1
    fi
}

# Initial setup
do_setup() {
    log_info "Running initial setup..."

    # Create required directories
    mkdir -p "$PROJECT_ROOT/nginx/ssl"
    mkdir -p "$PROJECT_ROOT/data"
    mkdir -p "$PROJECT_ROOT/logs"
    mkdir -p "$PROJECT_ROOT/backups"

    # Check for .env file
    if [ ! -f "$PROJECT_ROOT/.env" ]; then
        log_warn ".env file not found"
        log_info "Copying .env.production.example to .env"
        cp "$PROJECT_ROOT/.env.production.example" "$PROJECT_ROOT/.env"
        log_warn "Please edit .env with your production values before starting services"
        exit 1
    fi

    # Setup SSL if not exists
    if [ ! -f "$PROJECT_ROOT/nginx/ssl/fullchain.pem" ]; then
        log_info "Setting up SSL certificates..."
        source "$PROJECT_ROOT/.env"
        "$SCRIPT_DIR/setup_ssl.sh" "${SERVER_DOMAIN:-localhost}"
    fi

    log_info "Setup complete!"
}

# Start services
do_start() {
    check_prereqs
    log_info "Starting services..."

    # Build and start with production overrides
    cd "$PROJECT_ROOT"
    docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile frontend up -d --build

    log_info "Services started. Checking health..."
    sleep 10
    do_status
}

# Start with monitoring
do_start_full() {
    check_prereqs
    log_info "Starting all services including monitoring..."

    cd "$PROJECT_ROOT"
    docker compose -f docker-compose.yml -f docker-compose.prod.yml \
        --profile frontend --profile monitoring --profile dbadmin up -d --build

    log_info "All services started."
    sleep 10
    do_status
}

# Stop services
do_stop() {
    log_info "Stopping services..."
    cd "$PROJECT_ROOT"
    docker compose -f docker-compose.yml -f docker-compose.prod.yml \
        --profile frontend --profile monitoring --profile dbadmin down
    log_info "Services stopped."
}

# Restart services
do_restart() {
    do_stop
    sleep 5
    do_start
}

# View logs
do_logs() {
    cd "$PROJECT_ROOT"
    docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f "${@:2}"
}

# Check status
do_status() {
    log_info "Service Status:"
    cd "$PROJECT_ROOT"
    docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

    echo ""
    log_info "Health Checks:"

    # Check nginx
    if curl -sf http://localhost/health > /dev/null 2>&1; then
        echo -e "  Nginx:     ${GREEN}OK${NC}"
    else
        echo -e "  Nginx:     ${RED}FAIL${NC}"
    fi

    # Check API
    if curl -sf http://localhost/api/health > /dev/null 2>&1; then
        echo -e "  API:       ${GREEN}OK${NC}"
    else
        echo -e "  API:       ${YELLOW}PENDING${NC}"
    fi
}

# Backup database
do_backup() {
    check_prereqs
    source "$PROJECT_ROOT/.env"

    BACKUP_DIR="$PROJECT_ROOT/backups"
    BACKUP_FILE="$BACKUP_DIR/backup_$(date +%Y%m%d_%H%M%S).sql.gz"

    mkdir -p "$BACKUP_DIR"

    log_info "Creating database backup..."
    docker exec tavr-postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$BACKUP_FILE"

    log_info "Backup saved to: $BACKUP_FILE"

    # Keep only last 7 backups
    cd "$BACKUP_DIR"
    ls -t backup_*.sql.gz | tail -n +8 | xargs -r rm --
    log_info "Cleanup complete. Keeping last 7 backups."
}

# Run migrations
do_migrate() {
    check_prereqs
    log_info "Running database migrations..."

    cd "$PROJECT_ROOT"
    for migration in sql/migrations/*.sql; do
        log_info "Running: $migration"
        docker exec -i tavr-postgres psql -U postgres -d edwards_tavr < "$migration" || true
    done

    log_info "Migrations complete."
}

# Main
case "${1:-help}" in
    setup)
        do_setup
        ;;
    start)
        do_start
        ;;
    start-full)
        do_start_full
        ;;
    stop)
        do_stop
        ;;
    restart)
        do_restart
        ;;
    logs)
        do_logs "$@"
        ;;
    status)
        do_status
        ;;
    backup)
        do_backup
        ;;
    migrate)
        do_migrate
        ;;
    help|*)
        echo "DK Data Platform - Deployment Script"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  setup       Initial setup (SSL, env, directories)"
        echo "  start       Start core services"
        echo "  start-full  Start all services (including monitoring, dbadmin)"
        echo "  stop        Stop all services"
        echo "  restart     Restart all services"
        echo "  logs        View logs (optionally: logs <service>)"
        echo "  status      Check service status"
        echo "  backup      Backup database"
        echo "  migrate     Run database migrations"
        echo ""
        echo "URLs (after start):"
        echo "  https://\$SERVER_DOMAIN/           - Web UI"
        echo "  https://\$SERVER_DOMAIN/docs       - API Documentation"
        echo "  https://\$SERVER_DOMAIN/rest/      - PostgREST API"
        echo "  https://\$SERVER_DOMAIN/metabase/  - BI Dashboards"
        echo "  https://\$SERVER_DOMAIN/grafana/   - Monitoring (if enabled)"
        echo "  https://\$SERVER_DOMAIN/pgadmin/   - Database Admin (if enabled)"
        ;;
esac
