"""Configuration loader for JSON/YAML files and environment variables."""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from datetime import datetime

from .schema import ConnectorConfig, EndpointConfig, ProjectConfig, ScheduleType
from ..utils.logging import get_logger


class ConfigurationError(Exception):
    """Raised when configuration loading fails."""
    pass


class ConfigLoader:
    """Loads and validates configuration from various sources."""
    
    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
    
    def load_from_file(self, file_path: Union[str, Path]) -> ConnectorConfig:
        """Load configuration from JSON or YAML file.
        
        Args:
            file_path: Path to configuration file
            
        Returns:
            Validated ConnectorConfig object
            
        Raises:
            ConfigurationError: If file cannot be loaded or validated
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise ConfigurationError(f"Configuration file not found: {file_path}")
        
        self.logger.info("Loading configuration from file", file_path=str(file_path))
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                if file_path.suffix.lower() in ['.yaml', '.yml']:
                    data = yaml.safe_load(f)
                elif file_path.suffix.lower() == '.json':
                    data = json.load(f)
                else:
                    raise ConfigurationError(f"Unsupported file format: {file_path.suffix}")
            
            # Apply environment variable overrides
            data = self._apply_env_overrides(data)
            
            # Validate and create config object
            config = ConnectorConfig(**data)
            
            self.logger.info(
                "Configuration loaded successfully",
                endpoints_count=len(config.endpoints),
                environment=config.environment
            )
            
            return config
            
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML format: {e}")
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON format: {e}")
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}")
    
    def load_from_dict(self, data: Dict[str, Any]) -> ConnectorConfig:
        """Load configuration from dictionary.
        
        Args:
            data: Configuration data as dictionary
            
        Returns:
            Validated ConnectorConfig object
        """
        try:
            # Apply environment variable overrides
            data = self._apply_env_overrides(data)
            
            # Validate and create config object
            config = ConnectorConfig(**data)
            
            self.logger.info(
                "Configuration loaded from dictionary",
                endpoints_count=len(config.endpoints)
            )
            
            return config
            
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration from dict: {e}")
    
    def load_project_config(self, file_path: Union[str, Path]) -> ProjectConfig:
        """Load project-specific configuration.
        
        Args:
            file_path: Path to project configuration file
            
        Returns:
            Validated ProjectConfig object
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise ConfigurationError(f"Project configuration file not found: {file_path}")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                if file_path.suffix.lower() in ['.yaml', '.yml']:
                    data = yaml.safe_load(f)
                elif file_path.suffix.lower() == '.json':
                    data = json.load(f)
                else:
                    raise ConfigurationError(f"Unsupported file format: {file_path.suffix}")
            
            # Apply environment variable overrides
            data = self._apply_env_overrides(data)
            
            # Validate and create config object
            config = ProjectConfig(**data)
            
            self.logger.info(
                "Project configuration loaded successfully",
                project_id=config.project_id,
                endpoints_count=len(config.endpoints)
            )
            
            return config
            
        except Exception as e:
            raise ConfigurationError(f"Failed to load project configuration: {e}")
    
    def save_to_file(self, config: ConnectorConfig, file_path: Union[str, Path], format: str = 'yaml'):
        """Save configuration to file.
        
        Args:
            config: Configuration to save
            file_path: Output file path
            format: Output format ('yaml' or 'json')
        """
        file_path = Path(file_path)
        
        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to dictionary with proper serialization
        data = config.dict()
        
        # Update timestamp
        data['updated_at'] = datetime.now().isoformat()
        
        # Convert enum values to strings for YAML/JSON compatibility
        def convert_enums(obj):
            if isinstance(obj, dict):
                return {k: convert_enums(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_enums(v) for v in obj]
            elif hasattr(obj, 'value'):  # Enum objects
                return obj.value
            else:
                return obj
        
        data = convert_enums(data)
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                if format.lower() == 'yaml':
                    yaml.dump(data, f, default_flow_style=False, indent=2, allow_unicode=True)
                elif format.lower() == 'json':
                    json.dump(data, f, indent=2, default=str)
                else:
                    raise ConfigurationError(f"Unsupported format: {format}")
            
            self.logger.info("Configuration saved successfully", file_path=str(file_path))
            
        except Exception as e:
            raise ConfigurationError(f"Failed to save configuration: {e}")
    
    def create_default_config(self) -> ConnectorConfig:
        """Create a default configuration with examples.
        
        Returns:
            Default ConnectorConfig with example endpoints
        """
        from .schema import GOOGLE_DRIVE_ENDPOINT_EXAMPLE, AUTODESK_ENDPOINT_EXAMPLE
        
        config = ConnectorConfig(
            version="1.0.0",
            environment="development",
            endpoints=[
                GOOGLE_DRIVE_ENDPOINT_EXAMPLE,
                AUTODESK_ENDPOINT_EXAMPLE
            ]
        )
        
        self.logger.info("Created default configuration")
        return config
    
    def merge_configs(self, base_config: ConnectorConfig, override_config: ConnectorConfig) -> ConnectorConfig:
        """Merge two configurations, with override taking precedence.
        
        Args:
            base_config: Base configuration
            override_config: Override configuration
            
        Returns:
            Merged configuration
        """
        # Convert to dictionaries for easier merging
        base_data = base_config.dict()
        override_data = override_config.dict()
        
        # Merge dictionaries (override takes precedence)
        merged_data = {**base_data, **override_data}
        
        # Special handling for endpoints - merge lists
        if 'endpoints' in base_data and 'endpoints' in override_data:
            merged_data['endpoints'] = base_data['endpoints'] + override_data['endpoints']
        
        # Create merged config
        merged_config = ConnectorConfig(**merged_data)
        
        self.logger.info(
            "Configurations merged successfully",
            total_endpoints=len(merged_config.endpoints)
        )
        
        return merged_config
    
    def _apply_env_overrides(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides to configuration data.
        
        Environment variables use the format: CONNECTOR_<SECTION>_<KEY>
        For example: CONNECTOR_DATABASE_URL, CONNECTOR_LOG_LEVEL
        """
        env_overrides = {}
        
        # Database configuration
        if os.getenv('CONNECTOR_DATABASE_URL'):
            env_overrides['database_url'] = os.getenv('CONNECTOR_DATABASE_URL')
        
        # Logging configuration
        if os.getenv('CONNECTOR_LOG_LEVEL'):
            env_overrides['log_level'] = os.getenv('CONNECTOR_LOG_LEVEL')
        
        if os.getenv('CONNECTOR_LOG_FORMAT'):
            env_overrides['log_format'] = os.getenv('CONNECTOR_LOG_FORMAT')
        
        # Environment
        if os.getenv('CONNECTOR_ENVIRONMENT'):
            env_overrides['environment'] = os.getenv('CONNECTOR_ENVIRONMENT')
        
        # Scheduling overrides
        scheduling_overrides = {}
        
        if os.getenv('CONNECTOR_MAX_CONCURRENT_SYNCS'):
            try:
                scheduling_overrides['max_concurrent_syncs'] = int(os.getenv('CONNECTOR_MAX_CONCURRENT_SYNCS'))
            except ValueError:
                self.logger.warning("Invalid CONNECTOR_MAX_CONCURRENT_SYNCS value, ignoring")
        
        if os.getenv('CONNECTOR_SYNC_TIMEOUT_MINUTES'):
            try:
                scheduling_overrides['sync_timeout_minutes'] = int(os.getenv('CONNECTOR_SYNC_TIMEOUT_MINUTES'))
            except ValueError:
                self.logger.warning("Invalid CONNECTOR_SYNC_TIMEOUT_MINUTES value, ignoring")
        
        if os.getenv('CONNECTOR_MAX_FILES_PER_SYNC'):
            try:
                scheduling_overrides['max_files_per_sync'] = int(os.getenv('CONNECTOR_MAX_FILES_PER_SYNC'))
            except ValueError:
                self.logger.warning("Invalid CONNECTOR_MAX_FILES_PER_SYNC value, ignoring")
        
        if scheduling_overrides:
            if 'scheduling' not in env_overrides:
                env_overrides['scheduling'] = data.get('scheduling', {})
            env_overrides['scheduling'].update(scheduling_overrides)
        
        # Security overrides
        if os.getenv('CONNECTOR_REQUIRE_HTTPS'):
            env_overrides['require_https'] = os.getenv('CONNECTOR_REQUIRE_HTTPS').lower() in ['true', '1', 'yes']
        
        # Monitoring overrides
        if os.getenv('CONNECTOR_METRICS_ENABLED'):
            env_overrides['metrics_enabled'] = os.getenv('CONNECTOR_METRICS_ENABLED').lower() in ['true', '1', 'yes']
        
        # Apply overrides
        if env_overrides:
            self.logger.info("Applied environment variable overrides", overrides=list(env_overrides.keys()))
            data = {**data, **env_overrides}
        
        return data
    
    def validate_config(self, config: ConnectorConfig) -> List[str]:
        """Validate configuration and return list of warnings/issues.
        
        Args:
            config: Configuration to validate
            
        Returns:
            List of validation warnings
        """
        warnings = []
        
        # Check for duplicate endpoint names
        endpoint_names = [ep.name for ep in config.endpoints]
        if len(endpoint_names) != len(set(endpoint_names)):
            warnings.append("Duplicate endpoint names found")
        
        # Check for endpoints without schedules in production
        if config.environment == 'production':
            manual_endpoints = [ep for ep in config.endpoints if ep.schedule == ScheduleType.MANUAL]
            if manual_endpoints:
                warnings.append(f"{len(manual_endpoints)} endpoints have manual schedule in production")
        
        # Check for reasonable file limits
        for endpoint in config.endpoints:
            if endpoint.max_files_per_sync and endpoint.max_files_per_sync > 10000:
                warnings.append(f"Endpoint '{endpoint.name}' has very high max_files_per_sync: {endpoint.max_files_per_sync}")
        
        # Check for missing required environment variables in production
        if config.environment == 'production':
            required_env_vars = ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'AUTODESK_CLIENT_ID', 'AUTODESK_CLIENT_SECRET']
            missing_vars = [var for var in required_env_vars if not os.getenv(var)]
            if missing_vars:
                warnings.append(f"Missing required environment variables: {missing_vars}")
        
        # Check database configuration
        if not config.database_url and not os.getenv('CONNECTOR_DATABASE_URL'):
            warnings.append("No database URL configured")
        
        if warnings:
            self.logger.warning("Configuration validation warnings", warnings=warnings)
        else:
            self.logger.info("Configuration validation passed")
        
        return warnings


def load_config_from_env() -> ConnectorConfig:
    """Load configuration from environment variables and default files.
    
    Looks for configuration files in this order:
    1. CONNECTOR_CONFIG_FILE environment variable
    2. ./config/connector.yaml
    3. ./config/connector.json
    4. ./connector.yaml
    5. ./connector.json
    
    If no file is found, creates a default configuration.
    """
    loader = ConfigLoader()
    logger = get_logger("load_config_from_env")
    
    # Check for explicit config file
    config_file = os.getenv('CONNECTOR_CONFIG_FILE')
    if config_file:
        if os.path.exists(config_file):
            return loader.load_from_file(config_file)
        else:
            logger.warning("Specified config file not found", file=config_file)
    
    # Look for default config files
    possible_files = [
        './config/connector.yaml',
        './config/connector.yml', 
        './config/connector.json',
        './connector.yaml',
        './connector.yml',
        './connector.json'
    ]
    
    for file_path in possible_files:
        if os.path.exists(file_path):
            logger.info("Found configuration file", file=file_path)
            return loader.load_from_file(file_path)
    
    # No config file found, create default
    logger.info("No configuration file found, creating default configuration")
    return loader.create_default_config()