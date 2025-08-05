"""Scheduler manager for coordinating sync operations and monitoring."""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

from .job_scheduler import JobScheduler, SchedulerError
from ..config import ConfigManager, ConnectorConfig, EndpointConfig, ScheduleType
from ..core import FileConnector, SyncStats
from ..database import DatabaseService
from ..utils.logging import get_logger, log_async_execution_time


class SchedulerManager:
    """High-level manager for scheduling and monitoring sync operations."""
    
    def __init__(
        self,
        connector: FileConnector,
        config_manager: ConfigManager,
        max_concurrent_syncs: int = 10
    ):
        """Initialize scheduler manager.
        
        Args:
            connector: File connector for sync operations
            config_manager: Configuration manager
            max_concurrent_syncs: Maximum concurrent sync operations
        """
        self.connector = connector
        self.config_manager = config_manager
        self.max_concurrent_syncs = max_concurrent_syncs
        self.logger = get_logger(self.__class__.__name__)
        
        # Initialize job scheduler
        self.job_scheduler = JobScheduler(
            connector=connector,
            config_manager=config_manager,
            max_workers=max_concurrent_syncs
        )
        
        # Health monitoring
        self.health_check_interval = 300  # 5 minutes
        self.health_check_task: Optional[asyncio.Task] = None
        self._is_running = False
        
        # Statistics
        self.start_time: Optional[datetime] = None
        self.last_health_check: Optional[datetime] = None
        self.health_status = "unknown"
        
        self.logger.info("Scheduler manager initialized")
    
    @log_async_execution_time
    async def start(self):
        """Start the scheduler manager and all components."""
        if self._is_running:
            self.logger.warning("Scheduler manager is already running")
            return
        
        try:
            # Start job scheduler
            await self.job_scheduler.start()
            
            # Start health monitoring
            self.health_check_task = asyncio.create_task(self._health_monitor_loop())
            
            # Mark as running
            self._is_running = True
            self.start_time = datetime.now(timezone.utc)
            self.health_status = "healthy"
            
            self.logger.info(
                "Scheduler manager started successfully",
                max_concurrent_syncs=self.max_concurrent_syncs
            )
            
        except Exception as e:
            self.logger.error("Failed to start scheduler manager", error=str(e))
            await self._cleanup()
            raise SchedulerError(f"Failed to start scheduler manager: {e}")
    
    async def stop(self, wait: bool = True):
        """Stop the scheduler manager and all components.
        
        Args:
            wait: Whether to wait for running operations to complete
        """
        if not self._is_running:
            self.logger.warning("Scheduler manager is not running")
            return
        
        try:
            # Mark as stopping
            self._is_running = False
            
            # Stop health monitoring
            if self.health_check_task:
                self.health_check_task.cancel()
                try:
                    await self.health_check_task
                except asyncio.CancelledError:
                    pass
            
            # Stop job scheduler
            await self.job_scheduler.stop(wait=wait)
            
            self.logger.info("Scheduler manager stopped successfully")
            
        except Exception as e:
            self.logger.error("Error stopping scheduler manager", error=str(e))
            raise SchedulerError(f"Failed to stop scheduler manager: {e}")
    
    @log_async_execution_time
    async def reload_configuration(self):
        """Reload configuration and update scheduled jobs."""
        if not self._is_running:
            raise SchedulerError("Scheduler manager is not running")
        
        try:
            # Reload configuration in config manager
            self.config_manager.reload_config()
            
            # Reload jobs in scheduler
            await self.job_scheduler.reload_jobs()
            
            self.logger.info("Configuration reloaded successfully")
            
        except Exception as e:
            self.logger.error("Failed to reload configuration", error=str(e))
            raise SchedulerError(f"Failed to reload configuration: {e}")
    
    async def add_endpoint(self, endpoint_config: EndpointConfig) -> bool:
        """Add a new endpoint to scheduling.
        
        Args:
            endpoint_config: Endpoint configuration
            
        Returns:
            True if endpoint was added successfully
        """
        if not self._is_running:
            raise SchedulerError("Scheduler manager is not running")
        
        try:
            # Add to configuration
            db_endpoint = self.config_manager.add_endpoint(endpoint_config, sync_to_db=True)
            
            # Add to scheduler if it has a schedule
            if endpoint_config.schedule != ScheduleType.MANUAL:
                await self.job_scheduler.add_endpoint_job(endpoint_config)
            
            self.logger.info(
                "Endpoint added successfully",
                endpoint_name=endpoint_config.name,
                endpoint_id=db_endpoint.id if db_endpoint else None,
                scheduled=endpoint_config.schedule != ScheduleType.MANUAL
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to add endpoint",
                endpoint_name=endpoint_config.name,
                error=str(e)
            )
            raise SchedulerError(f"Failed to add endpoint {endpoint_config.name}: {e}")
    
    async def remove_endpoint(self, endpoint_name: str) -> bool:
        """Remove an endpoint from scheduling.
        
        Args:
            endpoint_name: Name of endpoint to remove
            
        Returns:
            True if endpoint was removed successfully
        """
        if not self._is_running:
            raise SchedulerError("Scheduler manager is not running")
        
        try:
            # Get endpoint configuration
            endpoint_config = self.config_manager.get_endpoint_config(endpoint_name)
            if not endpoint_config:
                self.logger.warning("Endpoint not found", endpoint_name=endpoint_name)
                return False
            
            # Remove from scheduler
            if endpoint_config.schedule != ScheduleType.MANUAL:
                await self.job_scheduler.remove_endpoint_job(endpoint_config)
            
            # Remove from configuration
            self.config_manager.remove_endpoint(endpoint_name, sync_to_db=True)
            
            self.logger.info("Endpoint removed successfully", endpoint_name=endpoint_name)
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to remove endpoint",
                endpoint_name=endpoint_name,
                error=str(e)
            )
            raise SchedulerError(f"Failed to remove endpoint {endpoint_name}: {e}")
    
    async def trigger_sync(self, endpoint_name: str) -> Dict[str, Any]:
        """Manually trigger sync for a specific endpoint.
        
        Args:
            endpoint_name: Name of endpoint to sync
            
        Returns:
            Sync result information
        """
        if not self._is_running:
            raise SchedulerError("Scheduler manager is not running")
        
        try:
            # Get endpoint configuration
            endpoint_config = self.config_manager.get_endpoint_config(endpoint_name)
            if not endpoint_config:
                raise SchedulerError(f"Endpoint not found: {endpoint_name}")
            
            # Trigger sync
            result = await self.job_scheduler.trigger_sync(endpoint_config)
            
            return {
                "endpoint_name": endpoint_name,
                "success": result.success,
                "files_processed": result.files_processed,
                "files_changed": result.files_changed,
                "duration": result.sync_duration,
                "error_message": result.error_message,
                "triggered_at": datetime.now(timezone.utc)
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to trigger sync",
                endpoint_name=endpoint_name,
                error=str(e)
            )
            raise SchedulerError(f"Failed to trigger sync for {endpoint_name}: {e}")
    
    async def trigger_project_sync(self, project_id: str) -> Dict[str, Any]:
        """Trigger sync for all endpoints in a project.
        
        Args:
            project_id: Project identifier
            
        Returns:
            Project sync statistics
        """
        if not self._is_running:
            raise SchedulerError("Scheduler manager is not running")
        
        try:
            # Get project endpoints
            project_endpoints = self.config_manager.get_endpoints_by_project(project_id)
            
            if not project_endpoints:
                raise SchedulerError(f"No endpoints found for project: {project_id}")
            
            # Trigger sync for all endpoints
            sync_tasks = []
            for endpoint_config in project_endpoints:
                if endpoint_config.is_active:
                    task = self.job_scheduler.trigger_sync(endpoint_config)
                    sync_tasks.append(task)
            
            # Wait for all syncs to complete
            results = await asyncio.gather(*sync_tasks, return_exceptions=True)
            
            # Calculate statistics
            successful_syncs = 0
            failed_syncs = 0
            total_files_processed = 0
            total_files_changed = 0
            
            for result in results:
                if isinstance(result, Exception):
                    failed_syncs += 1
                else:
                    if result.success:
                        successful_syncs += 1
                    else:
                        failed_syncs += 1
                    
                    total_files_processed += result.files_processed
                    total_files_changed += result.files_changed
            
            return {
                "project_id": project_id,
                "total_endpoints": len(project_endpoints),
                "active_endpoints": len(sync_tasks),
                "successful_syncs": successful_syncs,
                "failed_syncs": failed_syncs,
                "total_files_processed": total_files_processed,
                "total_files_changed": total_files_changed,
                "triggered_at": datetime.now(timezone.utc)
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to trigger project sync",
                project_id=project_id,
                error=str(e)
            )
            raise SchedulerError(f"Failed to trigger project sync for {project_id}: {e}")
    
    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get comprehensive scheduler status.
        
        Returns:
            Scheduler status information
        """
        # Get basic scheduler stats
        scheduler_stats = self.job_scheduler.get_scheduler_stats()
        
        # Get job statuses
        job_statuses = self.job_scheduler.get_all_job_statuses()
        
        # Calculate uptime
        uptime = None
        if self.start_time:
            uptime = (datetime.now(timezone.utc) - self.start_time).total_seconds()
        
        return {
            "is_running": self._is_running,
            "health_status": self.health_status,
            "start_time": self.start_time,
            "uptime_seconds": uptime,
            "last_health_check": self.last_health_check,
            "max_concurrent_syncs": self.max_concurrent_syncs,
            "scheduler_stats": scheduler_stats,
            "job_count": len(job_statuses),
            "jobs": job_statuses
        }
    
    def get_endpoint_status(self, endpoint_name: str) -> Optional[Dict[str, Any]]:
        """Get status for a specific endpoint.
        
        Args:
            endpoint_name: Name of endpoint
            
        Returns:
            Endpoint status or None if not found
        """
        endpoint_config = self.config_manager.get_endpoint_config(endpoint_name)
        if not endpoint_config:
            return None
        
        job_status = self.job_scheduler.get_job_status(endpoint_config)
        
        return {
            "endpoint_name": endpoint_name,
            "endpoint_type": endpoint_config.endpoint_type.value,
            "project_id": endpoint_config.project_id,
            "schedule_type": endpoint_config.schedule.value,
            "is_active": endpoint_config.is_active,
            "job_status": job_status
        }
    
    async def perform_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check.
        
        Returns:
            Health check results
        """
        health = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc),
            "scheduler_running": self._is_running,
            "job_scheduler_running": self.job_scheduler.scheduler.running,
            "issues": []
        }
        
        try:
            # Check if scheduler is running
            if not self._is_running or not self.job_scheduler.scheduler.running:
                health["issues"].append("Scheduler is not running")
                health["status"] = "unhealthy"
            
            # Check connector health
            connector_health = await self.connector.health_check()
            if connector_health["status"] != "healthy":
                health["issues"].extend(connector_health.get("issues", []))
                health["status"] = "degraded" if health["status"] == "healthy" else "unhealthy"
            
            # Check job statistics
            scheduler_stats = self.job_scheduler.get_scheduler_stats()
            if scheduler_stats["total_errors"] > scheduler_stats["total_successes"]:
                health["issues"].append("More failed jobs than successful ones")
                health["status"] = "degraded" if health["status"] == "healthy" else health["status"]
            
            # Check for stuck jobs (no runs in last hour)
            current_time = datetime.now(timezone.utc)
            stuck_jobs = []
            
            for job_status in self.job_scheduler.get_all_job_statuses():
                if job_status["last_run"]:
                    time_since_last_run = current_time - job_status["last_run"]
                    if time_since_last_run > timedelta(hours=1) and job_status["is_scheduled"]:
                        stuck_jobs.append(job_status["endpoint_name"])
            
            if stuck_jobs:
                health["issues"].append(f"Jobs appear stuck: {', '.join(stuck_jobs)}")
                health["status"] = "degraded" if health["status"] == "healthy" else health["status"]
            
            # Add detailed information
            health.update({
                "scheduler_stats": scheduler_stats,
                "connector_health": connector_health
            })
            
        except Exception as e:
            health["status"] = "unhealthy"
            health["issues"].append(f"Health check failed: {e}")
        
        self.last_health_check = health["timestamp"]
        self.health_status = health["status"]
        
        return health
    
    async def _health_monitor_loop(self):
        """Background health monitoring loop."""
        self.logger.info("Health monitoring started")
        
        try:
            while self._is_running:
                try:
                    # Perform health check
                    health_result = await self.perform_health_check()
                    
                    # Log health status changes
                    if health_result["status"] != "healthy":
                        self.logger.warning(
                            "Health check detected issues",
                            status=health_result["status"],
                            issues=health_result["issues"]
                        )
                    
                    # Wait for next check
                    await asyncio.sleep(self.health_check_interval)
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.logger.error("Error in health monitoring", error=str(e))
                    await asyncio.sleep(60)  # Wait before retrying
        
        except asyncio.CancelledError:
            pass
        
        self.logger.info("Health monitoring stopped")
    
    async def _cleanup(self):
        """Cleanup resources."""
        self._is_running = False
        
        if self.health_check_task:
            self.health_check_task.cancel()
        
        try:
            await self.job_scheduler.stop(wait=False)
        except Exception:
            pass