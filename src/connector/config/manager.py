"""Configuration manager for dynamic endpoint and schedule management."""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime
from pathlib import Path

from .schema import ConnectorConfig, EndpointConfig, ProjectConfig, ScheduleType
from .loader import ConfigLoader, ConfigurationError
from ..database import DatabaseService, EndpointModel, EndpointType
from ..database.models import EndpointCreate, EndpointUpdate
from ..utils.logging import get_logger, log_execution_time


class ConfigManager:
    """Manages configuration loading, validation, and synchronization with database."""
    
    def __init__(self, database_service: DatabaseService, config_file: Optional[str] = None):
        """Initialize configuration manager.
        
        Args:
            database_service: Database service for persistence
            config_file: Optional configuration file path
        """
        self.db_service = database_service
        self.config_file = config_file
        self.loader = ConfigLoader()
        self.logger = get_logger(self.__class__.__name__)
        
        # Current loaded configuration
        self._config: Optional[ConnectorConfig] = None
        self._config_loaded_at: Optional[datetime] = None
        
        self.logger.info("Configuration manager initialized")
    
    @log_execution_time
    def load_config(self, force_reload: bool = False) -> ConnectorConfig:
        """Load configuration from file or create default.
        
        Args:
            force_reload: Force reload even if config is already loaded
            
        Returns:
            Loaded configuration
        """
        if self._config and not force_reload:
            return self._config
        
        try:
            if self.config_file:
                self._config = self.loader.load_from_file(self.config_file)
            else:
                from .loader import load_config_from_env
                self._config = load_config_from_env()
            
            self._config_loaded_at = datetime.now()
            
            # Validate configuration
            warnings = self.loader.validate_config(self._config)
            if warnings:
                self.logger.warning("Configuration validation warnings", warnings=warnings)
            
            self.logger.info(
                "Configuration loaded successfully",
                endpoints_count=len(self._config.endpoints),
                environment=self._config.environment,
                config_file=self.config_file
            )
            
            return self._config
            
        except Exception as e:
            self.logger.error("Failed to load configuration", error=str(e))
            raise ConfigurationError(f"Failed to load configuration: {e}")
    
    @log_execution_time
    def sync_to_database(self) -> Dict[str, int]:
        """Sync configuration endpoints to database.
        
        Returns:
            Dictionary with sync statistics
        """
        config = self.load_config()
        
        stats = {
            "endpoints_added": 0,
            "endpoints_updated": 0,
            "endpoints_skipped": 0,
            "endpoints_deactivated": 0
        }
        
        self.logger.info("Starting configuration sync to database")
        
        try:
            # Get existing endpoints from database
            existing_endpoints = {
                f"{ep.endpoint_type.value}:{ep.project_id}:{ep.user_id}": ep
                for ep in self.db_service.get_endpoints()
            }
            
            config_endpoint_keys = set()
            
            # Process each endpoint from configuration
            for endpoint_config in config.endpoints:
                endpoint_key = f"{endpoint_config.endpoint_type.value}:{endpoint_config.project_id}:{endpoint_config.user_id}"
                config_endpoint_keys.add(endpoint_key)
                
                if endpoint_key in existing_endpoints:
                    # Update existing endpoint
                    existing_endpoint = existing_endpoints[endpoint_key]
                    
                    # Check if update is needed
                    if self._endpoint_needs_update(existing_endpoint, endpoint_config):
                        update_data = EndpointUpdate(
                            endpoint_details=endpoint_config.endpoint_details,
                            description=endpoint_config.description,
                            is_active=endpoint_config.is_active
                        )
                        
                        self.db_service.update_endpoint(existing_endpoint.id, update_data)
                        stats["endpoints_updated"] += 1
                        
                        self.logger.info(
                            "Updated endpoint from configuration",
                            endpoint_id=existing_endpoint.id,
                            name=endpoint_config.name
                        )
                    else:
                        stats["endpoints_skipped"] += 1
                else:
                    # Create new endpoint
                    endpoint_create = EndpointCreate(
                        endpoint_type=endpoint_config.endpoint_type,
                        project_id=endpoint_config.project_id,
                        user_id=endpoint_config.user_id,
                        endpoint_details=endpoint_config.endpoint_details,
                        description=endpoint_config.description,
                        is_active=endpoint_config.is_active
                    )
                    
                    new_endpoint = self.db_service.create_endpoint(endpoint_create)
                    stats["endpoints_added"] += 1
                    
                    self.logger.info(
                        "Created new endpoint from configuration",
                        endpoint_id=new_endpoint.id,
                        name=endpoint_config.name
                    )
            
            # Deactivate endpoints not in configuration (optional)
            if config.environment == "production":
                for endpoint_key, existing_endpoint in existing_endpoints.items():
                    if endpoint_key not in config_endpoint_keys and existing_endpoint.is_active:
                        self.db_service.update_endpoint(existing_endpoint.id, {"is_active": False})
                        stats["endpoints_deactivated"] += 1
                        
                        self.logger.info(
                            "Deactivated endpoint not in configuration",
                            endpoint_id=existing_endpoint.id
                        )
            
            self.logger.info("Configuration sync completed", stats=stats)
            return stats
            
        except Exception as e:
            self.logger.error("Failed to sync configuration to database", error=str(e))
            raise ConfigurationError(f"Failed to sync to database: {e}")
    
    @log_execution_time
    def export_from_database(self) -> ConnectorConfig:
        """Export current database state as configuration.
        
        Returns:
            Configuration representing current database state
        """
        try:
            # Get all endpoints from database
            db_endpoints = self.db_service.get_endpoints()
            
            # Convert to configuration endpoints
            config_endpoints = []
            for db_endpoint in db_endpoints:
                endpoint_config = EndpointConfig(
                    name=f"{db_endpoint.endpoint_type.value}_{db_endpoint.project_id}_{db_endpoint.id}",
                    endpoint_type=db_endpoint.endpoint_type,
                    project_id=db_endpoint.project_id,
                    user_id=db_endpoint.user_id,
                    description=db_endpoint.description,
                    endpoint_details=db_endpoint.endpoint_details or {},
                    schedule=ScheduleType.MANUAL,  # Default to manual
                    is_active=db_endpoint.is_active
                )
                config_endpoints.append(endpoint_config)
            
            # Create configuration
            config = ConnectorConfig(
                version="1.0.0",
                environment="exported",
                endpoints=config_endpoints
            )
            
            self.logger.info(
                "Exported configuration from database",
                endpoints_count=len(config_endpoints)
            )
            
            return config
            
        except Exception as e:
            self.logger.error("Failed to export configuration from database", error=str(e))
            raise ConfigurationError(f"Failed to export from database: {e}")
    
    def save_config(self, config: ConnectorConfig, file_path: Optional[str] = None, format: str = 'yaml'):
        """Save configuration to file.
        
        Args:
            config: Configuration to save
            file_path: Output file path (defaults to current config file)
            format: Output format ('yaml' or 'json')
        """
        output_path = file_path or self.config_file or f"connector.{format}"
        
        try:
            self.loader.save_to_file(config, output_path, format)
            self.logger.info("Configuration saved", file_path=output_path)
            
        except Exception as e:
            self.logger.error("Failed to save configuration", error=str(e))
            raise ConfigurationError(f"Failed to save configuration: {e}")
    
    def add_endpoint(self, endpoint_config: EndpointConfig, sync_to_db: bool = True) -> EndpointModel:
        """Add new endpoint to configuration and optionally to database.
        
        Args:
            endpoint_config: Endpoint configuration to add
            sync_to_db: Whether to sync to database immediately
            
        Returns:
            Created endpoint model (if synced to DB)
        """
        # Add to in-memory configuration
        if self._config:
            self._config.endpoints.append(endpoint_config)
        
        # Sync to database if requested
        if sync_to_db:
            endpoint_create = EndpointCreate(
                endpoint_type=endpoint_config.endpoint_type,
                project_id=endpoint_config.project_id,
                user_id=endpoint_config.user_id,
                endpoint_details=endpoint_config.endpoint_details,
                description=endpoint_config.description,
                is_active=endpoint_config.is_active
            )
            
            endpoint = self.db_service.create_endpoint(endpoint_create)
            
            self.logger.info(
                "Added new endpoint",
                endpoint_id=endpoint.id,
                name=endpoint_config.name
            )
            
            return endpoint
    
    def remove_endpoint(self, endpoint_name: str, sync_to_db: bool = True) -> bool:
        """Remove endpoint from configuration and optionally from database.
        
        Args:
            endpoint_name: Name of endpoint to remove
            sync_to_db: Whether to sync to database immediately
            
        Returns:
            True if endpoint was found and removed
        """
        if not self._config:
            return False
        
        # Find and remove from configuration
        for i, endpoint in enumerate(self._config.endpoints):
            if endpoint.name == endpoint_name:
                removed_endpoint = self._config.endpoints.pop(i)
                
                # Deactivate in database if requested
                if sync_to_db:
                    # Find corresponding database endpoint
                    db_endpoints = self.db_service.get_endpoints(
                        endpoint_type=removed_endpoint.endpoint_type,
                        project_id=removed_endpoint.project_id,
                        user_id=removed_endpoint.user_id
                    )
                    
                    for db_endpoint in db_endpoints:
                        self.db_service.update_endpoint(db_endpoint.id, {"is_active": False})
                
                self.logger.info("Removed endpoint", name=endpoint_name)
                return True
        
        return False
    
    def get_endpoint_config(self, endpoint_name: str) -> Optional[EndpointConfig]:
        """Get endpoint configuration by name.
        
        Args:
            endpoint_name: Name of endpoint
            
        Returns:
            Endpoint configuration or None if not found
        """
        if not self._config:
            self.load_config()
        
        for endpoint in self._config.endpoints:
            if endpoint.name == endpoint_name:
                return endpoint
        
        return None
    
    def get_endpoints_by_project(self, project_id: str) -> List[EndpointConfig]:
        """Get all endpoints for a project.
        
        Args:
            project_id: Project identifier
            
        Returns:
            List of endpoint configurations
        """
        if not self._config:
            self.load_config()
        
        return [ep for ep in self._config.endpoints if ep.project_id == project_id]
    
    def get_scheduled_endpoints(self) -> List[EndpointConfig]:
        """Get all endpoints with scheduled syncing.
        
        Returns:
            List of scheduled endpoint configurations
        """
        if not self._config:
            self.load_config()
        
        return [
            ep for ep in self._config.endpoints
            if ep.is_active and ep.schedule != ScheduleType.MANUAL
        ]
    
    def reload_config(self) -> ConnectorConfig:
        """Reload configuration from file.
        
        Returns:
            Reloaded configuration
        """
        return self.load_config(force_reload=True)
    
    def get_config(self) -> ConnectorConfig:
        """Get current configuration.
        
        Returns:
            Current configuration (loads if not already loaded)
        """
        return self.load_config()
    
    def _endpoint_needs_update(self, db_endpoint: EndpointModel, config_endpoint: EndpointConfig) -> bool:
        """Check if database endpoint needs update based on configuration.
        
        Args:
            db_endpoint: Database endpoint
            config_endpoint: Configuration endpoint
            
        Returns:
            True if update is needed
        """
        # Check key fields that might have changed
        if db_endpoint.endpoint_details != config_endpoint.endpoint_details:
            return True
        
        if db_endpoint.description != config_endpoint.description:
            return True
        
        if db_endpoint.is_active != config_endpoint.is_active:
            return True
        
        return False