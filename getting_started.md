# Getting Started with File Connector

A comprehensive guide to setting up and running the File Connector system for synchronizing files from Google Drive and Autodesk Construction Cloud APIs.

## Table of Contents

- [Quick Start](#quick-start)
- [Configuration](#configuration)
  - [Environment Variables](#environment-variables)
  - [Endpoint Configuration](#endpoint-configuration)
  - [Database Setup](#database-setup)
- [Running the System](#running-the-system)
- [Testing Endpoints](#testing-endpoints)
- [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)

## Quick Start

### 1. Prerequisites

- Python 3.8+
- PostgreSQL (for production) or SQLite (for development)
- Google Drive API credentials
- Autodesk Construction Cloud API credentials

### 2. Installation

```bash
# Clone and navigate to the project
git clone <repository-url>
cd connector

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Basic Configuration

```bash
# Copy environment template
cp env.example .env

# Copy connector configuration template
cp config/connector.example.yaml config/connector.yaml

# Copy endpoints configuration template
cp config/endpoints.example.json config/endpoints.json
```

### 4. Quick Test

```bash
# Test endpoint connectivity
python scripts/test_endpoints.py

# Run the connector
python -m src.connector.main
```

## Configuration

### Environment Variables

Edit the `.env` file with your specific configuration:

#### Database Configuration

**For Development (SQLite):**
```env
CONNECTOR_DATABASE_URL=sqlite:///./data/connector.db
```

**For Production (PostgreSQL):**
```env
CONNECTOR_DATABASE_URL=postgresql://username:password@host:port/database
DB_PASSWORD=your_db_password
```

#### API Credentials

**Google Drive API:**
```env
CONNECTOR_GOOGLE_DRIVE_CREDENTIALS_PATH=./credentials/google-service-account.json
```

**Autodesk Construction Cloud API:**
```env
CONNECTOR_AUTODESK_CLIENT_ID=your_client_id
CONNECTOR_AUTODESK_CLIENT_SECRET=your_client_secret
CONNECTOR_AUTODESK_BASE_URL=https://developer.api.autodesk.com
```

#### Application Settings

```env
CONNECTOR_ENVIRONMENT=development
CONNECTOR_LOG_LEVEL=INFO
CONNECTOR_MAX_CONCURRENT_SYNCS=10
```

### Endpoint Configuration

Endpoints define which cloud storage locations to sync from. You can configure them in two ways:

#### Method 1: YAML Configuration File (`config/connector.yaml`)

```yaml
endpoints:
  - name: "Main Google Drive Folder"
    endpoint_type: "google_drive"
    project_id: "project_123"
    user_id: "user_456"
    
    endpoint_details:
      folder_id: "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"  # Optional
      include_shared: true
      file_types: ["pdf", "docx", "xlsx", "pptx"]
    
    schedule: "interval"
    schedule_config:
      interval_minutes: 5
    
    is_active: true

  - name: "Construction Project Files"
    endpoint_type: "autodesk_construction_cloud"
    project_id: "project_123"
    user_id: "user_456"
    
    endpoint_details:
      project_id: "b.project_id_here"  # Required: Autodesk project ID
      folder_id: "folder_123"  # Optional
      include_subfolders: true
      file_types: ["dwg", "rvt", "pdf", "nwd", "nwc"]
    
    schedule: "interval"
    schedule_config:
      interval_minutes: 10
    
    is_active: true
```

#### Method 2: JSON Configuration File (`config/endpoints.json`)

```json
[
  {
    "type": "google_drive",
    "endpoint_details": {
      "folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
      "include_shared": true,
      "file_types": ["pdf", "docx", "xlsx"],
      "max_results": 1000
    },
    "project_id": "project_alpha",
    "user_id": "user_alpha",
    "schedule": "*/5 * * * *",
    "enabled": true
  },
  {
    "type": "autodesk_construction_cloud",
    "endpoint_details": {
      "project_id": "your_autodesk_project_id_here",
      "folder_id": null,
      "include_subfolders": true,
      "file_types": ["dwg", "pdf", "rvt", "ifc"],
      "max_results": 1000
    },
    "project_id": "autodesk_project_1",
    "user_id": "autodesk_user_1",
    "schedule": "*/5 * * * *",
    "enabled": true
  }
]
```

### Endpoint Configuration Parameters

#### Google Drive Endpoints

| Parameter | Required | Description | Example |
|-----------|----------|-------------|---------|
| `folder_id` | No | Specific folder to sync (if null, syncs entire drive) | `"1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"` |
| `include_shared` | No | Include shared drives and files | `true` |
| `file_types` | No | Filter by file extensions | `["pdf", "docx", "xlsx"]` |
| `max_results` | No | Maximum files per sync | `1000` |

#### Autodesk Construction Cloud Endpoints

| Parameter | Required | Description | Example |
|-----------|----------|-------------|---------|
| `project_id` | Yes | Autodesk project identifier | `"b.project_id_here"` |
| `folder_id` | No | Specific folder to sync | `"folder_123"` |
| `include_subfolders` | No | Include subfolders | `true` |
| `file_types` | No | Filter by file extensions | `["dwg", "rvt", "pdf"]` |
| `max_results` | No | Maximum files per sync | `1000` |

### Database Setup

#### Option 1: PostgreSQL (Recommended for Production)

**Using Docker:**
```bash
docker-compose up -d postgres
```

**Manual Setup:**
```sql
CREATE DATABASE connector_db;
CREATE USER connector WITH PASSWORD 'connector123';
GRANT ALL PRIVILEGES ON DATABASE connector_db TO connector;
```

#### Option 2: SQLite (Development Only)

SQLite databases are created automatically. Ensure the `data/` directory exists:

```bash
mkdir -p data/
```

The system will automatically create tables on first run.

## Running the System

### Development Mode

```bash
# Activate virtual environment
source venv/bin/activate

# Run the connector
python -m src.connector.main
```

### Production Mode with Docker

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f connector

# Stop services
docker-compose down
```

### Environment-Specific Configurations

**Development:**
```env
CONNECTOR_ENVIRONMENT=development
CONNECTOR_LOG_LEVEL=DEBUG
CONNECTOR_DATABASE_URL=sqlite:///./data/connector.db
```

**Production:**
```env
CONNECTOR_ENVIRONMENT=production
CONNECTOR_LOG_LEVEL=INFO
CONNECTOR_DATABASE_URL=postgresql://connector:password@postgres:5432/connector_db
```

## Testing Endpoints

### Quick Endpoint Test

Use the provided test script to verify your endpoints are configured correctly:

```bash
# Test all configured endpoints
python scripts/test_endpoints.py

# Test specific endpoint type
python scripts/test_endpoints.py --type google_drive

# Test with verbose output
python scripts/test_endpoints.py --verbose

# Test authentication only (no file listing)
python scripts/test_endpoints.py --auth-only
```

### Test Script Options

| Option | Description | Example |
|--------|-------------|---------|
| `--type TYPE` | Test only specific endpoint type | `--type autodesk_construction_cloud` |
| `--config CONFIG` | Use specific config file | `--config config/test-endpoints.yaml` |
| `--verbose` | Show detailed output | `--verbose` |
| `--auth-only` | Test authentication only | `--auth-only` |
| `--max-files N` | Limit files to fetch per endpoint | `--max-files 5` |

### Understanding Test Results

**✅ Authentication Success:** API credentials are valid and authentication works.

**✅ File Listing Success:** Can successfully fetch file metadata from the endpoint.

**❌ Authentication Failed:** Check your API credentials and network connectivity.

**❌ File Listing Failed:** Authentication works but file access has issues (permissions, folder IDs, etc.).

### Example Test Output

```bash
$ python scripts/test_endpoints.py --verbose

🧪 Testing File Connector Endpoints
====================================

📁 Google Drive Endpoint: Main Google Drive Folder
   ✅ Authentication successful
   ✅ File listing successful (found 42 files)
   📄 Sample files:
      - Project_Requirements.pdf (2024-01-15)
      - Design_Specifications.docx (2024-01-14)
      - Budget_Report.xlsx (2024-01-13)

🏗️  Autodesk Construction Cloud Endpoint: Construction Project Files
   ✅ Authentication successful
   ✅ File listing successful (found 18 files)
   📄 Sample files:
      - Floor_Plan_Rev_A.dwg (2024-01-16)
      - Building_Model.rvt (2024-01-15)
      - Structural_Analysis.pdf (2024-01-14)

🎉 All endpoints tested successfully!
```

## Monitoring and Troubleshooting

### Health Checks

The connector provides built-in health check endpoints:

```bash
# Check overall system health
curl http://localhost:8080/health

# Check metrics
curl http://localhost:8080/metrics
```

### Common Issues and Solutions

#### 1. Authentication Failures

**Google Drive Issues:**
- Verify service account JSON file exists and path is correct
- Ensure service account has necessary permissions
- Check that Google Drive API is enabled in Google Cloud Console

**Autodesk Issues:**
- Verify client ID and secret are correct
- Ensure your app has necessary scopes
- Check that the Autodesk project ID is valid

#### 2. Database Connection Issues

**PostgreSQL:**
```bash
# Test database connection
psql postgresql://connector:password@localhost:5432/connector_db

# Check if database exists
docker-compose exec postgres psql -U connector -l
```

**SQLite:**
```bash
# Check if file exists and is readable
ls -la data/connector.db
sqlite3 data/connector.db ".tables"
```

#### 3. File Permission Issues

- Ensure the connector has read access to all specified folders
- For Google Drive shared folders, verify sharing permissions
- For Autodesk, check project membership and role permissions

#### 4. Network and Firewall Issues

```bash
# Test API connectivity
curl -I https://www.googleapis.com
curl -I https://developer.api.autodesk.com

# Check DNS resolution
nslookup www.googleapis.com
nslookup developer.api.autodesk.com
```

### Logging

View detailed logs to troubleshoot issues:

```bash
# View application logs
tail -f logs/connector.log

# View Docker logs
docker-compose logs -f connector

# Set debug logging
export CONNECTOR_LOG_LEVEL=DEBUG
```

### Performance Tuning

Adjust these settings in `.env` for better performance:

```env
# Increase concurrent syncs for faster processing
CONNECTOR_MAX_CONCURRENT_SYNCS=20

# Adjust batch sizes in connector.yaml
scheduling:
  batch_size: 100
  max_files_per_sync: 2000
```

## Next Steps

1. **Configure Your Endpoints:** Add your specific Google Drive folders and Autodesk projects
2. **Test Connectivity:** Run the endpoint test script to verify everything works
3. **Start the Connector:** Begin synchronizing files to your database
4. **Monitor Progress:** Use health checks and logs to monitor synchronization
5. **Scale as Needed:** Add more endpoints and adjust performance settings

For advanced configuration and deployment options, see:
- [Configuration Guide](docs/CONFIGURATION_GUIDE.md)
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)
- [API Guide](docs/API_GUIDE.md)