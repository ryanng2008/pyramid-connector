"""Main connector orchestrator for managing file synchronization."""

import asyncio
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timezone

from .sync_engine import SyncEngine, SyncResult, SyncStats
from ..database import DatabaseService, EndpointType, EndpointModel
from ..database.models import EndpointCreate
from ..utils.logging import get_logger, log_async_execution_time


class FileConnector:
    """Main connector for orchestrating file synchronization across multiple services."""
    
    def __init__(self, database_service: DatabaseService):
        """Initialize the file connector.
        
        Args:
            database_service: Database service for persistence
        """
        self.db_service = database_service
        self.sync_engine = SyncEngine(database_service)
        self.logger = get_logger(self.__class__.__name__)
        
        self.logger.info("File connector initialized")
    
    @log_async_execution_time
    async def add_endpoint(
        self,
        endpoint_type: EndpointType,
        project_id: str,
        user_id: str,
        endpoint_details: Dict[str, Any],
        description: Optional[str] = None
    ) -> EndpointModel:
        """Add a new sync endpoint.
        
        Args:
            endpoint_type: Type of endpoint (google_drive, autodesk_construction_cloud)
            project_id: Project identifier
            user_id: User identifier
            endpoint_details: Endpoint-specific configuration
            description: Optional description
            
        Returns:
            Created endpoint model
        """
        self.logger.info(
            "Adding new endpoint",
            endpoint_type=endpoint_type.value,
            project_id=project_id,
            user_id=user_id
        )
        
        endpoint_create = EndpointCreate(
            endpoint_type=endpoint_type,
            project_id=project_id,
            user_id=user_id,
            endpoint_details=endpoint_details,
            description=description
        )
        
        endpoint = self.db_service.create_endpoint(endpoint_create)
        
        self.logger.info(
            "Endpoint added successfully",
            endpoint_id=endpoint.id,
            endpoint_type=endpoint_type.value
        )
        
        return endpoint
    
    @log_async_execution_time
    async def sync_endpoint_by_id(
        self,
        endpoint_id: int,
        since: Optional[datetime] = None,
        max_files: Optional[int] = None
    ) -> SyncResult:
        """Sync files from a specific endpoint by ID.
        
        Args:
            endpoint_id: ID of endpoint to sync
            since: Only sync files modified after this datetime
            max_files: Maximum number of files to process
            
        Returns:
            SyncResult with sync operation details
        """
        endpoint = self.db_service.get_endpoint_by_id(endpoint_id)
        if not endpoint:
            raise ValueError(f"Endpoint with ID {endpoint_id} not found")
        
        if not endpoint.is_active:
            raise ValueError(f"Endpoint {endpoint_id} is not active")
        
        return await self.sync_engine.sync_endpoint(endpoint, since, max_files)
    
    @log_async_execution_time
    async def sync_project(
        self,
        project_id: str,
        endpoint_type: Optional[EndpointType] = None,
        max_files_per_endpoint: Optional[int] = None
    ) -> SyncStats:
        """Sync all endpoints for a specific project.
        
        Args:
            project_id: Project identifier
            endpoint_type: Only sync endpoints of this type
            max_files_per_endpoint: Maximum files per endpoint
            
        Returns:
            SyncStats with overall sync statistics
        """
        self.logger.info(
            "Starting project sync",
            project_id=project_id,
            endpoint_type=endpoint_type.value if endpoint_type else "all"
        )
        
        return await self.sync_engine.sync_all_endpoints(
            endpoint_type=endpoint_type,
            project_id=project_id,
            max_files_per_endpoint=max_files_per_endpoint
        )
    
    @log_async_execution_time
    async def sync_all(
        self,
        endpoint_type: Optional[EndpointType] = None,
        max_files_per_endpoint: Optional[int] = None
    ) -> SyncStats:
        """Sync all active endpoints.
        
        Args:
            endpoint_type: Only sync endpoints of this type
            max_files_per_endpoint: Maximum files per endpoint
            
        Returns:
            SyncStats with overall sync statistics
        """
        self.logger.info(
            "Starting full sync",
            endpoint_type=endpoint_type.value if endpoint_type else "all"
        )
        
        return await self.sync_engine.sync_all_endpoints(
            endpoint_type=endpoint_type,
            max_files_per_endpoint=max_files_per_endpoint
        )
    
    @log_async_execution_time
    async def sync_incremental(
        self,
        endpoint_type: Optional[EndpointType] = None,
        project_id: Optional[str] = None
    ) -> SyncStats:
        """Perform incremental sync using last sync timestamps.
        
        This method will only sync files that have been modified since the last
        successful sync for each endpoint.
        
        Args:
            endpoint_type: Only sync endpoints of this type
            project_id: Only sync endpoints for this project
            
        Returns:
            SyncStats with overall sync statistics
        """
        self.logger.info(
            "Starting incremental sync",
            endpoint_type=endpoint_type.value if endpoint_type else "all",
            project_id=project_id
        )
        
        # Get endpoints for incremental sync
        filters = {"is_active": True}
        if endpoint_type:
            filters["endpoint_type"] = endpoint_type
        if project_id:
            filters["project_id"] = project_id
        
        endpoints = self.db_service.get_endpoints(**filters)
        
        if not endpoints:
            self.logger.info("No endpoints found for incremental sync")
            return SyncStats(
                total_endpoints=0,
                successful_syncs=0,
                failed_syncs=0,
                total_files_processed=0,
                total_files_changed=0,
                total_duration=0.0
            )
        
        # Sync each endpoint since its last sync time
        start_time = datetime.now()
        sync_tasks = []
        
        for endpoint in endpoints:
            # Use last sync time or a reasonable default
            since = endpoint.last_sync_at or datetime(2020, 1, 1, tzinfo=timezone.utc)
            
            sync_tasks.append(
                self.sync_engine.sync_endpoint(endpoint, since=since)
            )
        
        results = await asyncio.gather(*sync_tasks, return_exceptions=True)
        stats = self.sync_engine._calculate_sync_stats(results, start_time)
        
        self.logger.info(
            "Completed incremental sync",
            endpoints_processed=len(endpoints),
            files_changed=stats.total_files_changed,
            success_rate=f"{stats.success_rate:.1f}%"
        )
        
        return stats
    
    async def get_endpoint_status(self, endpoint_id: int) -> Dict[str, Any]:
        """Get status information for an endpoint.
        
        Args:
            endpoint_id: ID of endpoint
            
        Returns:
            Dictionary with endpoint status information
        """
        endpoint = self.db_service.get_endpoint_by_id(endpoint_id)
        if not endpoint:
            raise ValueError(f"Endpoint with ID {endpoint_id} not found")
        
        # Get recent sync logs
        recent_syncs = self.db_service.get_recent_sync_logs(endpoint_id, limit=5)
        
        # Get file count
        file_count = len(self.db_service.get_files_by_endpoint(endpoint_id, limit=1000))
        
        # Calculate sync statistics
        last_sync = recent_syncs[0] if recent_syncs else None
        
        status = {
            "endpoint_id": endpoint.id,
            "endpoint_type": endpoint.endpoint_type.value,
            "project_id": endpoint.project_id,
            "user_id": endpoint.user_id,
            "is_active": endpoint.is_active,
            "created_at": endpoint.created_at,
            "last_sync_at": endpoint.last_sync_at,
            "file_count": file_count,
            "last_sync_status": last_sync.status.value if last_sync else None,
            "last_sync_files_processed": last_sync.files_processed if last_sync else 0,
            "last_sync_files_added": last_sync.files_added if last_sync else 0,
            "last_sync_files_updated": last_sync.files_updated if last_sync else 0,
            "recent_sync_count": len(recent_syncs)
        }
        
        return status
    
    async def get_project_status(self, project_id: str) -> Dict[str, Any]:
        """Get status information for all endpoints in a project.
        
        Args:
            project_id: Project identifier
            
        Returns:
            Dictionary with project status information
        """
        endpoints = self.db_service.get_endpoints(project_id=project_id)
        
        if not endpoints:
            return {
                "project_id": project_id,
                "endpoint_count": 0,
                "active_endpoints": 0,
                "total_files": 0,
                "endpoints": []
            }
        
        # Get status for each endpoint
        endpoint_statuses = []
        total_files = 0
        active_endpoints = 0
        
        for endpoint in endpoints:
            try:
                status = await self.get_endpoint_status(endpoint.id)
                endpoint_statuses.append(status)
                total_files += status["file_count"]
                if status["is_active"]:
                    active_endpoints += 1
            except Exception as e:
                self.logger.warning(
                    "Failed to get endpoint status",
                    endpoint_id=endpoint.id,
                    error=str(e)
                )
        
        return {
            "project_id": project_id,
            "endpoint_count": len(endpoints),
            "active_endpoints": active_endpoints,
            "total_files": total_files,
            "endpoints": endpoint_statuses
        }
    
    async def deactivate_endpoint(self, endpoint_id: int) -> bool:
        """Deactivate an endpoint (stop syncing without deleting).
        
        Args:
            endpoint_id: ID of endpoint to deactivate
            
        Returns:
            True if successful
        """
        endpoint = self.db_service.get_endpoint_by_id(endpoint_id)
        if not endpoint:
            raise ValueError(f"Endpoint with ID {endpoint_id} not found")
        
        self.db_service.update_endpoint(endpoint_id, {"is_active": False})
        
        self.logger.info(
            "Endpoint deactivated",
            endpoint_id=endpoint_id
        )
        
        return True
    
    async def activate_endpoint(self, endpoint_id: int) -> bool:
        """Activate an endpoint (resume syncing).
        
        Args:
            endpoint_id: ID of endpoint to activate
            
        Returns:
            True if successful
        """
        endpoint = self.db_service.get_endpoint_by_id(endpoint_id)
        if not endpoint:
            raise ValueError(f"Endpoint with ID {endpoint_id} not found")
        
        self.db_service.update_endpoint(endpoint_id, {"is_active": True})
        
        self.logger.info(
            "Endpoint activated",
            endpoint_id=endpoint_id
        )
        
        return True
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the connector system.
        
        Returns:
            Dictionary with health check results
        """
        health = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc),
            "database": False,
            "endpoints": 0,
            "active_endpoints": 0,
            "issues": []
        }
        
        try:
            # Check database connectivity
            # Use the correct attribute name from DatabaseService
            health["database"] = self.db_service.db_manager.test_connection()
            if not health["database"]:
                health["issues"].append("Database connection failed")
                health["status"] = "degraded"
            
            # Check endpoint count
            all_endpoints = self.db_service.get_endpoints()
            active_endpoints = [e for e in all_endpoints if e.is_active]
            
            health["endpoints"] = len(all_endpoints)
            health["active_endpoints"] = len(active_endpoints)
            
            if health["active_endpoints"] == 0:
                health["issues"].append("No active endpoints configured")
                if health["status"] == "healthy":
                    health["status"] = "warning"
            
            # Test API client creation for active endpoints
            api_issues = 0
            for endpoint in active_endpoints[:5]:  # Test up to 5 endpoints
                try:
                    from ..api_clients import APIClientFactory
                    client = APIClientFactory.create_client(
                        endpoint.endpoint_type,
                        endpoint.endpoint_details or {}
                    )
                    # Don't actually authenticate in health check
                except Exception as e:
                    api_issues += 1
                    self.logger.warning(
                        "API client creation failed in health check",
                        endpoint_id=endpoint.id,
                        error=str(e)
                    )
            
            if api_issues > 0:
                health["issues"].append(f"API client issues detected for {api_issues} endpoints")
                health["status"] = "degraded"
            
        except Exception as e:
            health["status"] = "unhealthy"
            health["issues"].append(f"Health check failed: {e}")
        
        return health