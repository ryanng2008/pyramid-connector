"""High-level database service layer."""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from contextlib import contextmanager

from .database import get_db_manager
from .operations import (
    get_endpoint_repository,
    get_file_repository,
    get_sync_log_repository
)
from .models import (
    EndpointCreate, EndpointUpdate, EndpointResponse,
    FileCreate, FileResponse,
    SyncLogCreate, SyncLogUpdate, SyncLogResponse,
    SyncStatus, EndpointType
)
from ..utils.logging import get_logger, log_execution_time


logger = get_logger("database.service")


class DatabaseService:
    """High-level database service for file connector operations."""
    
    def __init__(self):
        self.db_manager = get_db_manager()
    
    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        with self.db_manager.session_scope() as session:
            yield session
    
    # Endpoint operations
    
    @log_execution_time
    def create_endpoint(self, endpoint_data: EndpointCreate) -> EndpointResponse:
        """Create a new endpoint configuration."""
        with self.transaction() as session:
            repo = get_endpoint_repository(session)
            endpoint = repo.create(endpoint_data)
            session.commit()
            return EndpointResponse.from_orm(endpoint)
    
    @log_execution_time
    def get_endpoint(self, endpoint_id: int) -> Optional[EndpointResponse]:
        """Get endpoint by ID."""
        with self.transaction() as session:
            repo = get_endpoint_repository(session)
            endpoint = repo.get_by_id(endpoint_id)
            return EndpointResponse.from_orm(endpoint) if endpoint else None
    
    @log_execution_time
    def get_all_endpoints(self, enabled_only: bool = True) -> List[EndpointResponse]:
        """Get all endpoints."""
        with self.transaction() as session:
            repo = get_endpoint_repository(session)
            endpoints = repo.get_all(enabled_only=enabled_only)
            return [EndpointResponse.from_orm(ep) for ep in endpoints]
    
    @log_execution_time
    def get_endpoints_for_sync(self) -> List[EndpointResponse]:
        """Get all enabled endpoints that need to be synced."""
        return self.get_all_endpoints(enabled_only=True)
    
    @log_execution_time
    def update_endpoint(self, endpoint_id: int, update_data: EndpointUpdate) -> Optional[EndpointResponse]:
        """Update an endpoint."""
        with self.transaction() as session:
            repo = get_endpoint_repository(session)
            endpoint = repo.update(endpoint_id, update_data)
            if endpoint:
                session.commit()
                return EndpointResponse.from_orm(endpoint)
            return None
    
    @log_execution_time
    def update_endpoint_sync_status(
        self,
        endpoint_id: int,
        status: SyncStatus,
        sync_time: Optional[datetime] = None
    ) -> bool:
        """Update endpoint sync status."""
        with self.transaction() as session:
            repo = get_endpoint_repository(session)
            success = repo.update_sync_status(endpoint_id, status, sync_time)
            if success:
                session.commit()
            return success
    
    @log_execution_time
    def delete_endpoint(self, endpoint_id: int) -> bool:
        """Delete an endpoint and all its files."""
        with self.transaction() as session:
            # First delete all files for this endpoint
            file_repo = get_file_repository(session)
            deleted_files = file_repo.delete_by_endpoint(endpoint_id)
            
            # Then delete the endpoint
            endpoint_repo = get_endpoint_repository(session)
            success = endpoint_repo.delete(endpoint_id)
            
            if success:
                session.commit()
                logger.info(
                    "Endpoint and files deleted",
                    endpoint_id=endpoint_id,
                    deleted_files=deleted_files
                )
            
            return success
    
    # File operations
    
    @log_execution_time
    def sync_file(self, file_data: FileCreate) -> Tuple[FileResponse, bool]:
        """Sync a file (update if exists, create if new). Returns (file, is_new)."""
        with self.transaction() as session:
            repo = get_file_repository(session)
            file_record, is_new = repo.update_or_create(file_data)
            session.commit()
            return FileResponse.from_orm(file_record), is_new
    
    @log_execution_time
    def sync_files_batch(self, files_data: List[FileCreate]) -> Dict[str, int]:
        """Sync multiple files in a batch. Returns statistics."""
        stats = {
            "total": len(files_data),
            "new": 0,
            "updated": 0,
            "errors": 0
        }
        
        with self.transaction() as session:
            repo = get_file_repository(session)
            
            for file_data in files_data:
                try:
                    file_record, is_new = repo.update_or_create(file_data)
                    if is_new:
                        stats["new"] += 1
                    else:
                        stats["updated"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    logger.error(
                        "Error syncing file",
                        external_file_id=file_data.external_file_id,
                        error=str(e)
                    )
            
            session.commit()
        
        logger.info("Batch file sync completed", stats=stats)
        return stats
    
    @log_execution_time
    def get_file_by_external_id(self, endpoint_id: int, external_file_id: str) -> Optional[FileResponse]:
        """Get file by external ID."""
        with self.transaction() as session:
            repo = get_file_repository(session)
            file_record = repo.get_by_external_id(endpoint_id, external_file_id)
            return FileResponse.from_orm(file_record) if file_record else None
    
    @log_execution_time
    def get_endpoint_files(self, endpoint_id: int, limit: Optional[int] = None) -> List[FileResponse]:
        """Get files for an endpoint."""
        with self.transaction() as session:
            repo = get_file_repository(session)
            files = repo.get_by_endpoint(endpoint_id, limit)
            return [FileResponse.from_orm(f) for f in files]
    
    @log_execution_time
    def file_exists(self, endpoint_id: int, external_file_id: str) -> bool:
        """Check if file exists in database."""
        with self.transaction() as session:
            repo = get_file_repository(session)
            return repo.file_exists(endpoint_id, external_file_id)
    
    @log_execution_time
    def get_files_to_sync(
        self,
        endpoint_id: int,
        since: Optional[datetime] = None
    ) -> List[str]:
        """Get list of external file IDs that should be synced (for deduplication)."""
        if since is None:
            since = datetime.utcnow() - timedelta(days=30)  # Default: last 30 days
        
        with self.transaction() as session:
            repo = get_file_repository(session)
            files = repo.get_files_newer_than(endpoint_id, since, external_updated_field=True)
            return [f.external_file_id for f in files]
    
    # Sync log operations
    
    @log_execution_time
    def start_sync_log(self, endpoint_id: int) -> int:
        """Start a new sync log. Returns sync log ID."""
        with self.transaction() as session:
            repo = get_sync_log_repository(session)
            sync_log = repo.create(SyncLogCreate(endpoint_id=endpoint_id))
            session.commit()
            
            logger.info("Sync started", endpoint_id=endpoint_id, sync_log_id=sync_log.id)
            return sync_log.id
    
    @log_execution_time
    def complete_sync_log(
        self,
        sync_log_id: int,
        status: SyncStatus,
        stats: Dict[str, int],
        error_message: Optional[str] = None,
        error_details: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Complete a sync log with results."""
        with self.transaction() as session:
            repo = get_sync_log_repository(session)
            
            update_data = SyncLogUpdate(
                sync_completed_at=datetime.utcnow(),
                sync_status=status,
                files_found=stats.get("total", 0),
                files_new=stats.get("new", 0),
                files_updated=stats.get("updated", 0),
                files_skipped=stats.get("skipped", 0),
                files_error=stats.get("errors", 0),
                error_message=error_message,
                error_details=error_details
            )
            
            sync_log = repo.update(sync_log_id, update_data)
            if sync_log:
                session.commit()
                
                logger.info(
                    "Sync completed",
                    sync_log_id=sync_log_id,
                    status=status.value,
                    stats=stats
                )
                return True
            
            return False
    
    @log_execution_time
    def get_sync_history(self, endpoint_id: int, limit: int = 10) -> List[SyncLogResponse]:
        """Get sync history for an endpoint."""
        with self.transaction() as session:
            repo = get_sync_log_repository(session)
            logs = repo.get_recent_logs(endpoint_id, limit)
            return [SyncLogResponse.from_orm(log) for log in logs]
    
    @log_execution_time
    def get_failed_syncs(self, hours: int = 24) -> List[SyncLogResponse]:
        """Get failed syncs within specified hours."""
        with self.transaction() as session:
            repo = get_sync_log_repository(session)
            logs = repo.get_failed_logs(hours)
            return [SyncLogResponse.from_orm(log) for log in logs]
    
    # Utility operations
    
    @log_execution_time
    def get_database_stats(self) -> Dict[str, Any]:
        """Get overall database statistics."""
        with self.transaction() as session:
            from sqlalchemy import func, and_
            from .models import EndpointModel, FileModel, SyncLogModel
            
            stats = {}
            
            # Endpoint stats
            stats["endpoints"] = {
                "total": session.query(EndpointModel).count(),
                "enabled": session.query(EndpointModel).filter(EndpointModel.enabled == True).count(),
                "by_type": {}
            }
            
            # Files stats
            stats["files"] = {
                "total": session.query(FileModel).count(),
                "recent": session.query(FileModel).filter(
                    FileModel.last_synced_at > datetime.utcnow() - timedelta(days=1)
                ).count()
            }
            
            # Sync logs stats
            stats["sync_logs"] = {
                "total": session.query(SyncLogModel).count(),
                "recent_successful": session.query(SyncLogModel).filter(
                    and_(
                        SyncLogModel.sync_status == SyncStatus.COMPLETED,
                        SyncLogModel.sync_started_at > datetime.utcnow() - timedelta(days=1)
                    )
                ).count(),
                "recent_failed": session.query(SyncLogModel).filter(
                    and_(
                        SyncLogModel.sync_status == SyncStatus.FAILED,
                        SyncLogModel.sync_started_at > datetime.utcnow() - timedelta(days=1)
                    )
                ).count()
            }
            
        return stats
    
    @log_execution_time
    def cleanup_old_data(self, days: int = 90) -> Dict[str, int]:
        """Clean up old sync logs and unused data."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        cleanup_stats = {"sync_logs_deleted": 0}
        
        with self.transaction() as session:
            # Delete old sync logs
            deleted_logs = session.query(SyncLogModel).filter(
                SyncLogModel.sync_started_at < cutoff_date
            ).count()
            
            session.query(SyncLogModel).filter(
                SyncLogModel.sync_started_at < cutoff_date
            ).delete()
            
            cleanup_stats["sync_logs_deleted"] = deleted_logs
            session.commit()
        
        logger.info("Database cleanup completed", stats=cleanup_stats, cutoff_date=cutoff_date)
        return cleanup_stats


# Global service instance
_db_service: Optional[DatabaseService] = None


def get_database_service() -> DatabaseService:
    """Get the global database service instance."""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service