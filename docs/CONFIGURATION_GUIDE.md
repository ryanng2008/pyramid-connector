# Configuration Guide

Comprehensive guide for configuring the File Connector system across different environments and use cases.

## Table of Contents

- [Overview](#overview)
- [Configuration Methods](#configuration-methods)
- [Environment Variables](#environment-variables)
- [Configuration Files](#configuration-files)
- [Endpoint Configuration](#endpoint-configuration)
- [Database Configuration](#database-configuration)
- [Performance Tuning](#performance-tuning)
- [Security Configuration](#security-configuration)
- [Monitoring Configuration](#monitoring-configuration)
- [Environment-Specific Setup](#environment-specific-setup)

## Overview

The File Connector supports multiple configuration methods to accommodate different deployment scenarios:

1. **Environment Variables**: For sensitive data and deployment-specific settings
2. **Configuration Files**: For structured settings and endpoint definitions
3. **Database Configuration**: For runtime-managed settings
4. **Command Line Arguments**: For debugging and development

### Configuration Hierarchy

Settings are applied in the following order (later sources override earlier ones):

```
Default Values → Configuration Files → Environment Variables → Command Line Arguments
```

## Configuration Methods

### 1. Environment Variables

Environment variables are the primary method for sensitive configuration:

```bash
# Core Application Settings
export CONNECTOR_ENVIRONMENT=production
export CONNECTOR_LOG_LEVEL=INFO
export CONNECTOR_MAX_CONCURRENT_SYNCS=10

# Database Configuration
export CONNECTOR_DATABASE_URL="postgresql://user:pass@host:5432/connector_db"

# API Credentials
export CONNECTOR_GOOGLE_DRIVE_CREDENTIALS_PATH="/app/credentials/google.json"
export CONNECTOR_AUTODESK_CLIENT_ID="your_client_id"
export CONNECTOR_AUTODESK_CLIENT_SECRET="your_client_secret"
```

### 2. Configuration Files

YAML or JSON files for structured configuration:

```yaml
# config/connector.yaml
connector:
  name: "file-connector-prod"
  environment: "production"
  version: "1.0.0"
  debug: false

database:
  pool_size: 20
  max_overflow: 30
  pool_timeout: 30
  pool_recycle: 3600

performance:
  max_concurrent_syncs: 10
  batch_size: 50
  connection_pool_size: 100
  rate_limit_calls: 100
  rate_limit_window: 60

endpoints:
  - id: "google-drive-engineering"
    type: "google_drive"
    name: "Engineering Files"
    # ... endpoint configuration
```

### 3. Dynamic Configuration

Runtime configuration through the API:

```python
# Update configuration via API
POST /api/v1/configuration
{
  "max_concurrent_syncs": 15,
  "batch_size": 75,
  "endpoints": [
    {
      "id": "new-endpoint",
      "type": "google_drive",
      "name": "New Endpoint",
      "is_active": true
    }
  ]
}
```

## Environment Variables

### Core Application Variables

```bash
# Application Identity
CONNECTOR_NAME="file-connector"
CONNECTOR_VERSION="1.0.0"
CONNECTOR_ENVIRONMENT="production"  # development, staging, production

# Logging Configuration
CONNECTOR_LOG_LEVEL="INFO"          # DEBUG, INFO, WARNING, ERROR, CRITICAL
CONNECTOR_LOG_FORMAT="json"         # json, text
CONNECTOR_LOG_FILE="/app/logs/connector.log"

# Operational Settings
CONNECTOR_MAX_CONCURRENT_SYNCS=10
CONNECTOR_SHUTDOWN_TIMEOUT=30
CONNECTOR_HEALTH_CHECK_INTERVAL=60
```

### Database Configuration

```bash
# Primary Database
CONNECTOR_DATABASE_URL="postgresql://user:password@host:5432/database"

# Connection Pool Settings
CONNECTOR_DB_POOL_SIZE=20
CONNECTOR_DB_MAX_OVERFLOW=30
CONNECTOR_DB_POOL_TIMEOUT=30
CONNECTOR_DB_POOL_RECYCLE=3600
CONNECTOR_DB_ECHO=false

# Alternative: SQLite for development
CONNECTOR_DATABASE_URL="sqlite:///./data/connector.db"
```

### API Credentials

```bash
# Google Drive API
CONNECTOR_GOOGLE_DRIVE_CREDENTIALS_PATH="/app/credentials/google-service-account.json"
CONNECTOR_GOOGLE_DRIVE_SCOPES="https://www.googleapis.com/auth/drive.readonly"

# Autodesk Construction Cloud
CONNECTOR_AUTODESK_CLIENT_ID="your_autodesk_client_id"
CONNECTOR_AUTODESK_CLIENT_SECRET="your_autodesk_client_secret"
CONNECTOR_AUTODESK_BASE_URL="https://developer.api.autodesk.com"

# Supabase (Mock)
CONNECTOR_SUPABASE_URL="https://your-project.supabase.co"
CONNECTOR_SUPABASE_SERVICE_ROLE_KEY="your_service_role_key"
CONNECTOR_SUPABASE_ANON_KEY="your_anon_key"

# Microsoft SharePoint (if using SharePoint client)
CONNECTOR_SHAREPOINT_TENANT_ID="your_tenant_id"
CONNECTOR_SHAREPOINT_CLIENT_ID="your_client_id"
CONNECTOR_SHAREPOINT_CLIENT_SECRET="your_client_secret"
```

### Performance Configuration

```bash
# Concurrency Settings
CONNECTOR_MAX_CONCURRENT_SYNCS=10
CONNECTOR_MAX_WORKERS=4
CONNECTOR_SEMAPHORE_LIMIT=10

# Batch Processing
CONNECTOR_BATCH_SIZE=50
CONNECTOR_MAX_BATCH_SIZE=200
CONNECTOR_BATCH_TIMEOUT=300

# HTTP Configuration
CONNECTOR_MAX_CONNECTIONS=100
CONNECTOR_MAX_CONNECTIONS_PER_HOST=30
CONNECTOR_CONNECTION_TIMEOUT=30
CONNECTOR_READ_TIMEOUT=60

# Rate Limiting
CONNECTOR_RATE_LIMIT_CALLS=100
CONNECTOR_RATE_LIMIT_WINDOW=60
CONNECTOR_RATE_LIMIT_BURST=10
```

### Caching and Redis

```bash
# Redis Configuration
CONNECTOR_REDIS_URL="redis://localhost:6379"
CONNECTOR_REDIS_PASSWORD="your_redis_password"
CONNECTOR_REDIS_DB=0
CONNECTOR_REDIS_MAX_CONNECTIONS=20

# Cache Settings
CONNECTOR_CACHE_TTL=3600
CONNECTOR_CACHE_PREFIX="file_connector:"
CONNECTOR_ENABLE_CACHING=true
```

### Monitoring and Metrics

```bash
# Metrics Collection
CONNECTOR_ENABLE_METRICS=true
CONNECTOR_METRICS_PORT=8081
CONNECTOR_METRICS_PATH="/metrics"

# Health Checks
CONNECTOR_HEALTH_CHECK_PORT=8080
CONNECTOR_HEALTH_CHECK_PATH="/health"

# External Monitoring
CONNECTOR_PROMETHEUS_GATEWAY_URL="http://prometheus-gateway:9091"
CONNECTOR_GRAFANA_URL="http://grafana:3000"
```

## Configuration Files

### Main Configuration File

Create `config/connector.yaml`:

```yaml
# Core connector configuration
connector:
  name: "file-connector-production"
  environment: "production"
  version: "1.0.0"
  debug: false
  
  # Operational settings
  max_concurrent_syncs: 10
  shutdown_timeout: 30
  health_check_interval: 60

# Database configuration
database:
  # Connection pool settings
  pool_size: 20
  max_overflow: 30
  pool_timeout: 30
  pool_recycle: 3600
  echo: false
  
  # Query optimization
  enable_query_cache: true
  query_cache_size: 1000

# Performance settings
performance:
  # Batch processing
  batch_size: 50
  max_batch_size: 200
  batch_timeout: 300
  
  # Connection management
  max_connections: 100
  max_connections_per_host: 30
  connection_timeout: 30
  read_timeout: 60
  
  # Rate limiting
  rate_limit_calls: 100
  rate_limit_window: 60
  rate_limit_burst: 10
  
  # Async settings
  semaphore_limit: 10
  max_workers: 4

# Logging configuration
logging:
  level: "INFO"
  format: "json"
  file: "/app/logs/connector.log"
  max_size: "100MB"
  backup_count: 5
  
  # Structured logging fields
  include_fields:
    - timestamp
    - level
    - component
    - correlation_id
    - duration

# Monitoring configuration
monitoring:
  enable_metrics: true
  metrics_port: 8081
  health_check_port: 8080
  
  # Prometheus integration
  prometheus:
    enabled: true
    gateway_url: "http://prometheus-gateway:9091"
    job_name: "file-connector"
    push_interval: 60

# Security settings
security:
  # Credential management
  credentials_directory: "/app/credentials"
  secrets_directory: "/app/secrets"
  
  # API security
  enable_rate_limiting: true
  max_requests_per_minute: 100
  
  # TLS settings
  tls:
    enabled: false
    cert_file: "/app/certs/tls.crt"
    key_file: "/app/certs/tls.key"

# Endpoint configurations
endpoints:
  - id: "google-drive-engineering"
    type: "google_drive"
    name: "Engineering Files"
    description: "CAD files and technical documentation"
    project_id: "engineering-project-001"
    user_id: "engineering@company.com"
    
    # Google Drive specific settings
    endpoint_details:
      folder_id: "1a2b3c4d5e6f7g8h9i0j"
      include_shared: true
      file_types: ["dwg", "pdf", "docx", "xlsx"]
      max_file_size_mb: 100
      exclude_patterns: ["*temp*", "*backup*"]
    
    # Scheduling configuration
    schedule: "interval"
    schedule_config:
      interval_minutes: 5
      max_runtime_minutes: 30
      retry_on_failure: true
      max_retries: 3
    
    # Processing configuration
    processors:
      - virus_scanner
      - metadata_extractor
    
    processor_config:
      virus_scanner:
        enabled: true
        api_key: "${VIRUS_TOTAL_API_KEY}"
        skip_large_files: true
        max_file_size_mb: 50
      
      metadata_extractor:
        enabled: true
        extract_text: false
        generate_thumbnails: false
    
    # Filter configuration
    filters:
      file_size:
        min_size_bytes: 1024
        max_size_bytes: 104857600  # 100MB
      
      date_range:
        max_age_days: 365
        min_modification_date: "2023-01-01"
    
    is_active: true

  - id: "autodesk-construction"
    type: "autodesk"
    name: "Construction Project Files"
    description: "BIM models and construction documents"
    project_id: "construction-project-001"
    user_id: "pm@company.com"
    
    # Autodesk specific settings
    endpoint_details:
      project_id: "b.abc123def456ghi789"
      folder_id: "urn:adsk.wipprod:fs.folder:co.xyz789abc123"
      file_types: ["rvt", "dwg", "ifc", "nwd"]
      include_versions: false
    
    # Custom scheduling - business hours only
    schedule: "business_hours"
    schedule_config:
      start_hour: 9
      end_hour: 17
      weekdays_only: true
      interval_minutes: 30
      timezone: "America/New_York"
    
    processors:
      - metadata_extractor
    
    processor_config:
      metadata_extractor:
        enabled: true
        extract_bim_data: true
        generate_thumbnails: true
    
    is_active: true

# Filter definitions (reusable)
filter_definitions:
  standard_office_files:
    file_types: ["pdf", "docx", "xlsx", "pptx"]
    max_size_mb: 50
  
  cad_files:
    file_types: ["dwg", "dxf", "rvt", "ifc"]
    max_size_mb: 500
  
  recent_files:
    max_age_days: 30
    min_modification_date: "2023-01-01"

# Processor definitions (reusable)
processor_definitions:
  virus_scanner:
    class: "VirusScannerProcessor"
    config:
      api_key: "${VIRUS_TOTAL_API_KEY}"
      skip_large_files: true
      max_file_size_mb: 100
  
  metadata_extractor:
    class: "MetadataExtractorProcessor"
    config:
      extract_text: true
      generate_thumbnails: false
      thumbnail_size: [200, 200]
```

### Environment-Specific Overrides

Create environment-specific configuration files:

#### Development (`config/connector.dev.yaml`)

```yaml
connector:
  environment: "development"
  debug: true

database:
  echo: true  # Enable SQL logging

logging:
  level: "DEBUG"
  format: "text"

performance:
  max_concurrent_syncs: 2
  batch_size: 10

endpoints:
  - id: "test-google-drive"
    type: "google_drive"
    name: "Test Google Drive"
    schedule: "manual"  # Manual testing only
    is_active: false
```

#### Staging (`config/connector.staging.yaml`)

```yaml
connector:
  environment: "staging"

performance:
  max_concurrent_syncs: 5
  batch_size: 25

monitoring:
  prometheus:
    enabled: false  # Disable in staging

endpoints:
  # Reduced set of endpoints for staging
  - id: "staging-google-drive"
    type: "google_drive"
    name: "Staging Google Drive"
    schedule: "interval"
    schedule_config:
      interval_minutes: 15  # Less frequent in staging
```

#### Production (`config/connector.prod.yaml`)

```yaml
connector:
  environment: "production"

security:
  enable_rate_limiting: true
  tls:
    enabled: true

monitoring:
  enable_metrics: true
  prometheus:
    enabled: true

# Full endpoint configuration
endpoints:
  # ... production endpoints
```

## Endpoint Configuration

### Google Drive Endpoint

```yaml
- id: "google-drive-legal"
  type: "google_drive"
  name: "Legal Documents"
  project_id: "legal-dept"
  user_id: "legal@company.com"
  
  endpoint_details:
    # Required: Service account credentials
    credentials_path: "/app/credentials/google-legal.json"
    
    # Optional: Specific folder (null for entire drive)
    folder_id: "1BcDeFgHiJkLmNoPqRsTuVwXyZ"
    
    # Include shared drives
    include_shared: true
    
    # File type filtering
    file_types: ["pdf", "docx", "txt"]
    
    # Size limits
    max_file_size_mb: 25
    min_file_size_kb: 1
    
    # Exclusion patterns
    exclude_patterns:
      - "*draft*"
      - "*temp*"
      - ".*"  # Hidden files
    
    # Additional Google Drive options
    include_trashed: false
    include_team_drives: true
    
    # Performance tuning
    page_size: 100
    max_pages: 50
  
  # Scheduling
  schedule: "cron"
  schedule_config:
    cron_expression: "0 */4 * * *"  # Every 4 hours
    timezone: "America/New_York"
  
  # Error handling
  error_handling:
    max_retries: 3
    retry_delay_seconds: 60
    fail_on_auth_error: true
  
  is_active: true
```

### Autodesk Construction Cloud Endpoint

```yaml
- id: "autodesk-office-building"
  type: "autodesk"
  name: "Office Building Project"
  project_id: "office-building-2024"
  user_id: "architect@company.com"
  
  endpoint_details:
    # Required: OAuth credentials
    client_id: "${AUTODESK_CLIENT_ID}"
    client_secret: "${AUTODESK_CLIENT_SECRET}"
    
    # Required: Project and folder IDs
    project_id: "b.1234567890abcdef"
    folder_id: "urn:adsk.wipprod:fs.folder:co.abcdef123456"
    
    # File type filtering
    file_types: ["rvt", "dwg", "ifc", "nwd", "pdf"]
    
    # Version handling
    include_versions: false  # Latest version only
    version_limit: 5        # If including versions
    
    # Performance settings
    max_concurrent_requests: 5
    request_timeout_seconds: 300
    
    # Additional Autodesk options
    include_hidden: false
    include_deleted: false
  
  # Business hours schedule
  schedule: "business_hours"
  schedule_config:
    start_hour: 8
    end_hour: 18
    weekdays_only: true
    interval_minutes: 60
    timezone: "America/Chicago"
  
  is_active: true
```

### SharePoint Endpoint (Custom)

```yaml
- id: "sharepoint-hr-docs"
  type: "sharepoint"
  name: "HR Documents"
  project_id: "human-resources"
  user_id: "hr@company.com"
  
  endpoint_details:
    # Required: Azure AD app registration
    tenant_id: "${SHAREPOINT_TENANT_ID}"
    client_id: "${SHAREPOINT_CLIENT_ID}"
    client_secret: "${SHAREPOINT_CLIENT_SECRET}"
    
    # SharePoint site and library
    site_url: "https://company.sharepoint.com/sites/HR"
    document_library: "Documents"
    
    # Folder filtering
    folder_path: "/Policies"  # Optional subfolder
    
    # File filtering
    file_types: ["pdf", "docx", "xlsx"]
    max_file_size_mb: 20
    
    # Permissions filtering
    include_private: false
    required_permissions: ["read"]
  
  schedule: "interval"
  schedule_config:
    interval_minutes: 30
  
  is_active: true
```

## Database Configuration

### PostgreSQL Configuration

```yaml
database:
  # Connection settings
  url: "${CONNECTOR_DATABASE_URL}"
  driver: "postgresql+asyncpg"
  
  # Pool configuration
  pool_size: 20
  max_overflow: 30
  pool_timeout: 30
  pool_recycle: 3600
  pool_pre_ping: true
  
  # Query settings
  echo: false
  echo_pool: false
  query_timeout: 30
  
  # Migration settings
  migration_directory: "migrations"
  auto_migrate: false
  
  # Performance tuning
  isolation_level: "READ_COMMITTED"
  enable_query_cache: true
  query_cache_size: 1000
  
  # Monitoring
  enable_slow_query_log: true
  slow_query_threshold: 1.0
```

### SQLite Configuration (Development)

```yaml
database:
  url: "sqlite:///./data/connector.db"
  driver: "sqlite+aiosqlite"
  
  # SQLite-specific settings
  enable_foreign_keys: true
  journal_mode: "WAL"
  synchronous: "NORMAL"
  cache_size: 10000
  
  # Connection settings
  pool_size: 1  # SQLite is single-threaded
  pool_timeout: 30
  
  # Performance
  enable_query_cache: false  # Not beneficial for SQLite
```

## Performance Tuning

### Connection Pool Optimization

```yaml
performance:
  # HTTP connection pooling
  http_connections:
    max_total: 100
    max_per_host: 30
    keepalive_timeout: 30
    connection_timeout: 10
    read_timeout: 60
    
  # Database connection pooling
  database_connections:
    pool_size: 20
    max_overflow: 30
    pool_timeout: 30
    pool_recycle: 3600
    
  # Redis connection pooling
  redis_connections:
    max_connections: 20
    retry_on_timeout: true
    socket_timeout: 30
```

### Batch Processing Configuration

```yaml
performance:
  batching:
    # File processing batches
    default_batch_size: 50
    max_batch_size: 200
    min_batch_size: 10
    
    # Database operation batches
    db_batch_size: 100
    db_batch_timeout: 30
    
    # Concurrent batch processing
    max_concurrent_batches: 5
    batch_queue_size: 1000
```

### Memory Management

```yaml
performance:
  memory:
    # File processing limits
    max_file_size_mb: 100
    max_total_memory_mb: 1024
    
    # Cache limits
    metadata_cache_size: 10000
    file_cache_size_mb: 100
    
    # Garbage collection
    gc_threshold: 700
    gc_frequency: 60
```

### Rate Limiting Configuration

```yaml
performance:
  rate_limiting:
    # Global rate limiting
    global_rate_limit: 1000  # requests per minute
    burst_rate_limit: 50     # burst allowance
    
    # Per-endpoint rate limiting
    endpoint_rate_limits:
      google_drive: 100
      autodesk: 200
      sharepoint: 150
    
    # Backoff configuration
    initial_backoff: 1
    max_backoff: 300
    backoff_multiplier: 2
```

## Security Configuration

### Credential Management

```yaml
security:
  credentials:
    # Storage locations
    credentials_directory: "/app/credentials"
    secrets_directory: "/app/secrets"
    
    # File permissions
    file_mode: 0o600
    directory_mode: 0o700
    
    # Encryption (if supported)
    encrypt_at_rest: true
    encryption_key: "${ENCRYPTION_KEY}"
    
    # Rotation
    auto_rotate: false
    rotation_interval_days: 90
```

### API Security

```yaml
security:
  api:
    # Authentication
    require_authentication: true
    auth_method: "bearer_token"
    token_header: "Authorization"
    
    # Rate limiting
    enable_rate_limiting: true
    rate_limit_per_minute: 100
    rate_limit_burst: 10
    
    # CORS settings
    cors:
      enabled: true
      allowed_origins: ["https://dashboard.company.com"]
      allowed_methods: ["GET", "POST", "PUT", "DELETE"]
      allowed_headers: ["Authorization", "Content-Type"]
      max_age: 3600
```

### TLS Configuration

```yaml
security:
  tls:
    enabled: true
    cert_file: "/app/certs/tls.crt"
    key_file: "/app/certs/tls.key"
    ca_file: "/app/certs/ca.crt"
    
    # TLS settings
    min_version: "TLSv1.2"
    ciphers: "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS"
    
    # Client certificate validation
    verify_client_certs: false
    client_ca_file: "/app/certs/client-ca.crt"
```

## Monitoring Configuration

### Prometheus Integration

```yaml
monitoring:
  prometheus:
    enabled: true
    
    # Metrics endpoint
    metrics_port: 8081
    metrics_path: "/metrics"
    
    # Push gateway (for ephemeral jobs)
    push_gateway:
      enabled: true
      url: "http://prometheus-gateway:9091"
      job_name: "file-connector"
      push_interval: 60
      
    # Custom metrics
    custom_metrics:
      - name: "connector_custom_counter"
        type: "counter"
        description: "Custom counter metric"
        labels: ["endpoint", "status"]
```

### Health Check Configuration

```yaml
monitoring:
  health_checks:
    # HTTP health endpoint
    enabled: true
    port: 8080
    path: "/health"
    
    # Health check components
    components:
      database: true
      redis: true
      api_clients: true
      scheduler: true
      
    # Check intervals
    check_interval: 30
    timeout: 10
    
    # Failure thresholds
    max_failures: 3
    failure_window: 300
```

### Logging Configuration

```yaml
logging:
  # Basic settings
  level: "INFO"
  format: "json"
  
  # Output configuration
  handlers:
    console:
      enabled: true
      format: "text"
      level: "INFO"
    
    file:
      enabled: true
      filename: "/app/logs/connector.log"
      format: "json"
      level: "DEBUG"
      max_size: "100MB"
      backup_count: 5
      
    syslog:
      enabled: false
      address: ["localhost", 514]
      facility: "daemon"
      
  # Structured logging
  structured:
    include_timestamp: true
    include_level: true
    include_component: true
    include_correlation_id: true
    include_duration: true
    
  # Log filtering
  filters:
    # Suppress noisy loggers
    suppress_loggers:
      - "urllib3.connectionpool"
      - "asyncio"
    
    # Custom log levels
    logger_levels:
      "connector.api_clients": "DEBUG"
      "connector.database": "INFO"
```

## Environment-Specific Setup

### Development Environment

```yaml
# config/development.yaml
connector:
  environment: "development"
  debug: true

database:
  url: "sqlite:///./data/dev.db"
  echo: true

logging:
  level: "DEBUG"
  format: "text"

performance:
  max_concurrent_syncs: 2
  batch_size: 5

monitoring:
  enable_metrics: false

endpoints:
  - id: "dev-test"
    type: "google_drive"
    name: "Development Test"
    schedule: "manual"
    is_active: false
```

### Production Environment

```yaml
# config/production.yaml
connector:
  environment: "production"
  debug: false

database:
  url: "${CONNECTOR_DATABASE_URL}"
  pool_size: 50

logging:
  level: "INFO"
  format: "json"

performance:
  max_concurrent_syncs: 20
  batch_size: 100

security:
  tls:
    enabled: true
  api:
    require_authentication: true

monitoring:
  enable_metrics: true
  prometheus:
    enabled: true
```

### Configuration Validation

The system validates configuration on startup:

```python
# Configuration validation example
class ConfigValidator:
    def validate_config(self, config: dict) -> List[str]:
        errors = []
        
        # Validate required fields
        if not config.get('database', {}).get('url'):
            errors.append("Database URL is required")
        
        # Validate endpoint configurations
        for endpoint in config.get('endpoints', []):
            if not endpoint.get('type'):
                errors.append(f"Endpoint type required for {endpoint.get('id')}")
        
        # Validate performance settings
        max_syncs = config.get('performance', {}).get('max_concurrent_syncs', 0)
        if max_syncs > 50:
            errors.append("max_concurrent_syncs should not exceed 50")
        
        return errors
```

This configuration guide provides comprehensive coverage of all configuration options available in the File Connector system, enabling administrators to customize the system for their specific needs and environments.