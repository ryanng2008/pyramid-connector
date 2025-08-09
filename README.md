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
   Edit `config/connector.yaml` with your API credentials:
   ```yaml
   clients:
     autodesk:
       client_id: "your_client_id"
       client_secret: "your_client_secret"
       base_url: "https://developer.api.autodesk.com"
       callback_url: "http://localhost:8081/oauth/callback"
     google_drive:
       credentials_path: "./credentials/google-service-account.json"
       application_name: "File Connector"
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

# Scheduling
SYNC_INTERVAL_MINUTES=5
MAX_CONCURRENT_SYNCS=5

# Logging
CONNECTOR_LOG_LEVEL=INFO
```

**Note**: API credentials are now configured in `config/connector.yaml` under the `clients:` section for better multi-client support.

### Adding New Endpoints

1. **Add client credentials and endpoint to config file** (`config/connector.yaml`):
   ```yaml
   clients:
     autodesk:
       client_id: "your_client_id"
       client_secret: "your_client_secret"
       base_url: "https://developer.api.autodesk.com"
       callback_url: "http://localhost:8081/oauth/callback"
   
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

### Adding New Autodesk Endpoint

To add a new Autodesk Construction Cloud endpoint, you need to set up OAuth 2.0 credentials and configure the endpoint:

#### 1. **Get Autodesk APS Credentials**

1. **Create APS App**: Go to [Autodesk Platform Services](https://aps.autodesk.com/)
2. **Create new app** with these settings:
   - **App Type**: Web App
   - **Callback URL**: `http://localhost:8081/oauth/callback` (note: port 8081, not 8080)
   - **API Access**: Data Management API, Construction Cloud API
3. **Get credentials**: Note your `Client ID` and `Client Secret`

#### 2. **Configure Credentials**

Add your credentials directly to `config/connector.yaml` (we'll make this more secure later):
```yaml
# Global client configurations
clients:
  autodesk:
    client_id: "your_client_id_here"
    client_secret: "your_client_secret_here"
    base_url: "https://developer.api.autodesk.com"
    callback_url: "http://localhost:8081/oauth/callback"
```

#### 3. **Get Project ID**

You need the Autodesk project ID (starts with `b.`):
- **Option A**: Use Autodesk Construction Cloud web interface → Copy project ID from URL
- **Option B**: Use the test script: `python scripts/test_endpoints.py --type autodesk_construction_cloud --list-projects`

#### 4. **Add Endpoint Configuration**

Complete your `config/connector.yaml` with both client config and endpoints:
```yaml
# Global client configurations
clients:
  autodesk:
    client_id: "your_client_id_here"
    client_secret: "your_client_secret_here" 
    base_url: "https://developer.api.autodesk.com"
    callback_url: "http://localhost:8081/oauth/callback"
  google_drive:
    credentials_path: "./credentials/google-service-account.json"
    application_name: "File Connector"

# Individual endpoints
endpoints:
  - name: "My Project Name"                    # Human-readable name
    endpoint_type: "autodesk_construction_cloud"
    project_id: "my_project_001"              # Internal project identifier
    user_id: "admin"                          # Internal user identifier
    endpoint_details:
      project_id: "b.6c2cffb0-e8c8-43d3-b415-e53f4377cedb"  # Autodesk project ID
      folder_id: null                         # Optional: specific folder ID
      file_types: ["rvt", "dwg", "ifc", "nwd", "pdf"]      # File types to sync
      include_subfolders: true                # Include subfolders
    schedule:
      type: "interval"                        # Schedule type
      interval_minutes: 5                     # Sync every 5 minutes
    is_active: true                           # Enable this endpoint

  # Add more endpoints for different clients/projects
  - name: "Another Project"
    endpoint_type: "autodesk_construction_cloud"
    project_id: "project_002"
    user_id: "user2"
    endpoint_details:
      project_id: "b.another-project-id-here"
      file_types: ["dwg", "pdf"]
    schedule:
      type: "interval"
      interval_minutes: 10
    is_active: true
```

#### 5. **Complete 3-Legged OAuth Flow**

The first time you run the connector, it will need to authenticate:

1. **Start the connector**: `python -m src.connector.main`
2. **Wait for sync trigger** (or run manually): The system will detect missing tokens
3. **Follow the authentication flow**:
   ```
   ================================================
   AUTODESK AUTHENTICATION REQUIRED
   ================================================
   Please visit the following URL to authorize the application:
   
   https://developer.api.autodesk.com/authentication/v1/authorize?...
   
   Waiting for authentication... (this window will auto-close)
   ================================================
   ```
4. **Click the URL** → Log in to Autodesk → Grant permissions
5. **Tokens saved automatically** to `tokens/autodesk_tokens.json`

#### 6. **Verify Setup**

Test your endpoint:
```bash
# Test authentication and file listing
python scripts/test_endpoints.py --type autodesk_construction_cloud --max-files 5

# Check logs for successful sync
tail -f logs/connector.log | grep -i autodesk
```

#### 7. **Token Management**

- **Automatic refresh**: Tokens refresh automatically when expired
- **Token location**: `tokens/autodesk_tokens.json`
- **Re-authentication**: Delete token file to force re-authentication
- **Token expires**: If not used for ~1 hour, you may need to re-authenticate

#### Troubleshooting

**Common Issues:**
- **Port conflict**: Make sure port 8081 is free for OAuth callback
- **Wrong callback URL**: Must match exactly in APS app settings
- **Project access**: Ensure your Autodesk account has access to the project
- **API permissions**: Verify your APS app has Data Management + Construction Cloud access

**Test Commands:**
```bash
# Test OAuth flow specifically
python scripts/test_oauth.py

# Test with verbose logging
CONNECTOR_LOG_LEVEL=DEBUG python scripts/test_endpoints.py --type autodesk_construction_cloud --verbose
```

### OAuth Setup
1. **Autodesk**: Follow steps above for APS app setup
2. **Google Drive**: Set up service account and download credentials JSON

### Extending the System
- **New API clients**: Inherit from `BaseAPIClient` in `src/connector/api_clients/`
- **Custom sync logic**: Modify `SyncEngine` in `src/connector/core/`
- **Database changes**: Update models in `src/connector/database/models.py`

---

For detailed OAuth setup instructions, see `OAUTH_SETUP.md`.