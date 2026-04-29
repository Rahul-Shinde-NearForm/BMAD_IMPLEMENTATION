# ============================================================================
# Docker Utilities Script
# Quick commands for Docker operations
# ============================================================================

#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_header() {
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Command implementations
cmd_build() {
    print_header "Building Docker Images"
    docker-compose build
    print_success "Docker images built successfully"
}

cmd_up() {
    print_header "Starting Services"
    docker-compose up -d
    print_success "Services started"
    echo ""
    cmd_status
}

cmd_down() {
    print_header "Stopping Services"
    docker-compose down
    print_success "Services stopped"
}

cmd_status() {
    print_header "Service Status"
    docker-compose ps
}

cmd_logs() {
    local service=${1:-""}
    if [ -z "$service" ]; then
        print_header "All Logs"
        docker-compose logs -f
    else
        print_header "Logs for: $service"
        docker-compose logs -f "$service"
    fi
}

cmd_shell() {
    local service=${1:-"backend"}
    print_header "Shell: $service"
    docker-compose exec "$service" bash || docker-compose exec "$service" sh
}

cmd_migrate() {
    print_header "Running Migrations"
    docker-compose exec backend python manage.py migrate
    print_success "Migrations completed"
}

cmd_createsuperuser() {
    print_header "Creating Superuser"
    docker-compose exec backend python manage.py createsuperuser
}

cmd_collectstatic() {
    print_header "Collecting Static Files"
    docker-compose exec backend python manage.py collectstatic --noinput
    print_success "Static files collected"
}

cmd_test() {
    print_header "Running Tests"
    docker-compose exec backend pytest ../tests "$@"
}

cmd_health() {
    print_header "Health Checks"
    
    echo ""
    print_info "Backend health:"
    docker-compose exec backend curl -s http://localhost:8000/health/ || print_error "Backend unhealthy"
    
    echo ""
    print_info "Frontend health:"
    docker-compose exec frontend curl -s http://localhost/health || print_error "Frontend unhealthy"
    
    echo ""
    print_info "Database status:"
    docker-compose exec database pg_isready -U opd_user || print_error "Database unhealthy"
}

cmd_clean() {
    print_header "Cleaning Up"
    print_warning "This will remove dangling images and containers"
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker system prune -a
        print_success "Cleanup completed"
    fi
}

cmd_backup() {
    print_header "Backing Up Database"
    local backup_file="backup_$(date +%Y%m%d_%H%M%S).sql"
    docker-compose exec -T database pg_dump -U opd_user opd_management > "$backup_file"
    print_success "Database backed up to: $backup_file"
}

cmd_restore() {
    if [ -z "$1" ]; then
        print_error "Usage: $0 restore <backup.sql>"
        return 1
    fi
    
    if [ ! -f "$1" ]; then
        print_error "Backup file not found: $1"
        return 1
    fi
    
    print_header "Restoring Database"
    print_warning "This will overwrite the current database"
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker-compose exec -T database psql -U opd_user opd_management < "$1"
        print_success "Database restored from: $1"
    fi
}

cmd_stats() {
    print_header "Container Resource Usage"
    docker stats opd-backend opd-frontend opd-db opd-redis --no-stream
}

cmd_help() {
    cat << EOF
${BLUE}OPD Management System - Docker Utilities${NC}

${YELLOW}Usage:${NC}
    docker-utils.sh [COMMAND] [OPTIONS]

${YELLOW}Commands:${NC}
    build               Build Docker images
    up                  Start all services
    down                Stop all services
    status              Show service status
    logs [service]      View logs (follow mode)
    shell [service]     Access container shell (default: backend)
    migrate             Run Django migrations
    createsuperuser     Create admin user
    collectstatic       Collect static files
    test [options]      Run tests
    health              Check service health
    clean               Remove unused images/containers
    backup              Backup database to SQL file
    restore <file>      Restore database from SQL file
    stats               Show container resource usage
    help                Show this help message

${YELLOW}Examples:${NC}
    ./docker-utils.sh build
    ./docker-utils.sh up
    ./docker-utils.sh logs backend
    ./docker-utils.sh shell frontend
    ./docker-utils.sh test tests/unit
    ./docker-utils.sh backup
    ./docker-utils.sh restore backup_20260429_120000.sql

${YELLOW}Configuration:${NC}
    Edit .env file for environment variables
    Edit docker-compose.yml for service configuration

EOF
}

# Main script
main() {
    local command=${1:-"help"}
    
    case "$command" in
        build)
            cmd_build
            ;;
        up)
            cmd_up
            ;;
        down)
            cmd_down
            ;;
        status|ps)
            cmd_status
            ;;
        logs)
            cmd_logs "$2"
            ;;
        shell)
            cmd_shell "$2"
            ;;
        migrate)
            cmd_migrate
            ;;
        createsuperuser)
            cmd_createsuperuser
            ;;
        collectstatic)
            cmd_collectstatic
            ;;
        test)
            shift
            cmd_test "$@"
            ;;
        health)
            cmd_health
            ;;
        clean)
            cmd_clean
            ;;
        backup)
            cmd_backup
            ;;
        restore)
            cmd_restore "$2"
            ;;
        stats)
            cmd_stats
            ;;
        help|--help|-h)
            cmd_help
            ;;
        *)
            print_error "Unknown command: $command"
            echo ""
            cmd_help
            exit 1
            ;;
    esac
}

main "$@"
