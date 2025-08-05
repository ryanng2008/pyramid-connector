# File Connector

A Python-based connector that periodically fetches files from cloud storage APIs and synchronizes metadata to a database.

## Features

- **Multi-API Support**: Google Drive and Autodesk Construction Cloud APIs
- **Automated Sync**: Scheduled synchronization every 5 minutes
- **Parallel Processing**: Concurrent handling of multiple endpoints
- **Extensible**: Easy to add new API connectors
- **Cloud Ready**: Containerized for cloud deployment

## Project Structure

```
connector/
├── src/connector/           # Main application code
│   ├── api_clients/        # API client implementations
│   ├── database/           # Database models and operations
│   ├── core/              # Core business logic
│   ├── config/            # Configuration management
│   └── utils/             # Utility functions
├── tests/                 # Test files
│   ├── unit/             # Unit tests
│   └── integration/      # Integration tests
├── data/                 # Database files
├── secrets/              # API credentials
└── logs/                 # Application logs
```

## Quick Start

1. **Clone and Setup**:
   ```bash
   git clone <repository>
   cd connector
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   pip install -r requirements.txt
   ```

2. **Configure Environment**:
   ```bash
   cp env.example .env
   # Edit .env with your API credentials
   ```

3. **Setup API Credentials**:
   - Place Google service account JSON in `secrets/google_service_account.json`
   - Configure Autodesk Construction Cloud OAuth credentials in `.env`

4. **Run the Application**:
   ```bash
   python -m src.connector.main
   ```

## Configuration

### Environment Variables

See `env.example` for all available configuration options.

### Endpoints Configuration

Create `config/endpoints.json` to define sync endpoints:

```json
[
  {
    "type": "google_drive",
    "endpoint_details": {
      "folder_id": null,
      "include_shared": true
    },
    "project_id": "project_1",
    "user_id": "user_1",
    "schedule": "*/5 * * * *"
  }
]
```

## Development

### Setup Development Environment

```bash
pip install -r requirements.txt
pre-commit install
```

### Running Tests

```bash
pytest tests/
```

### Code Formatting

```bash
black src/ tests/
flake8 src/ tests/
mypy src/
```

## Deployment

### Docker

```bash
docker build -t file-connector .
docker run file-connector
```

### Environment Variables for Production

Set the following environment variables in your production environment:
- `DATABASE_URL`
- `GOOGLE_CREDENTIALS_PATH`
- `AUTODESK_CLIENT_ID`
- `AUTODESK_CLIENT_SECRET`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

## API Documentation

### Supported APIs

1. **Google Drive API v3**
   - File listing with metadata
   - Folder traversal
   - Shared file access

2. **Autodesk Construction Cloud API**
   - Project file access
   - Folder structure navigation
   - File metadata extraction

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run the test suite
6. Submit a pull request

## License

MIT License - see LICENSE file for details.