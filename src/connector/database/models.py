"""Database models for the File Connector."""

from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

from sqlalchemy import Column, Integer, String, DateTime, JSON, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field


Base = declarative_base()


class EndpointType(str, Enum):
    """Supported endpoint types."""
    GOOGLE_DRIVE = "google_drive"
    AUTODESK_CONSTRUCTION_CLOUD = "autodesk_construction_cloud"


class SyncStatus(str, Enum):
    """Sync status for files and endpoints."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# SQLAlchemy Models (Database Tables)

class EndpointModel(Base):
    """Database model for API endpoints configuration."""
    
    __tablename__ = "endpoints"
    
    id = Column(Integer, primary_key=True, index=True)
    endpoint_type = Column(String(50), nullable=False, index=True)
    endpoint_details = Column(JSON, nullable=False)
    project_id = Column(String(100), nullable=False, index=True)
    user_id = Column(String(100), nullable=False, index=True)
    description = Column(String(500), nullable=True)
    schedule_cron = Column(String(50), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_sync_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(20), default=SyncStatus.PENDING, nullable=False)
    
    # Relationships
    files = relationship("FileModel", back_populates="endpoint", cascade="all, delete-orphan")
    sync_logs = relationship("SyncLogModel", back_populates="endpoint", cascade="all, delete-orphan")


class FileModel(Base):
    """Database model for file metadata."""
    
    __tablename__ = "files"
    
    id = Column(Integer, primary_key=True, index=True)
    endpoint_id = Column(Integer, ForeignKey("endpoints.id"), nullable=False, index=True)
    
    # File identification
    external_file_id = Column(String(255), nullable=False, index=True)  # ID from external API
    file_name = Column(String(500), nullable=False)
    file_path = Column(Text, nullable=True)  # Full path in the source system
    file_link = Column(Text, nullable=False)  # Download/view link
    
    # File metadata
    file_size = Column(Integer, nullable=True)  # Size in bytes
    file_type = Column(String(100), nullable=True)  # MIME type or extension
    
    # Timestamps
    external_created_at = Column(DateTime, nullable=True)  # Created timestamp from external system
    external_updated_at = Column(DateTime, nullable=True)  # Modified timestamp from external system
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # When record was created in our DB
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Sync tracking
    last_synced_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sync_status = Column(String(20), default=SyncStatus.COMPLETED, nullable=False)
    
    # Additional metadata (JSON field for flexibility)
    file_metadata = Column(JSON, nullable=True)
    
    # Relationships
    endpoint = relationship("EndpointModel", back_populates="files")
    
    def __repr__(self):
        return f"<FileModel(id={self.id}, name='{self.file_name}', external_id='{self.external_file_id}')>"


class SyncLogModel(Base):
    """Database model for sync operation logs."""
    
    __tablename__ = "sync_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    endpoint_id = Column(Integer, ForeignKey("endpoints.id"), nullable=False, index=True)
    
    # Sync operation details
    sync_started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sync_completed_at = Column(DateTime, nullable=True)
    sync_status = Column(String(20), default=SyncStatus.IN_PROGRESS, nullable=False)
    
    # Results
    files_found = Column(Integer, default=0, nullable=False)
    files_new = Column(Integer, default=0, nullable=False)
    files_updated = Column(Integer, default=0, nullable=False)
    files_skipped = Column(Integer, default=0, nullable=False)
    files_error = Column(Integer, default=0, nullable=False)
    
    # Error tracking
    error_message = Column(Text, nullable=True)
    error_details = Column(JSON, nullable=True)
    
    # Performance metrics
    execution_time_seconds = Column(Integer, nullable=True)
    
    # Relationships
    endpoint = relationship("EndpointModel", back_populates="sync_logs")
    
    def __repr__(self):
        return f"<SyncLogModel(id={self.id}, endpoint_id={self.endpoint_id}, status='{self.sync_status}')>"


# Pydantic Models (API/Transfer Objects)

class EndpointCreate(BaseModel):
    """Pydantic model for creating an endpoint."""
    endpoint_type: EndpointType
    endpoint_details: Dict[str, Any]
    project_id: str
    user_id: str
    schedule_cron: str = "*/5 * * * *"  # Default: every 5 minutes
    enabled: bool = True


class EndpointUpdate(BaseModel):
    """Pydantic model for updating an endpoint."""
    endpoint_details: Optional[Dict[str, Any]] = None
    schedule_cron: Optional[str] = None
    enabled: Optional[bool] = None


class EndpointResponse(BaseModel):
    """Pydantic model for endpoint response."""
    id: int
    endpoint_type: str
    endpoint_details: Dict[str, Any]
    project_id: str
    user_id: str
    schedule_cron: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    last_sync_at: Optional[datetime] = None
    last_sync_status: str
    
    class Config:
        from_attributes = True


class FileCreate(BaseModel):
    """Pydantic model for creating a file record."""
    endpoint_id: int
    external_file_id: str
    file_name: str
    file_path: Optional[str] = None
    file_link: str
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    external_created_at: Optional[datetime] = None
    external_updated_at: Optional[datetime] = None
    file_metadata: Optional[Dict[str, Any]] = None


class FileResponse(BaseModel):
    """Pydantic model for file response."""
    id: int
    endpoint_id: int
    external_file_id: str
    file_name: str
    file_path: Optional[str] = None
    file_link: str
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    external_created_at: Optional[datetime] = None
    external_updated_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    last_synced_at: datetime
    sync_status: str
    file_metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True


class SyncLogCreate(BaseModel):
    """Pydantic model for creating a sync log."""
    endpoint_id: int
    sync_started_at: Optional[datetime] = None


class SyncLogUpdate(BaseModel):
    """Pydantic model for updating a sync log."""
    sync_completed_at: Optional[datetime] = None
    sync_status: Optional[SyncStatus] = None
    files_found: Optional[int] = None
    files_new: Optional[int] = None
    files_updated: Optional[int] = None
    files_skipped: Optional[int] = None
    files_error: Optional[int] = None
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    execution_time_seconds: Optional[int] = None


class SyncLogResponse(BaseModel):
    """Pydantic model for sync log response."""
    id: int
    endpoint_id: int
    sync_started_at: datetime
    sync_completed_at: Optional[datetime] = None
    sync_status: str
    files_found: int
    files_new: int
    files_updated: int
    files_skipped: int
    files_error: int
    error_message: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    execution_time_seconds: Optional[int] = None
    
    class Config:
        from_attributes = True