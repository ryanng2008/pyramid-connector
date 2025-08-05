"""Database operations and repository classes."""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func

from .models import (
    EndpointModel, FileModel, SyncLogModel,
    EndpointCreate, EndpointUpdate, EndpointResponse,
    FileCreate, FileResponse,
    SyncLogCreate, SyncLogUpdate, SyncLogResponse,
    SyncStatus, EndpointType
)
from .database import get_db_manager
from ..utils.logging import get_logger, log_execution_time


logger = get_logger("database.operations")


class EndpointRepository:
    """Repository for endpoint operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    @log_execution_time
    def create(self, endpoint_data: EndpointCreate) -> EndpointModel:
        """Create a new endpoint."""
        endpoint = EndpointModel(
            endpoint_type=endpoint_data.endpoint_type.value,
            endpoint_details=endpoint_data.endpoint_details,
            project_id=endpoint_data.project_id,
            user_id=endpoint_data.user_id,
            schedule_cron=endpoint_data.schedule_cron,
            enabled=endpoint_data.enabled
        )
        
        self.session.add(endpoint)
        self.session.flush()  # Get the ID without committing
        
        logger.info(
            "Endpoint created",
            endpoint_id=endpoint.id,
            endpoint_type=endpoint.endpoint_type,
            project_id=endpoint.project_id
        )
        
        return endpoint
    
    @log_execution_time
    def get_by_id(self, endpoint_id: int) -> Optional[EndpointModel]:
        """Get endpoint by ID."""
        return self.session.query(EndpointModel).filter(EndpointModel.id == endpoint_id).first()
    
    @log_execution_time
    def get_all(self, enabled_only: bool = True) -> List[EndpointModel]:
        """Get all endpoints."""
        query = self.session.query(EndpointModel)
        if enabled_only:
            query = query.filter(EndpointModel.enabled == True)
        return query.order_by(EndpointModel.created_at).all()
    
    @log_execution_time
    def get_by_project(self, project_id: str, enabled_only: bool = True) -> List[EndpointModel]:
        """Get endpoints by project ID."""
        query = self.session.query(EndpointModel).filter(EndpointModel.project_id == project_id)
        if enabled_only:
            query = query.filter(EndpointModel.enabled == True)
        return query.order_by(EndpointModel.created_at).all()
    
    @log_execution_time
    def get_by_type(self, endpoint_type: EndpointType, enabled_only: bool = True) -> List[EndpointModel]:
        """Get endpoints by type."""
        query = self.session.query(EndpointModel).filter(EndpointModel.endpoint_type == endpoint_type.value)
        if enabled_only:
            query = query.filter(EndpointModel.enabled == True)
        return query.order_by(EndpointModel.created_at).all()
    
    @log_execution_time
    def update(self, endpoint_id: int, update_data: EndpointUpdate) -> Optional[EndpointModel]:
        """Update an endpoint."""
        endpoint = self.get_by_id(endpoint_id)
        if not endpoint:
            return None
        
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(endpoint, field, value)
        
        endpoint.updated_at = datetime.utcnow()
        
        logger.info("Endpoint updated", endpoint_id=endpoint_id, updated_fields=list(update_dict.keys()))
        
        return endpoint
    
    @log_execution_time
    def update_sync_status(self, endpoint_id: int, status: SyncStatus, sync_time: Optional[datetime] = None) -> bool:
        """Update endpoint sync status."""
        endpoint = self.get_by_id(endpoint_id)
        if not endpoint:
            return False
        
        endpoint.last_sync_status = status.value
        endpoint.last_sync_at = sync_time or datetime.utcnow()
        endpoint.updated_at = datetime.utcnow()
        
        logger.info(
            "Endpoint sync status updated",
            endpoint_id=endpoint_id,
            status=status.value,
            sync_time=endpoint.last_sync_at
        )
        
        return True
    
    @log_execution_time
    def delete(self, endpoint_id: int) -> bool:
        """Delete an endpoint."""
        endpoint = self.get_by_id(endpoint_id)
        if not endpoint:
            return False
        
        self.session.delete(endpoint)
        logger.info("Endpoint deleted", endpoint_id=endpoint_id)
        
        return True


class FileRepository:
    """Repository for file operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    @log_execution_time
    def create(self, file_data: FileCreate) -> FileModel:
        """Create a new file record."""
        file_record = FileModel(
            endpoint_id=file_data.endpoint_id,
            external_file_id=file_data.external_file_id,
            file_name=file_data.file_name,
            file_path=file_data.file_path,
            file_link=file_data.file_link,
            file_size=file_data.file_size,
            file_type=file_data.file_type,
            external_created_at=file_data.external_created_at,
            external_updated_at=file_data.external_updated_at,
            file_metadata=file_data.file_metadata
        )
        
        self.session.add(file_record)
        self.session.flush()
        
        logger.info(
            "File record created",
            file_id=file_record.id,
            external_file_id=file_record.external_file_id,
            file_name=file_record.file_name
        )
        
        return file_record
    
    @log_execution_time
    def get_by_id(self, file_id: int) -> Optional[FileModel]:
        """Get file by ID."""
        return self.session.query(FileModel).filter(FileModel.id == file_id).first()
    
    @log_execution_time
    def get_by_external_id(self, endpoint_id: int, external_file_id: str) -> Optional[FileModel]:
        """Get file by external ID and endpoint."""
        return self.session.query(FileModel).filter(
            and_(
                FileModel.endpoint_id == endpoint_id,
                FileModel.external_file_id == external_file_id
            )
        ).first()
    
    @log_execution_time
    def get_by_endpoint(self, endpoint_id: int, limit: Optional[int] = None) -> List[FileModel]:
        """Get files by endpoint ID."""
        query = self.session.query(FileModel).filter(FileModel.endpoint_id == endpoint_id)
        query = query.order_by(desc(FileModel.external_updated_at))
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    @log_execution_time
    def get_files_newer_than(
        self,
        endpoint_id: int,
        cutoff_time: datetime,
        external_updated_field: bool = True
    ) -> List[FileModel]:
        """Get files newer than specified time."""
        time_field = FileModel.external_updated_at if external_updated_field else FileModel.updated_at
        
        return self.session.query(FileModel).filter(
            and_(
                FileModel.endpoint_id == endpoint_id,
                time_field > cutoff_time
            )
        ).order_by(desc(time_field)).all()
    
    @log_execution_time
    def file_exists(self, endpoint_id: int, external_file_id: str) -> bool:
        """Check if file exists."""
        count = self.session.query(FileModel).filter(
            and_(
                FileModel.endpoint_id == endpoint_id,
                FileModel.external_file_id == external_file_id
            )
        ).count()
        
        return count > 0
    
    @log_execution_time
    def update_or_create(self, file_data: FileCreate) -> Tuple[FileModel, bool]:
        """Update existing file or create new one. Returns (file, created)."""
        existing_file = self.get_by_external_id(file_data.endpoint_id, file_data.external_file_id)
        
        if existing_file:
            # Update existing file
            update_fields = [
                'file_name', 'file_path', 'file_link', 'file_size', 'file_type',
                'external_created_at', 'external_updated_at', 'file_metadata'
            ]
            
            updated = False
            for field in update_fields:
                new_value = getattr(file_data, field)
                if new_value is not None and getattr(existing_file, field) != new_value:
                    setattr(existing_file, field, new_value)
                    updated = True
            
            if updated:
                existing_file.updated_at = datetime.utcnow()
                existing_file.last_synced_at = datetime.utcnow()
                logger.info(
                    "File record updated",
                    file_id=existing_file.id,
                    external_file_id=existing_file.external_file_id
                )
            
            return existing_file, False
        else:
            # Create new file
            new_file = self.create(file_data)
            return new_file, True
    
    @log_execution_time
    def get_sync_statistics(self, endpoint_id: int) -> Dict[str, int]:
        """Get sync statistics for an endpoint."""
        total_files = self.session.query(FileModel).filter(FileModel.endpoint_id == endpoint_id).count()
        
        recent_files = self.session.query(FileModel).filter(
            and_(
                FileModel.endpoint_id == endpoint_id,
                FileModel.last_synced_at > datetime.utcnow() - timedelta(days=1)
            )
        ).count()
        
        return {
            "total_files": total_files,
            "recent_files": recent_files
        }
    
    @log_execution_time
    def delete_by_endpoint(self, endpoint_id: int) -> int:
        """Delete all files for an endpoint. Returns count of deleted files."""
        count = self.session.query(FileModel).filter(FileModel.endpoint_id == endpoint_id).count()
        self.session.query(FileModel).filter(FileModel.endpoint_id == endpoint_id).delete()
        
        logger.info("Files deleted for endpoint", endpoint_id=endpoint_id, count=count)
        return count


class SyncLogRepository:
    """Repository for sync log operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    @log_execution_time
    def create(self, log_data: SyncLogCreate) -> SyncLogModel:
        """Create a new sync log."""
        sync_log = SyncLogModel(
            endpoint_id=log_data.endpoint_id,
            sync_started_at=log_data.sync_started_at or datetime.utcnow()
        )
        
        self.session.add(sync_log)
        self.session.flush()
        
        logger.info("Sync log created", sync_log_id=sync_log.id, endpoint_id=sync_log.endpoint_id)
        
        return sync_log
    
    @log_execution_time
    def update(self, sync_log_id: int, update_data: SyncLogUpdate) -> Optional[SyncLogModel]:
        """Update a sync log."""
        sync_log = self.session.query(SyncLogModel).filter(SyncLogModel.id == sync_log_id).first()
        if not sync_log:
            return None
        
        update_dict = update_data.dict(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(sync_log, field, value)
        
        # Calculate execution time if completed
        if sync_log.sync_completed_at and not sync_log.execution_time_seconds:
            duration = (sync_log.sync_completed_at - sync_log.sync_started_at).total_seconds()
            sync_log.execution_time_seconds = int(duration)
        
        logger.info("Sync log updated", sync_log_id=sync_log_id, updated_fields=list(update_dict.keys()))
        
        return sync_log
    
    @log_execution_time
    def get_recent_logs(self, endpoint_id: int, limit: int = 10) -> List[SyncLogModel]:
        """Get recent sync logs for an endpoint."""
        return self.session.query(SyncLogModel).filter(
            SyncLogModel.endpoint_id == endpoint_id
        ).order_by(desc(SyncLogModel.sync_started_at)).limit(limit).all()
    
    @log_execution_time
    def get_failed_logs(self, hours: int = 24) -> List[SyncLogModel]:
        """Get failed sync logs within specified hours."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        return self.session.query(SyncLogModel).filter(
            and_(
                SyncLogModel.sync_status == SyncStatus.FAILED,
                SyncLogModel.sync_started_at > cutoff_time
            )
        ).order_by(desc(SyncLogModel.sync_started_at)).all()


# Repository factory functions

def get_endpoint_repository(session: Session) -> EndpointRepository:
    """Get endpoint repository instance."""
    return EndpointRepository(session)


def get_file_repository(session: Session) -> FileRepository:
    """Get file repository instance."""
    return FileRepository(session)


def get_sync_log_repository(session: Session) -> SyncLogRepository:
    """Get sync log repository instance."""
    return SyncLogRepository(session)