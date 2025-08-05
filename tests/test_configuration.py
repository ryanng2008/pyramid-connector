"""Test script for configuration management system."""

import sys
import os
import tempfile
import json
import yaml
from pathlib import Path
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from connector.config import (
    ConnectorConfig, EndpointConfig, ScheduleConfig, ScheduleType,
    ConfigLoader, ConfigurationError, load_config_from_env,
    GOOGLE_DRIVE_ENDPOINT_EXAMPLE, AUTODESK_ENDPOINT_EXAMPLE
)
from connector.database.models import EndpointType
from connector.utils.logging import setup_logging, get_logger


def create_test_config_data():
    """Create test configuration data."""
    return {
        "version": "1.0.0",
        "environment": "development",
        "scheduling": {
            "default_schedule": "interval",
            "default_interval_minutes": 5,
            "max_concurrent_syncs": 5,
            "sync_timeout_minutes": 15,
            "max_retries": 2,
            "max_files_per_sync": 100
        },
        "log_level": "INFO",
        "log_format": "json",
        "endpoints": [
            {
                "name": "Test Google Drive",
                "endpoint_type": "google_drive",
                "project_id": "test_project",
                "user_id": "test_user",
                "description": "Test Google Drive endpoint",
                "endpoint_details": {
                    "folder_id": "test_folder",
                    "include_shared": True,
                    "file_types": ["pdf", "docx"]
                },
                "schedule": "interval",
                "schedule_config": {
                    "interval_minutes": 10
                },
                "file_types": ["pdf", "docx"],
                "is_active": True,
                "tags": ["test", "documents"]
            },
            {
                "name": "Test Autodesk",
                "endpoint_type": "autodesk_construction_cloud",
                "project_id": "test_project",
                "user_id": "test_user",
                "description": "Test Autodesk endpoint",
                "endpoint_details": {
                    "project_id": "autodesk_project_123",
                    "folder_id": "autodesk_folder",
                    "include_subfolders": True,
                    "file_types": ["dwg", "rvt"]
                },
                "schedule": "manual",
                "file_types": ["dwg", "rvt"],
                "is_active": True,
                "tags": ["test", "cad"]
            }
        ]
    }


async def test_configuration_schema():
    """Test configuration schema validation."""
    
    setup_logging(log_level="INFO")
    logger = get_logger("test_config_schema")
    
    logger.info("Testing configuration schema...")
    
    try:
        # Test 1: Valid configuration
        logger.info("Testing valid configuration creation...")
        
        test_data = create_test_config_data()
        config = ConnectorConfig(**test_data)
        
        assert config.version == "1.0.0"
        assert config.environment == "development"
        assert len(config.endpoints) == 2
        assert config.scheduling.default_interval_minutes == 5
        
        logger.info("✅ Valid configuration test passed")
        
        # Test 2: Configuration methods
        logger.info("Testing configuration methods...")
        
        # Test get methods
        google_endpoints = config.get_endpoints_by_type(EndpointType.GOOGLE_DRIVE)
        autodesk_endpoints = config.get_endpoints_by_type(EndpointType.AUTODESK_CONSTRUCTION_CLOUD)
        project_endpoints = config.get_endpoints_by_project("test_project")
        active_endpoints = config.get_active_endpoints()
        scheduled_endpoints = config.get_scheduled_endpoints()
        
        assert len(google_endpoints) == 1
        assert len(autodesk_endpoints) == 1
        assert len(project_endpoints) == 2
        assert len(active_endpoints) == 2
        assert len(scheduled_endpoints) == 1  # Only Google Drive has interval schedule
        
        logger.info("✅ Configuration methods test passed")
        
        # Test 3: Endpoint validation
        logger.info("Testing endpoint validation...")
        
        # Valid Google Drive endpoint
        google_endpoint = EndpointConfig(
            name="Valid Google Drive",
            endpoint_type=EndpointType.GOOGLE_DRIVE,
            project_id="test",
            user_id="test",
            endpoint_details={
                "folder_id": "test_folder",
                "include_shared": True
            },
            schedule=ScheduleType.INTERVAL,
            schedule_config={
                "interval_minutes": 5
            }
        )
        
        assert google_endpoint.name == "Valid Google Drive"
        assert google_endpoint.schedule == ScheduleType.INTERVAL
        
        # Valid Autodesk endpoint
        autodesk_endpoint = EndpointConfig(
            name="Valid Autodesk",
            endpoint_type=EndpointType.AUTODESK_CONSTRUCTION_CLOUD,
            project_id="test",
            user_id="test",
            endpoint_details={
                "project_id": "autodesk_project"
            },
            schedule=ScheduleType.CRON,
            schedule_config={
                "cron_expression": "0 */6 * * *"
            }
        )
        
        assert autodesk_endpoint.endpoint_type == EndpointType.AUTODESK_CONSTRUCTION_CLOUD
        
        logger.info("✅ Endpoint validation test passed")
        
        # Test 4: Schedule validation
        logger.info("Testing schedule validation...")
        
        schedule_config = ScheduleConfig(
            default_schedule=ScheduleType.INTERVAL,
            default_interval_minutes=10,
            max_concurrent_syncs=5,
            max_files_per_sync=500
        )
        
        assert schedule_config.default_interval_minutes == 10
        assert schedule_config.max_concurrent_syncs == 5
        
        logger.info("✅ Schedule validation test passed")
        
        # Test 5: Error validation
        logger.info("Testing error validation...")
        
        # Test invalid interval
        try:
            EndpointConfig(
                name="Invalid Interval",
                endpoint_type=EndpointType.GOOGLE_DRIVE,
                project_id="test",
                user_id="test",
                schedule=ScheduleType.INTERVAL,
                schedule_config={
                    "interval_minutes": 0  # Invalid: must be >= 1
                }
            )
            assert False, "Should have raised ValidationError"
        except Exception as e:
            assert "at least 1 minute" in str(e)
        
        # Test missing Autodesk project_id
        try:
            EndpointConfig(
                name="Invalid Autodesk",
                endpoint_type=EndpointType.AUTODESK_CONSTRUCTION_CLOUD,
                project_id="test",
                user_id="test",
                endpoint_details={}  # Missing project_id
            )
            assert False, "Should have raised ValidationError"
        except Exception as e:
            assert "project_id" in str(e)
        
        logger.info("✅ Error validation test passed")
        
        logger.info("✅ All configuration schema tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Configuration schema test failed: {e}")
        raise


async def test_configuration_loader():
    """Test configuration loading from files."""
    
    logger = get_logger("test_config_loader")
    logger.info("Testing configuration loader...")
    
    try:
        loader = ConfigLoader()
        test_data = create_test_config_data()
        
        # Test 1: JSON file loading
        logger.info("Testing JSON file loading...")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f, indent=2)
            json_file = f.name
        
        try:
            config = loader.load_from_file(json_file)
            assert isinstance(config, ConnectorConfig)
            assert len(config.endpoints) == 2
            assert config.environment == "development"
            
            logger.info("✅ JSON file loading test passed")
        finally:
            os.unlink(json_file)
        
        # Test 2: YAML file loading
        logger.info("Testing YAML file loading...")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_data, f, default_flow_style=False)
            yaml_file = f.name
        
        try:
            config = loader.load_from_file(yaml_file)
            assert isinstance(config, ConnectorConfig)
            assert len(config.endpoints) == 2
            
            logger.info("✅ YAML file loading test passed")
        finally:
            os.unlink(yaml_file)
        
        # Test 3: Dictionary loading
        logger.info("Testing dictionary loading...")
        
        config = loader.load_from_dict(test_data)
        assert isinstance(config, ConnectorConfig)
        assert len(config.endpoints) == 2
        
        logger.info("✅ Dictionary loading test passed")
        
        # Test 4: Default configuration
        logger.info("Testing default configuration...")
        
        default_config = loader.create_default_config()
        assert isinstance(default_config, ConnectorConfig)
        assert len(default_config.endpoints) >= 2  # Should have examples
        
        logger.info("✅ Default configuration test passed")
        
        # Test 5: Configuration validation
        logger.info("Testing configuration validation...")
        
        warnings = loader.validate_config(config)
        assert isinstance(warnings, list)
        
        logger.info("✅ Configuration validation test passed")
        
        # Test 6: Environment variable overrides
        logger.info("Testing environment variable overrides...")
        
        # Set test environment variables
        os.environ['CONNECTOR_LOG_LEVEL'] = 'DEBUG'
        os.environ['CONNECTOR_ENVIRONMENT'] = 'staging'
        os.environ['CONNECTOR_MAX_CONCURRENT_SYNCS'] = '15'
        
        try:
            # Load config with env overrides
            config_with_env = loader.load_from_dict(test_data.copy())
            
            assert config_with_env.log_level == 'DEBUG'
            assert config_with_env.environment == 'staging'
            assert config_with_env.scheduling.max_concurrent_syncs == 15
            
            logger.info("✅ Environment variable overrides test passed")
        finally:
            # Clean up environment variables
            for var in ['CONNECTOR_LOG_LEVEL', 'CONNECTOR_ENVIRONMENT', 'CONNECTOR_MAX_CONCURRENT_SYNCS']:
                if var in os.environ:
                    del os.environ[var]
        
        # Test 7: File saving
        logger.info("Testing file saving...")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save as YAML
            yaml_output = Path(temp_dir) / "test_output.yaml"
            loader.save_to_file(config, yaml_output, "yaml")
            assert yaml_output.exists()
            
            # Load back and verify
            loaded_config = loader.load_from_file(yaml_output)
            assert len(loaded_config.endpoints) == len(config.endpoints)
            
            # Save as JSON
            json_output = Path(temp_dir) / "test_output.json"
            loader.save_to_file(config, json_output, "json")
            assert json_output.exists()
            
            logger.info("✅ File saving test passed")
        
        # Test 8: Error handling
        logger.info("Testing error handling...")
        
        # Test file not found
        try:
            loader.load_from_file("nonexistent_file.yaml")
            assert False, "Should have raised ConfigurationError"
        except ConfigurationError as e:
            assert "not found" in str(e)
        
        # Test invalid JSON
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content {")
            invalid_json_file = f.name
        
        try:
            loader.load_from_file(invalid_json_file)
            assert False, "Should have raised ConfigurationError"
        except ConfigurationError as e:
            assert "JSON" in str(e)
        finally:
            os.unlink(invalid_json_file)
        
        logger.info("✅ Error handling test passed")
        
        logger.info("✅ All configuration loader tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Configuration loader test failed: {e}")
        raise


async def test_example_configurations():
    """Test the example configurations."""
    
    logger = get_logger("test_examples")
    logger.info("Testing example configurations...")
    
    try:
        # Test 1: Example endpoint configurations
        logger.info("Testing example endpoint configurations...")
        
        # Test Google Drive example
        google_example = GOOGLE_DRIVE_ENDPOINT_EXAMPLE
        assert google_example.endpoint_type == EndpointType.GOOGLE_DRIVE
        assert google_example.schedule == ScheduleType.INTERVAL
        assert "pdf" in google_example.file_types
        
        # Test Autodesk example
        autodesk_example = AUTODESK_ENDPOINT_EXAMPLE
        assert autodesk_example.endpoint_type == EndpointType.AUTODESK_CONSTRUCTION_CLOUD
        assert autodesk_example.schedule == ScheduleType.INTERVAL
        assert "dwg" in autodesk_example.file_types
        
        logger.info("✅ Example endpoint configurations test passed")
        
        # Test 2: Example configuration files exist
        logger.info("Testing example configuration files...")
        
        example_yaml = Path("config/connector.example.yaml")
        example_json = Path("config/connector.example.json")
        
        # Check if files exist (they should be in the project)
        if example_yaml.exists():
            loader = ConfigLoader()
            yaml_config = loader.load_from_file(example_yaml)
            assert isinstance(yaml_config, ConnectorConfig)
            logger.info("✅ Example YAML configuration loads successfully")
        
        if example_json.exists():
            json_config = loader.load_from_file(example_json)
            assert isinstance(json_config, ConnectorConfig)
            logger.info("✅ Example JSON configuration loads successfully")
        
        logger.info("✅ Example configuration files test passed")
        
        # Test 3: Configuration with different schedule types
        logger.info("Testing different schedule types...")
        
        # Manual schedule
        manual_endpoint = EndpointConfig(
            name="Manual Sync",
            endpoint_type=EndpointType.GOOGLE_DRIVE,
            project_id="test",
            user_id="test",
            schedule=ScheduleType.MANUAL
        )
        assert manual_endpoint.schedule == ScheduleType.MANUAL
        
        # Cron schedule
        cron_endpoint = EndpointConfig(
            name="Cron Sync",
            endpoint_type=EndpointType.GOOGLE_DRIVE,
            project_id="test",
            user_id="test",
            schedule=ScheduleType.CRON,
            schedule_config={
                "cron_expression": "0 9 * * *"  # Daily at 9 AM
            }
        )
        assert cron_endpoint.schedule == ScheduleType.CRON
        assert cron_endpoint.schedule_config["cron_expression"] == "0 9 * * *"
        
        # Webhook schedule
        webhook_endpoint = EndpointConfig(
            name="Webhook Sync",
            endpoint_type=EndpointType.GOOGLE_DRIVE,
            project_id="test",
            user_id="test",
            schedule=ScheduleType.WEBHOOK,
            schedule_config={
                "webhook_secret": "secret123"
            }
        )
        assert webhook_endpoint.schedule == ScheduleType.WEBHOOK
        
        logger.info("✅ Different schedule types test passed")
        
        logger.info("✅ All example configuration tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Example configuration test failed: {e}")
        raise


if __name__ == "__main__":
    async def run_tests():
        await test_configuration_schema()
        await test_configuration_loader()
        await test_example_configurations()
        print("\n🎉 Configuration management tests completed successfully!")
    
    try:
        import asyncio
        asyncio.run(run_tests())
    except Exception as e:
        print(f"\n💥 Configuration management tests failed: {e}")
        sys.exit(1)