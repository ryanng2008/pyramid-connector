# File Connector

A high-performance, cloud-native file synchronization system that automatically discovers, extracts, and synchronizes file metadata from multiple cloud storage platforms (Google Drive, Autodesk Construction Cloud) to a centralized database.

## Overview

The File Connector is an enterprise-grade Python application designed to periodically fetch file metadata from various cloud APIs and maintain a synchronized view in a database. It operates as a scheduled service that can run in containers, Kubernetes, or traditional server environments.

### How It Works

The File Connector operates through a sophisticated pipeline that orchestrates file discovery, metadata extraction, and database synchronization:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   API Sources   │───▶│  File Connector  │───▶│    Database     │
│                 │    │     Pipeline     │    │   (Metadata)    │
│ • Google Drive  │    │                  │    │ • Files        │
│ • Autodesk CC   │    │ ┌──────────────┐ │    │ • Endpoints    │
│ • [Extensible]  │    │ │ Sync Engine  │ │    │ • Sync Logs    │
└─────────────────┘    │ └──────────────┘ │    └─────────────────┘
                       │ ┌──────────────┐ │
                       │ │  Scheduler   │ │
                       │ └──────────────┘ │
                       │ ┌──────────────┐ │
                       │ │ Performance  │ │
                       │ │ Monitoring   │ │
                       │ └──────────────┘ │
                       └──────────────────┘
```

## Core Features

### 🔄 **Automated File Synchronization**
- **Periodic Discovery**: Automatically discovers files from configured cloud storage endpoints every 5 minutes (configurable)
- **Incremental Sync**: Uses timestamp-based filtering to only process new or modified files, avoiding duplicates
- **Deduplication**: Intelligent handling of file updates using external file IDs and modification timestamps
- **Batch Processing**: Efficiently processes large file sets using configurable batch sizes (default: 50 files)

### 🚀 **Multi-Platform API Integration**
- **Google Drive**: Service account authentication with OAuth 2.0, supports shared drives and folder-specific syncing
- **Autodesk Construction Cloud**: OAuth 2.0 client credentials flow with project-based file access
- **Extensible Architecture**: Plugin-based system allows easy addition of new cloud storage platforms

### ⚡ **High-Performance Processing**
- **Async Architecture**: Built on asyncio for concurrent API calls and non-blocking operations
- **Connection Pooling**: HTTP connection reuse with configurable limits (100 total, 30 per host)
- **Rate Limiting**: Automatic API rate limit handling with backoff strategies and retry logic
- **Circuit Breakers**: Fault tolerance patterns prevent cascade failures during API outages
- **Parallel Processing**: Multiple endpoints processed concurrently (up to 10 by default)

### 📊 **Comprehensive Monitoring**
- **Performance Metrics**: Real-time collection of timing, throughput, and error metrics
- **System Monitoring**: CPU, memory, disk, and network usage tracking with psutil
- **Health Endpoints**: HTTP endpoints for container orchestration health checks
- **Structured Logging**: JSON-formatted logs with correlation IDs and performance metadata

### 🕐 **Flexible Scheduling**
- **Multiple Schedule Types**: 
  - Interval-based (every N minutes)
  - Cron expressions (complex schedules)
  - Manual triggers (on-demand execution)
- **Dynamic Configuration**: Hot-reload of endpoint configurations without restart
- **Job Management**: Start, stop, and monitor individual sync jobs

### 🛡️ **Enterprise Security**
- **Secure Credential Management**: Environment variable and secrets-based configuration
- **Input Validation**: Pydantic-based validation for all configuration and API inputs
- **Non-Root Containers**: Security-hardened Docker images with minimal attack surface
- **Audit Logging**: Comprehensive audit trail of all sync operations and changes

## Pipeline Logic

### 1. **Configuration Loading**
```python
# Load endpoint configurations from YAML/JSON
endpoints = [
    {
        "type": "google_drive",
        "name": "Engineering Files",
        "project_id": "eng-project-001",
        "user_id": "engineer@company.com",
        "endpoint_details": {
            "folder_id": "1a2b3c4d5e6f",
            "include_shared": True,
            "file_types": ["dwg", "pdf", "docx"]
        },
        "schedule": "interval",
        "schedule_config": {"interval_minutes": 5}
    }
]
```

### 2. **Scheduler Initialization**
The scheduler starts background jobs for each active endpoint:

```python
# APScheduler manages concurrent sync jobs
scheduler = AsyncIOScheduler()
for endpoint in active_endpoints:
    scheduler.add_job(
        sync_endpoint,
        trigger=create_trigger(endpoint.schedule),
        args=[endpoint.id],
        id=f"sync_{endpoint.id}",
        max_instances=1  # Prevent overlapping syncs
    )
```

### 3. **Sync Execution Pipeline**

For each scheduled sync operation:

**a) API Client Authentication**
```python
# Factory pattern creates appropriate client
client = APIClientFactory.create_client(
    endpoint.type, 
    endpoint.endpoint_details
)
await client.authenticate()  # OAuth 2.0 flow
```

**b) File Discovery with Filtering**
```python
# Fetch only files modified since last sync
since_timestamp = get_last_sync_timestamp(endpoint.id)
async for file_metadata in client.list_files(since=since_timestamp):
    # Apply filters: file types, folders, size limits
    if file_passes_filters(file_metadata, endpoint.filters):
        yield file_metadata
```

**c) Metadata Extraction and Standardization**
```python
# Convert API-specific metadata to standard format
standardized_metadata = FileMetadata(
    external_id=file_data["id"],
    title=file_data["name"],
    file_link=generate_download_link(file_data),
    date_created=parse_timestamp(file_data["createdTime"]),
    date_updated=parse_timestamp(file_data["modifiedTime"]),
    project_id=endpoint.project_id,
    user_id=endpoint.user_id,
    metadata={
        "size": file_data.get("size"),
        "mime_type": file_data.get("mimeType"),
        "permissions": extract_permissions(file_data)
    }
)
```

**d) Database Synchronization**
```python
# Batch process for efficiency
async with database.transaction():
    files_to_create = []
    files_to_update = []
    
    for file_metadata in file_batch:
        existing_file = await db.get_file_by_external_id(
            file_metadata.external_id, endpoint.id
        )
        
        if existing_file:
            if file_metadata.date_updated > existing_file.date_updated:
                files_to_update.append(file_metadata)
        else:
            files_to_create.append(file_metadata)
    
    # Batch database operations
    await db.batch_create_files(files_to_create)
    await db.batch_update_files(files_to_update)
```

**e) Sync Logging and Metrics**
```python
# Record sync statistics
sync_result = SyncResult(
    endpoint_id=endpoint.id,
    success=True,
    files_processed=len(all_files),
    files_added=len(files_to_create),
    files_updated=len(files_to_update),
    sync_duration=end_time - start_time
)

await db.create_sync_log(sync_result)
metrics.record_timing("sync.duration", sync_result.sync_duration)
metrics.increment_counter("sync.files_processed", sync_result.files_processed)
```

### 4. **Error Handling and Recovery**

The pipeline includes comprehensive error handling:

```python
try:
    result = await sync_endpoint(endpoint)
except RateLimitError as e:
    # Exponential backoff retry
    await asyncio.sleep(e.retry_after or 60)
    await schedule_retry(endpoint, delay=e.retry_after)
    
except AuthenticationError as e:
    # Refresh credentials and retry
    await client.refresh_authentication()
    await schedule_retry(endpoint, delay=30)
    
except APIConnectionError as e:
    # Circuit breaker pattern
    circuit_breaker.record_failure()
    if circuit_breaker.should_trip():
        await disable_endpoint_temporarily(endpoint)
```

### 5. **Performance Optimization**

The pipeline employs several performance optimizations:

**Connection Pooling**
```python
# Reuse HTTP connections across requests
connection_pool = ConnectionPoolManager(
    max_connections=100,
    max_connections_per_host=30,
    keepalive_timeout=30
)
```

**Batch Processing**
```python
# Process files in configurable batches
batch_processor = BatchProcessor(
    default_batch_size=50,
    max_concurrent_batches=10
)
await batch_processor.process_batches(files, process_file_batch)
```

**Async Concurrency**
```python
# Process multiple endpoints concurrently
semaphore = asyncio.Semaphore(max_concurrent_syncs)
tasks = [sync_endpoint_with_semaphore(ep) for ep in endpoints]
results = await asyncio.gather(*tasks, return_exceptions=True)
```

## Data Flow Architecture

### File Metadata Model
Each synchronized file is stored with standardized metadata:

```python
@dataclass
class FileMetadata:
    external_id: str        # API-specific file identifier
    title: str             # File name/title
    file_link: str         # Direct download/view URL
    date_created: datetime # File creation timestamp
    date_updated: datetime # Last modification timestamp
    project_id: str        # Associated project identifier
    user_id: str          # File owner/creator identifier
    metadata: Dict[str, Any]  # Platform-specific additional data
```

### Database Schema
The system maintains three core tables:

**Endpoints Table**
- `id`: Primary key
- `endpoint_type`: google_drive, autodesk, etc.
- `name`: Human-readable endpoint name
- `project_id`: Associated project
- `user_id`: Endpoint owner
- `endpoint_details`: JSON configuration
- `is_active`: Enable/disable flag
- `created_at`, `updated_at`: Timestamps

**Files Table**
- `id`: Primary key
- `external_id`: API-specific file ID
- `endpoint_id`: Foreign key to endpoints
- `title`: File name
- `file_link`: Access URL
- `date_created`, `date_updated`: File timestamps
- `project_id`, `user_id`: Association fields
- `file_metadata`: JSON additional data
- `created_at`, `updated_at`: Record timestamps

**Sync Logs Table**
- `id`: Primary key
- `endpoint_id`: Foreign key to endpoints
- `sync_started`, `sync_completed`: Operation timestamps
- `files_processed`, `files_added`, `files_updated`: Counters
- `sync_status`: completed, failed, partial
- `error_message`: Failure details
- `sync_duration`: Performance metric

## Quick Start

### 1. Installation
```bash
git clone https://github.com/your-org/file-connector.git
cd file-connector
pip install -r requirements.txt
```

### 2. Configuration
```bash
# Copy environment template
cp env.example .env

# Edit configuration
vim .env  # Add your API credentials

# Copy configuration template
cp config/connector.example.yaml config/connector.yaml
```

### 3. Run Locally
```bash
# Start the connector
python -m src.connector.main

# Or using Docker
docker-compose up -d
```

### 4. Verify Operation
```bash
# Check health
curl http://localhost:8080/health

# View metrics
curl http://localhost:8080/metrics

# Run tests
./scripts/test.sh quick
```

## Architecture Benefits

### 🔧 **Extensibility**
- **Plugin Architecture**: New API clients can be added by implementing the `BaseAPIClient` interface
- **Configurable Filters**: File type, size, and folder filters can be customized per endpoint
- **Multiple Databases**: Supports SQLite (development) and PostgreSQL (production)

### 🚀 **Scalability**
- **Horizontal Scaling**: Multiple connector instances can run concurrently with different endpoints
- **Kubernetes Ready**: Includes complete Kubernetes manifests with autoscaling
- **Resource Efficient**: Optimized for minimal CPU and memory usage

### 🛡️ **Reliability**
- **Fault Tolerance**: Circuit breakers and retry logic handle API failures gracefully
- **Data Consistency**: Database transactions ensure consistent metadata state
- **Monitoring**: Comprehensive metrics enable proactive issue detection

### ⚡ **Performance**
- **Concurrent Processing**: Async architecture maximizes throughput
- **Intelligent Caching**: Connection pooling and metadata caching reduce API calls
- **Batch Operations**: Database batch processing minimizes transaction overhead

This architecture enables the File Connector to efficiently manage thousands of files across multiple cloud platforms while maintaining high availability and performance standards.