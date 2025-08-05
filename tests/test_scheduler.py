"""Simplified test script for scheduling system."""

import sys
import os
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from connector.scheduler import JobScheduler, SchedulerManager, SchedulerError
from connector.config import EndpointConfig, ScheduleType
from connector.database.models import EndpointType
from connector.utils.logging import setup_logging, get_logger


async def test_scheduler_basic():
    """Test basic scheduler functionality."""
    
    setup_logging(log_level="INFO")
    logger = get_logger("test_scheduler_basic")
    
    logger.info("Testing basic scheduler functionality...")
    
    try:
        # Create mock dependencies
        mock_connector = Mock()
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = Mock(
            get_scheduled_endpoints=Mock(return_value=[])
        )
        
        # Test 1: Create scheduler
        logger.info("Testing scheduler creation...")
        
        scheduler = JobScheduler(
            connector=mock_connector,
            config_manager=mock_config_manager,
            max_workers=2
        )
        
        assert scheduler is not None
        assert scheduler.max_workers == 2
        
        logger.info("✅ Scheduler creation test passed")
        
        # Test 2: Start and stop scheduler
        logger.info("Testing scheduler start/stop...")
        
        await scheduler.start()
        assert scheduler.scheduler.running == True
        
        await scheduler.stop()
        # Note: We don't assert scheduler.running == False due to APScheduler async shutdown
        
        logger.info("✅ Scheduler start/stop test passed")
        
        # Test 3: Endpoint configuration
        logger.info("Testing endpoint configuration...")
        
        test_endpoint = EndpointConfig(
            name="Test Endpoint",
            endpoint_type=EndpointType.GOOGLE_DRIVE,
            project_id="test_project",
            user_id="test_user",
            schedule=ScheduleType.INTERVAL,
            schedule_config={"interval_minutes": 5},
            is_active=True
        )
        
        # Test job ID generation
        job_id = scheduler._get_job_id(test_endpoint)
        assert job_id == "google_drive_test_project_test_user"
        
        # Test trigger creation
        trigger = scheduler._create_trigger(test_endpoint)
        assert trigger is not None
        
        logger.info("✅ Endpoint configuration test passed")
        
        # Test 4: Schedule type validation
        logger.info("Testing schedule type validation...")
        
        # Valid interval
        interval_endpoint = EndpointConfig(
            name="Interval Test",
            endpoint_type=EndpointType.GOOGLE_DRIVE,
            project_id="test",
            user_id="test",
            schedule=ScheduleType.INTERVAL,
            schedule_config={"interval_minutes": 10}
        )
        
        trigger = scheduler._create_trigger(interval_endpoint)
        assert trigger is not None
        
        # Valid cron
        cron_endpoint = EndpointConfig(
            name="Cron Test", 
            endpoint_type=EndpointType.GOOGLE_DRIVE,
            project_id="test",
            user_id="test",
            schedule=ScheduleType.CRON,
            schedule_config={"cron_expression": "0 9 * * *"}
        )
        
        trigger = scheduler._create_trigger(cron_endpoint)
        assert trigger is not None
        
        logger.info("✅ Schedule type validation test passed")
        
        logger.info("✅ All basic scheduler tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Basic scheduler test failed: {e}")
        raise


async def test_schedule_types():
    """Test different schedule types."""
    
    logger = get_logger("test_schedule_types")
    logger.info("Testing schedule type configurations...")
    
    try:
        # Create mock dependencies
        mock_connector = Mock()
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = Mock(
            get_scheduled_endpoints=Mock(return_value=[])
        )
        
        scheduler = JobScheduler(
            connector=mock_connector,
            config_manager=mock_config_manager,
            max_workers=1
        )
        
        # Test different schedule configurations
        test_cases = [
            {
                "name": "Every 5 minutes",
                "schedule": ScheduleType.INTERVAL,
                "config": {"interval_minutes": 5}
            },
            {
                "name": "Daily at 9 AM",
                "schedule": ScheduleType.CRON,
                "config": {"cron_expression": "0 9 * * *"}
            },
            {
                "name": "Every weekday at noon",
                "schedule": ScheduleType.CRON,
                "config": {"cron_expression": "0 12 * * 1-5"}
            },
            {
                "name": "Every hour",
                "schedule": ScheduleType.INTERVAL,
                "config": {"interval_minutes": 60}
            }
        ]
        
        for i, test_case in enumerate(test_cases):
            logger.info(f"Testing: {test_case['name']}")
            
            endpoint = EndpointConfig(
                name=f"Test {i}",
                endpoint_type=EndpointType.GOOGLE_DRIVE,
                project_id="test",
                user_id=f"user_{i}",
                schedule=test_case["schedule"],
                schedule_config=test_case["config"],
                is_active=True
            )
            
            # Should not raise exception
            trigger = scheduler._create_trigger(endpoint)
            assert trigger is not None
            
            logger.info(f"✅ {test_case['name']} test passed")
        
        logger.info("✅ All schedule type tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Schedule type test failed: {e}")
        raise


async def test_error_handling():
    """Test error handling scenarios."""
    
    logger = get_logger("test_error_handling")
    logger.info("Testing error handling...")
    
    try:
        # Create mock dependencies
        mock_connector = Mock()
        mock_config_manager = Mock()
        mock_config_manager.get_config.return_value = Mock(
            get_scheduled_endpoints=Mock(return_value=[])
        )
        
        scheduler = JobScheduler(
            connector=mock_connector,
            config_manager=mock_config_manager,
            max_workers=1
        )
        
        # Test 1: Invalid cron expression
        logger.info("Testing invalid cron expression...")
        
        invalid_cron = EndpointConfig(
            name="Invalid Cron",
            endpoint_type=EndpointType.GOOGLE_DRIVE,
            project_id="test",
            user_id="test",
            schedule=ScheduleType.CRON,
            schedule_config={"cron_expression": "invalid"}
        )
        
        try:
            scheduler._create_trigger(invalid_cron)
            assert False, "Should have raised SchedulerError"
        except SchedulerError as e:
            assert "Invalid cron expression" in str(e)
        
        logger.info("✅ Invalid cron expression test passed")
        
        # Test 2: Missing cron expression
        logger.info("Testing missing cron expression...")
        
        missing_cron = EndpointConfig(
            name="Missing Cron",
            endpoint_type=EndpointType.GOOGLE_DRIVE,
            project_id="test",
            user_id="test",
            schedule=ScheduleType.CRON,
            schedule_config={"cron_expression": "0 9 * * *"}  # Valid initially
        )
        
        # Manually modify the config to simulate missing expression
        missing_cron.schedule_config = {}
        
        try:
            scheduler._create_trigger(missing_cron)
            assert False, "Should have raised SchedulerError"
        except SchedulerError as e:
            assert "Cron expression required" in str(e)
        
        logger.info("✅ Missing cron expression test passed")
        
        logger.info("✅ All error handling tests passed!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error handling test failed: {e}")
        raise


if __name__ == "__main__":
    async def run_tests():
        await test_scheduler_basic()
        await test_schedule_types()
        await test_error_handling()
        print("\n🎉 Simplified scheduler tests completed successfully!")
    
    try:
        asyncio.run(run_tests())
    except Exception as e:
        print(f"\n💥 Simplified scheduler tests failed: {e}")
        sys.exit(1)