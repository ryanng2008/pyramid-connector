"""Configuration package for the file connector."""

from .settings import (
    DatabaseSettings,
    GoogleDriveSettings,
    AutodeskSettings,
    SupabaseSettings,
    AppSettings,
    get_settings
)

from .schema import (
    ConnectorConfig,
    EndpointConfig,
    ProjectConfig,
    ScheduleConfig,
    ScheduleType,
    GOOGLE_DRIVE_ENDPOINT_EXAMPLE,
    AUTODESK_ENDPOINT_EXAMPLE
)

from .loader import (
    ConfigLoader,
    ConfigurationError,
    load_config_from_env
)

from .manager import ConfigManager

__all__ = [
    # Legacy settings
    "DatabaseSettings",
    "GoogleDriveSettings", 
    "AutodeskSettings",
    "SupabaseSettings",
    "AppSettings",
    "get_settings",
    
    # New configuration system
    "ConnectorConfig",
    "EndpointConfig", 
    "ProjectConfig",
    "ScheduleConfig",
    "ScheduleType",
    "GOOGLE_DRIVE_ENDPOINT_EXAMPLE",
    "AUTODESK_ENDPOINT_EXAMPLE",
    
    "ConfigLoader",
    "ConfigurationError", 
    "load_config_from_env",
    
    "ConfigManager"
]
