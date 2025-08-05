"""Simplified test for core connector logic."""

import sys
import os
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from connector.core import SyncResult, SyncStats, SyncEngine
from connector.api_clients import FileMetadata
from connector.utils.logging import setup_logging, get_logger


def create_mock_file_metadata():
    """Create mock file metadata objects."""
    return [
        FileMetadata(
            external_file_id="file_001",
            file_name="test_document.pdf",
            file_path="/documents/test_document.pdf",
            file_link="https://example.com/file_001",
            file_size=1024000,
            file_type="pdf",
            external_created_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
            external_updated_at=datetime(2024, 1, 2, 15, 30, 0, tzinfo=timezone.utc),
            file_metadata={"version": 1, "owner": "user123"}
        ),
        FileMetadata(
            external_file_id="file_002",
            file_name="project_plan.dwg",
            file_path="/projects/project_plan.dwg",
            file_link="https://example.com/file_002",
            file_size=2048000,
            file_type="dwg",
            external_created_at=datetime(2024, 1, 3, 8, 15, 0, tzinfo=timezone.utc),
            external_updated_at=datetime(2024, 1, 4, 12, 45, 0, tzinfo=timezone.utc),
            file_metadata={"version": 2, "owner": "user456"}
        )
    ]


async def test_core_classes():
    """Test core connector classes without database dependencies."""
    
    setup_logging(log_level="INFO")
    logger = get_logger("test_core_simple")
    
    logger.info("Starting simplified core connector test...")
    
    try:
        # Test 1: SyncResult class
        logger.info("Testing SyncResult class...")
        
        result = SyncResult(
            endpoint_id=1,
            success=True,
            files_processed=10,
            files_added=5,
            files_updated=3,
            files_skipped=2,
            sync_duration=15.5
        )
        
        assert result.files_changed == 8  # 5 + 3
        assert result.success == True
        assert result.sync_duration == 15.5
        
        logger.info("✅ SyncResult class test passed")
        
        # Test 2: SyncStats class
        logger.info("Testing SyncStats class...")
        
        stats = SyncStats(
            total_endpoints=4,
            successful_syncs=3,
            failed_syncs=1,
            total_files_processed=50,
            total_files_changed=25,
            total_duration=120.0
        )
        
        assert stats.success_rate == 75.0  # 3/4 * 100
        assert stats.total_files_changed == 25
        
        logger.info("✅ SyncStats class test passed")
        
        # Test 3: FileMetadata conversion
        logger.info("Testing FileMetadata functionality...")
        
        mock_files = create_mock_file_metadata()
        
        # Test to_dict conversion
        file_dict = mock_files[0].to_dict()
        
        assert file_dict["external_file_id"] == "file_001"
        assert file_dict["file_name"] == "test_document.pdf"
        assert file_dict["file_size"] == 1024000
        assert file_dict["file_metadata"]["version"] == 1
        
        logger.info("✅ FileMetadata functionality test passed")
        
        # Test 4: Core logic patterns
        logger.info("Testing core logic patterns...")
        
        # Test file filtering by type
        pdf_files = [f for f in mock_files if f.file_type == "pdf"]
        dwg_files = [f for f in mock_files if f.file_type == "dwg"]
        
        assert len(pdf_files) == 1
        assert len(dwg_files) == 1
        
        # Test timestamp-based filtering
        since_date = datetime(2024, 1, 2, tzinfo=timezone.utc)
        recent_files = [
            f for f in mock_files 
            if f.external_updated_at and f.external_updated_at > since_date
        ]
        
        assert len(recent_files) == 2  # Both files updated after Jan 2
        
        logger.info("✅ Core logic patterns test passed")
        
        # Test 5: Mock sync engine functionality 
        logger.info("Testing sync engine patterns...")
        
        # Create mock database service
        mock_db_service = Mock()
        mock_db_service.sync_file.return_value = (Mock(id=1), True)  # file_record, was_created
        
        # Create sync engine
        sync_engine = SyncEngine(mock_db_service)
        
        # Test configuration
        assert sync_engine.max_retries == 3
        assert sync_engine.retry_delay == 30
        assert sync_engine.max_files_per_sync == 1000
        
        logger.info("✅ Sync engine patterns test passed")
        
        # Test 6: Error handling patterns
        logger.info("Testing error handling patterns...")
        
        # Test SyncResult error states
        error_result = SyncResult(
            endpoint_id=1,
            success=False,
            files_processed=0,
            files_added=0,
            files_updated=0,
            files_skipped=0,
            error_message="Authentication failed"
        )
        
        assert error_result.success == False
        assert error_result.files_changed == 0
        assert "authentication" in error_result.error_message.lower()
        
        logger.info("✅ Error handling patterns test passed")
        
        # Test 7: Timestamp and datetime handling
        logger.info("Testing timestamp handling...")
        
        # Test timezone-aware datetime
        now_utc = datetime.now(timezone.utc)
        assert now_utc.tzinfo is not None
        
        # Test file metadata timestamps
        file_meta = mock_files[0]
        assert file_meta.external_created_at.tzinfo is not None
        assert file_meta.external_updated_at.tzinfo is not None
        assert file_meta.external_updated_at > file_meta.external_created_at
        
        logger.info("✅ Timestamp handling test passed")
        
        # Test 8: Configuration validation
        logger.info("Testing configuration validation...")
        
        # Test valid endpoint types
        from connector.database.models import EndpointType
        
        valid_types = [EndpointType.GOOGLE_DRIVE, EndpointType.AUTODESK_CONSTRUCTION_CLOUD]
        assert len(valid_types) == 2
        
        # Test file metadata structure
        required_fields = [
            "external_file_id", "file_name", "file_link", 
            "external_created_at", "external_updated_at"
        ]
        
        for field in required_fields:
            assert hasattr(mock_files[0], field)
            assert getattr(mock_files[0], field) is not None
        
        logger.info("✅ Configuration validation test passed")
        
        logger.info("✅ All simplified core connector tests passed successfully!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Simplified core connector test failed: {e}")
        raise
    
    finally:
        # Cleanup
        pass


async def test_api_client_integration():
    """Test API client integration patterns."""
    
    logger = get_logger("test_api_integration")
    logger.info("Testing API client integration patterns...")
    
    try:
        # Test 1: API client factory integration
        logger.info("Testing API client factory integration...")
        
        from connector.api_clients import APIClientFactory
        from connector.database.models import EndpointType
        
        # Test supported types
        supported_types = APIClientFactory.get_supported_types()
        assert EndpointType.GOOGLE_DRIVE in supported_types
        assert EndpointType.AUTODESK_CONSTRUCTION_CLOUD in supported_types
        
        logger.info("✅ API client factory integration test passed")
        
        # Test 2: FileMetadata consistency
        logger.info("Testing FileMetadata consistency...")
        
        # Test that FileMetadata can be converted to database format
        mock_file = create_mock_file_metadata()[0]
        file_dict = mock_file.to_dict()
        
        # Check all required database fields are present
        required_db_fields = [
            "external_file_id", "file_name", "file_path", "file_link",
            "file_size", "file_type", "external_created_at", 
            "external_updated_at", "file_metadata"
        ]
        
        for field in required_db_fields:
            assert field in file_dict
        
        logger.info("✅ FileMetadata consistency test passed")
        
        # Test 3: Async generator patterns
        logger.info("Testing async generator patterns...")
        
        # Mock async generator like API clients use
        async def mock_file_generator():
            for file_meta in create_mock_file_metadata():
                yield file_meta
        
        files_collected = []
        async for file_meta in mock_file_generator():
            files_collected.append(file_meta)
        
        assert len(files_collected) == 2
        assert all(isinstance(f, FileMetadata) for f in files_collected)
        
        logger.info("✅ Async generator patterns test passed")
        
        logger.info("✅ All API client integration tests passed successfully!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ API client integration test failed: {e}")
        raise


if __name__ == "__main__":
    async def run_tests():
        await test_core_classes()
        await test_api_client_integration()
        print("\n🎉 Simplified core connector tests completed successfully!")
    
    try:
        asyncio.run(run_tests())
    except Exception as e:
        print(f"\n💥 Simplified core connector tests failed: {e}")
        sys.exit(1)