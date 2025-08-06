#!/bin/bash
# File Connector deployment script

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"
DOCKER_COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
DEV_COMPOSE_FILE="${PROJECT_DIR}/docker-compose.dev.yml"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed and running
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker is not running. Please start Docker first."
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    log_success "Docker and Docker Compose are available"
}

# Check if environment file exists
check_environment() {
    if [[ ! -f "$ENV_FILE" ]]; then
        log_warning "Environment file not found at $ENV_FILE"
        log_info "Creating example environment file..."
        
        cat > "$ENV_FILE" << EOF
# Database Configuration
DB_PASSWORD=connector123

# API Keys (set these for production)
AUTODESK_CLIENT_ID=your_autodesk_client_id
AUTODESK_CLIENT_SECRET=your_autodesk_client_secret

# Supabase Configuration (set these for production)
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key

# Optional: Redis Configuration
REDIS_PASSWORD=redis123

# Optional: Grafana Configuration
GRAFANA_PASSWORD=admin123

# Optional: Build arguments
BUILD_ENV=production
EOF
        
        log_warning "Please edit $ENV_FILE with your actual configuration values"
        log_info "You can continue with development mode using default values"
    else
        log_success "Environment file found"
    fi
}

# Create necessary directories
create_directories() {
    log_info "Creating necessary directories..."
    
    mkdir -p "$PROJECT_DIR/logs"
    mkdir -p "$PROJECT_DIR/data"
    mkdir -p "$PROJECT_DIR/credentials"
    mkdir -p "$PROJECT_DIR/test-results"
    
    log_success "Directories created"
}

# Build and start services
deploy_production() {
    log_info "Deploying File Connector in production mode..."
    
    cd "$PROJECT_DIR"
    
    # Pull latest images
    log_info "Pulling latest base images..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" pull postgres redis
    
    # Build application
    log_info "Building File Connector application..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" build connector
    
    # Start services
    log_info "Starting services..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" up -d
    
    # Wait for services to be healthy
    log_info "Waiting for services to be healthy..."
    timeout 120 docker-compose -f "$DOCKER_COMPOSE_FILE" exec postgres pg_isready -U connector -d connector_db
    
    log_success "File Connector deployed successfully in production mode"
    log_info "Services running:"
    docker-compose -f "$DOCKER_COMPOSE_FILE" ps
}

# Deploy development environment
deploy_development() {
    log_info "Deploying File Connector in development mode..."
    
    cd "$PROJECT_DIR"
    
    # Build development image
    log_info "Building development environment..."
    docker-compose -f "$DEV_COMPOSE_FILE" build
    
    # Start development services
    log_info "Starting development services..."
    docker-compose -f "$DEV_COMPOSE_FILE" up -d
    
    log_success "File Connector deployed successfully in development mode"
    log_info "Development services running:"
    docker-compose -f "$DEV_COMPOSE_FILE" ps
    
    log_info "Development URLs:"
    log_info "  - Application: http://localhost:8080"
    log_info "  - Database: localhost:5433"
    log_info "  - Redis: localhost:6380"
}

# Deploy with monitoring
deploy_monitoring() {
    log_info "Deploying File Connector with monitoring stack..."
    
    cd "$PROJECT_DIR"
    
    # Deploy production services first
    deploy_production
    
    # Start monitoring services
    log_info "Starting monitoring services..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" --profile monitoring up -d
    
    log_success "File Connector deployed with monitoring"
    log_info "Monitoring URLs:"
    log_info "  - Prometheus: http://localhost:9090"
    log_info "  - Grafana: http://localhost:3000 (admin/admin123)"
}

# Run tests
run_tests() {
    log_info "Running tests..."
    
    cd "$PROJECT_DIR"
    
    # Build test image
    docker-compose -f "$DEV_COMPOSE_FILE" build test-runner
    
    # Run tests
    docker-compose -f "$DEV_COMPOSE_FILE" --profile testing run --rm test-runner
    
    log_success "Tests completed"
}

# Stop services
stop_services() {
    log_info "Stopping File Connector services..."
    
    cd "$PROJECT_DIR"
    
    # Stop all services
    docker-compose -f "$DOCKER_COMPOSE_FILE" --profile monitoring down
    docker-compose -f "$DEV_COMPOSE_FILE" --profile testing down
    
    log_success "Services stopped"
}

# Clean up
cleanup() {
    log_info "Cleaning up File Connector deployment..."
    
    cd "$PROJECT_DIR"
    
    # Stop and remove all containers, networks
    docker-compose -f "$DOCKER_COMPOSE_FILE" --profile monitoring down --volumes --remove-orphans
    docker-compose -f "$DEV_COMPOSE_FILE" --profile testing down --volumes --remove-orphans
    
    # Remove unused images
    docker image prune -f
    
    log_success "Cleanup completed"
}

# Show logs
show_logs() {
    local service=${1:-connector}
    log_info "Showing logs for service: $service"
    
    cd "$PROJECT_DIR"
    docker-compose -f "$DOCKER_COMPOSE_FILE" logs -f "$service"
}

# Health check
health_check() {
    log_info "Performing health check..."
    
    cd "$PROJECT_DIR"
    
    # Check if services are running
    if docker-compose -f "$DOCKER_COMPOSE_FILE" ps | grep -q "Up"; then
        log_success "Services are running"
        
        # Check application health
        if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
            log_success "Application health check passed"
        else
            log_warning "Application health check failed"
        fi
    else
        log_warning "Services are not running"
    fi
}

# Main script
case "${1:-}" in
    "prod"|"production")
        check_docker
        check_environment
        create_directories
        deploy_production
        ;;
    "dev"|"development")
        check_docker
        check_environment
        create_directories
        deploy_development
        ;;
    "monitoring")
        check_docker
        check_environment
        create_directories
        deploy_monitoring
        ;;
    "test")
        check_docker
        run_tests
        ;;
    "stop")
        stop_services
        ;;
    "clean"|"cleanup")
        cleanup
        ;;
    "logs")
        show_logs "${2:-connector}"
        ;;
    "health")
        health_check
        ;;
    "help"|"--help"|"-h")
        echo "File Connector Deployment Script"
        echo
        echo "Usage: $0 [COMMAND]"
        echo
        echo "Commands:"
        echo "  prod, production    Deploy in production mode"
        echo "  dev, development    Deploy in development mode"
        echo "  monitoring          Deploy with monitoring stack"
        echo "  test                Run tests"
        echo "  stop                Stop all services"
        echo "  clean, cleanup      Stop and clean up all resources"
        echo "  logs [service]      Show logs for service (default: connector)"
        echo "  health              Check service health"
        echo "  help                Show this help message"
        echo
        echo "Examples:"
        echo "  $0 dev              # Start development environment"
        echo "  $0 prod             # Deploy to production"
        echo "  $0 monitoring       # Deploy with Prometheus & Grafana"
        echo "  $0 logs postgres    # Show PostgreSQL logs"
        ;;
    *)
        log_error "Unknown command: ${1:-}"
        log_info "Use '$0 help' for usage information"
        exit 1
        ;;
esac