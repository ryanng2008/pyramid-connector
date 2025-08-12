"""Application configuration settings."""

import os
from typing import Optional, List, Dict, Any
from pydantic import Field
from pydantic_settings import BaseSettings
from pathlib import Path


class DatabaseSettings(BaseSettings):
    """Database configuration."""
    
    url: str = Field(default="sqlite:///./data/connector.db", env="DATABASE_URL")
    
    class Config:
        env_prefix = "DB_"


class GoogleDriveSettings(BaseSettings):
    """Google Drive API configuration."""
    
    credentials_path: str = Field(default="./secrets/google_service_account.json", env="GOOGLE_CREDENTIALS_PATH")
    application_name: str = Field(default="File Connector", env="GOOGLE_APPLICATION_NAME")
    
    class Config:
        env_prefix = "GOOGLE_"


class AutodeskSettings(BaseSettings):
    """Autodesk Construction Cloud API configuration."""
    
    client_id: str = Field(default="", env="AUTODESK_CLIENT_ID")
    client_secret: str = Field(default="", env="AUTODESK_CLIENT_SECRET")
    callback_url: str = Field(default="http://localhost:8080/callback", env="AUTODESK_CALLBACK_URL")
    base_url: str = Field(default="https://developer.api.autodesk.com", env="AUTODESK_BASE_URL")
    
    class Config:
        env_prefix = "AUTODESK_"


class SupabaseSettings(BaseSettings):
    """Supabase configuration."""
    
    url: str = Field(default="", env="SUPABASE_URL")
    anon_key: str = Field(default="", env="SUPABASE_ANON_KEY")
    service_role_key: str = Field(default="", env="SUPABASE_SERVICE_ROLE_KEY")
    
    class Config:
        env_prefix = "CONNECTOR_SUPABASE_"


class SchedulingSettings(BaseSettings):
    """Scheduling configuration."""
    
    sync_interval_minutes: int = Field(default=5, env="SYNC_INTERVAL_MINUTES")
    max_concurrent_syncs: int = Field(default=5, env="MAX_CONCURRENT_SYNCS")
    
    class Config:
        env_prefix = "SCHEDULE_"


class LoggingSettings(BaseSettings):
    """Logging configuration."""
    
    level: str = Field(default="INFO", env="LOG_LEVEL")
    format: str = Field(default="json", env="LOG_FORMAT")
    file_path: Optional[str] = Field(default="./logs/connector.log", env="LOG_FILE_PATH")
    
    class Config:
        env_prefix = "LOG_"


class AppSettings(BaseSettings):
    """Main application settings."""
    
    name: str = Field(default="File Connector", env="APP_NAME")
    version: str = Field(default="1.0.0", env="APP_VERSION")
    environment: str = Field(default="development", env="ENVIRONMENT")
    
    # Sub-settings
    database: DatabaseSettings = DatabaseSettings()
    google_drive: GoogleDriveSettings = GoogleDriveSettings()
    autodesk: AutodeskSettings = AutodeskSettings()
    supabase: SupabaseSettings = SupabaseSettings()
    scheduling: SchedulingSettings = SchedulingSettings()
    logging: LoggingSettings = LoggingSettings()
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "allow"  # Allow extra fields in environment


# Global settings instance
settings = AppSettings()


def get_settings() -> AppSettings:
    """Get application settings."""
    return settings


def load_endpoints_config(config_path: str = "./config/endpoints.json") -> List[Dict[str, Any]]:
    """Load endpoints configuration from file."""
    import json
    
    config_file = Path(config_path)
    if not config_file.exists():
        # Return default configuration
        return [
            {
                "type": "google_drive",
                "endpoint_details": {
                    "folder_id": None,  # None means root folder
                    "include_shared": True
                },
                "project_id": "default_project",
                "user_id": "default_user",
                "schedule": "*/5 * * * *"  # Every 5 minutes
            },
            {
                "type": "autodesk_construction_cloud",
                "endpoint_details": {
                    "project_id": "your_autodesk_project_id",
                    "folder_id": None
                },
                "project_id": "autodesk_project_1",
                "user_id": "autodesk_user_1",
                "schedule": "*/5 * * * *"  # Every 5 minutes
            }
        ]
    
    with open(config_file, 'r') as f:
        return json.load(f)