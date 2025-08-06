# API Integration Guide

This guide explains how to integrate new API clients into the File Connector system and provides detailed documentation for existing integrations.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Implementing New API Clients](#implementing-new-api-clients)
- [Existing API Clients](#existing-api-clients)
- [Authentication Patterns](#authentication-patterns)
- [Error Handling](#error-handling)
- [Testing API Clients](#testing-api-clients)
- [Best Practices](#best-practices)

## Architecture Overview

The File Connector uses a plugin-based architecture for API clients, allowing easy integration of new cloud storage platforms while maintaining consistent behavior and error handling.

```
┌─────────────────────────────────────────────────────────────┐
│                    APIClientFactory                        │
├─────────────────────────────────────────────────────────────┤
│  create_client(type, endpoint_details, **kwargs)           │
│  register_client(type, client_class)                       │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────▼─────────────┐
        │      BaseAPIClient        │
        │    (Abstract Base)        │
        ├───────────────────────────┤
        │ + authenticate()          │
        │ + list_files()           │
        │ + get_sync_info()        │
        │ + health_check()         │
        └─────────────┬─────────────┘
                      │
         ┌────────────┼────────────┐
         │            │            │
┌────────▼────┐ ┌─────▼─────┐ ┌───▼───────┐
│GoogleDrive  │ │  Autodesk │ │  Future   │
│   Client    │ │  Client   │ │  Clients  │
└─────────────┘ └───────────┘ └───────────┘
```

### Core Components

1. **BaseAPIClient**: Abstract base class defining the interface all API clients must implement
2. **APIClientFactory**: Factory class for creating and registering API client instances
3. **FileMetadata**: Standardized data model for file information across all platforms
4. **Exception Classes**: Unified error handling for authentication, rate limiting, and connection issues

## Implementing New API Clients

### Step 1: Create Client Class

Create a new file in `src/connector/api_clients/` (e.g., `dropbox.py`):

```python
"""Dropbox API client implementation."""

import asyncio
from typing import Dict, Any, Optional, AsyncGenerator
from datetime import datetime, timezone

from .base import BaseAPIClient, FileMetadata, RateLimitError, AuthenticationError, APIConnectionError
from ..utils.logging import log_async_execution_time
from ..performance import get_metrics_collector

class DropboxClient(BaseAPIClient):
    """Dropbox API client for file synchronization."""
    
    def __init__(self, endpoint_details: Dict[str, Any], **kwargs):
        """Initialize Dropbox client.
        
        Args:
            endpoint_details: Configuration for this endpoint
            **kwargs: Additional configuration parameters
        """
        super().__init__(endpoint_details, **kwargs)
        
        # Extract Dropbox-specific configuration
        self.access_token = endpoint_details.get("access_token")
        self.folder_path = endpoint_details.get("folder_path", "")
        self.include_deleted = endpoint_details.get("include_deleted", False)
        
        # Performance components
        self.metrics = get_metrics_collector()
        
        # Dropbox API configuration
        self.api_base_url = "https://api.dropboxapi.com/2"
        self.content_base_url = "https://content.dropboxapi.com/2"
        
        self.logger.info(
            "Dropbox client initialized",
            folder_path=self.folder_path,
            include_deleted=self.include_deleted
        )
    
    async def authenticate(self) -> bool:
        """Authenticate with Dropbox API."""
        if not self.access_token:
            raise AuthenticationError("Dropbox access token not provided")
        
        try:
            # Test authentication with a simple API call
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            # Use connection pool for HTTP requests
            from ..performance import get_connection_pool_manager
            pool_manager = get_connection_pool_manager()
            
            async with pool_manager.request(
                "POST", 
                f"{self.api_base_url}/users/get_current_account",
                service_type="dropbox",
                headers=headers,
                json=None
            ) as response:
                if response.status == 200:
                    user_info = await response.json()
                    self._authenticated = True
                    self.logger.info(
                        "Dropbox authentication successful",
                        user_email=user_info.get("email")
                    )
                    return True
                else:
                    error_data = await response.json()
                    raise AuthenticationError(f"Dropbox auth failed: {error_data}")
                    
        except Exception as e:
            self.logger.error("Dropbox authentication failed", error=str(e))
            raise AuthenticationError(f"Authentication failed: {e}")
    
    @log_async_execution_time
    async def list_files(
        self,
        since: Optional[datetime] = None,
        max_results: Optional[int] = None
    ) -> AsyncGenerator[FileMetadata, None]:
        """List files from Dropbox.
        
        Args:
            since: Only return files modified after this datetime
            max_results: Maximum number of files to return
            
        Yields:
            FileMetadata objects for each file found
        """
        if not self._authenticated:
            await self.authenticate()
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        cursor = None
        files_returned = 0
        target_max = max_results or float('inf')
        
        self.logger.info(
            "Starting Dropbox file listing",
            folder_path=self.folder_path,
            since=since,
            max_results=max_results
        )
        
        try:
            while files_returned < target_max:
                # Build request payload
                if cursor:
                    # Continue previous request
                    payload = {"cursor": cursor}
                    endpoint = f"{self.api_base_url}/files/list_folder/continue"
                else:
                    # Initial request
                    payload = {
                        "path": self.folder_path,
                        "recursive": True,
                        "include_deleted": self.include_deleted,
                        "include_has_explicit_shared_members": True
                    }
                    endpoint = f"{self.api_base_url}/files/list_folder"
                
                # Execute API request with rate limiting and metrics
                async with self.rate_limiter.limit():
                    async with self.metrics.time_operation(
                        "dropbox.api_request",
                        tags={"operation": "list_folder"}
                    ):
                        from ..performance import get_connection_pool_manager
                        pool_manager = get_connection_pool_manager()
                        
                        async with pool_manager.request(
                            "POST",
                            endpoint,
                            service_type="dropbox",
                            headers=headers,
                            json=payload
                        ) as response:
                            if response.status == 200:
                                result = await response.json()
                            elif response.status == 429:
                                # Rate limit handling
                                retry_after = int(response.headers.get("Retry-After", 60))
                                self.metrics.increment_counter("dropbox.rate_limit_errors")
                                raise RateLimitError("Dropbox rate limit exceeded", retry_after)
                            else:
                                error_data = await response.json()
                                self.metrics.increment_counter("dropbox.api_errors")
                                raise APIConnectionError(f"Dropbox API error: {error_data}")
                
                # Record successful API call
                self.metrics.increment_counter("dropbox.api_calls")
                
                # Process files
                for entry in result.get("entries", []):
                    if files_returned >= target_max:
                        break
                    
                    # Skip folders
                    if entry.get(".tag") != "file":
                        continue
                    
                    # Apply date filter if specified
                    if since:
                        file_modified = datetime.fromisoformat(
                            entry["server_modified"].replace("Z", "+00:00")
                        )
                        if file_modified <= since:
                            continue
                    
                    try:
                        file_metadata = self._convert_to_file_metadata(entry)
                        yield file_metadata
                        files_returned += 1
                        self.metrics.increment_counter("dropbox.files_processed")
                        
                    except Exception as e:
                        self.logger.warning(
                            "Failed to process Dropbox file metadata",
                            file_id=entry.get("id"),
                            error=str(e)
                        )
                        self.metrics.increment_counter("dropbox.processing_errors")
                        continue
                
                # Check for more pages
                cursor = result.get("cursor")
                has_more = result.get("has_more", False)
                
                if not has_more:
                    break
                    
        except Exception as e:
            self.logger.error("Error listing Dropbox files", error=str(e))
            raise APIConnectionError(f"Error listing files: {e}")
    
    def _convert_to_file_metadata(self, file_data: Dict[str, Any]) -> FileMetadata:
        """Convert Dropbox file data to FileMetadata format.
        
        Args:
            file_data: Raw file data from Dropbox API
            
        Returns:
            FileMetadata object
        """
        # Parse timestamps
        date_created = datetime.fromisoformat(
            file_data["client_modified"].replace("Z", "+00:00")
        )
        date_updated = datetime.fromisoformat(
            file_data["server_modified"].replace("Z", "+00:00")
        )
        
        # Generate file link (temporary link)
        file_link = f"https://www.dropbox.com/home{file_data['path_display']}"
        
        return FileMetadata(
            external_id=file_data["id"],
            title=file_data["name"],
            file_link=file_link,
            date_created=date_created,
            date_updated=date_updated,
            project_id=self.endpoint_details.get("project_id", ""),
            user_id=self.endpoint_details.get("user_id", ""),
            metadata={
                "size": file_data.get("size"),
                "path": file_data["path_display"],
                "content_hash": file_data.get("content_hash"),
                "rev": file_data.get("rev")
            }
        )
    
    async def get_sync_info(self) -> Dict[str, Any]:
        """Get information about the sync process."""
        return {
            "last_sync": None,  # TODO: Implement last sync tracking
            "api_quota_remaining": None,  # Dropbox doesn't expose quota in API
            "rate_limit_reset": None,
            "folder_path": self.folder_path,
            "include_deleted": self.include_deleted
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on Dropbox connection."""
        try:
            if not self._authenticated:
                await self.authenticate()
            
            return {
                "status": "healthy",
                "authenticated": self._authenticated,
                "folder_path": self.folder_path
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "authenticated": False
            }
```

### Step 2: Register Client in Factory

Update `src/connector/api_clients/factory.py`:

```python
from .dropbox import DropboxClient

class APIClientFactory:
    """Factory for creating API client instances."""
    
    _clients = {
        "google_drive": GoogleDriveClient,
        "autodesk": AutodeskConstructionCloudClient,
        "dropbox": DropboxClient,  # Add new client
    }
```

### Step 3: Update Package Exports

Update `src/connector/api_clients/__init__.py`:

```python
from .dropbox import DropboxClient

__all__ = [
    "BaseAPIClient",
    "FileMetadata", 
    "GoogleDriveClient",
    "AutodeskConstructionCloudClient",
    "DropboxClient",  # Add new client
    "APIClientFactory",
    # Exception classes
    "RateLimitError",
    "AuthenticationError", 
    "APIConnectionError",
]
```

### Step 4: Create Tests

Create `tests/test_dropbox_client.py`:

```python
"""Tests for Dropbox API client."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from connector.api_clients import DropboxClient, APIClientFactory
from connector.api_clients.base import FileMetadata, AuthenticationError, RateLimitError


class TestDropboxClient:
    """Test Dropbox API client functionality."""
    
    @pytest.fixture
    def endpoint_details(self):
        """Dropbox endpoint configuration."""
        return {
            "access_token": "test_access_token",
            "folder_path": "/test_folder",
            "include_deleted": False,
            "project_id": "test_project",
            "user_id": "test_user"
        }
    
    @pytest.fixture
    def dropbox_client(self, endpoint_details):
        """Create Dropbox client instance."""
        return DropboxClient(endpoint_details)
    
    @pytest.mark.asyncio
    async def test_authentication_success(self, dropbox_client):
        """Test successful authentication."""
        with patch('connector.performance.get_connection_pool_manager') as mock_pool:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"email": "test@example.com"})
            
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_pool.return_value.request.return_value = mock_context
            
            result = await dropbox_client.authenticate()
            
            assert result is True
            assert dropbox_client._authenticated is True
    
    @pytest.mark.asyncio
    async def test_list_files(self, dropbox_client):
        """Test file listing functionality."""
        # Mock authentication
        dropbox_client._authenticated = True
        
        # Mock API response
        mock_api_response = {
            "entries": [
                {
                    ".tag": "file",
                    "id": "file_1",
                    "name": "test_file.pdf",
                    "path_display": "/test_folder/test_file.pdf",
                    "client_modified": "2023-01-01T00:00:00Z",
                    "server_modified": "2023-01-01T00:00:00Z",
                    "size": 1024,
                    "content_hash": "abc123",
                    "rev": "rev123"
                }
            ],
            "cursor": None,
            "has_more": False
        }
        
        with patch('connector.performance.get_connection_pool_manager') as mock_pool:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_api_response)
            
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=mock_response)
            mock_context.__aexit__ = AsyncMock(return_value=None)
            
            mock_pool.return_value.request.return_value = mock_context
            
            # Test file listing
            files = []
            async for file_metadata in dropbox_client.list_files():
                files.append(file_metadata)
            
            assert len(files) == 1
            assert files[0].external_id == "file_1"
            assert files[0].title == "test_file.pdf"
            assert files[0].project_id == "test_project"
    
    def test_factory_registration(self, endpoint_details):
        """Test that client is properly registered in factory."""
        factory = APIClientFactory()
        client = factory.create_client("dropbox", endpoint_details)
        
        assert isinstance(client, DropboxClient)
        assert client.folder_path == "/test_folder"
```

## Existing API Clients

### Google Drive Client

**Authentication**: Service Account with JSON key file
**Capabilities**:
- List files from specific folders or entire drive
- Support for shared drives and permissions
- File type filtering by extension or MIME type
- Automatic pagination with configurable page sizes
- Export links for Google Workspace files

**Configuration Example**:
```yaml
endpoints:
  - type: google_drive
    name: "Engineering Files"
    endpoint_details:
      folder_id: "1a2b3c4d5e6f"  # Optional, null for root
      include_shared: true
      file_types: ["pdf", "dwg", "docx"]
      max_results: 1000
    credentials_path: "/path/to/service-account.json"
```

### Autodesk Construction Cloud Client

**Authentication**: OAuth 2.0 Client Credentials
**Capabilities**:
- Project-based file access
- CAD/BIM file type filtering
- Version tracking and metadata
- Construction-specific file formats (DWG, RVT, IFC)
- Project hierarchy navigation

**Configuration Example**:
```yaml
endpoints:
  - type: autodesk
    name: "Construction Project"
    endpoint_details:
      project_id: "b.abc123"
      folder_id: "urn:adsk.wipprod:fs.folder:co.xyz789"
      file_types: ["dwg", "rvt", "pdf", "ifc"]
    client_id: "${AUTODESK_CLIENT_ID}"
    client_secret: "${AUTODESK_CLIENT_SECRET}"
```

## Authentication Patterns

### OAuth 2.0 Client Credentials Flow

Used by Autodesk Construction Cloud:

```python
async def authenticate(self) -> bool:
    """Authenticate using OAuth 2.0 client credentials."""
    
    token_url = f"{self.base_url}/authentication/v1/authenticate"
    
    payload = {
        "client_id": self.client_id,
        "client_secret": self.client_secret,
        "grant_type": "client_credentials",
        "scope": "data:read"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=payload) as response:
            if response.status == 200:
                token_data = await response.json()
                self.access_token = token_data["access_token"]
                self.token_expires = datetime.now() + timedelta(
                    seconds=token_data["expires_in"]
                )
                return True
            else:
                raise AuthenticationError("OAuth authentication failed")
```

### Service Account Authentication

Used by Google Drive:

```python
async def authenticate(self) -> bool:
    """Authenticate using service account credentials."""
    
    credentials = service_account.Credentials.from_service_account_file(
        self.credentials_path,
        scopes=self.scopes
    )
    
    self.service = build('drive', 'v3', credentials=credentials)
    self._authenticated = True
    
    return True
```

### Bearer Token Authentication

Used by Dropbox and similar services:

```python
async def authenticate(self) -> bool:
    """Authenticate using bearer token."""
    
    headers = {
        "Authorization": f"Bearer {self.access_token}",
        "Content-Type": "application/json"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{self.api_base_url}/users/get_current_account",
            headers=headers
        ) as response:
            if response.status == 200:
                self._authenticated = True
                return True
            else:
                raise AuthenticationError("Bearer token authentication failed")
```

## Error Handling

All API clients should implement consistent error handling:

### Rate Limiting

```python
if response.status == 429:
    retry_after = int(response.headers.get("Retry-After", 60))
    self.metrics.increment_counter(f"{client_type}.rate_limit_errors")
    raise RateLimitError("Rate limit exceeded", retry_after)
```

### Authentication Errors

```python
if response.status in [401, 403]:
    self.metrics.increment_counter(f"{client_type}.auth_errors")
    raise AuthenticationError("Authentication failed")
```

### Connection Errors

```python
try:
    async with session.get(url) as response:
        # Process response
        pass
except aiohttp.ClientError as e:
    self.metrics.increment_counter(f"{client_type}.connection_errors")
    raise APIConnectionError(f"Connection error: {e}")
```

## Testing API Clients

### Mock HTTP Responses

```python
@pytest.mark.asyncio
async def test_api_call_with_mock():
    """Test API call with mocked HTTP response."""
    
    with patch('aiohttp.ClientSession') as mock_session_class:
        mock_session = AsyncMock()
        mock_session_class.return_value = mock_session
        
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"result": "success"})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)
        
        mock_session.get.return_value = mock_response
        
        # Test the client
        client = MyAPIClient(endpoint_details)
        result = await client.some_api_call()
        
        assert result["result"] == "success"
```

### Integration Tests

```python
@pytest.mark.integration
async def test_real_api_integration():
    """Test with real API (requires credentials)."""
    
    if not os.getenv("API_CREDENTIALS_AVAILABLE"):
        pytest.skip("Real API credentials not available")
    
    client = MyAPIClient(real_endpoint_details)
    await client.authenticate()
    
    files = []
    async for file_metadata in client.list_files(max_results=5):
        files.append(file_metadata)
    
    assert len(files) <= 5
    assert all(isinstance(f, FileMetadata) for f in files)
```

## Best Practices

### 1. Performance Optimization

- **Use Connection Pooling**: Leverage the global connection pool manager
- **Implement Rate Limiting**: Respect API rate limits with exponential backoff
- **Batch Operations**: Process files in batches for efficiency
- **Async Patterns**: Use async/await throughout for non-blocking operations

### 2. Error Handling

- **Specific Exceptions**: Use appropriate exception types for different errors
- **Retry Logic**: Implement retry with exponential backoff for transient errors
- **Circuit Breakers**: Use circuit breaker pattern for reliability
- **Comprehensive Logging**: Log errors with context for debugging

### 3. Security

- **Credential Management**: Use environment variables for sensitive data
- **Token Refresh**: Implement automatic token refresh for OAuth flows
- **Input Validation**: Validate all configuration parameters
- **Secure Defaults**: Use secure defaults for all configuration options

### 4. Monitoring

- **Metrics Collection**: Record performance and error metrics
- **Health Checks**: Implement health check endpoints
- **Structured Logging**: Use structured logging with correlation IDs
- **Performance Tracking**: Track API response times and success rates

### 5. Testing

- **Unit Tests**: Test individual methods with mocked dependencies
- **Integration Tests**: Test with real APIs when possible
- **Error Scenarios**: Test error conditions and edge cases
- **Performance Tests**: Validate performance characteristics

### 6. Documentation

- **Configuration Examples**: Provide clear configuration examples
- **API Reference**: Document all public methods and parameters
- **Error Codes**: Document possible errors and their meanings
- **Migration Guides**: Provide migration guides for breaking changes