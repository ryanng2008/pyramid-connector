"""Supabase database service for the File Connector."""

import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from contextlib import asynccontextmanager

from supabase import create_client, Client
from postgrest.exceptions import APIError
from pydantic import ValidationError

from .models import FileCreate, FileResponse, EndpointCreate, EndpointResponse, SyncLogCreate, SyncLogUpdate, SyncLogResponse
from ..config.settings import get_settings
from ..utils.logging import get_logger

logger = get_logger(__name__)


class SupabaseService:
    """High-level Supabase service for file connector operations."""
    
    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[Client] = None
        
    async def initialize(self) -> bool:
        """Initialize Supabase client."""
        try:
            if not self.settings.supabase.url or not self.settings.supabase.anon_key:
                logger.warning("Supabase credentials not configured")
                return False
                
            self.client = create_client(
                self.settings.supabase.url,
                self.settings.supabase.anon_key
            )
            
            # Test connection
            await self.test_connection()
            logger.info("Supabase service initialized successfully")
            return True
            
        except Exception as e:
            logger.error("Failed to initialize Supabase service", error=str(e))
            return False
    
    async def test_connection(self) -> bool:
        """Test Supabase connection."""
        try:
            if not self.client:
                return False
                
            # Try a simple query to test connection
            result = self.client.table("endpoints").select("id").limit(1).execute()
            logger.info("Supabase connection test successful")
            return True
            
        except Exception as e:
            logger.error("Supabase connection test failed", error=str(e))
            return False
    
    # Endpoint operations
    async def create_endpoint(self, endpoint_data: EndpointCreate) -> EndpointResponse:
        """Create a new endpoint."""
        try:
            data = {
                "endpoint_type": endpoint_data.endpoint_type,
                "endpoint_details": endpoint_data.endpoint_details,
                "project_id": endpoint_data.project_id,
                "user_id": endpoint_data.user_id,
                "schedule_cron": endpoint_data.schedule_cron,
                "enabled": endpoint_data.enabled,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "last_sync_status": "pending"
            }
            
            result = self.client.table("endpoints").insert(data).execute()
            
            if result.data:
                endpoint_dict = result.data[0]
                logger.info("Endpoint created", endpoint_id=endpoint_dict["id"])
                return EndpointResponse(**endpoint_dict)
            else:
                raise Exception("No data returned from endpoint creation")
                
        except Exception as e:
            logger.error("Failed to create endpoint", error=str(e))
            raise
    
    async def get_endpoint(self, endpoint_id: int) -> Optional[EndpointResponse]:
        """Get endpoint by ID."""
        try:
            result = self.client.table("endpoints").select("*").eq("id", endpoint_id).execute()
            
            if result.data:
                return EndpointResponse(**result.data[0])
            return None
            
        except Exception as e:
            logger.error("Failed to get endpoint", endpoint_id=endpoint_id, error=str(e))
            return None
    
    async def get_active_endpoints(self) -> List[EndpointResponse]:
        """Get all active endpoints."""
        try:
            result = self.client.table("endpoints").select("*").eq("enabled", True).execute()
            
            endpoints = []
            for endpoint_dict in result.data:
                try:
                    endpoints.append(EndpointResponse(**endpoint_dict))
                except ValidationError as e:
                    logger.warning("Invalid endpoint data", endpoint_id=endpoint_dict.get("id"), error=str(e))
                    
            logger.info("Retrieved active endpoints", count=len(endpoints))
            return endpoints
            
        except Exception as e:
            logger.error("Failed to get active endpoints", error=str(e))
            return []
    
    # File operations
    async def sync_file(self, file_data: FileCreate) -> Tuple[FileResponse, bool]:
        """Sync a file record (create or update). Returns (file, is_new)."""
        try:
            # Check if file exists
            existing_result = self.client.table("files").select("*").eq(
                "endpoint_id", file_data.endpoint_id
            ).eq("external_file_id", file_data.external_file_id).execute()
            
            if existing_result.data:
                # Update existing file
                existing_file = existing_result.data[0]
                update_data = {
                    "file_name": file_data.file_name,
                    "file_path": file_data.file_path,
                    "file_link": file_data.file_link,
                    "file_size": file_data.file_size,
                    "file_type": file_data.file_type,
                    "external_created_at": file_data.external_created_at.isoformat() if file_data.external_created_at else None,
                    "external_updated_at": file_data.external_updated_at.isoformat() if file_data.external_updated_at else None,
                    "file_metadata": file_data.file_metadata,
                    "updated_at": datetime.utcnow().isoformat(),
                    "last_synced_at": datetime.utcnow().isoformat()
                }
                
                result = self.client.table("files").update(update_data).eq("id", existing_file["id"]).execute()
                
                if result.data:
                    return FileResponse(**result.data[0]), False
                else:
                    raise Exception("No data returned from file update")
            else:
                # Create new file
                insert_data = {
                    "endpoint_id": file_data.endpoint_id,
                    "external_file_id": file_data.external_file_id,
                    "file_name": file_data.file_name,
                    "file_path": file_data.file_path,
                    "file_link": file_data.file_link,
                    "file_size": file_data.file_size,
                    "file_type": file_data.file_type,
                    "external_created_at": file_data.external_created_at.isoformat() if file_data.external_created_at else None,
                    "external_updated_at": file_data.external_updated_at.isoformat() if file_data.external_updated_at else None,
                    "file_metadata": file_data.file_metadata,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "last_synced_at": datetime.utcnow().isoformat(),
                    "sync_status": "completed"
                }
                
                result = self.client.table("files").insert(insert_data).execute()
                
                if result.data:
                    logger.info("File created", file_id=result.data[0]["id"], external_file_id=file_data.external_file_id)
                    return FileResponse(**result.data[0]), True
                else:
                    raise Exception("No data returned from file creation")
                    
        except Exception as e:
            logger.error("Failed to sync file", external_file_id=file_data.external_file_id, error=str(e))
            raise
    
    async def get_endpoint_files(self, endpoint_id: int, limit: Optional[int] = None) -> List[FileResponse]:
        """Get files for an endpoint."""
        try:
            query = self.client.table("files").select("*").eq("endpoint_id", endpoint_id)
            
            if limit:
                query = query.limit(limit)
                
            result = query.execute()
            
            files = []
            for file_dict in result.data:
                try:
                    files.append(FileResponse(**file_dict))
                except ValidationError as e:
                    logger.warning("Invalid file data", file_id=file_dict.get("id"), error=str(e))
                    
            return files
            
        except Exception as e:
            logger.error("Failed to get endpoint files", endpoint_id=endpoint_id, error=str(e))
            return []
    
    async def get_file_by_external_id(self, endpoint_id: int, external_file_id: str) -> Optional[FileResponse]:
        """Get file by external ID."""
        try:
            result = self.client.table("files").select("*").eq(
                "endpoint_id", endpoint_id
            ).eq("external_file_id", external_file_id).execute()
            
            if result.data:
                return FileResponse(**result.data[0])
            return None
            
        except Exception as e:
            logger.error("Failed to get file by external ID", external_file_id=external_file_id, error=str(e))
            return None
    
    # Sync log operations
    async def create_sync_log(self, sync_data: SyncLogCreate) -> SyncLogResponse:
        """Create a new sync log."""
        try:
            data = {
                "endpoint_id": sync_data.endpoint_id,
                "sync_started_at": (sync_data.sync_started_at or datetime.utcnow()).isoformat(),
                "sync_status": "in_progress",
                "files_found": 0,
                "files_new": 0,
                "files_updated": 0,
                "files_skipped": 0,
                "files_error": 0
            }
            
            result = self.client.table("sync_logs").insert(data).execute()
            
            if result.data:
                logger.info("Sync log created", sync_log_id=result.data[0]["id"])
                return SyncLogResponse(**result.data[0])
            else:
                raise Exception("No data returned from sync log creation")
                
        except Exception as e:
            logger.error("Failed to create sync log", error=str(e))
            raise
    
    async def update_sync_log(self, sync_log_id: int, update_data: SyncLogUpdate) -> SyncLogResponse:
        """Update sync log."""
        try:
            data = {}
            
            if update_data.sync_completed_at:
                data["sync_completed_at"] = update_data.sync_completed_at.isoformat()
            if update_data.sync_status:
                data["sync_status"] = update_data.sync_status
            if update_data.files_found is not None:
                data["files_found"] = update_data.files_found
            if update_data.files_new is not None:
                data["files_new"] = update_data.files_new
            if update_data.files_updated is not None:
                data["files_updated"] = update_data.files_updated
            if update_data.files_skipped is not None:
                data["files_skipped"] = update_data.files_skipped
            if update_data.files_error is not None:
                data["files_error"] = update_data.files_error
            if update_data.error_message:
                data["error_message"] = update_data.error_message
            if update_data.error_details:
                data["error_details"] = update_data.error_details
            if update_data.execution_time_seconds is not None:
                data["execution_time_seconds"] = update_data.execution_time_seconds
            
            result = self.client.table("sync_logs").update(data).eq("id", sync_log_id).execute()
            
            if result.data:
                return SyncLogResponse(**result.data[0])
            else:
                raise Exception("No data returned from sync log update")
                
        except Exception as e:
            logger.error("Failed to update sync log", sync_log_id=sync_log_id, error=str(e))
            raise
    
    async def get_sync_logs(self, endpoint_id: int, limit: int = 10) -> List[SyncLogResponse]:
        """Get sync logs for an endpoint."""
        try:
            result = self.client.table("sync_logs").select("*").eq(
                "endpoint_id", endpoint_id
            ).order("sync_started_at", desc=True).limit(limit).execute()
            
            logs = []
            for log_dict in result.data:
                try:
                    logs.append(SyncLogResponse(**log_dict))
                except ValidationError as e:
                    logger.warning("Invalid sync log data", sync_log_id=log_dict.get("id"), error=str(e))
                    
            return logs
            
        except Exception as e:
            logger.error("Failed to get sync logs", endpoint_id=endpoint_id, error=str(e))
            return []
    
    # Database management
    async def create_tables_if_not_exist(self) -> bool:
        """Create tables if they don't exist (for initial setup)."""
        try:
            # Note: In Supabase, tables are typically created via the dashboard or SQL editor
            # This method is mainly for checking if tables exist and logging
            
            tables = ["endpoints", "files", "sync_logs"]
            for table in tables:
                try:
                    result = self.client.table(table).select("id").limit(1).execute()
                    logger.info(f"Table '{table}' is accessible")
                except Exception as e:
                    logger.warning(f"Table '{table}' may not exist or is not accessible", error=str(e))
                    return False
            
            logger.info("All required tables are accessible")
            return True
            
        except Exception as e:
            logger.error("Failed to check table accessibility", error=str(e))
            return False


# Global Supabase service instance
_supabase_service: Optional[SupabaseService] = None


async def get_supabase_service() -> SupabaseService:
    """Get or create the global Supabase service instance."""
    global _supabase_service
    
    if _supabase_service is None:
        _supabase_service = SupabaseService()
        await _supabase_service.initialize()
    
    return _supabase_service


async def init_supabase_service() -> SupabaseService:
    """Initialize Supabase service."""
    service = SupabaseService()
    success = await service.initialize()
    
    if not success:
        raise Exception("Failed to initialize Supabase service")
    
    return service
