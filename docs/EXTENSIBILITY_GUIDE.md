# Extensibility Guide

The File Connector is designed with extensibility as a core principle. This guide explains how to extend the system with new features, API integrations, data sources, and custom functionality.

## Table of Contents

- [Architecture for Extensibility](#architecture-for-extensibility)
- [Adding New API Clients](#adding-new-api-clients)
- [Custom File Processors](#custom-file-processors)
- [Database Extensions](#database-extensions)
- [Scheduling Extensions](#scheduling-extensions)
- [Performance Optimizations](#performance-optimizations)
- [Plugin System](#plugin-system)
- [Configuration Extensions](#configuration-extensions)
- [Monitoring Extensions](#monitoring-extensions)
- [Testing Extensions](#testing-extensions)

## Architecture for Extensibility

The File Connector follows several design patterns that enable easy extension:

### 1. Plugin Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Core Framework                           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │   Factory   │ │  Registry   │ │  Interface  │          │
│  │   Pattern   │ │   Pattern   │ │   Pattern   │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
├─────────────────────────────────────────────────────────────┤
│                    Plugin Layers                           │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │ API Clients │ │ Processors  │ │ Schedulers  │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │  Databases  │ │  Monitors   │ │   Filters   │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

### 2. Interface-Based Design

All major components implement well-defined interfaces:

```python
# Abstract base classes define contracts
class BaseAPIClient(ABC):
    @abstractmethod
    async def authenticate(self) -> bool: ...
    
    @abstractmethod
    async def list_files(self) -> AsyncGenerator[FileMetadata, None]: ...

class BaseProcessor(ABC):
    @abstractmethod
    async def process(self, file_metadata: FileMetadata) -> ProcessResult: ...

class BaseScheduler(ABC):
    @abstractmethod
    async def schedule_job(self, job: Job) -> str: ...
```

### 3. Dependency Injection

Components are loosely coupled through dependency injection:

```python
class SyncEngine:
    def __init__(
        self,
        database_service: DatabaseService,
        api_client_factory: APIClientFactory,
        processor_registry: ProcessorRegistry,
        metrics_collector: MetricsCollector
    ):
        self.db_service = database_service
        self.api_factory = api_client_factory
        self.processors = processor_registry
        self.metrics = metrics_collector
```

## Adding New API Clients

### Step-by-Step Implementation

#### 1. Define the Client Class

Create `src/connector/api_clients/sharepoint.py`:

```python
"""Microsoft SharePoint API client implementation."""

import asyncio
from typing import Dict, Any, Optional, AsyncGenerator
from datetime import datetime, timezone
import aiohttp
from msal import ConfidentialClientApplication

from .base import BaseAPIClient, FileMetadata, RateLimitError, AuthenticationError, APIConnectionError
from ..utils.logging import log_async_execution_time
from ..performance import get_metrics_collector, get_connection_pool_manager


class SharePointClient(BaseAPIClient):
    """Microsoft SharePoint API client for file synchronization."""
    
    def __init__(self, endpoint_details: Dict[str, Any], **kwargs):
        """Initialize SharePoint client.
        
        Args:
            endpoint_details: Configuration including tenant_id, client_id, etc.
            **kwargs: Additional configuration parameters
        """
        super().__init__(endpoint_details, **kwargs)
        
        # SharePoint-specific configuration
        self.tenant_id = endpoint_details["tenant_id"]
        self.client_id = endpoint_details["client_id"]
        self.client_secret = endpoint_details["client_secret"]
        self.site_url = endpoint_details["site_url"]
        self.document_library = endpoint_details.get("document_library", "Documents")
        
        # Microsoft Graph API configuration
        self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        self.scope = ["https://graph.microsoft.com/.default"]
        self.graph_endpoint = "https://graph.microsoft.com/v1.0"
        
        # MSAL client for authentication
        self.msal_client = ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=self.authority
        )
        
        self.access_token = None
        self.token_expires_at = None
        
        # Performance components
        self.metrics = get_metrics_collector()
        self.pool_manager = get_connection_pool_manager()
        
        self.logger.info(
            "SharePoint client initialized",
            tenant_id=self.tenant_id,
            site_url=self.site_url,
            document_library=self.document_library
        )
    
    async def authenticate(self) -> bool:
        """Authenticate with Microsoft Graph API using client credentials."""
        try:
            # Use MSAL to acquire token
            result = self.msal_client.acquire_token_for_client(scopes=self.scope)
            
            if "access_token" in result:
                self.access_token = result["access_token"]
                self.token_expires_at = datetime.now() + timedelta(seconds=result["expires_in"])
                self._authenticated = True
                
                self.logger.info("SharePoint authentication successful")
                return True
            else:
                error_msg = result.get("error_description", "Unknown authentication error")
                raise AuthenticationError(f"SharePoint authentication failed: {error_msg}")
                
        except Exception as e:
            self.logger.error("SharePoint authentication failed", error=str(e))
            raise AuthenticationError(f"Authentication failed: {e}")
    
    async def _ensure_authenticated(self):
        """Ensure we have a valid access token."""
        if not self._authenticated or (
            self.token_expires_at and 
            datetime.now() >= self.token_expires_at - timedelta(minutes=5)
        ):
            await self.authenticate()
    
    @log_async_execution_time
    async def list_files(
        self,
        since: Optional[datetime] = None,
        max_results: Optional[int] = None
    ) -> AsyncGenerator[FileMetadata, None]:
        """List files from SharePoint document library."""
        await self._ensure_authenticated()
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        # Build Microsoft Graph API endpoint
        site_id = await self._get_site_id()
        drive_id = await self._get_drive_id(site_id)
        
        # Construct filter for date-based queries
        filter_query = ""
        if since:
            since_iso = since.isoformat()
            filter_query = f"?$filter=lastModifiedDateTime gt {since_iso}"
        
        endpoint = f"{self.graph_endpoint}/sites/{site_id}/drives/{drive_id}/root/children{filter_query}"
        
        files_returned = 0
        target_max = max_results or float('inf')
        
        self.logger.info(
            "Starting SharePoint file listing",
            site_url=self.site_url,
            since=since,
            max_results=max_results
        )
        
        try:
            while endpoint and files_returned < target_max:
                async with self.pool_manager.request(
                    "GET",
                    endpoint,
                    service_type="sharepoint",
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        self.metrics.increment_counter("sharepoint.api_calls")
                        
                        # Process files
                        for item in data.get("value", []):
                            if files_returned >= target_max:
                                break
                            
                            # Skip folders
                            if "folder" in item:
                                continue
                            
                            try:
                                file_metadata = self._convert_to_file_metadata(item)
                                yield file_metadata
                                files_returned += 1
                                self.metrics.increment_counter("sharepoint.files_processed")
                                
                            except Exception as e:
                                self.logger.warning(
                                    "Failed to process SharePoint file",
                                    file_id=item.get("id"),
                                    error=str(e)
                                )
                                self.metrics.increment_counter("sharepoint.processing_errors")
                        
                        # Get next page URL
                        endpoint = data.get("@odata.nextLink")
                        
                    elif response.status == 429:
                        retry_after = int(response.headers.get("Retry-After", 60))
                        self.metrics.increment_counter("sharepoint.rate_limit_errors")
                        raise RateLimitError("SharePoint rate limit exceeded", retry_after)
                    
                    else:
                        error_data = await response.json()
                        self.metrics.increment_counter("sharepoint.api_errors")
                        raise APIConnectionError(f"SharePoint API error: {error_data}")
                        
        except Exception as e:
            self.logger.error("Error listing SharePoint files", error=str(e))
            raise APIConnectionError(f"Error listing files: {e}")
    
    async def _get_site_id(self) -> str:
        """Get SharePoint site ID from site URL."""
        # Extract site path from URL
        site_path = self.site_url.replace("https://", "").split("/", 1)
        hostname = site_path[0]
        site_name = site_path[1] if len(site_path) > 1 else ""
        
        endpoint = f"{self.graph_endpoint}/sites/{hostname}:/{site_name}"
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        async with self.pool_manager.request(
            "GET",
            endpoint,
            service_type="sharepoint",
            headers=headers
        ) as response:
            if response.status == 200:
                data = await response.json()
                return data["id"]
            else:
                raise APIConnectionError(f"Failed to get site ID: {response.status}")
    
    async def _get_drive_id(self, site_id: str) -> str:
        """Get document library drive ID."""
        endpoint = f"{self.graph_endpoint}/sites/{site_id}/drives"
        
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        async with self.pool_manager.request(
            "GET",
            endpoint,
            service_type="sharepoint",
            headers=headers
        ) as response:
            if response.status == 200:
                data = await response.json()
                
                # Find the specified document library
                for drive in data.get("value", []):
                    if drive.get("name") == self.document_library:
                        return drive["id"]
                
                # Fallback to default drive
                if data.get("value"):
                    return data["value"][0]["id"]
                
                raise APIConnectionError("No document library found")
            else:
                raise APIConnectionError(f"Failed to get drive ID: {response.status}")
    
    def _convert_to_file_metadata(self, item: Dict[str, Any]) -> FileMetadata:
        """Convert SharePoint file item to FileMetadata."""
        # Parse timestamps
        date_created = datetime.fromisoformat(
            item["createdDateTime"].replace("Z", "+00:00")
        )
        date_updated = datetime.fromisoformat(
            item["lastModifiedDateTime"].replace("Z", "+00:00")
        )
        
        # Get download URL
        file_link = item.get("webUrl", "")
        if "@microsoft.graph.downloadUrl" in item:
            file_link = item["@microsoft.graph.downloadUrl"]
        
        return FileMetadata(
            external_id=item["id"],
            title=item["name"],
            file_link=file_link,
            date_created=date_created,
            date_updated=date_updated,
            project_id=self.endpoint_details.get("project_id", ""),
            user_id=self.endpoint_details.get("user_id", ""),
            metadata={
                "size": item.get("size"),
                "mime_type": item.get("file", {}).get("mimeType"),
                "web_url": item.get("webUrl"),
                "etag": item.get("eTag"),
                "parent_path": item.get("parentReference", {}).get("path")
            }
        )
    
    async def get_sync_info(self) -> Dict[str, Any]:
        """Get SharePoint sync information."""
        return {
            "last_sync": None,
            "api_quota_remaining": None,  # Microsoft Graph doesn't expose quota
            "rate_limit_reset": None,
            "site_url": self.site_url,
            "document_library": self.document_library,
            "tenant_id": self.tenant_id
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on SharePoint connection."""
        try:
            await self._ensure_authenticated()
            
            # Test API access with a simple call
            headers = {"Authorization": f"Bearer {self.access_token}"}
            
            async with self.pool_manager.request(
                "GET",
                f"{self.graph_endpoint}/me",
                service_type="sharepoint",
                headers=headers
            ) as response:
                if response.status == 200:
                    return {
                        "status": "healthy",
                        "authenticated": True,
                        "site_url": self.site_url
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "error": f"API test failed: {response.status}",
                        "authenticated": self._authenticated
                    }
                    
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "authenticated": False
            }
```

#### 2. Register the Client

Update `src/connector/api_clients/factory.py`:

```python
from .sharepoint import SharePointClient

class APIClientFactory:
    _clients = {
        "google_drive": GoogleDriveClient,
        "autodesk": AutodeskConstructionCloudClient,
        "sharepoint": SharePointClient,  # Register new client
    }
    
    @classmethod
    def register_client(cls, client_type: str, client_class: type):
        """Register a new API client type."""
        cls._clients[client_type] = client_class
        cls.logger.info(f"Registered API client: {client_type}")
```

#### 3. Add Configuration Support

Update configuration schema in `src/connector/config/schema.py`:

```python
class SharePointEndpointConfig(BaseModel):
    """SharePoint-specific endpoint configuration."""
    
    tenant_id: str = Field(..., description="Azure AD tenant ID")
    client_id: str = Field(..., description="Application (client) ID")
    client_secret: str = Field(..., description="Client secret")
    site_url: str = Field(..., description="SharePoint site URL")
    document_library: str = Field(default="Documents", description="Document library name")
    
    @validator('site_url')
    def validate_site_url(cls, v):
        if not v.startswith(('https://', 'http://')):
            raise ValueError('Site URL must start with https:// or http://')
        return v

# Update main EndpointConfig to support SharePoint
class EndpointConfig(BaseModel):
    # ... existing fields ...
    
    @root_validator
    def validate_endpoint_details(cls, values):
        endpoint_type = values.get('type')
        details = values.get('endpoint_details', {})
        
        if endpoint_type == 'sharepoint':
            # Validate SharePoint-specific configuration
            SharePointEndpointConfig(**details)
        
        return values
```

## Custom File Processors

File processors allow custom handling of file metadata after extraction but before database storage.

### Creating a File Processor

```python
# src/connector/processors/virus_scanner.py
"""Virus scanning processor for file safety validation."""

import asyncio
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
import aiohttp
import hashlib

from ..api_clients.base import FileMetadata
from ..utils.logging import get_logger


class ProcessResult:
    """Result of file processing operation."""
    
    def __init__(self, success: bool, metadata: Optional[FileMetadata] = None, 
                 error: Optional[str] = None, skip: bool = False):
        self.success = success
        self.metadata = metadata
        self.error = error
        self.skip = skip  # If True, skip this file from database storage


class BaseProcessor(ABC):
    """Abstract base class for file processors."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
    
    @abstractmethod
    async def process(self, file_metadata: FileMetadata) -> ProcessResult:
        """Process file metadata.
        
        Args:
            file_metadata: Original file metadata
            
        Returns:
            ProcessResult with processed metadata or error
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Get processor name for registration."""
        pass


class VirusScannerProcessor(BaseProcessor):
    """Processor that scans files for viruses using VirusTotal API."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("virus_total_api_key")
        self.skip_large_files = config.get("skip_large_files", True)
        self.max_file_size = config.get("max_file_size_mb", 100) * 1024 * 1024
        
        if not self.api_key:
            raise ValueError("VirusTotal API key is required")
    
    def get_name(self) -> str:
        return "virus_scanner"
    
    async def process(self, file_metadata: FileMetadata) -> ProcessResult:
        """Scan file for viruses using VirusTotal API."""
        try:
            # Skip large files if configured
            file_size = file_metadata.metadata.get("size", 0)
            if self.skip_large_files and file_size > self.max_file_size:
                self.logger.info(
                    f"Skipping virus scan for large file: {file_metadata.title}"
                )
                return ProcessResult(success=True, metadata=file_metadata)
            
            # Calculate file hash for VirusTotal lookup
            file_hash = await self._get_file_hash(file_metadata)
            if not file_hash:
                # If we can't get hash, proceed without scanning
                return ProcessResult(success=True, metadata=file_metadata)
            
            # Check VirusTotal for scan results
            scan_result = await self._check_virus_total(file_hash)
            
            # Update metadata with scan results
            updated_metadata = file_metadata
            updated_metadata.metadata["virus_scan"] = {
                "scanned": True,
                "clean": scan_result.get("clean", True),
                "threats_found": scan_result.get("threats", []),
                "scan_date": datetime.now(timezone.utc).isoformat(),
                "scanner": "virustotal"
            }
            
            # Skip file if threats detected
            if not scan_result.get("clean", True):
                self.logger.warning(
                    f"Threats detected in file: {file_metadata.title}",
                    threats=scan_result.get("threats", [])
                )
                return ProcessResult(
                    success=True, 
                    metadata=updated_metadata, 
                    skip=True  # Skip storing infected files
                )
            
            return ProcessResult(success=True, metadata=updated_metadata)
            
        except Exception as e:
            self.logger.error(f"Virus scanning failed: {e}")
            return ProcessResult(
                success=False, 
                error=f"Virus scanning failed: {e}"
            )
    
    async def _get_file_hash(self, file_metadata: FileMetadata) -> Optional[str]:
        """Get file hash for VirusTotal lookup."""
        try:
            # For demonstration - in practice, you'd download the file
            # and calculate its hash, or use file metadata if available
            file_id = file_metadata.external_id
            return hashlib.sha256(file_id.encode()).hexdigest()
            
        except Exception as e:
            self.logger.warning(f"Could not calculate file hash: {e}")
            return None
    
    async def _check_virus_total(self, file_hash: str) -> Dict[str, Any]:
        """Check file hash against VirusTotal API."""
        headers = {
            "x-apikey": self.api_key,
            "Content-Type": "application/json"
        }
        
        url = f"https://www.virustotal.com/api/v3/files/{file_hash}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
                    
                    malicious = stats.get("malicious", 0)
                    suspicious = stats.get("suspicious", 0)
                    
                    return {
                        "clean": malicious == 0 and suspicious == 0,
                        "threats": [] if malicious == 0 else ["malware_detected"],
                        "stats": stats
                    }
                elif response.status == 404:
                    # File not found in VirusTotal - assume clean
                    return {"clean": True, "threats": []}
                else:
                    raise Exception(f"VirusTotal API error: {response.status}")


class ProcessorRegistry:
    """Registry for file processors."""
    
    def __init__(self):
        self._processors: Dict[str, BaseProcessor] = {}
        self.logger = get_logger(self.__class__.__name__)
    
    def register(self, processor: BaseProcessor):
        """Register a processor."""
        name = processor.get_name()
        self._processors[name] = processor
        self.logger.info(f"Registered processor: {name}")
    
    def get_processor(self, name: str) -> Optional[BaseProcessor]:
        """Get processor by name."""
        return self._processors.get(name)
    
    def get_all_processors(self) -> Dict[str, BaseProcessor]:
        """Get all registered processors."""
        return self._processors.copy()
    
    async def process_file(self, file_metadata: FileMetadata, 
                          processor_names: List[str]) -> ProcessResult:
        """Process file through multiple processors."""
        current_metadata = file_metadata
        
        for processor_name in processor_names:
            processor = self.get_processor(processor_name)
            if not processor:
                self.logger.warning(f"Processor not found: {processor_name}")
                continue
            
            result = await processor.process(current_metadata)
            
            if not result.success:
                return result
            
            if result.skip:
                return result
            
            if result.metadata:
                current_metadata = result.metadata
        
        return ProcessResult(success=True, metadata=current_metadata)
```

### Using Custom Processors

```python
# In sync engine integration
class SyncEngine:
    def __init__(self, database_service: DatabaseService, 
                 processor_registry: ProcessorRegistry):
        self.db_service = database_service
        self.processors = processor_registry
    
    async def sync_endpoint(self, endpoint: EndpointModel) -> SyncResult:
        # ... existing sync logic ...
        
        # Process each file through configured processors
        for file_metadata in files:
            processor_names = endpoint.processor_config.get("processors", [])
            
            if processor_names:
                result = await self.processors.process_file(
                    file_metadata, processor_names
                )
                
                if not result.success:
                    self.logger.error(f"Processing failed: {result.error}")
                    continue
                
                if result.skip:
                    self.logger.info(f"Skipping file: {file_metadata.title}")
                    continue
                
                file_metadata = result.metadata
            
            # Store processed metadata
            await self.db_service.create_or_update_file(file_metadata)
```

## Database Extensions

### Custom Database Backends

```python
# src/connector/database/backends/mongodb.py
"""MongoDB backend implementation for File Connector."""

from typing import Dict, Any, List, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import IndexModel, ASCENDING, DESCENDING

from ..models import EndpointModel, FileModel, SyncLogModel
from ..base import BaseDatabaseBackend
from ...utils.logging import get_logger


class MongoDBBackend(BaseDatabaseBackend):
    """MongoDB database backend implementation."""
    
    def __init__(self, connection_string: str, database_name: str = "file_connector"):
        self.connection_string = connection_string
        self.database_name = database_name
        self.client: Optional[AsyncIOMotorClient] = None
        self.database = None
        self.logger = get_logger(self.__class__.__name__)
    
    async def connect(self):
        """Connect to MongoDB."""
        self.client = AsyncIOMotorClient(self.connection_string)
        self.database = self.client[self.database_name]
        
        # Create indexes for performance
        await self._create_indexes()
        
        self.logger.info("Connected to MongoDB", database=self.database_name)
    
    async def disconnect(self):
        """Disconnect from MongoDB."""
        if self.client:
            self.client.close()
            self.logger.info("Disconnected from MongoDB")
    
    async def _create_indexes(self):
        """Create performance indexes."""
        # Files collection indexes
        files_indexes = [
            IndexModel([("external_id", ASCENDING), ("endpoint_id", ASCENDING)], unique=True),
            IndexModel([("endpoint_id", ASCENDING), ("updated_at", DESCENDING)]),
            IndexModel([("project_id", ASCENDING)]),
            IndexModel([("date_updated", DESCENDING)]),
        ]
        await self.database.files.create_indexes(files_indexes)
        
        # Endpoints collection indexes
        endpoint_indexes = [
            IndexModel([("endpoint_type", ASCENDING)]),
            IndexModel([("is_active", ASCENDING)]),
            IndexModel([("project_id", ASCENDING)]),
        ]
        await self.database.endpoints.create_indexes(endpoint_indexes)
        
        # Sync logs collection indexes
        sync_log_indexes = [
            IndexModel([("endpoint_id", ASCENDING), ("sync_started", DESCENDING)]),
            IndexModel([("sync_status", ASCENDING)]),
        ]
        await self.database.sync_logs.create_indexes(sync_log_indexes)
    
    async def create_endpoint(self, endpoint_data: Dict[str, Any]) -> EndpointModel:
        """Create new endpoint."""
        endpoint_data["created_at"] = datetime.utcnow()
        endpoint_data["updated_at"] = datetime.utcnow()
        
        result = await self.database.endpoints.insert_one(endpoint_data)
        endpoint_data["_id"] = result.inserted_id
        
        return EndpointModel(**endpoint_data)
    
    async def get_file_by_external_id(self, external_id: str, endpoint_id: int) -> Optional[FileModel]:
        """Get file by external ID and endpoint."""
        doc = await self.database.files.find_one({
            "external_id": external_id,
            "endpoint_id": endpoint_id
        })
        
        if doc:
            return FileModel(**doc)
        return None
    
    async def batch_create_files(self, files_data: List[Dict[str, Any]]) -> List[FileModel]:
        """Batch create files."""
        if not files_data:
            return []
        
        # Add timestamps
        for file_data in files_data:
            file_data["created_at"] = datetime.utcnow()
            file_data["updated_at"] = datetime.utcnow()
        
        # Use ordered=False for better performance
        result = await self.database.files.insert_many(files_data, ordered=False)
        
        # Return created models
        created_files = []
        for i, file_data in enumerate(files_data):
            file_data["_id"] = result.inserted_ids[i]
            created_files.append(FileModel(**file_data))
        
        return created_files
    
    async def batch_update_files(self, files_data: List[Dict[str, Any]]) -> List[FileModel]:
        """Batch update files."""
        if not files_data:
            return []
        
        # Use bulk operations for efficiency
        operations = []
        for file_data in files_data:
            file_data["updated_at"] = datetime.utcnow()
            
            operations.append(
                UpdateOne(
                    {"external_id": file_data["external_id"], 
                     "endpoint_id": file_data["endpoint_id"]},
                    {"$set": file_data}
                )
            )
        
        await self.database.files.bulk_write(operations)
        
        # Return updated models (simplified - in practice you might want to fetch)
        return [FileModel(**data) for data in files_data]
```

### Database Schema Migrations

```python
# src/connector/database/migrations/001_add_file_processing.py
"""Migration to add file processing fields."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    """Add file processing columns."""
    # Add processing status to files table
    op.add_column('files', sa.Column('processing_status', sa.String(50), default='pending'))
    op.add_column('files', sa.Column('processing_errors', postgresql.JSONB))
    op.add_column('files', sa.Column('processed_at', sa.DateTime))
    
    # Add processor configuration to endpoints
    op.add_column('endpoints', sa.Column('processor_config', postgresql.JSONB))
    
    # Create index for processing status
    op.create_index('idx_files_processing_status', 'files', ['processing_status'])


def downgrade():
    """Remove file processing columns."""
    op.drop_index('idx_files_processing_status', 'files')
    op.drop_column('files', 'processing_status')
    op.drop_column('files', 'processing_errors')
    op.drop_column('files', 'processed_at')
    op.drop_column('endpoints', 'processor_config')
```

## Scheduling Extensions

### Custom Schedule Types

```python
# src/connector/scheduling/custom_schedules.py
"""Custom scheduling implementations."""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio
from abc import ABC, abstractmethod

from ..config.schema import ScheduleConfig
from ..utils.logging import get_logger


class BaseSchedule(ABC):
    """Abstract base class for custom schedules."""
    
    def __init__(self, config: ScheduleConfig):
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
    
    @abstractmethod
    async def get_next_run_time(self, last_run: Optional[datetime] = None) -> Optional[datetime]:
        """Get the next scheduled run time."""
        pass
    
    @abstractmethod
    def get_schedule_type(self) -> str:
        """Get the schedule type identifier."""
        pass


class BusinessHoursSchedule(BaseSchedule):
    """Schedule that only runs during business hours."""
    
    def get_schedule_type(self) -> str:
        return "business_hours"
    
    async def get_next_run_time(self, last_run: Optional[datetime] = None) -> Optional[datetime]:
        """Calculate next run time within business hours."""
        now = datetime.now()
        
        # Get configuration
        start_hour = self.config.get("start_hour", 9)  # 9 AM
        end_hour = self.config.get("end_hour", 17)     # 5 PM
        interval_minutes = self.config.get("interval_minutes", 60)
        weekdays_only = self.config.get("weekdays_only", True)
        
        # Calculate next run time
        if last_run:
            next_run = last_run + timedelta(minutes=interval_minutes)
        else:
            next_run = now + timedelta(minutes=interval_minutes)
        
        # Adjust to business hours
        while True:
            # Skip weekends if configured
            if weekdays_only and next_run.weekday() >= 5:  # Saturday=5, Sunday=6
                # Move to next Monday
                days_to_monday = 7 - next_run.weekday()
                next_run = next_run.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                next_run += timedelta(days=days_to_monday)
                continue
            
            # Check if within business hours
            if start_hour <= next_run.hour < end_hour:
                return next_run
            elif next_run.hour < start_hour:
                # Too early - move to start of business day
                next_run = next_run.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                return next_run
            else:
                # Too late - move to next business day
                next_run += timedelta(days=1)
                next_run = next_run.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                continue


class ConditionalSchedule(BaseSchedule):
    """Schedule that runs based on external conditions."""
    
    def get_schedule_type(self) -> str:
        return "conditional"
    
    async def get_next_run_time(self, last_run: Optional[datetime] = None) -> Optional[datetime]:
        """Calculate next run time based on conditions."""
        # Check condition function
        condition_func = self.config.get("condition_function")
        if not condition_func:
            return None
        
        # Evaluate condition (this would call external service/function)
        should_run = await self._evaluate_condition(condition_func)
        
        if should_run:
            return datetime.now() + timedelta(minutes=1)  # Run soon
        else:
            # Check again in specified interval
            check_interval = self.config.get("check_interval_minutes", 15)
            return datetime.now() + timedelta(minutes=check_interval)
    
    async def _evaluate_condition(self, condition_func: str) -> bool:
        """Evaluate external condition."""
        # This could check external APIs, file systems, databases, etc.
        # For example, check if new files exist in a monitored location
        try:
            if condition_func == "check_file_count":
                # Example: check if file count exceeds threshold
                threshold = self.config.get("file_count_threshold", 100)
                current_count = await self._get_file_count()
                return current_count >= threshold
            
            elif condition_func == "check_external_trigger":
                # Example: check external system for trigger
                return await self._check_external_trigger()
            
            return False
            
        except Exception as e:
            self.logger.error(f"Condition evaluation failed: {e}")
            return False
    
    async def _get_file_count(self) -> int:
        """Get current file count from monitoring location."""
        # Implementation would depend on specific monitoring needs
        return 0
    
    async def _check_external_trigger(self) -> bool:
        """Check external system for trigger."""
        # Implementation would check external API or service
        return False


class ScheduleRegistry:
    """Registry for custom schedule types."""
    
    def __init__(self):
        self._schedules: Dict[str, type] = {}
        self.logger = get_logger(self.__class__.__name__)
    
    def register(self, schedule_class: type):
        """Register a custom schedule type."""
        instance = schedule_class({})  # Temporary instance to get type
        schedule_type = instance.get_schedule_type()
        
        self._schedules[schedule_type] = schedule_class
        self.logger.info(f"Registered schedule type: {schedule_type}")
    
    def create_schedule(self, schedule_type: str, config: ScheduleConfig) -> Optional[BaseSchedule]:
        """Create schedule instance by type."""
        schedule_class = self._schedules.get(schedule_type)
        if schedule_class:
            return schedule_class(config)
        return None
    
    def get_available_types(self) -> List[str]:
        """Get list of available schedule types."""
        return list(self._schedules.keys())
```

## Plugin System

### Plugin Interface

```python
# src/connector/plugins/base.py
"""Base plugin system for File Connector."""

from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
import importlib
import inspect
from pathlib import Path

from ..utils.logging import get_logger


class PluginMetadata:
    """Plugin metadata information."""
    
    def __init__(self, name: str, version: str, description: str, 
                 author: str, dependencies: List[str] = None):
        self.name = name
        self.version = version
        self.description = description
        self.author = author
        self.dependencies = dependencies or []


class BasePlugin(ABC):
    """Abstract base class for File Connector plugins."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = get_logger(f"plugin.{self.get_metadata().name}")
        self._initialized = False
    
    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """Get plugin metadata."""
        pass
    
    async def initialize(self):
        """Initialize the plugin."""
        if not self._initialized:
            await self._setup()
            self._initialized = True
            self.logger.info(f"Plugin initialized: {self.get_metadata().name}")
    
    async def cleanup(self):
        """Cleanup plugin resources."""
        if self._initialized:
            await self._teardown()
            self._initialized = False
            self.logger.info(f"Plugin cleaned up: {self.get_metadata().name}")
    
    async def _setup(self):
        """Plugin-specific setup logic."""
        pass
    
    async def _teardown(self):
        """Plugin-specific teardown logic."""
        pass
    
    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute plugin functionality."""
        pass


class PluginManager:
    """Manager for loading and executing plugins."""
    
    def __init__(self, plugin_directories: List[str] = None):
        self.plugin_directories = plugin_directories or ["plugins"]
        self._plugins: Dict[str, BasePlugin] = {}
        self.logger = get_logger(self.__class__.__name__)
    
    async def load_plugins(self):
        """Load all plugins from configured directories."""
        for directory in self.plugin_directories:
            await self._load_plugins_from_directory(directory)
    
    async def _load_plugins_from_directory(self, directory: str):
        """Load plugins from a specific directory."""
        plugin_path = Path(directory)
        if not plugin_path.exists():
            self.logger.warning(f"Plugin directory not found: {directory}")
            return
        
        for plugin_file in plugin_path.glob("*.py"):
            if plugin_file.name.startswith("__"):
                continue
            
            try:
                await self._load_plugin_file(plugin_file)
            except Exception as e:
                self.logger.error(f"Failed to load plugin {plugin_file}: {e}")
    
    async def _load_plugin_file(self, plugin_file: Path):
        """Load a specific plugin file."""
        module_name = plugin_file.stem
        spec = importlib.util.spec_from_file_location(module_name, plugin_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Find plugin classes in the module
        for name, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and 
                issubclass(obj, BasePlugin) and 
                obj != BasePlugin):
                
                try:
                    # Instantiate plugin with empty config for now
                    plugin = obj({})
                    metadata = plugin.get_metadata()
                    
                    await plugin.initialize()
                    self._plugins[metadata.name] = plugin
                    
                    self.logger.info(f"Loaded plugin: {metadata.name} v{metadata.version}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to initialize plugin {name}: {e}")
    
    def get_plugin(self, name: str) -> Optional[BasePlugin]:
        """Get plugin by name."""
        return self._plugins.get(name)
    
    def list_plugins(self) -> List[PluginMetadata]:
        """List all loaded plugins."""
        return [plugin.get_metadata() for plugin in self._plugins.values()]
    
    async def execute_plugin(self, name: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Execute a specific plugin."""
        plugin = self.get_plugin(name)
        if plugin:
            return await plugin.execute(context)
        return None
    
    async def cleanup_all(self):
        """Cleanup all plugins."""
        for plugin in self._plugins.values():
            await plugin.cleanup()
        self._plugins.clear()


# Example plugin implementation
class EmailNotificationPlugin(BasePlugin):
    """Plugin for sending email notifications on sync completion."""
    
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="email_notification",
            version="1.0.0",
            description="Send email notifications on sync completion",
            author="File Connector Team",
            dependencies=["aiosmtplib"]
        )
    
    async def _setup(self):
        """Setup email configuration."""
        self.smtp_server = self.config.get("smtp_server", "localhost")
        self.smtp_port = self.config.get("smtp_port", 587)
        self.username = self.config.get("username")
        self.password = self.config.get("password")
        self.from_email = self.config.get("from_email")
        self.to_emails = self.config.get("to_emails", [])
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Send email notification."""
        sync_result = context.get("sync_result")
        endpoint_name = context.get("endpoint_name")
        
        if not sync_result or not self.to_emails:
            return {"status": "skipped", "reason": "no recipients or sync result"}
        
        # Compose email
        subject = f"File Sync Completed: {endpoint_name}"
        body = f"""
        File synchronization completed for endpoint: {endpoint_name}
        
        Results:
        - Files processed: {sync_result.files_processed}
        - Files added: {sync_result.files_added}
        - Files updated: {sync_result.files_updated}
        - Success: {sync_result.success}
        """
        
        # Send email (implementation would use aiosmtplib or similar)
        try:
            await self._send_email(subject, body)
            return {"status": "sent", "recipients": len(self.to_emails)}
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    async def _send_email(self, subject: str, body: str):
        """Send email using SMTP."""
        # Implementation would use aiosmtplib or similar
        self.logger.info(f"Email sent: {subject}")
```

This extensibility guide provides a comprehensive framework for extending the File Connector with new functionality while maintaining consistency and reliability. The plugin system, custom processors, and scheduling extensions enable the system to adapt to diverse organizational needs and integration requirements.