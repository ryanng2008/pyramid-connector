"""Core sync engine for orchestrating file synchronization across API clients."""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass

from ..api_clients import APIClientFactory, BaseAPIClient, FileMetadata
from ..api_clients.base import RateLimitError, AuthenticationError, APIConnectionError
from ..database import DatabaseService, EndpointModel, EndpointType, SyncStatus
from ..database.models import FileCreate
from ..utils.logging import get_logger, log_async_execution_time


@dataclass
class SyncResult:
    """Result of a sync operation."""
    
    endpoint_id: int
    success: bool
    files_processed: int
    files_added: int
    files_updated: int
    files_skipped: int
    error_message: Optional[str] = None
    sync_duration: Optional[float] = None
    
    @property
    def files_changed(self) -> int:
        """Total files that were added or updated."""
        return self.files_added + self.files_updated


@dataclass
class SyncStats:
    """Statistics for multiple sync operations."""
    
    total_endpoints: int
    successful_syncs: int
    failed_syncs: int
    total_files_processed: int
    total_files_changed: int
    total_duration: float
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_endpoints == 0:
            return 0.0
        return (self.successful_syncs / self.total_endpoints) * 100


class SyncEngine:
    """Core sync engine for orchestrating file synchronization."""
    
    def __init__(self, database_service: DatabaseService):
        """Initialize sync engine.
        
        Args:
            database_service: Database service for persistence
        """
        self.db_service = database_service
        self.logger = get_logger(self.__class__.__name__)
        
        # Configuration
        self.max_retries = 3
        self.retry_delay = 30  # seconds
        self.rate_limit_backoff = 60  # seconds
        self.max_files_per_sync = 1000
        
        self.logger.info("Sync engine initialized")
    
    @log_async_execution_time
    async def sync_endpoint(
        self,
        endpoint: EndpointModel,
        since: Optional[datetime] = None,
        max_files: Optional[int] = None
    ) -> SyncResult:
        """Sync files from a single endpoint.
        
        Args:
            endpoint: Endpoint configuration
            since: Only sync files modified after this datetime
            max_files: Maximum number of files to process
            
        Returns:
            SyncResult with sync operation details
        """
        start_time = datetime.now()
        result = SyncResult(
            endpoint_id=endpoint.id,
            success=False,
            files_processed=0,
            files_added=0,
            files_updated=0,
            files_skipped=0
        )
        
        self.logger.info(
            "Starting sync for endpoint",
            endpoint_id=endpoint.id,
            endpoint_type=endpoint.endpoint_type.value,
            project_id=endpoint.project_id,
            user_id=endpoint.user_id,
            since=since
        )
        
        try:
            # Create API client
            api_client = await self._create_api_client(endpoint)
            
            # Determine sync start time
            sync_since = since or endpoint.last_sync_at or datetime(2020, 1, 1, tzinfo=timezone.utc)
            
            # Get maximum files to process
            max_to_process = min(
                max_files or self.max_files_per_sync,
                self.max_files_per_sync
            )
            
            # Perform sync with retries
            result = await self._sync_with_retries(
                api_client, endpoint, sync_since, max_to_process, result
            )
            
            # Update endpoint last sync time if successful
            if result.success:
                await self._update_endpoint_sync_time(endpoint)
            
        except Exception as e:
            error_msg = f"Unexpected error during sync: {e}"
            self.logger.error(
                "Sync failed with unexpected error",
                endpoint_id=endpoint.id,
                error=error_msg
            )
            result.error_message = error_msg
        
        finally:
            # Calculate duration
            result.sync_duration = (datetime.now() - start_time).total_seconds()
            
            # Log sync result
            await self._log_sync_result(endpoint, result)
        
        self.logger.info(
            "Sync completed for endpoint",
            endpoint_id=endpoint.id,
            success=result.success,
            files_processed=result.files_processed,
            files_changed=result.files_changed,
            duration=f"{result.sync_duration:.2f}s"
        )
        
        return result
    
    @log_async_execution_time
    async def sync_all_endpoints(
        self,
        endpoint_type: Optional[EndpointType] = None,
        project_id: Optional[str] = None,
        max_files_per_endpoint: Optional[int] = None
    ) -> SyncStats:
        """Sync files from all configured endpoints.
        
        Args:
            endpoint_type: Only sync endpoints of this type
            project_id: Only sync endpoints for this project
            max_files_per_endpoint: Maximum files per endpoint
            
        Returns:
            SyncStats with overall sync statistics
        """
        start_time = datetime.now()
        
        self.logger.info(
            "Starting sync for all endpoints",
            endpoint_type=endpoint_type.value if endpoint_type else "all",
            project_id=project_id
        )
        
        # Get endpoints to sync
        endpoints = await self._get_endpoints_to_sync(endpoint_type, project_id)
        
        if not endpoints:
            self.logger.warning("No endpoints found to sync")
            return SyncStats(
                total_endpoints=0,
                successful_syncs=0,
                failed_syncs=0,
                total_files_processed=0,
                total_files_changed=0,
                total_duration=0.0
            )
        
        # Sync all endpoints in parallel
        sync_tasks = [
            self.sync_endpoint(endpoint, max_files=max_files_per_endpoint)
            for endpoint in endpoints
        ]
        
        results = await asyncio.gather(*sync_tasks, return_exceptions=True)
        
        # Calculate statistics
        stats = self._calculate_sync_stats(results, start_time)
        
        self.logger.info(
            "Completed sync for all endpoints",
            total_endpoints=stats.total_endpoints,
            successful_syncs=stats.successful_syncs,
            failed_syncs=stats.failed_syncs,
            success_rate=f"{stats.success_rate:.1f}%",
            total_files_changed=stats.total_files_changed,
            duration=f"{stats.total_duration:.2f}s"
        )
        
        return stats
    
    async def _create_api_client(self, endpoint: EndpointModel) -> BaseAPIClient:
        """Create API client for endpoint."""
        try:
            # Parse endpoint details
            endpoint_details = endpoint.endpoint_details or {}
            
            # Create client using factory
            client = APIClientFactory.create_client(
                endpoint_type=endpoint.endpoint_type,
                endpoint_details=endpoint_details
            )
            
            # Authenticate
            authenticated = await client.authenticate()
            if not authenticated:
                raise AuthenticationError(f"Failed to authenticate with {endpoint.endpoint_type.value}")
            
            return client
            
        except Exception as e:
            self.logger.error(
                "Failed to create API client",
                endpoint_id=endpoint.id,
                endpoint_type=endpoint.endpoint_type.value,
                error=str(e)
            )
            raise
    
    async def _sync_with_retries(
        self,
        api_client: BaseAPIClient,
        endpoint: EndpointModel,
        since: datetime,
        max_files: int,
        result: SyncResult
    ) -> SyncResult:
        """Perform sync with retry logic."""
        
        for attempt in range(self.max_retries + 1):
            try:
                return await self._perform_sync(api_client, endpoint, since, max_files, result)
                
            except RateLimitError as e:
                if attempt < self.max_retries:
                    backoff = getattr(e, 'retry_after', self.rate_limit_backoff)
                    self.logger.warning(
                        "Rate limit exceeded, retrying after backoff",
                        endpoint_id=endpoint.id,
                        attempt=attempt + 1,
                        backoff_seconds=backoff
                    )
                    await asyncio.sleep(backoff)
                    continue
                else:
                    result.error_message = f"Rate limit exceeded after {self.max_retries} retries"
                    break
                    
            except (AuthenticationError, APIConnectionError) as e:
                if attempt < self.max_retries:
                    self.logger.warning(
                        "API error, retrying after delay",
                        endpoint_id=endpoint.id,
                        attempt=attempt + 1,
                        error=str(e)
                    )
                    await asyncio.sleep(self.retry_delay)
                    continue
                else:
                    result.error_message = f"API error after {self.max_retries} retries: {e}"
                    break
                    
            except Exception as e:
                result.error_message = f"Unexpected error: {e}"
                break
        
        return result
    
    async def _perform_sync(
        self,
        api_client: BaseAPIClient,
        endpoint: EndpointModel,
        since: datetime,
        max_files: int,
        result: SyncResult
    ) -> SyncResult:
        """Perform the actual file sync."""
        
        files_processed = 0
        
        try:
            # List files from API
            async for file_metadata in api_client.list_files(since=since, max_results=max_files):
                if files_processed >= max_files:
                    break
                
                # Convert to database format
                file_create = FileCreate(
                    endpoint_id=endpoint.id,
                    external_file_id=file_metadata.external_file_id,
                    file_name=file_metadata.file_name,
                    file_path=file_metadata.file_path,
                    file_link=file_metadata.file_link,
                    file_size=file_metadata.file_size,
                    file_type=file_metadata.file_type,
                    external_created_at=file_metadata.external_created_at,
                    external_updated_at=file_metadata.external_updated_at,
                    file_metadata=file_metadata.file_metadata
                )
                
                # Sync to database
                file_record, was_created = self.db_service.sync_file(file_create)
                
                if was_created:
                    result.files_added += 1
                    self.logger.debug(
                        "Added new file",
                        file_id=file_record.id,
                        external_file_id=file_metadata.external_file_id,
                        file_name=file_metadata.file_name
                    )
                else:
                    # Check if file was actually updated
                    if file_record.external_updated_at and file_metadata.external_updated_at:
                        if file_record.external_updated_at < file_metadata.external_updated_at:
                            result.files_updated += 1
                            self.logger.debug(
                                "Updated existing file",
                                file_id=file_record.id,
                                external_file_id=file_metadata.external_file_id,
                                file_name=file_metadata.file_name
                            )
                        else:
                            result.files_skipped += 1
                    else:
                        result.files_skipped += 1
                
                files_processed += 1
                result.files_processed = files_processed
                
                # Small delay to avoid overwhelming the system
                if files_processed % 50 == 0:
                    await asyncio.sleep(0.1)
            
            result.success = True
            
        except Exception as e:
            self.logger.error(
                "Error during file sync",
                endpoint_id=endpoint.id,
                files_processed=files_processed,
                error=str(e)
            )
            raise
        
        return result
    
    async def _get_endpoints_to_sync(
        self,
        endpoint_type: Optional[EndpointType] = None,
        project_id: Optional[str] = None
    ) -> List[EndpointModel]:
        """Get list of endpoints to sync."""
        
        filters = {"is_active": True}
        
        if endpoint_type:
            filters["endpoint_type"] = endpoint_type
        
        if project_id:
            filters["project_id"] = project_id
        
        return self.db_service.get_endpoints(**filters)
    
    async def _update_endpoint_sync_time(self, endpoint: EndpointModel):
        """Update endpoint last sync time."""
        try:
            self.db_service.update_endpoint_sync_time(endpoint.id)
        except Exception as e:
            self.logger.warning(
                "Failed to update endpoint sync time",
                endpoint_id=endpoint.id,
                error=str(e)
            )
    
    async def _log_sync_result(self, endpoint: EndpointModel, result: SyncResult):
        """Log sync result to database."""
        try:
            status = SyncStatus.SUCCESS if result.success else SyncStatus.FAILED
            
            self.db_service.log_sync_operation(
                endpoint_id=endpoint.id,
                status=status,
                files_processed=result.files_processed,
                files_added=result.files_added,
                files_updated=result.files_updated,
                error_message=result.error_message,
                sync_duration=result.sync_duration
            )
        except Exception as e:
            self.logger.warning(
                "Failed to log sync result",
                endpoint_id=endpoint.id,
                error=str(e)
            )
    
    def _calculate_sync_stats(self, results: List, start_time: datetime) -> SyncStats:
        """Calculate overall sync statistics."""
        
        total_endpoints = len(results)
        successful_syncs = 0
        failed_syncs = 0
        total_files_processed = 0
        total_files_changed = 0
        
        for result in results:
            if isinstance(result, Exception):
                failed_syncs += 1
            elif isinstance(result, SyncResult):
                if result.success:
                    successful_syncs += 1
                else:
                    failed_syncs += 1
                
                total_files_processed += result.files_processed
                total_files_changed += result.files_changed
            else:
                failed_syncs += 1
        
        total_duration = (datetime.now() - start_time).total_seconds()
        
        return SyncStats(
            total_endpoints=total_endpoints,
            successful_syncs=successful_syncs,
            failed_syncs=failed_syncs,
            total_files_processed=total_files_processed,
            total_files_changed=total_files_changed,
            total_duration=total_duration
        )


class SyncEngineError(Exception):
    """Base exception for sync engine errors."""
    pass