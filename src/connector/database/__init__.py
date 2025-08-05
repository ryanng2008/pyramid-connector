"""Database package for File Connector."""

from .database import (
    DatabaseManager,
    get_db_manager,
    init_database,
    get_db_session,
    close_database
)

from .models import (
    EndpointModel,
    FileModel,
    SyncLogModel,
    EndpointCreate,
    EndpointUpdate,
    EndpointResponse,
    FileCreate,
    FileResponse,
    SyncLogCreate,
    SyncLogUpdate,
    SyncLogResponse,
    SyncStatus,
    EndpointType
)

from .operations import (
    EndpointRepository,
    FileRepository,
    SyncLogRepository,
    get_endpoint_repository,
    get_file_repository,
    get_sync_log_repository
)

from .service import (
    DatabaseService,
    get_database_service
)

__all__ = [
    # Database management
    "DatabaseManager",
    "get_db_manager", 
    "init_database",
    "get_db_session",
    "close_database",
    
    # Models
    "EndpointModel",
    "FileModel", 
    "SyncLogModel",
    "EndpointCreate",
    "EndpointUpdate",
    "EndpointResponse",
    "FileCreate",
    "FileResponse",
    "SyncLogCreate",
    "SyncLogUpdate", 
    "SyncLogResponse",
    "SyncStatus",
    "EndpointType",
    
    # Repositories
    "EndpointRepository",
    "FileRepository",
    "SyncLogRepository",
    "get_endpoint_repository",
    "get_file_repository", 
    "get_sync_log_repository",
    
    # Service
    "DatabaseService",
    "get_database_service"
]
