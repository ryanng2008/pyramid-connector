#!/bin/bash
# Kubernetes deployment script for File Connector

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
K8S_DIR="${PROJECT_DIR}/kubernetes"
NAMESPACE="file-connector"

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

# Check if kubectl is available
check_kubectl() {
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed. Please install kubectl first."
        exit 1
    fi
    
    if ! kubectl cluster-info &> /dev/null; then
        log_error "kubectl is not connected to a cluster. Please configure kubectl first."
        exit 1
    fi
    
    log_success "kubectl is available and connected"
}

# Build and push Docker image
build_and_push_image() {
    local registry=${1:-"localhost:5000"}
    local tag=${2:-"latest"}
    local image_name="$registry/file-connector:$tag"
    
    log_info "Building Docker image: $image_name"
    
    cd "$PROJECT_DIR"
    docker build -t "$image_name" .
    
    if [[ "$registry" != "localhost:5000" && "$registry" != "kind-registry:5000" ]]; then
        log_info "Pushing image to registry: $registry"
        docker push "$image_name"
    fi
    
    log_success "Image built: $image_name"
}

# Create namespace
create_namespace() {
    log_info "Creating namespace: $NAMESPACE"
    
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        log_warning "Namespace $NAMESPACE already exists"
    else
        kubectl apply -f "$K8S_DIR/namespace.yaml"
        log_success "Namespace created"
    fi
}

# Deploy secrets
deploy_secrets() {
    log_info "Deploying secrets..."
    
    # Check if secrets file exists
    if [[ ! -f "$K8S_DIR/secrets.yaml" ]]; then
        log_error "Secrets file not found. Please create kubernetes/secrets.yaml with your actual secrets."
        exit 1
    fi
    
    kubectl apply -f "$K8S_DIR/secrets.yaml"
    log_success "Secrets deployed"
}

# Deploy PostgreSQL
deploy_postgres() {
    log_info "Deploying PostgreSQL..."
    
    kubectl apply -f "$K8S_DIR/postgres.yaml"
    
    log_info "Waiting for PostgreSQL to be ready..."
    kubectl wait --for=condition=ready pod -l component=database -n "$NAMESPACE" --timeout=300s
    
    log_success "PostgreSQL deployed and ready"
}

# Deploy application
deploy_application() {
    local image_tag=${1:-"latest"}
    
    log_info "Deploying File Connector application..."
    
    # Update image tag in deployment
    if [[ "$image_tag" != "latest" ]]; then
        sed -i.bak "s|image: file-connector:latest|image: file-connector:$image_tag|g" "$K8S_DIR/deployment.yaml"
    fi
    
    kubectl apply -f "$K8S_DIR/deployment.yaml"
    
    log_info "Waiting for application to be ready..."
    kubectl wait --for=condition=ready pod -l component=application -n "$NAMESPACE" --timeout=300s
    
    # Restore original deployment file
    if [[ -f "$K8S_DIR/deployment.yaml.bak" ]]; then
        mv "$K8S_DIR/deployment.yaml.bak" "$K8S_DIR/deployment.yaml"
    fi
    
    log_success "Application deployed and ready"
}

# Deploy ingress
deploy_ingress() {
    log_info "Deploying ingress..."
    
    # Check if ingress controller is available
    if ! kubectl get ingressclass nginx &> /dev/null; then
        log_warning "NGINX ingress controller not found. Please install it first:"
        log_info "kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.1/deploy/static/provider/cloud/deploy.yaml"
    fi
    
    kubectl apply -f "$K8S_DIR/ingress.yaml"
    log_success "Ingress deployed"
}

# Get status
get_status() {
    log_info "File Connector Kubernetes Status:"
    echo
    
    echo "Namespace:"
    kubectl get namespace "$NAMESPACE" 2>/dev/null || echo "Namespace not found"
    echo
    
    echo "Pods:"
    kubectl get pods -n "$NAMESPACE" 2>/dev/null || echo "No pods found"
    echo
    
    echo "Services:"
    kubectl get services -n "$NAMESPACE" 2>/dev/null || echo "No services found"
    echo
    
    echo "Ingress:"
    kubectl get ingress -n "$NAMESPACE" 2>/dev/null || echo "No ingress found"
    echo
    
    echo "PVCs:"
    kubectl get pvc -n "$NAMESPACE" 2>/dev/null || echo "No PVCs found"
}

# Show logs
show_logs() {
    local component=${1:-"application"}
    log_info "Showing logs for component: $component"
    
    kubectl logs -l component="$component" -n "$NAMESPACE" -f --tail=100
}

# Health check
health_check() {
    log_info "Performing health check..."
    
    # Check if pods are running
    if kubectl get pods -n "$NAMESPACE" | grep -q "Running"; then
        log_success "Pods are running"
        
        # Port forward and check application health
        log_info "Testing application health..."
        kubectl port-forward service/file-connector-service 8080:80 -n "$NAMESPACE" &
        PF_PID=$!
        
        sleep 5
        
        if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
            log_success "Application health check passed"
        else
            log_warning "Application health check failed"
        fi
        
        kill $PF_PID 2>/dev/null || true
    else
        log_warning "No running pods found"
    fi
}

# Scale application
scale_application() {
    local replicas=${1:-2}
    log_info "Scaling application to $replicas replicas..."
    
    kubectl scale deployment file-connector -n "$NAMESPACE" --replicas="$replicas"
    kubectl wait --for=condition=ready pod -l component=application -n "$NAMESPACE" --timeout=300s
    
    log_success "Application scaled to $replicas replicas"
}

# Clean up
cleanup() {
    log_info "Cleaning up File Connector deployment..."
    
    # Delete all resources in namespace
    kubectl delete all --all -n "$NAMESPACE" 2>/dev/null || true
    kubectl delete pvc --all -n "$NAMESPACE" 2>/dev/null || true
    kubectl delete secrets --all -n "$NAMESPACE" 2>/dev/null || true
    kubectl delete configmaps --all -n "$NAMESPACE" 2>/dev/null || true
    kubectl delete namespace "$NAMESPACE" 2>/dev/null || true
    
    log_success "Cleanup completed"
}

# Full deployment
deploy_full() {
    local registry=${1:-"localhost:5000"}
    local tag=${2:-"latest"}
    
    log_info "Starting full deployment..."
    
    check_kubectl
    build_and_push_image "$registry" "$tag"
    create_namespace
    deploy_secrets
    deploy_postgres
    deploy_application "$tag"
    deploy_ingress
    
    log_success "Full deployment completed!"
    log_info "Application should be available at the configured ingress URL"
    
    get_status
}

# Main script
case "${1:-}" in
    "build")
        build_and_push_image "${2:-localhost:5000}" "${3:-latest}"
        ;;
    "deploy")
        deploy_full "${2:-localhost:5000}" "${3:-latest}"
        ;;
    "namespace")
        check_kubectl
        create_namespace
        ;;
    "secrets")
        check_kubectl
        deploy_secrets
        ;;
    "postgres")
        check_kubectl
        deploy_postgres
        ;;
    "app"|"application")
        check_kubectl
        deploy_application "${2:-latest}"
        ;;
    "ingress")
        check_kubectl
        deploy_ingress
        ;;
    "status")
        check_kubectl
        get_status
        ;;
    "logs")
        check_kubectl
        show_logs "${2:-application}"
        ;;
    "health")
        check_kubectl
        health_check
        ;;
    "scale")
        check_kubectl
        scale_application "${2:-2}"
        ;;
    "clean"|"cleanup")
        check_kubectl
        cleanup
        ;;
    "help"|"--help"|"-h")
        echo "File Connector Kubernetes Deployment Script"
        echo
        echo "Usage: $0 [COMMAND] [OPTIONS]"
        echo
        echo "Commands:"
        echo "  build [registry] [tag]     Build and push Docker image"
        echo "  deploy [registry] [tag]    Full deployment"
        echo "  namespace                  Create namespace"
        echo "  secrets                    Deploy secrets"
        echo "  postgres                   Deploy PostgreSQL"
        echo "  app, application [tag]     Deploy application"
        echo "  ingress                    Deploy ingress"
        echo "  status                     Show deployment status"
        echo "  logs [component]           Show logs (default: application)"
        echo "  health                     Check application health"
        echo "  scale [replicas]           Scale application (default: 2)"
        echo "  clean, cleanup             Clean up all resources"
        echo "  help                       Show this help message"
        echo
        echo "Examples:"
        echo "  $0 deploy                          # Deploy with defaults"
        echo "  $0 deploy my-registry.com latest   # Deploy with custom registry"
        echo "  $0 build localhost:5000 v1.0.0     # Build specific version"
        echo "  $0 logs postgres                   # Show PostgreSQL logs"
        echo "  $0 scale 5                         # Scale to 5 replicas"
        ;;
    *)
        log_error "Unknown command: ${1:-}"
        log_info "Use '$0 help' for usage information"
        exit 1
        ;;
esac