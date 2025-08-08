# File Connector

A Python-based file synchronization connector that fetches files from external APIs (Autodesk Construction Cloud, Google Drive) and stores metadata in a database. Files are synced on a configurable schedule.

## 🚀 Quick Start

### Development Setup

1. **Prerequisites**
   ```bash
   python 3.9+
   pip
   ```

2. **Install Dependencies**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure Environment**
   ```bash
   cp env.example .env
   cp config/connector.example.yaml config/connector.yaml
   ```

4. **Set API Credentials**
   Edit `.env` with your API credentials:
   ```bash
   # Autodesk Construction Cloud
   CONNECTOR_AUTODESK_CLIENT_ID=your_client_id
   CONNECTOR_AUTODESK_CLIENT_SECRET=your_client_secret
   
   # Google Drive (optional)
   GOOGLE_CREDENTIALS_PATH=./credentials/google-service-account.json
   ```

5. **Launch in Development**
   ```bash
   python -m src.connector.main
   ```
   
   The application will start on `http://localhost:8080`
   - Health: `GET /health`
   - Status: `GET /status`

## 🔧 How It Works

### Architecture Overview
```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   API Clients   │───▶│   Sync Engine    │───▶│    Database     │
│ (Autodesk/GDrive)│    │                  │    │   (SQLite)      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐              │
         └──────────────│   Scheduler     │──────────────┘
                        │ (Every 5 mins)  │
                        └─────────────────┘
```

### Endpoint Fetching

**Where:** `src/connector/api_clients/`
- `autodesk.py` - Autodesk Construction Cloud API client
- `google_drive.py` - Google Drive API client
- `factory.py` - Creates appropriate client based on endpoint type

**How it works:**
1. **Authentication**: OAuth 2.0 flow with automatic token refresh
2. **File Discovery**: API calls to list files with filters (file types, folders, date ranges)
3. **Metadata Extraction**: Standardizes file metadata across different APIs
4. **Rate Limiting**: Built-in delays to respect API limits

**Configuration:** `config/connector.yaml`
```yaml
endpoints:
  - name: "Project 0001"
    endpoint_type: "autodesk_construction_cloud"
    project_id: "project_0001"
    user_id: "admin"
    endpoint_details:
      project_id: "b.6c2cffb0-e8c8-43d3-b415-e53f4377cedb"
      file_types: ["rvt", "dwg", "ifc", "nwd", "pdf"]
    schedule: 
      type: "interval"
      interval_minutes: 5
```

### Database Infrastructure

**Where:** `src/connector/database/`
- `models.py` - SQLAlchemy table definitions
- `service.py` - Database operations
- `operations.py` - Repository pattern for CRUD

**Current Implementation:** SQLite (placeholder for Supabase)
- **Location**: `./data/connector.db`
- **Tables**: 
  - `endpoints` - API endpoint configurations
  - `files` - File metadata from external APIs
  - `sync_logs` - Sync operation history

**Schema:**
```sql
-- File metadata table
CREATE TABLE files (
  id INTEGER PRIMARY KEY,
  endpoint_id INTEGER,
  external_file_id VARCHAR(255),
  file_name VARCHAR(500),
  file_path VARCHAR(1000),
  file_link VARCHAR(1000),
  file_size INTEGER,
  created_at DATETIME,
  updated_at DATETIME
);
```

### Scheduler System

**Where:** `src/connector/scheduler/`
- `scheduler_manager.py` - Manages multiple sync jobs
- `job_scheduler.py` - Individual job execution

**How it works:**
1. **Initialization**: Reads endpoint configs from database
2. **Job Creation**: Creates APScheduler jobs for each active endpoint
3. **Execution**: Runs sync jobs on configured intervals (default: 5 minutes)
4. **Monitoring**: Health checks and job status tracking

**Schedule Types:**
- `interval` - Fixed intervals (e.g., every 5 minutes)
- `cron` - Cron-style scheduling
- `manual` - Manual trigger only

## 📊 Monitoring

### Health Endpoints
- `GET /health` - Basic health check
- `GET /status` - Detailed system status including database and scheduler

### Logs
- **Location**: `./logs/connector.log`
- **Format**: Structured JSON with timestamps
- **Levels**: DEBUG, INFO, WARNING, ERROR

## 🐳 Deployment

### Docker (Simple)
```bash
# Build image
docker build -t file-connector .

# Run container
docker run -d \
  -p 8080:8080 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -e CONNECTOR_AUTODESK_CLIENT_ID=your_id \
  -e CONNECTOR_AUTODESK_CLIENT_SECRET=your_secret \
  file-connector
```

### Docker Compose (Recommended)
```bash
# Development environment
docker-compose -f docker-compose.dev.yml up

# Production environment  
docker-compose up -d
```

### Manual Deployment
1. Install Python 3.9+ on target system
2. Copy project files
3. Set environment variables
4. Run: `python -m src.connector.main`

## 🔧 Configuration

### Environment Variables
```bash
# Database
DATABASE_URL=sqlite:///./data/connector.db

# Autodesk ACC
CONNECTOR_AUTODESK_CLIENT_ID=your_client_id
CONNECTOR_AUTODESK_CLIENT_SECRET=your_client_secret
CONNECTOR_AUTODESK_BASE_URL=https://developer.api.autodesk.com

# Google Drive
GOOGLE_CREDENTIALS_PATH=./credentials/google-service-account.json

# Scheduling
SYNC_INTERVAL_MINUTES=5
MAX_CONCURRENT_SYNCS=5

# Logging
CONNECTOR_LOG_LEVEL=INFO
```

### Adding New Endpoints

1. **Add to config file** (`config/connector.yaml`):
   ```yaml
   endpoints:
     - name: "My New Endpoint"
       endpoint_type: "autodesk_construction_cloud"
       project_id: "my_project"
       user_id: "my_user"
       endpoint_details:
         project_id: "autodesk_project_id"
         folder_id: "specific_folder_id"  # optional
         file_types: ["dwg", "pdf"]
   ```

2. **Restart application** - Config is synced to database on startup

## 🧪 Testing

### Manual Testing
```bash
# Test specific endpoint
python scripts/test_endpoints.py --type autodesk_construction_cloud --max-files 5

# Test OAuth flow
python scripts/test_oauth.py
```

### Unit Tests
```bash
# Run remaining essential tests
python -m pytest tests/ -v
```

## 📁 Project Structure

```
connector/
├── src/connector/           # Main application code
│   ├── api_clients/        # API integrations (Autodesk, Google Drive)
│   ├── auth/              # OAuth authentication handlers
│   ├── config/            # Configuration management
│   ├── core/              # Core business logic (FileConnector, SyncEngine)
│   ├── database/          # Database models and operations
│   ├── scheduler/         # Job scheduling and management
│   ├── utils/             # Utilities (logging, etc.)
│   └── main.py            # Application entry point
├── tests/                 # Essential unit tests
├── scripts/               # Utility scripts
├── config/                # Configuration files
├── data/                  # SQLite database
├── logs/                  # Application logs
└── tokens/                # OAuth tokens (auto-generated)
```

## 🔧 Development

### Key Files
- `src/connector/main.py` - Application entry point and web server
- `src/connector/core/sync_engine.py` - Core sync logic
- `src/connector/scheduler/scheduler_manager.py` - Job scheduling
- `config/connector.yaml` - Endpoint and schedule configuration

### OAuth Setup
1. **Autodesk**: Follow `OAUTH_SETUP.md` for APS app setup
2. **Google Drive**: Set up service account and download credentials JSON

### Extending the System
- **New API clients**: Inherit from `BaseAPIClient` in `src/connector/api_clients/`
- **Custom sync logic**: Modify `SyncEngine` in `src/connector/core/`
- **Database changes**: Update models in `src/connector/database/models.py`

---

For detailed OAuth setup instructions, see `OAUTH_SETUP.md`.