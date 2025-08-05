"""Test script for database functionality."""

import sys
import os
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from connector.database import (
    init_database,
    get_database_service,
    EndpointCreate,
    FileCreate,
    EndpointType,
    SyncStatus,
    close_database
)
from connector.config.settings import get_settings
from connector.utils.logging import setup_logging, get_logger


def test_database_setup():
    """Test database setup and basic operations."""
    
    # Setup logging
    setup_logging(log_level="INFO")
    logger = get_logger("test_database")
    
    logger.info("Starting database test...")
    
    try:
        # Initialize database with test SQLite file
        test_db_path = "./data/test_connector.db"
        Path(test_db_path).parent.mkdir(exist_ok=True)
        
        # Remove existing test database
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
        
        db_manager = init_database(f"sqlite:///{test_db_path}")
        db_service = get_database_service()
        
        logger.info("Database initialized successfully")
        
        # Test 1: Create endpoints
        logger.info("Testing endpoint creation...")
        
        google_endpoint = EndpointCreate(
            endpoint_type=EndpointType.GOOGLE_DRIVE,
            endpoint_details={
                "folder_id": "test_folder_123",
                "include_shared": True
            },
            project_id="test_project_1",
            user_id="test_user_1",
            schedule_cron="*/5 * * * *"
        )
        
        autodesk_endpoint = EndpointCreate(
            endpoint_type=EndpointType.AUTODESK_CONSTRUCTION_CLOUD,
            endpoint_details={
                "project_id": "autodesk_project_123",
                "folder_id": None
            },
            project_id="test_project_2",
            user_id="test_user_2",
            schedule_cron="*/10 * * * *"
        )
        
        google_ep = db_service.create_endpoint(google_endpoint)
        autodesk_ep = db_service.create_endpoint(autodesk_endpoint)
        
        logger.info(f"Created Google Drive endpoint: {google_ep.id}")
        logger.info(f"Created Autodesk endpoint: {autodesk_ep.id}")
        
        # Test 2: Get endpoints
        logger.info("Testing endpoint retrieval...")
        
        all_endpoints = db_service.get_all_endpoints()
        logger.info(f"Total endpoints: {len(all_endpoints)}")
        
        retrieved_google = db_service.get_endpoint(google_ep.id)
        assert retrieved_google is not None
        assert retrieved_google.endpoint_type == EndpointType.GOOGLE_DRIVE.value
        
        # Test 3: Create files
        logger.info("Testing file creation...")
        
        test_files = [
            FileCreate(
                endpoint_id=google_ep.id,
                external_file_id="google_file_1",
                file_name="test_document.pdf",
                file_path="/Drive/Documents/test_document.pdf",
                file_link="https://drive.google.com/file/d/abc123/view",
                file_size=1024000,
                file_type="application/pdf",
                external_created_at=datetime.utcnow(),
                external_updated_at=datetime.utcnow(),
                file_metadata={"source": "google_drive", "shared": True}
            ),
            FileCreate(
                endpoint_id=autodesk_ep.id,
                external_file_id="autodesk_file_1",
                file_name="blueprint.dwg",
                file_path="/Projects/Project1/blueprint.dwg",
                file_link="https://acc.autodesk.com/files/blueprint.dwg",
                file_size=5120000,
                file_type="application/dwg",
                external_created_at=datetime.utcnow(),
                external_updated_at=datetime.utcnow(),
                file_metadata={"source": "autodesk", "version": "2024"}
            )
        ]
        
        # Test batch file sync
        sync_stats = db_service.sync_files_batch(test_files)
        logger.info(f"Batch sync stats: {sync_stats}")
        
        assert sync_stats["new"] == 2
        assert sync_stats["errors"] == 0
        
        # Test 4: File operations
        logger.info("Testing file operations...")
        
        # Check if file exists
        exists = db_service.file_exists(google_ep.id, "google_file_1")
        assert exists
        
        # Get file by external ID
        retrieved_file = db_service.get_file_by_external_id(google_ep.id, "google_file_1")
        assert retrieved_file is not None
        assert retrieved_file.file_name == "test_document.pdf"
        
        # Get files for endpoint
        google_files = db_service.get_endpoint_files(google_ep.id)
        assert len(google_files) == 1
        
        # Test 5: Sync logging
        logger.info("Testing sync logging...")
        
        sync_log_id = db_service.start_sync_log(google_ep.id)
        logger.info(f"Started sync log: {sync_log_id}")
        
        # Complete sync log
        success = db_service.complete_sync_log(
            sync_log_id,
            SyncStatus.COMPLETED,
            {"total": 1, "new": 1, "updated": 0, "errors": 0}
        )
        assert success
        
        # Get sync history
        sync_history = db_service.get_sync_history(google_ep.id)
        assert len(sync_history) == 1
        assert sync_history[0].sync_status == SyncStatus.COMPLETED.value
        
        # Test 6: Update endpoint sync status
        logger.info("Testing endpoint sync status update...")
        
        updated = db_service.update_endpoint_sync_status(google_ep.id, SyncStatus.COMPLETED)
        assert updated
        
        # Test 7: Database statistics
        logger.info("Testing database statistics...")
        
        stats = db_service.get_database_stats()
        logger.info(f"Database stats: {stats}")
        
        assert stats["endpoints"]["total"] >= 2
        assert stats["files"]["total"] >= 2
        assert stats["sync_logs"]["total"] >= 1
        
        logger.info("✅ All database tests passed successfully!")
        
        # Test table info
        table_info = db_manager.get_table_info()
        logger.info(f"Database tables: {list(table_info.keys())}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Database test failed: {e}")
        raise
    
    finally:
        # Cleanup
        close_database()
        logger.info("Database connections closed")


if __name__ == "__main__":
    try:
        test_database_setup()
        print("\n🎉 Database layer test completed successfully!")
    except Exception as e:
        print(f"\n💥 Database layer test failed: {e}")
        sys.exit(1)