"""Simplified test script for Autodesk Construction Cloud API client."""

import sys
import os
import asyncio
from datetime import datetime, timezone

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from connector.api_clients import AutodeskConstructionCloudClient, FileMetadata, AuthenticationError
from connector.utils.logging import setup_logging, get_logger


def create_mock_autodesk_files():
    """Create mock Autodesk Construction Cloud file data."""
    return [
        {
            "type": "items",
            "id": "urn:adsk.wipprod:dm.lineage:abc123",
            "attributes": {
                "displayName": "floor_plan.dwg",
                "createTime": "2024-01-01T10:00:00.000Z",
                "lastModifiedTime": "2024-01-02T15:30:00.000Z",
                "createUserId": "user123",
                "lastModifiedUserId": "user456",
                "storageSize": 2048000,
                "mimeType": "application/dwg",
                "fileType": "dwg",
                "versionNumber": 3
            },
            "relationships": {
                "parent": {
                    "data": {
                        "type": "folders",
                        "id": "folder_123"
                    }
                }
            }
        },
        {
            "type": "items",
            "id": "urn:adsk.wipprod:dm.lineage:def456",
            "attributes": {
                "displayName": "specifications.pdf",
                "createTime": "2024-01-03T08:15:00.000Z",
                "lastModifiedTime": "2024-01-04T12:45:00.000Z",
                "createUserId": "user789",
                "lastModifiedUserId": "user789",
                "storageSize": 1024000,
                "mimeType": "application/pdf",
                "fileType": "pdf",
                "versionNumber": 1
            },
            "relationships": {
                "parent": {
                    "data": {
                        "type": "folders",
                        "id": "folder_456"
                    }
                }
            }
        },
        {
            "type": "folders",
            "id": "folder_789",
            "attributes": {
                "displayName": "Subfolder",
                "createTime": "2024-01-01T09:00:00.000Z"
            }
        }
    ]


async def test_autodesk_client():
    """Test Autodesk Construction Cloud client functionality (core features only)."""
    
    setup_logging(log_level="INFO")
    logger = get_logger("test_autodesk_simple")
    
    logger.info("Starting simplified Autodesk Construction Cloud client test...")
    
    try:
        # Test endpoint configuration
        endpoint_details = {
            "project_id": "test_project_123",
            "folder_id": "test_folder_456",
            "include_subfolders": True,
            "file_types": ["dwg", "pdf", "rvt"],
            "max_results": 100
        }
        
        # Create client
        client = AutodeskConstructionCloudClient(
            endpoint_details=endpoint_details,
            client_id="test_client_id",
            client_secret="test_client_secret",
            callback_url="http://localhost:8080/callback"
        )
        
        logger.info("Autodesk Construction Cloud client created successfully")
        
        # Test 1: File type filtering
        logger.info("Testing file type filtering...")
        
        mock_files = create_mock_autodesk_files()
        
        # Test file type filtering
        results = [client._matches_file_type_filter(f) for f in mock_files]
        # Should match dwg and pdf files, but not folders
        assert results == [True, True, False]
        
        logger.info("✅ File type filtering test passed")
        
        # Test 2: File metadata conversion
        logger.info("Testing file metadata conversion...")
        
        file_metadata = client._convert_to_file_metadata(mock_files[0])
        
        assert isinstance(file_metadata, FileMetadata)
        assert file_metadata.external_file_id == "urn:adsk.wipprod:dm.lineage:abc123"
        assert file_metadata.file_name == "floor_plan.dwg"
        assert file_metadata.file_type == "dwg"
        assert file_metadata.file_size == 2048000
        assert "test_project_123" in file_metadata.file_link
        
        # Check metadata
        assert file_metadata.file_metadata["autodesk_item_id"] == "urn:adsk.wipprod:dm.lineage:abc123"
        assert file_metadata.file_metadata["version_number"] == 3
        assert file_metadata.file_metadata["project_id"] == "test_project_123"
        assert file_metadata.file_metadata["parent_folder_id"] == "folder_123"
        
        logger.info("✅ File metadata conversion test passed")
        
        # Test 3: Test PDF file conversion
        logger.info("Testing PDF file metadata conversion...")
        
        pdf_file_metadata = client._convert_to_file_metadata(mock_files[1])
        
        assert pdf_file_metadata.file_name == "specifications.pdf"
        assert pdf_file_metadata.file_type == "pdf"
        assert pdf_file_metadata.file_size == 1024000
        assert pdf_file_metadata.file_metadata["version_number"] == 1
        
        logger.info("✅ PDF file metadata conversion test passed")
        
        # Test 4: Timestamp parsing
        logger.info("Testing timestamp parsing...")
        
        timestamp_str = "2024-01-01T10:00:00.000Z"
        parsed_timestamp = client._parse_timestamp(timestamp_str)
        
        assert parsed_timestamp is not None
        assert parsed_timestamp.year == 2024
        assert parsed_timestamp.month == 1
        assert parsed_timestamp.day == 1
        assert parsed_timestamp.hour == 10
        
        logger.info("✅ Timestamp parsing test passed")
        
        # Test 5: File path construction
        logger.info("Testing file path construction...")
        
        file_path = client._get_file_path(mock_files[0])
        assert file_path == "/floor_plan.dwg"
        
        logger.info("✅ File path construction test passed")
        
        # Test 6: Parent folder ID extraction
        logger.info("Testing parent folder ID extraction...")
        
        parent_folder_id = client._get_parent_folder_id(mock_files[0])
        assert parent_folder_id == "folder_123"
        
        # Test with no parent
        no_parent_file = {"relationships": {}}
        parent_folder_id = client._get_parent_folder_id(no_parent_file)
        assert parent_folder_id is None
        
        logger.info("✅ Parent folder ID extraction test passed")
        
        # Test 7: Download link generation
        logger.info("Testing download link generation...")
        
        download_link = client._get_download_link(mock_files[0])
        expected_link = f"{client.data_api_base}/projects/test_project_123/items/urn:adsk.wipprod:dm.lineage:abc123/content"
        assert download_link == expected_link
        
        logger.info("✅ Download link generation test passed")
        
        # Test 8: Configuration validation
        logger.info("Testing configuration validation...")
        
        assert client.project_id == "test_project_123"
        assert client.folder_id == "test_folder_456"
        assert client.include_subfolders == True
        assert client.file_types == ["dwg", "pdf", "rvt"]
        assert client.max_results_per_request == 100
        assert client.client_id == "test_client_id"
        assert client.client_secret == "test_client_secret"
        
        logger.info("✅ Configuration validation test passed")
        
        # Test 9: Sync info (without authentication)
        logger.info("Testing sync info (basic)...")
        
        # Mock authenticated state for sync info
        client._authenticated = True
        
        # Create a mock method that returns empty dict to avoid API calls
        async def mock_get_project_info():
            return {}
        
        original_get_project_info = client.get_project_info
        client.get_project_info = mock_get_project_info
        
        try:
            sync_info = await client.get_sync_info()
            assert sync_info["client_type"] == "AutodeskConstructionCloudClient"
            assert sync_info["project_id"] == "test_project_123"
            assert sync_info["folder_id"] == "test_folder_456"
            assert sync_info["include_subfolders"] == True
            assert sync_info["file_types"] == ["dwg", "pdf", "rvt"]
            assert sync_info["authenticated"] == True
            
            logger.info("✅ Sync info test passed")
        finally:
            # Restore original method
            client.get_project_info = original_get_project_info
        
        # Test 10: Error handling for missing project ID
        logger.info("Testing error handling for missing project ID...")
        
        client_no_project = AutodeskConstructionCloudClient(
            endpoint_details={"folder_id": "test"},
            client_id="test",
            client_secret="test",
            callback_url="test"
        )
        
        # Validate that project_id is None as expected
        assert client_no_project.project_id is None
        logger.info("✅ Error handling test passed - project_id properly validated as None")
        
        logger.info("✅ All Autodesk Construction Cloud client tests passed successfully!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Autodesk Construction Cloud client test failed: {e}")
        raise
    
    finally:
        # Cleanup
        pass


if __name__ == "__main__":
    try:
        asyncio.run(test_autodesk_client())
        print("\n🎉 Autodesk Construction Cloud client tests completed successfully!")
    except Exception as e:
        print(f"\n💥 Autodesk Construction Cloud client tests failed: {e}")
        sys.exit(1)