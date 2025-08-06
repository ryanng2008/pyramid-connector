# Deployment Guide

This comprehensive guide covers all aspects of deploying the File Connector in various environments, from local development to production Kubernetes clusters.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Docker Deployment](#docker-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Cloud Provider Setup](#cloud-provider-setup)
- [Configuration Management](#configuration-management)
- [Monitoring and Observability](#monitoring-and-observability)
- [Security Considerations](#security-considerations)
- [Troubleshooting](#troubleshooting)

## Overview

The File Connector is designed as a cloud-native application with multiple deployment options:

- **Local Development**: Direct Python execution with SQLite
- **Docker**: Containerized deployment with PostgreSQL and Redis
- **Kubernetes**: Production-ready orchestration with scaling and monitoring
- **Cloud Platforms**: AWS EKS, Google GKE, Azure AKS support

### Architecture Components

```
┌─────────────────────────────────────────────────────────────┐
│                    Load Balancer                            │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                File Connector Pods                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │ Connector 1 │ │ Connector 2 │ │ Connector N │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                  Data Layer                                │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │ PostgreSQL  │ │    Redis    │ │ Monitoring  │          │
│  │ (Primary)   │ │ (Caching)   │ │  Stack      │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

### Software Requirements

- **Python 3.10+** (for local development)
- **Docker 20.0+** and **Docker Compose 2.0+**
- **Kubernetes 1.24+** (for Kubernetes deployment)
- **kubectl** configured for your cluster

### Hardware Requirements

**Minimum (Development)**:
- 2 CPU cores
- 4 GB RAM
- 10 GB disk space

**Recommended (Production)**:
- 4 CPU cores
- 8 GB RAM
- 50 GB disk space
- SSD storage for database

### Network Requirements

- **Outbound HTTPS (443)**: API access to Google Drive, Autodesk, etc.
- **Inbound HTTP (8080)**: Health checks and metrics
- **Database Access**: PostgreSQL (5432), Redis (6379)

## Local Development

### Quick Start

```bash
# Clone repository
git clone https://github.com/your-org/file-connector.git
cd file-connector

# Set up Python environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp env.example .env
# Edit .env with your configurations

# Run locally
python -m src.connector.main
```

### Development Configuration

Create `.env` file:

```bash
# Application Configuration
CONNECTOR_ENVIRONMENT=development
CONNECTOR_LOG_LEVEL=DEBUG
CONNECTOR_MAX_CONCURRENT_SYNCS=5

# Database (SQLite for development)
CONNECTOR_DATABASE_URL=sqlite:///./data/connector.db

# API Credentials
CONNECTOR_GOOGLE_DRIVE_CREDENTIALS_PATH=./credentials/google-service-account.json
CONNECTOR_AUTODESK_CLIENT_ID=your_autodesk_client_id
CONNECTOR_AUTODESK_CLIENT_SECRET=your_autodesk_client_secret
CONNECTOR_SUPABASE_URL=your_supabase_url
CONNECTOR_SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key

# Optional: Redis for development
CONNECTOR_REDIS_URL=redis://localhost:6379
```

### Development Services

Start supporting services with Docker:

```bash
# Start PostgreSQL and Redis for development
docker-compose -f docker-compose.dev.yml up -d postgres-dev redis-dev

# Update .env for PostgreSQL
CONNECTOR_DATABASE_URL=postgresql://connector:connector123@localhost:5433/connector_dev

# Run connector
python -m src.connector.main
```

## Docker Deployment

### Production Deployment

```bash
# Clone and configure
git clone https://github.com/your-org/file-connector.git
cd file-connector

# Create environment file
cp env.example .env
# Edit .env with production values

# Create credentials directory
mkdir -p credentials
# Copy your Google service account JSON file to credentials/

# Deploy with Docker Compose
./scripts/deploy.sh prod
```

### Docker Compose Configuration

The production deployment includes:

- **File Connector**: Main application with health checks
- **PostgreSQL**: Primary database with persistent storage
- **Redis**: Caching and session storage
- **Prometheus**: Metrics collection (optional)
- **Grafana**: Monitoring dashboards (optional)

#### Service Configuration

```yaml
# docker-compose.yml
version: '3.8'

services:
  connector:
    build:
      context: .
      target: production
    environment:
      - CONNECTOR_ENVIRONMENT=production
      - CONNECTOR_DATABASE_URL=postgresql://connector:${DB_PASSWORD}@postgres:5432/connector_db
    volumes:
      - ./credentials:/app/credentials:ro
      - ./config:/app/config:ro
    ports:
      - "8080:8080"
    depends_on:
      - postgres
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Docker Commands

```bash
# Build production image
docker build -t file-connector:latest .

# Run with environment variables
docker run -d \
  --name file-connector \
  -p 8080:8080 \
  --env-file .env \
  -v $(pwd)/credentials:/app/credentials:ro \
  file-connector:latest

# View logs
docker logs -f file-connector

# Health check
curl http://localhost:8080/health
```

### Scaling with Docker Compose

```yaml
# Scale connector instances
version: '3.8'

services:
  connector:
    deploy:
      replicas: 3
    # ... other configuration

  # Load balancer
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - connector
```

## Kubernetes Deployment

### Quick Start

```bash
# Deploy to Kubernetes
./scripts/k8s-deploy.sh deploy

# Check deployment status
kubectl get pods -n file-connector

# View logs
kubectl logs -f deployment/file-connector -n file-connector

# Port forward for testing
kubectl port-forward service/file-connector-service 8080:80 -n file-connector
```

### Detailed Kubernetes Setup

#### 1. Namespace and Secrets

```bash
# Create namespace
kubectl apply -f kubernetes/namespace.yaml

# Create secrets (update with your values first)
# Edit kubernetes/secrets.yaml with base64-encoded values
kubectl apply -f kubernetes/secrets.yaml
```

#### 2. Database Setup

```bash
# Deploy PostgreSQL
kubectl apply -f kubernetes/postgres.yaml

# Wait for PostgreSQL to be ready
kubectl wait --for=condition=ready pod -l component=database -n file-connector --timeout=300s
```

#### 3. Application Deployment

```bash
# Deploy application
kubectl apply -f kubernetes/deployment.yaml

# Wait for pods to be ready
kubectl wait --for=condition=ready pod -l component=application -n file-connector --timeout=300s
```

#### 4. Ingress Configuration

```bash
# Install NGINX Ingress Controller (if not already installed)
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.8.1/deploy/static/provider/cloud/deploy.yaml

# Deploy ingress
kubectl apply -f kubernetes/ingress.yaml
```

### Kubernetes Configuration Files

#### Deployment Manifest

```yaml
# kubernetes/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: file-connector
  namespace: file-connector
spec:
  replicas: 2
  selector:
    matchLabels:
      app: file-connector
  template:
    metadata:
      labels:
        app: file-connector
    spec:
      containers:
      - name: file-connector
        image: file-connector:latest
        ports:
        - containerPort: 8080
        env:
        - name: CONNECTOR_ENVIRONMENT
          value: "production"
        - name: CONNECTOR_DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: file-connector-secrets
              key: database-url
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "512Mi"
            cpu: "500m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 60
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
```

#### Horizontal Pod Autoscaler

```yaml
# kubernetes/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: file-connector-hpa
  namespace: file-connector
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: file-connector
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### Advanced Kubernetes Features

#### Rolling Updates

```bash
# Update deployment with new image
kubectl set image deployment/file-connector file-connector=file-connector:v2.0.0 -n file-connector

# Monitor rollout
kubectl rollout status deployment/file-connector -n file-connector

# Rollback if needed
kubectl rollout undo deployment/file-connector -n file-connector
```

#### Resource Management

```yaml
# Resource quotas for namespace
apiVersion: v1
kind: ResourceQuota
metadata:
  name: file-connector-quota
  namespace: file-connector
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "8"
    limits.memory: 16Gi
    persistentvolumeclaims: "4"
```

## Cloud Provider Setup

### Amazon Web Services (EKS)

#### Prerequisites
```bash
# Install AWS CLI and eksctl
aws configure
eksctl version
kubectl version
```

#### Cluster Setup
```bash
# Create EKS cluster
eksctl create cluster \
  --name file-connector-cluster \
  --version 1.24 \
  --region us-west-2 \
  --nodegroup-name standard-workers \
  --node-type m5.large \
  --nodes 3 \
  --nodes-min 1 \
  --nodes-max 4 \
  --managed

# Configure kubectl
aws eks update-kubeconfig --region us-west-2 --name file-connector-cluster

# Deploy File Connector
./scripts/k8s-deploy.sh deploy
```

#### AWS-Specific Configuration
```yaml
# Use AWS Load Balancer Controller
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: file-connector-ingress
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
spec:
  rules:
  - host: file-connector.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: file-connector-service
            port:
              number: 80
```

### Google Cloud Platform (GKE)

#### Prerequisites
```bash
# Install gcloud CLI
gcloud auth login
gcloud config set project your-project-id
```

#### Cluster Setup
```bash
# Create GKE cluster
gcloud container clusters create file-connector-cluster \
  --zone us-central1-a \
  --machine-type e2-medium \
  --num-nodes 3 \
  --enable-autoscaling \
  --min-nodes 1 \
  --max-nodes 5

# Get credentials
gcloud container clusters get-credentials file-connector-cluster --zone us-central1-a

# Deploy File Connector
./scripts/k8s-deploy.sh deploy
```

### Microsoft Azure (AKS)

#### Prerequisites
```bash
# Install Azure CLI
az login
az account set --subscription your-subscription-id
```

#### Cluster Setup
```bash
# Create resource group
az group create --name file-connector-rg --location eastus

# Create AKS cluster
az aks create \
  --resource-group file-connector-rg \
  --name file-connector-cluster \
  --node-count 3 \
  --enable-addons monitoring \
  --generate-ssh-keys

# Get credentials
az aks get-credentials --resource-group file-connector-rg --name file-connector-cluster

# Deploy File Connector
./scripts/k8s-deploy.sh deploy
```

## Configuration Management

### Environment Variables

Core configuration via environment variables:

```bash
# Application Configuration
CONNECTOR_ENVIRONMENT=production          # development, staging, production
CONNECTOR_LOG_LEVEL=INFO                 # DEBUG, INFO, WARNING, ERROR
CONNECTOR_MAX_CONCURRENT_SYNCS=10         # Concurrent sync operations

# Database Configuration
CONNECTOR_DATABASE_URL=postgresql://user:pass@host:5432/db

# API Credentials
CONNECTOR_GOOGLE_DRIVE_CREDENTIALS_PATH=/app/credentials/google.json
CONNECTOR_AUTODESK_CLIENT_ID=your_client_id
CONNECTOR_AUTODESK_CLIENT_SECRET=your_client_secret
CONNECTOR_SUPABASE_URL=https://your-project.supabase.co
CONNECTOR_SUPABASE_SERVICE_ROLE_KEY=your_service_role_key

# Performance Tuning
CONNECTOR_MAX_CONNECTIONS=100             # HTTP connection pool size
CONNECTOR_BATCH_SIZE=50                   # File processing batch size
CONNECTOR_RATE_LIMIT_CALLS=100           # API rate limit
```

### Configuration Files

Advanced configuration via YAML files:

```yaml
# config/connector.yaml
connector:
  name: "production-connector"
  environment: "production"
  max_concurrent_syncs: 10

endpoints:
  - id: "google-drive-engineering"
    type: "google_drive"
    name: "Engineering Files"
    project_id: "eng-project-001"
    user_id: "engineering@company.com"
    endpoint_details:
      folder_id: "1a2b3c4d5e6f"
      include_shared: true
      file_types: ["dwg", "pdf", "docx"]
    schedule: "interval"
    schedule_config:
      interval_minutes: 5
    is_active: true

  - id: "autodesk-construction"
    type: "autodesk"
    name: "Construction Project Files"
    project_id: "construction-001"
    user_id: "pm@company.com"
    endpoint_details:
      project_id: "b.abc123def456"
      folder_id: "urn:adsk.wipprod:fs.folder:co.xyz789"
      file_types: ["rvt", "dwg", "ifc"]
    schedule: "cron"
    schedule_config:
      cron_expression: "0 */6 * * *"  # Every 6 hours
    is_active: true
```

### Secrets Management

#### Kubernetes Secrets

```bash
# Create secrets from literal values
kubectl create secret generic file-connector-secrets \
  --from-literal=database-url="postgresql://user:pass@host:5432/db" \
  --from-literal=autodesk-client-id="your_client_id" \
  --from-literal=autodesk-client-secret="your_client_secret" \
  -n file-connector

# Create secrets from files
kubectl create secret generic file-connector-credentials \
  --from-file=google-service-account.json=/path/to/credentials.json \
  -n file-connector
```

#### Docker Secrets

```yaml
# docker-compose.yml with secrets
version: '3.8'

services:
  connector:
    image: file-connector:latest
    secrets:
      - database_password
      - autodesk_client_secret
    environment:
      - CONNECTOR_DATABASE_URL=postgresql://connector:${database_password}@postgres:5432/db

secrets:
  database_password:
    file: ./secrets/db_password.txt
  autodesk_client_secret:
    file: ./secrets/autodesk_secret.txt
```

## Monitoring and Observability

### Metrics and Monitoring

#### Prometheus Integration

```yaml
# prometheus/prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'file-connector'
    static_configs:
      - targets: ['file-connector-service:8080']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

#### Grafana Dashboards

Key metrics to monitor:

- **Application Metrics**:
  - Sync success rate
  - Files processed per hour
  - API response times
  - Error rates by endpoint

- **System Metrics**:
  - CPU and memory usage
  - Database connection pool
  - HTTP request latency
  - Queue depth

#### Custom Metrics

```python
# Example custom metrics in application
from connector.performance import get_metrics_collector

metrics = get_metrics_collector()

# Record sync performance
metrics.record_timing("sync.duration", sync_time)
metrics.increment_counter("sync.files_processed", file_count)
metrics.set_gauge("sync.active_endpoints", active_count)
```

### Logging

#### Structured Logging Configuration

```python
# Logging configuration
LOGGING_CONFIG = {
    "version": 1,
    "formatters": {
        "json": {
            "format": '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "component": "%(name)s", "message": "%(message)s"}'
        }
    },
    "handlers": {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "/app/logs/connector.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5,
            "formatter": "json"
        }
    }
}
```

#### Log Aggregation

**ELK Stack Integration**:
```yaml
# filebeat.yml
filebeat.inputs:
- type: log
  enabled: true
  paths:
    - /app/logs/*.log
  fields:
    service: file-connector
  fields_under_root: true

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
```

### Health Checks

#### Application Health Endpoints

```python
# Health check implementation
@app.route('/health')
async def health_check():
    """Comprehensive health check."""
    health = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "database": await check_database_health(),
            "redis": await check_redis_health(),
            "api_clients": await check_api_clients_health()
        }
    }
    
    overall_status = "healthy"
    for component_status in health["components"].values():
        if component_status["status"] != "healthy":
            overall_status = "degraded"
            break
    
    health["status"] = overall_status
    status_code = 200 if overall_status == "healthy" else 503
    
    return web.json_response(health, status=status_code)
```

#### Kubernetes Probes

```yaml
# Liveness and readiness probes
containers:
- name: file-connector
  livenessProbe:
    httpGet:
      path: /health
      port: 8080
    initialDelaySeconds: 60
    periodSeconds: 30
    timeoutSeconds: 10
    failureThreshold: 3
  
  readinessProbe:
    httpGet:
      path: /health
      port: 8080
    initialDelaySeconds: 30
    periodSeconds: 10
    timeoutSeconds: 5
    failureThreshold: 3
```

## Security Considerations

### Container Security

#### Non-root User

```dockerfile
# Dockerfile security best practices
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r connector && useradd -r -g connector connector

# Set up application
WORKDIR /app
COPY . .
RUN chown -R connector:connector /app

# Switch to non-root user
USER connector

# Expose port
EXPOSE 8080
```

#### Security Scanning

```bash
# Scan container image for vulnerabilities
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  -v $(pwd):/tmp/.cache/:ro \
  aquasec/trivy image file-connector:latest

# Scan for secrets
docker run --rm -v $(pwd):/app trufflesecurity/trufflehog:latest github --repo file://app
```

### Network Security

#### Network Policies

```yaml
# kubernetes/network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: file-connector-netpol
  namespace: file-connector
spec:
  podSelector:
    matchLabels:
      app: file-connector
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress-nginx
    ports:
    - protocol: TCP
      port: 8080
  egress:
  - to: []  # Allow all outbound (for API calls)
    ports:
    - protocol: TCP
      port: 443
  - to:
    - podSelector:
        matchLabels:
          app: postgres
    ports:
    - protocol: TCP
      port: 5432
```

#### TLS Configuration

```yaml
# Ingress with TLS
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: file-connector-ingress
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
  - hosts:
    - file-connector.yourdomain.com
    secretName: file-connector-tls
  rules:
  - host: file-connector.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: file-connector-service
            port:
              number: 80
```

### Secrets Management

#### External Secrets Operator

```yaml
# external-secrets.yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: vault-secret-store
  namespace: file-connector
spec:
  provider:
    vault:
      server: "https://vault.company.com"
      path: "secret"
      version: "v2"
      auth:
        kubernetes:
          mountPath: "kubernetes"
          role: "file-connector"

---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: file-connector-secrets
  namespace: file-connector
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: vault-secret-store
    kind: SecretStore
  target:
    name: file-connector-secrets
    creationPolicy: Owner
  data:
  - secretKey: database-url
    remoteRef:
      key: file-connector/database
      property: url
  - secretKey: autodesk-client-secret
    remoteRef:
      key: file-connector/autodesk
      property: client_secret
```

## Troubleshooting

### Common Issues

#### 1. Database Connection Errors

**Symptoms**: `ConnectionError: could not connect to server`

**Solutions**:
```bash
# Check database connectivity
kubectl exec -it deployment/file-connector -n file-connector -- \
  python -c "import psycopg2; psycopg2.connect('postgresql://user:pass@postgres:5432/db')"

# Verify database service
kubectl get svc postgres -n file-connector

# Check database logs
kubectl logs deployment/postgres -n file-connector
```

#### 2. API Authentication Failures

**Symptoms**: `AuthenticationError: Invalid credentials`

**Solutions**:
```bash
# Verify secrets are properly set
kubectl get secret file-connector-secrets -n file-connector -o yaml

# Check credential files
kubectl exec -it deployment/file-connector -n file-connector -- \
  ls -la /app/credentials/

# Test API connectivity
kubectl exec -it deployment/file-connector -n file-connector -- \
  curl -H "Authorization: Bearer $TOKEN" https://api.service.com/test
```

#### 3. Memory Issues

**Symptoms**: `OOMKilled` events, high memory usage

**Solutions**:
```bash
# Check resource usage
kubectl top pods -n file-connector

# Increase memory limits
kubectl patch deployment file-connector -n file-connector -p \
  '{"spec":{"template":{"spec":{"containers":[{"name":"file-connector","resources":{"limits":{"memory":"1Gi"}}}]}}}}'

# Analyze memory usage
kubectl exec -it deployment/file-connector -n file-connector -- \
  python -c "import psutil; print(f'Memory: {psutil.virtual_memory().percent}%')"
```

#### 4. Performance Issues

**Symptoms**: Slow sync operations, timeouts

**Solutions**:
```bash
# Check metrics
curl http://localhost:8080/metrics

# Adjust concurrency settings
export CONNECTOR_MAX_CONCURRENT_SYNCS=5
export CONNECTOR_BATCH_SIZE=25

# Monitor database performance
kubectl exec -it deployment/postgres -n file-connector -- \
  psql -U connector -d connector_db -c "SELECT * FROM pg_stat_activity;"
```

### Debugging Tools

#### Kubectl Commands

```bash
# View pod status
kubectl get pods -n file-connector -o wide

# Describe pod issues
kubectl describe pod <pod-name> -n file-connector

# View logs
kubectl logs -f deployment/file-connector -n file-connector

# Execute commands in pod
kubectl exec -it deployment/file-connector -n file-connector -- /bin/bash

# Port forward for debugging
kubectl port-forward service/file-connector-service 8080:80 -n file-connector
```

#### Application Debugging

```bash
# Enable debug logging
export CONNECTOR_LOG_LEVEL=DEBUG

# Test database connection
python -c "
from connector.database import DatabaseManager
db = DatabaseManager('postgresql://user:pass@localhost:5432/db')
print('Database connection:', db.test_connection())
"

# Test API clients
python -c "
from connector.api_clients import APIClientFactory
client = APIClientFactory().create_client('google_drive', config)
print('Auth result:', await client.authenticate())
"
```

### Performance Tuning

#### Database Optimization

```sql
-- PostgreSQL performance tuning
-- config/init-db.sql

-- Connection settings
ALTER SYSTEM SET max_connections = 200;
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';

-- Performance indexes
CREATE INDEX CONCURRENTLY idx_files_endpoint_updated 
ON files(endpoint_id, updated_at);

CREATE INDEX CONCURRENTLY idx_sync_logs_endpoint_started 
ON sync_logs(endpoint_id, sync_started);

-- Analyze tables for query optimization
ANALYZE files;
ANALYZE endpoints;
ANALYZE sync_logs;
```

#### Application Tuning

```yaml
# Application performance settings
environment:
  # Connection pooling
  - CONNECTOR_MAX_CONNECTIONS=100
  - CONNECTOR_MAX_CONNECTIONS_PER_HOST=30
  
  # Batch processing
  - CONNECTOR_BATCH_SIZE=50
  - CONNECTOR_MAX_CONCURRENT_BATCHES=10
  
  # Rate limiting
  - CONNECTOR_RATE_LIMIT_CALLS=100
  - CONNECTOR_RATE_LIMIT_WINDOW=60
  
  # Async settings
  - CONNECTOR_MAX_CONCURRENT_SYNCS=10
```

### Monitoring and Alerting

#### Prometheus Alerts

```yaml
# alerts.yml
groups:
- name: file-connector
  rules:
  - alert: FileConnectorDown
    expr: up{job="file-connector"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "File Connector is down"
      description: "File Connector has been down for more than 1 minute"

  - alert: HighErrorRate
    expr: rate(connector_sync_errors_total[5m]) > 0.1
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High error rate in File Connector"
      description: "Error rate is {{ $value }} errors per second"

  - alert: DatabaseConnectionIssue
    expr: connector_database_connection_errors_total > 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Database connection issues"
      description: "Database connection errors detected"
```

This comprehensive deployment guide provides all the necessary information to successfully deploy and operate the File Connector in any environment, from development to production at scale.