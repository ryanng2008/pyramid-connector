"""Simplified Google Drive client test."""

import sys
import os
import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock, patch, AsyncMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from connector.api_clients import GoogleDriveClient, FileMetadata, AuthenticationError
from connector.utils.logging import setup_logging, get_logger


def create_mock_drive_files():
    """Create mock Google Drive file data."""
    return [
        {
            "id": "file_1",
            "name": "test_document.pdf",
            "parents": ["folder_123"],
            "webViewLink": "https://drive.google.com/file/d/file_1/view",
            "size": "1024000",
            "mimeType": "application/pdf",
            "createdTime": "2024-01-01T10:00:00.000Z",
            "modifiedTime": "2024-01-02T15:30:00.000Z",
            "ownedByMe": True,
            "shared": False
        },
        {
            "id": "file_2", 
            "name": "spreadsheet.xlsx",
            "parents": ["folder_123"],
            "webViewLink": "https://drive.google.com/file/d/file_2/view",
            "size": "2048000",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "createdTime": "2024-01-03T08:15:00.000Z",
            "modifiedTime": "2024-01-04T12:45:00.000Z",
            "ownedByMe": False,
            "shared": True
        }
    ]


async def test_google_drive_client():
    """Test Google Drive client functionality."""
    
    setup_logging(log_level="INFO")
    logger = get_logger("test_simple")
    
    logger.info("Starting simple Google Drive client test...")
    
    try:
        # Test endpoint configuration
        endpoint_details = {
            "folder_id": "test_folder_123",
            "include_shared": True,
            "file_types": ["pdf", "xlsx"],
            "max_results": 100
        }
        
        # Create client
        client = GoogleDriveClient(
            endpoint_details=endpoint_details,
            credentials_path="./secrets/test_credentials.json"
        )
        
        logger.info("Google Drive client created successfully")
        
        # Test 1: Authentication (mocked)
        logger.info("Testing authentication...")
        
        with patch('os.path.exists', return_value=True), \
             patch('connector.api_clients.google_drive.service_account') as mock_sa, \
             patch('connector.api_clients.google_drive.build') as mock_build:
            
            # Mock credentials
            mock_credentials = Mock()
            mock_sa.Credentials.from_service_account_file.return_value = mock_credentials
            
            # Mock Google Drive service
            mock_service = Mock()
            mock_build.return_value = mock_service
            
            # Mock about().get() for authentication test
            mock_about_response = Mock()
            mock_about_response.execute.return_value = {
                "user": {"emailAddress": "test@example.com"}
            }
            mock_about = Mock()
            mock_about.get.return_value = mock_about_response
            mock_service.about.return_value = mock_about
            
            # Test authentication
            auth_result = await client.authenticate()
            assert auth_result == True
            assert client._authenticated == True
            
            logger.info("✅ Authentication test passed")
            
            # Test 2: Query building
            logger.info("Testing query building...")
            
            since_date = datetime(2024, 1, 3, tzinfo=timezone.utc)
            query = client._build_query(since=since_date)
            
            assert "modifiedTime > '2024-01-03T00:00:00+00:00'" in query
            assert "trashed=false" in query
            assert "'test_folder_123' in parents" in query
            
            logger.info("✅ Query building test passed")
            
            # Test 3: File type filtering
            logger.info("Testing file type filtering...")
            
            test_files = [
                {"name": "doc.pdf", "mimeType": "application/pdf"},
                {"name": "sheet.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
                {"name": "image.jpg", "mimeType": "image/jpeg"}
            ]
            
            results = [client._matches_file_type_filter(f) for f in test_files]
            assert results == [True, True, False]  # Only pdf and xlsx should match
            
            logger.info("✅ File type filtering test passed")
            
            # Test 4: File metadata conversion
            logger.info("Testing file metadata conversion...")
            
            mock_files = create_mock_drive_files()
            file_metadata = client._convert_to_file_metadata(mock_files[0])
            
            assert isinstance(file_metadata, FileMetadata)
            assert file_metadata.external_file_id == "file_1"
            assert file_metadata.file_name == "test_document.pdf"
            assert file_metadata.file_type == "application/pdf"
            assert file_metadata.file_size == 1024000
            assert file_metadata.file_link == "https://drive.google.com/file/d/file_1/view"
            
            # Check metadata
            assert file_metadata.file_metadata["owned_by_me"] == True
            assert file_metadata.file_metadata["shared"] == False
            assert file_metadata.file_metadata["google_drive_id"] == "file_1"
            
            logger.info("✅ File metadata conversion test passed")
            
            # Test 5: Health check
            logger.info("Testing health check with mocked response...")
            
            # Mock the list_files method to return an empty generator
            async def mock_list_files(*args, **kwargs):
                # Empty async generator
                return
                yield  # This makes it an async generator
            
            # Replace the list_files method temporarily
            original_list_files = client.list_files
            client.list_files = mock_list_files
            
            try:
                health_ok = await client.health_check()
                assert health_ok == True
                logger.info("✅ Health check test passed")
            finally:
                # Restore original method
                client.list_files = original_list_files
            
            # Test 6: Sync info
            logger.info("Testing sync info...")
            
            sync_info = await client.get_sync_info()
            assert sync_info["client_type"] == "GoogleDriveClient"
            assert sync_info["folder_id"] == "test_folder_123"
            assert sync_info["include_shared"] == True
            assert sync_info["file_types"] == ["pdf", "xlsx"]
            assert sync_info["authenticated"] == True
            
            logger.info("✅ Sync info test passed")
        
        # Test 7: Error handling
        logger.info("Testing error handling...")
        
        # Test authentication failure with invalid credentials
        with patch('os.path.exists', return_value=False):
            try:
                await client.authenticate()
                assert False, "Should have raised AuthenticationError"
            except AuthenticationError as e:
                assert "not found" in str(e)
                logger.info("✅ Authentication error handling test passed")
        
        logger.info("✅ All Google Drive client tests passed successfully!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Google Drive client test failed: {e}")
        raise
    
    finally:
        # Cleanup
        pass


if __name__ == "__main__":
    try:
        asyncio.run(test_google_drive_client())
        print("\n🎉 Google Drive client tests completed successfully!")
    except Exception as e:
        print(f"\n💥 Google Drive client tests failed: {e}")
        sys.exit(1)