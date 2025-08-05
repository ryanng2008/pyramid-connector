"""Configuration schema definitions for endpoints and schedules."""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, validator

from ..database.models import EndpointType


class ScheduleType(str, Enum):
    """Types of sync schedules."""
    MANUAL = "manual"
    INTERVAL = "interval"
    CRON = "cron"
    WEBHOOK = "webhook"


class EndpointConfig(BaseModel):
    """Configuration for a single sync endpoint."""
    
    # Basic endpoint information
    name: str = Field(..., description="Human-readable name for the endpoint")
    endpoint_type: EndpointType = Field(..., description="Type of endpoint")
    project_id: str = Field(..., description="Project identifier")
    user_id: str = Field(..., description="User identifier")
    description: Optional[str] = Field(None, description="Optional description")
    
    # Endpoint-specific configuration
    endpoint_details: Dict[str, Any] = Field(default_factory=dict, description="Endpoint-specific settings")
    
    # Sync configuration
    schedule: ScheduleType = Field(default=ScheduleType.MANUAL, description="How this endpoint should be synced")
    schedule_config: Optional[Dict[str, Any]] = Field(None, description="Schedule-specific configuration")
    
    # Filtering and processing
    file_types: Optional[List[str]] = Field(None, description="File types to sync (None = all)")
    max_files_per_sync: Optional[int] = Field(None, description="Maximum files per sync operation")
    
    # Status and control
    is_active: bool = Field(default=True, description="Whether this endpoint is active")
    tags: Optional[List[str]] = Field(None, description="Tags for organizing endpoints")
    
    @validator('schedule_config')
    def validate_schedule_config(cls, v, values):
        """Validate schedule configuration based on schedule type."""
        if v is None:
            return v
        
        schedule_type = values.get('schedule')
        
        if schedule_type == ScheduleType.INTERVAL:
            required_fields = ['interval_minutes']
            if not all(field in v for field in required_fields):
                raise ValueError(f"Interval schedule requires: {required_fields}")
            
            if v['interval_minutes'] < 1:
                raise ValueError("Interval must be at least 1 minute")
        
        elif schedule_type == ScheduleType.CRON:
            required_fields = ['cron_expression']
            if not all(field in v for field in required_fields):
                raise ValueError(f"Cron schedule requires: {required_fields}")
        
        elif schedule_type == ScheduleType.WEBHOOK:
            required_fields = ['webhook_secret']
            if not all(field in v for field in required_fields):
                raise ValueError(f"Webhook schedule requires: {required_fields}")
        
        return v
    
    @validator('endpoint_details')
    def validate_endpoint_details(cls, v, values):
        """Validate endpoint details based on endpoint type."""
        endpoint_type = values.get('endpoint_type')
        
        if endpoint_type == EndpointType.GOOGLE_DRIVE:
            # Google Drive specific validation
            if 'folder_id' in v and not isinstance(v['folder_id'], (str, type(None))):
                raise ValueError("Google Drive folder_id must be a string or None")
        
        elif endpoint_type == EndpointType.AUTODESK_CONSTRUCTION_CLOUD:
            # Autodesk specific validation
            if 'project_id' not in v:
                raise ValueError("Autodesk Construction Cloud requires project_id in endpoint_details")
        
        return v


class ScheduleConfig(BaseModel):
    """Configuration for sync schedules."""
    
    # Default schedule settings
    default_schedule: ScheduleType = Field(default=ScheduleType.INTERVAL, description="Default schedule type")
    default_interval_minutes: int = Field(default=5, description="Default interval in minutes")
    
    # Global schedule limits
    max_concurrent_syncs: int = Field(default=10, description="Maximum concurrent sync operations")
    sync_timeout_minutes: int = Field(default=30, description="Timeout for sync operations")
    
    # Retry configuration
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    retry_delay_seconds: int = Field(default=30, description="Delay between retries")
    rate_limit_backoff_seconds: int = Field(default=60, description="Backoff for rate limits")
    
    # Performance settings
    max_files_per_sync: int = Field(default=1000, description="Default max files per sync")
    batch_size: int = Field(default=50, description="Batch size for database operations")
    
    @validator('default_interval_minutes')
    def validate_interval(cls, v):
        if v < 1:
            raise ValueError("Interval must be at least 1 minute")
        return v
    
    @validator('max_concurrent_syncs')
    def validate_concurrent_syncs(cls, v):
        if v < 1:
            raise ValueError("Must allow at least 1 concurrent sync")
        return v


class ConnectorConfig(BaseModel):
    """Root configuration for the entire connector system."""
    
    # Metadata
    version: str = Field(default="1.0.0", description="Configuration version")
    created_at: datetime = Field(default_factory=datetime.now, description="When config was created")
    updated_at: datetime = Field(default_factory=datetime.now, description="When config was last updated")
    
    # Environment
    environment: str = Field(default="development", description="Environment (development, staging, production)")
    
    # Endpoints configuration
    endpoints: List[EndpointConfig] = Field(default_factory=list, description="List of sync endpoints")
    
    # Scheduling configuration
    scheduling: ScheduleConfig = Field(default_factory=ScheduleConfig, description="Schedule configuration")
    
    # Logging configuration
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Logging format (json, console)")
    
    # Database configuration (overrides for environment)
    database_url: Optional[str] = Field(None, description="Database URL override")
    
    # Security settings
    require_https: bool = Field(default=True, description="Require HTTPS for webhooks")
    webhook_timeout_seconds: int = Field(default=30, description="Webhook timeout")
    
    # Monitoring and health
    health_check_interval_minutes: int = Field(default=5, description="Health check interval")
    metrics_enabled: bool = Field(default=True, description="Enable metrics collection")
    
    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()
    
    @validator('environment')
    def validate_environment(cls, v):
        valid_envs = ['development', 'staging', 'production']
        if v.lower() not in valid_envs:
            raise ValueError(f"Environment must be one of: {valid_envs}")
        return v.lower()
    
    def get_endpoints_by_type(self, endpoint_type: EndpointType) -> List[EndpointConfig]:
        """Get all endpoints of a specific type."""
        return [ep for ep in self.endpoints if ep.endpoint_type == endpoint_type]
    
    def get_endpoints_by_project(self, project_id: str) -> List[EndpointConfig]:
        """Get all endpoints for a specific project."""
        return [ep for ep in self.endpoints if ep.project_id == project_id]
    
    def get_active_endpoints(self) -> List[EndpointConfig]:
        """Get all active endpoints."""
        return [ep for ep in self.endpoints if ep.is_active]
    
    def get_scheduled_endpoints(self) -> List[EndpointConfig]:
        """Get endpoints that have scheduled syncing."""
        return [
            ep for ep in self.endpoints 
            if ep.is_active and ep.schedule != ScheduleType.MANUAL
        ]


class ProjectConfig(BaseModel):
    """Configuration for a specific project."""
    
    project_id: str = Field(..., description="Project identifier")
    name: str = Field(..., description="Project name")
    description: Optional[str] = Field(None, description="Project description")
    
    # Project-level settings
    default_file_types: Optional[List[str]] = Field(None, description="Default file types for this project")
    max_files_per_endpoint: Optional[int] = Field(None, description="Max files per endpoint for this project")
    
    # Project-specific endpoints
    endpoints: List[EndpointConfig] = Field(default_factory=list, description="Endpoints for this project")
    
    # Project metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = Field(default=True)
    tags: Optional[List[str]] = Field(None, description="Project tags")


# Example configurations for documentation
GOOGLE_DRIVE_ENDPOINT_EXAMPLE = EndpointConfig(
    name="Main Google Drive",
    endpoint_type=EndpointType.GOOGLE_DRIVE,
    project_id="project_123",
    user_id="user_456",
    description="Primary Google Drive folder sync",
    endpoint_details={
        "folder_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
        "include_shared": True,
        "file_types": ["pdf", "docx", "xlsx"]
    },
    schedule=ScheduleType.INTERVAL,
    schedule_config={
        "interval_minutes": 5
    },
    file_types=["pdf", "docx", "xlsx"],
    max_files_per_sync=500,
    tags=["documents", "main"]
)

AUTODESK_ENDPOINT_EXAMPLE = EndpointConfig(
    name="Construction Project Files",
    endpoint_type=EndpointType.AUTODESK_CONSTRUCTION_CLOUD,
    project_id="project_123", 
    user_id="user_456",
    description="Autodesk Construction Cloud project files",
    endpoint_details={
        "project_id": "b.project_id_here",
        "folder_id": "folder_123",
        "include_subfolders": True,
        "file_types": ["dwg", "rvt", "pdf", "nwd"]
    },
    schedule=ScheduleType.INTERVAL,
    schedule_config={
        "interval_minutes": 10
    },
    file_types=["dwg", "rvt", "pdf", "nwd"],
    max_files_per_sync=200,
    tags=["cad", "construction"]
)