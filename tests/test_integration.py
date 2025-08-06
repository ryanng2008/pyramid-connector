"""Integration tests for the File Connector system."""

import asyncio
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from connector.database import DatabaseManager, DatabaseService
from connector.api_clients import APIClientFactory
from connector.core import FileConnector, SyncEngine
from connector.config.schema import ConnectorConfig, EndpointConfig, ScheduleType
from connector.performance import get_metrics_collector, get_batch_processor


@pytest.mark.integration
class TestDatabaseIntegration:
    """Integration tests for database operations."""
    
    @pytest.fixture
    async def db_service(self):
        """Create test database service."""
        # Use in-memory SQLite for testing
        db_manager = DatabaseManager("sqlite:///:memory:")
        db_manager.create_tables()
        
        service = DatabaseService(db_manager)
        yield service
        
        # Cleanup
        await db_manager.close()
    
    @pytest.mark.asyncio
    async def test_full_database_workflow(self, db_service):
        """Test complete database workflow from endpoints to sync logs."""
        # Create endpoint
        endpoint_data = {
            "endpoint_type": "google_drive",
            "name": "Test Google Drive",
            "project_id": "test-project",
            "user_id": "test-user",
            "endpoint_details": {"folder_id": "test-folder"},
            "is_active": True
        }
        
        endpoint = await db_service.create_endpoint(endpoint_data)
        assert endpoint.id is not None
        assert endpoint.name == "Test Google Drive"
        
        # Create files for the endpoint
        file_data_list = [
            {
                "external_id": "file1",
                "endpoint_id": endpoint.id,
                "title": "Test File 1.pdf",
                "file_link": "https://example.com/file1",
                "date_created": datetime.now(timezone.utc),
                "date_updated": datetime.now(timezone.utc),
                "project_id": "test-project",
                "user_id": "test-user",
                "file_metadata": {"size": 1024, "type": "pdf"}
            },
            {
                "external_id": "file2", 
                "endpoint_id": endpoint.id,
                "title": "Test File 2.dwg",
                "file_link": "https://example.com/file2",
                "date_created": datetime.now(timezone.utc),
                "date_updated": datetime.now(timezone.utc),
                "project_id": "test-project",
                "user_id": "test-user",
                "file_metadata": {"size": 2048, "type": "dwg"}
            }
        ]
        
        # Batch create files
        created_files = await db_service.batch_create_files(file_data_list)
        assert len(created_files) == 2
        
        # Create sync log
        sync_log_data = {
            "endpoint_id": endpoint.id,
            "sync_started": datetime.now(timezone.utc),
            "files_processed": 2,
            "files_added": 2,
            "files_updated": 0,
            "files_skipped": 0,
            "sync_status": "completed"
        }
        
        sync_log = await db_service.create_sync_log(sync_log_data)
        assert sync_log.id is not None
        assert sync_log.files_processed == 2
        
        # Query files by endpoint
        endpoint_files = await db_service.get_files_by_endpoint(endpoint.id)
        assert len(endpoint_files) == 2
        
        # Get database statistics
        stats = await db_service.get_database_stats()
        assert stats["total_endpoints"] >= 1
        assert stats["total_files"] >= 2
        assert stats["total_sync_logs"] >= 1


@pytest.mark.integration
class TestAPIClientIntegration:
    """Integration tests for API clients with mocked responses."""
    
    @pytest.fixture
    def mock_google_drive_credentials(self):
        """Mock Google Drive credentials."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            credentials = {
                "type": "service_account",
                "project_id": "test-project",
                "private_key_id": "test-key-id",
                "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
                "client_email": "test@test.iam.gserviceaccount.com",
                "client_id": "test-client-id",
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
            json.dump(credentials, f)
            f.flush()
            yield f.name
        
        # Cleanup
        Path(f.name).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_google_drive_client_integration(self, mock_google_drive_credentials):
        """Test Google Drive client with mocked service."""
        endpoint_details = {
            "folder_id": "test-folder",
            "include_shared": True,
            "file_types": ["pdf", "dwg"]
        }
        
        with patch('connector.api_clients.google_drive.service_account'), \
             patch('connector.api_clients.google_drive.build') as mock_build:
            
            # Mock Google API service
            mock_service = MagicMock()
            mock_files = MagicMock()
            mock_service.files.return_value = mock_files
            mock_build.return_value = mock_service
            
            # Mock API response
            mock_response = {
                "files": [
                    {
                        "id": "file1",
                        "name": "Test File.pdf",
                        "webViewLink": "https://drive.google.com/file/d/file1/view",
                        "size": "1024",
                        "mimeType": "application/pdf",
                        "createdTime": "2023-01-01T00:00:00.000Z",
                        "modifiedTime": "2023-01-01T00:00:00.000Z",
                        "ownedByMe": True,
                        "shared": False,
                        "parents": ["test-folder"]
                    }
                ],
                "nextPageToken": None
            }
            
            mock_list = MagicMock()
            mock_list.execute.return_value = mock_response
            mock_files.list.return_value = mock_list
            
            # Create and test client
            factory = APIClientFactory()
            client = factory.create_client(
                "google_drive",
                endpoint_details,
                credentials_path=mock_google_drive_credentials
            )
            
            await client.authenticate()
            
            # Test file listing
            files = []
            async for file_metadata in client.list_files():
                files.append(file_metadata)
            
            assert len(files) == 1
            assert files[0].title == "Test File.pdf"
            assert files[0].external_id == "file1"
    
    @pytest.mark.asyncio
    async def test_autodesk_client_integration(self):
        """Test Autodesk client with mocked HTTP responses."""
        endpoint_details = {
            "project_id": "test-project",
            "folder_id": "test-folder",
            "file_types": ["dwg", "rvt"]
        }
        
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session_class.return_value = mock_session
            
            # Mock authentication response
            auth_response = AsyncMock()
            auth_response.json = AsyncMock(return_value={
                "access_token": "test-token",
                "token_type": "Bearer",
                "expires_in": 3600
            })
            auth_response.__aenter__ = AsyncMock(return_value=auth_response)
            auth_response.__aexit__ = AsyncMock(return_value=None)
            
            # Mock files list response
            files_response = AsyncMock()
            files_response.json = AsyncMock(return_value={
                "data": [
                    {
                        "id": "file1",
                        "attributes": {
                            "name": "Test Drawing.dwg",
                            "createTime": "2023-01-01T00:00:00.000Z",
                            "lastModifiedTime": "2023-01-01T00:00:00.000Z",
                            "storageSize": 2048
                        },
                        "relationships": {
                            "parent": {"data": {"id": "test-folder"}}
                        }
                    }
                ]
            })
            files_response.__aenter__ = AsyncMock(return_value=files_response)
            files_response.__aexit__ = AsyncMock(return_value=None)
            
            # Configure mock session
            mock_session.post.return_value = auth_response
            mock_session.get.return_value = files_response
            
            # Create and test client
            factory = APIClientFactory()
            client = factory.create_client("autodesk", endpoint_details)
            
            await client.authenticate()
            
            # Test file listing
            files = []
            async for file_metadata in client.list_files():
                files.append(file_metadata)
            
            assert len(files) == 1
            assert files[0].title == "Test Drawing.dwg"
            assert files[0].external_id == "file1"


@pytest.mark.integration
class TestSyncEngineIntegration:
    """Integration tests for the sync engine."""
    
    @pytest.fixture
    async def setup_integration_test(self):
        """Set up integration test environment."""
        # Create in-memory database
        db_manager = DatabaseManager("sqlite:///:memory:")
        db_manager.create_tables()
        db_service = DatabaseService(db_manager)
        
        # Create test endpoint
        endpoint_data = {
            "endpoint_type": "google_drive",
            "name": "Test Integration Endpoint",
            "project_id": "test-project",
            "user_id": "test-user",
            "endpoint_details": {"folder_id": "test-folder"},
            "is_active": True
        }
        
        endpoint = await db_service.create_endpoint(endpoint_data)
        
        # Create sync engine
        sync_engine = SyncEngine(db_service)
        
        yield {
            "db_service": db_service,
            "endpoint": endpoint,
            "sync_engine": sync_engine
        }
        
        # Cleanup
        await db_manager.close()
    
    @pytest.mark.asyncio
    async def test_full_sync_workflow(self, setup_integration_test):
        """Test complete sync workflow from API to database."""
        test_data = setup_integration_test
        sync_engine = test_data["sync_engine"]
        endpoint = test_data["endpoint"]
        
        # Mock API client
        mock_client = AsyncMock()
        
        # Mock file metadata
        from connector.api_clients.base import FileMetadata
        mock_files = [
            FileMetadata(
                external_id="file1",
                title="Test File 1.pdf",
                file_link="https://example.com/file1",
                date_created=datetime.now(timezone.utc),
                date_updated=datetime.now(timezone.utc),
                project_id="test-project",
                user_id="test-user",
                metadata={"size": 1024, "type": "pdf"}
            ),
            FileMetadata(
                external_id="file2",
                title="Test File 2.dwg", 
                file_link="https://example.com/file2",
                date_created=datetime.now(timezone.utc),
                date_updated=datetime.now(timezone.utc),
                project_id="test-project",
                user_id="test-user",
                metadata={"size": 2048, "type": "dwg"}
            )
        ]
        
        # Mock async generator
        async def mock_list_files(*args, **kwargs):
            for file_meta in mock_files:
                yield file_meta
        
        mock_client.list_files = mock_list_files
        mock_client.authenticate = AsyncMock()
        mock_client.get_sync_info = AsyncMock(return_value={
            "last_sync": None,
            "api_quota_remaining": 1000,
            "rate_limit_reset": None
        })
        
        # Patch the factory to return our mock client
        with patch('connector.api_clients.APIClientFactory.create_client', return_value=mock_client):
            # Perform sync
            result = await sync_engine.sync_endpoint(endpoint)
            
            # Verify sync result
            assert result.success is True
            assert result.files_processed == 2
            assert result.files_added == 2
            assert result.files_updated == 0
            
            # Verify files were stored in database
            db_service = test_data["db_service"]
            stored_files = await db_service.get_files_by_endpoint(endpoint.id)
            assert len(stored_files) == 2
            
            # Verify file details
            file_titles = [f.title for f in stored_files]
            assert "Test File 1.pdf" in file_titles
            assert "Test File 2.dwg" in file_titles


@pytest.mark.integration
class TestPerformanceIntegration:
    """Integration tests for performance components."""
    
    @pytest.mark.asyncio
    async def test_metrics_collection_integration(self):
        """Test metrics collection during operations."""
        metrics = get_metrics_collector()
        
        # Record some test metrics
        metrics.record_timing("test.operation", 1.5, {"type": "integration_test"})
        metrics.increment_counter("test.counter", 5)
        metrics.set_gauge("test.gauge", 42.0)
        
        # Get statistics
        stats = metrics.get_stats("test.operation")
        assert stats is not None
        assert stats.count == 1
        assert stats.mean == 1.5
        
        # Get all metrics
        all_metrics = metrics.get_all_metrics()
        assert all_metrics["counters"]["test.counter"] == 5
        assert all_metrics["gauges"]["test.gauge"] == 42.0
        
        # Cleanup
        await metrics.stop()
    
    @pytest.mark.asyncio
    async def test_batch_processing_integration(self):
        """Test batch processing with real async operations."""
        batch_processor = get_batch_processor()
        
        # Create test items
        test_items = list(range(20))
        
        # Mock processing function
        async def process_batch(items):
            await asyncio.sleep(0.01)  # Simulate work
            return [item * 2 for item in items]
        
        # Process in batches
        result = await batch_processor.process_batches(
            test_items, 
            process_batch,
            batch_size=5
        )
        
        # Verify results
        assert result.total_items == 20
        assert result.successful_items == 20
        assert result.batch_size == 5
        assert result.processing_time > 0


@pytest.mark.integration
class TestFileConnectorIntegration:
    """Integration tests for the main FileConnector class."""
    
    @pytest.fixture
    async def connector_setup(self):
        """Set up FileConnector for integration testing."""
        # Create in-memory database
        db_manager = DatabaseManager("sqlite:///:memory:")
        db_manager.create_tables()
        db_service = DatabaseService(db_manager)
        
        # Create FileConnector
        connector = FileConnector(db_service)
        
        yield {
            "connector": connector,
            "db_service": db_service
        }
        
        # Cleanup
        await db_manager.close()
    
    @pytest.mark.asyncio
    async def test_connector_lifecycle(self, connector_setup):
        """Test FileConnector initialization and health checks."""
        connector = connector_setup["connector"]
        
        # Test health check
        health = await connector.health_check()
        assert "database" in health
        assert "sync_engine" in health
        
        # Test statistics
        stats = await connector.get_sync_statistics()
        assert "total_endpoints" in stats
        assert "total_files" in stats
    
    @pytest.mark.asyncio
    async def test_configuration_integration(self, connector_setup):
        """Test configuration integration with FileConnector."""
        from connector.config.schema import ConnectorConfig, EndpointConfig
        
        # Create test configuration
        config = ConnectorConfig(
            connector={"name": "test-connector", "environment": "testing"},
            endpoints=[
                EndpointConfig(
                    id="test-endpoint-1",
                    type="google_drive",
                    name="Test Google Drive",
                    project_id="test-project",
                    user_id="test-user",
                    endpoint_details={"folder_id": "test-folder"},
                    schedule=ScheduleType.MANUAL,
                    is_active=True
                )
            ]
        )
        
        connector = connector_setup["connector"]
        
        # Test configuration loading (mock the actual config loading)
        with patch.object(connector, 'load_configuration') as mock_load:
            mock_load.return_value = config
            
            loaded_config = await connector.load_configuration("test-config.yaml")
            assert loaded_config.connector["name"] == "test-connector"
            assert len(loaded_config.endpoints) == 1


@pytest.mark.integration
class TestEndToEndWorkflow:
    """End-to-end integration tests."""
    
    @pytest.mark.asyncio
    async def test_complete_sync_workflow(self):
        """Test complete workflow from configuration to sync completion."""
        # Create in-memory database
        db_manager = DatabaseManager("sqlite:///:memory:")
        db_manager.create_tables()
        db_service = DatabaseService(db_manager)
        
        try:
            # Create FileConnector
            connector = FileConnector(db_service)
            
            # Create test endpoint in database
            endpoint_data = {
                "endpoint_type": "google_drive",
                "name": "E2E Test Endpoint",
                "project_id": "e2e-project",
                "user_id": "e2e-user",
                "endpoint_details": {"folder_id": "e2e-folder"},
                "is_active": True
            }
            
            endpoint = await db_service.create_endpoint(endpoint_data)
            
            # Mock API client for end-to-end test
            mock_client = AsyncMock()
            
            from connector.api_clients.base import FileMetadata
            mock_files = [
                FileMetadata(
                    external_id="e2e_file1",
                    title="E2E Test File.pdf",
                    file_link="https://example.com/e2e_file1",
                    date_created=datetime.now(timezone.utc),
                    date_updated=datetime.now(timezone.utc),
                    project_id="e2e-project",
                    user_id="e2e-user",
                    metadata={"size": 1024, "type": "pdf"}
                )
            ]
            
            async def mock_list_files(*args, **kwargs):
                for file_meta in mock_files:
                    yield file_meta
            
            mock_client.list_files = mock_list_files
            mock_client.authenticate = AsyncMock()
            mock_client.get_sync_info = AsyncMock(return_value={
                "last_sync": None,
                "api_quota_remaining": 1000
            })
            
            # Perform end-to-end sync
            with patch('connector.api_clients.APIClientFactory.create_client', return_value=mock_client):
                result = await connector.sync_endpoint(endpoint.id)
                
                # Verify sync completed successfully
                assert result.success is True
                assert result.files_processed == 1
                assert result.files_added == 1
                
                # Verify file was stored
                files = await db_service.get_files_by_endpoint(endpoint.id)
                assert len(files) == 1
                assert files[0].title == "E2E Test File.pdf"
                
                # Verify sync log was created
                sync_logs = await db_service.get_sync_logs_by_endpoint(endpoint.id)
                assert len(sync_logs) >= 1
                assert sync_logs[-1].files_processed == 1
                
                # Test health check
                health = await connector.health_check()
                assert health["database"]["status"] == "healthy"
                
                # Test statistics
                stats = await connector.get_sync_statistics()
                assert stats["total_files"] >= 1
                assert stats["total_sync_logs"] >= 1
        
        finally:
            # Cleanup
            await db_manager.close()


# Performance benchmarks
@pytest.mark.benchmark
class TestPerformanceBenchmarks:
    """Performance benchmark tests."""
    
    @pytest.mark.asyncio
    async def test_database_batch_insert_performance(self):
        """Benchmark database batch insert performance."""
        db_manager = DatabaseManager("sqlite:///:memory:")
        db_manager.create_tables()
        db_service = DatabaseService(db_manager)
        
        try:
            # Create endpoint
            endpoint_data = {
                "endpoint_type": "google_drive",
                "name": "Benchmark Endpoint",
                "project_id": "benchmark-project",
                "user_id": "benchmark-user",
                "endpoint_details": {},
                "is_active": True
            }
            endpoint = await db_service.create_endpoint(endpoint_data)
            
            # Generate test files
            file_data_list = []
            for i in range(1000):
                file_data_list.append({
                    "external_id": f"file_{i}",
                    "endpoint_id": endpoint.id,
                    "title": f"Test File {i}.pdf",
                    "file_link": f"https://example.com/file_{i}",
                    "date_created": datetime.now(timezone.utc),
                    "date_updated": datetime.now(timezone.utc),
                    "project_id": "benchmark-project",
                    "user_id": "benchmark-user",
                    "file_metadata": {"size": 1024, "index": i}
                })
            
            # Benchmark batch insert
            import time
            start_time = time.time()
            
            created_files = await db_service.batch_create_files(file_data_list)
            
            end_time = time.time()
            insert_time = end_time - start_time
            
            # Verify performance (should complete within reasonable time)
            assert len(created_files) == 1000
            assert insert_time < 5.0  # Should complete within 5 seconds
            
            # Log performance metrics
            print(f"Batch insert of 1000 files took {insert_time:.2f} seconds")
            print(f"Rate: {len(created_files) / insert_time:.1f} files/second")
        
        finally:
            await db_manager.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])