"""Job scheduler for managing sync operations."""

import asyncio
import threading
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED
from apscheduler.job import Job

from ..config import ConnectorConfig, EndpointConfig, ScheduleType, ConfigManager
from ..core import FileConnector, SyncResult
from ..database import DatabaseService
from ..utils.logging import get_logger, log_async_execution_time


class SchedulerError(Exception):
    """Raised when scheduler operations fail."""
    pass


class JobScheduler:
    """Manages scheduled sync operations for all endpoints."""
    
    def __init__(
        self,
        connector: FileConnector,
        config_manager: ConfigManager,
        max_workers: int = 10
    ):
        """Initialize job scheduler.
        
        Args:
            connector: File connector for sync operations
            config_manager: Configuration manager for endpoint config
            max_workers: Maximum number of concurrent sync jobs
        """
        self.connector = connector
        self.config_manager = config_manager
        self.max_workers = max_workers
        self.logger = get_logger(self.__class__.__name__)
        
        # Initialize scheduler
        self.scheduler = AsyncIOScheduler(
            job_defaults={
                'coalesce': True,  # Combine multiple pending executions
                'max_instances': 1,  # Only one instance per job
                'misfire_grace_time': 300  # 5 minutes grace time
            }
        )
        
        # Job tracking
        self.active_jobs: Dict[str, Job] = {}
        self.job_stats: Dict[str, Dict[str, Any]] = {}
        
        # Thread pool for CPU-intensive operations
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        
        # Event listeners
        self.scheduler.add_listener(self._job_executed, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(self._job_error, EVENT_JOB_ERROR)
        self.scheduler.add_listener(self._job_missed, EVENT_JOB_MISSED)
        
        self.logger.info("Job scheduler initialized", max_workers=max_workers)
    
    @log_async_execution_time
    async def start(self):
        """Start the scheduler and load all configured jobs."""
        if self.scheduler.running:
            self.logger.warning("Scheduler is already running")
            return
        
        try:
            # Start the scheduler
            self.scheduler.start()
            
            # Load and schedule all configured endpoints
            await self.reload_jobs()
            
            self.logger.info(
                "Job scheduler started successfully",
                active_jobs=len(self.active_jobs)
            )
            
        except Exception as e:
            self.logger.error("Failed to start scheduler", error=str(e))
            raise SchedulerError(f"Failed to start scheduler: {e}")
    
    async def stop(self, wait: bool = True):
        """Stop the scheduler and all jobs.
        
        Args:
            wait: Whether to wait for running jobs to complete
        """
        if not self.scheduler.running:
            self.logger.warning("Scheduler is not running")
            return
        
        try:
            # Shutdown scheduler
            self.scheduler.shutdown(wait=wait)
            
            # Shutdown thread pool
            self.thread_pool.shutdown(wait=wait)
            
            # Clear job tracking
            self.active_jobs.clear()
            
            self.logger.info("Job scheduler stopped successfully")
            
        except Exception as e:
            self.logger.error("Error stopping scheduler", error=str(e))
            # Don't raise exception for cleanup issues
            # raise SchedulerError(f"Failed to stop scheduler: {e}")
    
    @log_async_execution_time
    async def reload_jobs(self):
        """Reload all jobs from configuration."""
        try:
            # Get current configuration
            config = self.config_manager.get_config()
            
            # Remove all existing jobs
            self.scheduler.remove_all_jobs()
            self.active_jobs.clear()
            
            # Add jobs for scheduled endpoints
            scheduled_endpoints = config.get_scheduled_endpoints()
            
            for endpoint_config in scheduled_endpoints:
                await self.add_endpoint_job(endpoint_config)
            
            self.logger.info(
                "Jobs reloaded successfully",
                total_jobs=len(self.active_jobs),
                scheduled_endpoints=len(scheduled_endpoints)
            )
            
        except Exception as e:
            self.logger.error("Failed to reload jobs", error=str(e))
            raise SchedulerError(f"Failed to reload jobs: {e}")
    
    async def add_endpoint_job(self, endpoint_config: EndpointConfig) -> str:
        """Add a scheduled job for an endpoint.
        
        Args:
            endpoint_config: Endpoint configuration
            
        Returns:
            Job ID
        """
        job_id = self._get_job_id(endpoint_config)
        
        try:
            # Create trigger based on schedule type
            trigger = self._create_trigger(endpoint_config)
            
            # Add job to scheduler
            job = self.scheduler.add_job(
                func=self._execute_sync_job,
                trigger=trigger,
                args=[endpoint_config],
                id=job_id,
                name=f"Sync: {endpoint_config.name}",
                replace_existing=True
            )
            
            # Track job
            self.active_jobs[job_id] = job
            self.job_stats[job_id] = {
                "endpoint_name": endpoint_config.name,
                "endpoint_type": endpoint_config.endpoint_type.value,
                "project_id": endpoint_config.project_id,
                "schedule_type": endpoint_config.schedule.value,
                "created_at": datetime.now(timezone.utc),
                "last_run": None,
                "next_run": job.next_run_time,
                "run_count": 0,
                "success_count": 0,
                "error_count": 0,
                "last_result": None
            }
            
            self.logger.info(
                "Endpoint job added successfully",
                job_id=job_id,
                endpoint_name=endpoint_config.name,
                schedule_type=endpoint_config.schedule.value,
                next_run=job.next_run_time
            )
            
            return job_id
            
        except Exception as e:
            self.logger.error(
                "Failed to add endpoint job",
                job_id=job_id,
                endpoint_name=endpoint_config.name,
                error=str(e)
            )
            raise SchedulerError(f"Failed to add job for {endpoint_config.name}: {e}")
    
    async def remove_endpoint_job(self, endpoint_config: EndpointConfig) -> bool:
        """Remove a scheduled job for an endpoint.
        
        Args:
            endpoint_config: Endpoint configuration
            
        Returns:
            True if job was removed, False if not found
        """
        job_id = self._get_job_id(endpoint_config)
        
        try:
            if job_id in self.active_jobs:
                self.scheduler.remove_job(job_id)
                del self.active_jobs[job_id]
                del self.job_stats[job_id]
                
                self.logger.info(
                    "Endpoint job removed successfully",
                    job_id=job_id,
                    endpoint_name=endpoint_config.name
                )
                return True
            else:
                self.logger.warning(
                    "Job not found for removal",
                    job_id=job_id,
                    endpoint_name=endpoint_config.name
                )
                return False
                
        except Exception as e:
            self.logger.error(
                "Failed to remove endpoint job",
                job_id=job_id,
                endpoint_name=endpoint_config.name,
                error=str(e)
            )
            raise SchedulerError(f"Failed to remove job for {endpoint_config.name}: {e}")
    
    async def trigger_sync(self, endpoint_config: EndpointConfig) -> SyncResult:
        """Manually trigger a sync for an endpoint.
        
        Args:
            endpoint_config: Endpoint configuration
            
        Returns:
            Sync result
        """
        try:
            self.logger.info(
                "Manually triggering sync",
                endpoint_name=endpoint_config.name,
                endpoint_type=endpoint_config.endpoint_type.value
            )
            
            # Execute sync directly
            result = await self._execute_sync_job(endpoint_config)
            
            return result
            
        except Exception as e:
            self.logger.error(
                "Failed to trigger manual sync",
                endpoint_name=endpoint_config.name,
                error=str(e)
            )
            raise SchedulerError(f"Failed to trigger sync for {endpoint_config.name}: {e}")
    
    def get_job_status(self, endpoint_config: EndpointConfig) -> Optional[Dict[str, Any]]:
        """Get status information for an endpoint job.
        
        Args:
            endpoint_config: Endpoint configuration
            
        Returns:
            Job status information or None if not found
        """
        job_id = self._get_job_id(endpoint_config)
        
        if job_id not in self.job_stats:
            return None
        
        stats = self.job_stats[job_id].copy()
        
        # Add current job information
        if job_id in self.active_jobs:
            job = self.active_jobs[job_id]
            stats.update({
                "job_id": job_id,
                "next_run": job.next_run_time,
                "is_scheduled": True
            })
        else:
            stats.update({
                "job_id": job_id,
                "next_run": None,
                "is_scheduled": False
            })
        
        return stats
    
    def get_all_job_statuses(self) -> List[Dict[str, Any]]:
        """Get status information for all jobs.
        
        Returns:
            List of job status information
        """
        statuses = []
        
        for job_id, stats in self.job_stats.items():
            status = stats.copy()
            
            if job_id in self.active_jobs:
                job = self.active_jobs[job_id]
                status.update({
                    "job_id": job_id,
                    "next_run": job.next_run_time,
                    "is_scheduled": True
                })
            else:
                status.update({
                    "job_id": job_id,
                    "next_run": None,
                    "is_scheduled": False
                })
            
            statuses.append(status)
        
        return statuses
    
    def get_scheduler_stats(self) -> Dict[str, Any]:
        """Get overall scheduler statistics.
        
        Returns:
            Scheduler statistics
        """
        return {
            "is_running": self.scheduler.running,
            "total_jobs": len(self.active_jobs),
            "max_workers": self.max_workers,
            "pending_jobs": len([job for job in self.scheduler.get_jobs() if job.next_run_time]),
            "total_runs": sum(stats["run_count"] for stats in self.job_stats.values()),
            "total_successes": sum(stats["success_count"] for stats in self.job_stats.values()),
            "total_errors": sum(stats["error_count"] for stats in self.job_stats.values()),
            "last_reload": datetime.now(timezone.utc)
        }
    
    async def _execute_sync_job(self, endpoint_config: EndpointConfig) -> SyncResult:
        """Execute a sync job for an endpoint.
        
        Args:
            endpoint_config: Endpoint configuration
            
        Returns:
            Sync result
        """
        job_id = self._get_job_id(endpoint_config)
        
        self.logger.info(
            "Executing sync job",
            job_id=job_id,
            endpoint_name=endpoint_config.name,
            endpoint_type=endpoint_config.endpoint_type.value
        )
        
        try:
            # Find the corresponding database endpoint
            db_endpoints = self.connector.db_service.get_endpoints(
                endpoint_type=endpoint_config.endpoint_type,
                project_id=endpoint_config.project_id,
                user_id=endpoint_config.user_id
            )
            
            if not db_endpoints:
                raise SchedulerError(f"No database endpoint found for {endpoint_config.name}")
            
            # Use the first matching endpoint
            db_endpoint = db_endpoints[0]
            
            # Execute sync
            result = await self.connector.sync_endpoint_by_id(
                endpoint_id=db_endpoint.id,
                max_files=endpoint_config.max_files_per_sync
            )
            
            self.logger.info(
                "Sync job completed successfully",
                job_id=job_id,
                endpoint_name=endpoint_config.name,
                files_processed=result.files_processed,
                files_changed=result.files_changed,
                duration=f"{result.sync_duration:.2f}s"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(
                "Sync job failed",
                job_id=job_id,
                endpoint_name=endpoint_config.name,
                error=str(e)
            )
            
            # Create error result
            return SyncResult(
                endpoint_id=0,  # Will be updated by event handler
                success=False,
                files_processed=0,
                files_added=0,
                files_updated=0,
                files_skipped=0,
                error_message=str(e)
            )
    
    def _create_trigger(self, endpoint_config: EndpointConfig):
        """Create scheduler trigger for endpoint configuration.
        
        Args:
            endpoint_config: Endpoint configuration
            
        Returns:
            Scheduler trigger
        """
        if endpoint_config.schedule == ScheduleType.INTERVAL:
            # Interval-based scheduling
            interval_minutes = endpoint_config.schedule_config.get("interval_minutes", 5)
            return IntervalTrigger(minutes=interval_minutes)
        
        elif endpoint_config.schedule == ScheduleType.CRON:
            # Cron-based scheduling
            cron_expression = endpoint_config.schedule_config.get("cron_expression")
            if not cron_expression:
                raise SchedulerError(f"Cron expression required for {endpoint_config.name}")
            
            # Parse cron expression (format: minute hour day month day_of_week)
            parts = cron_expression.split()
            if len(parts) != 5:
                raise SchedulerError(f"Invalid cron expression for {endpoint_config.name}: {cron_expression}")
            
            return CronTrigger(
                minute=parts[0],
                hour=parts[1],
                day=parts[2],
                month=parts[3],
                day_of_week=parts[4]
            )
        
        else:
            raise SchedulerError(f"Unsupported schedule type: {endpoint_config.schedule}")
    
    def _get_job_id(self, endpoint_config: EndpointConfig) -> str:
        """Generate unique job ID for endpoint configuration.
        
        Args:
            endpoint_config: Endpoint configuration
            
        Returns:
            Unique job ID
        """
        return f"{endpoint_config.endpoint_type.value}_{endpoint_config.project_id}_{endpoint_config.user_id}"
    
    def _job_executed(self, event):
        """Handle job execution event."""
        job_id = event.job_id
        
        if job_id in self.job_stats:
            stats = self.job_stats[job_id]
            stats["last_run"] = datetime.now(timezone.utc)
            stats["run_count"] += 1
            
            # Check if job was successful
            if hasattr(event, 'retval') and isinstance(event.retval, SyncResult):
                result = event.retval
                stats["last_result"] = {
                    "success": result.success,
                    "files_processed": result.files_processed,
                    "files_changed": result.files_changed,
                    "duration": result.sync_duration,
                    "error_message": result.error_message
                }
                
                if result.success:
                    stats["success_count"] += 1
                else:
                    stats["error_count"] += 1
            else:
                stats["success_count"] += 1
            
            # Update next run time
            if job_id in self.active_jobs:
                stats["next_run"] = self.active_jobs[job_id].next_run_time
    
    def _job_error(self, event):
        """Handle job error event."""
        job_id = event.job_id
        
        if job_id in self.job_stats:
            stats = self.job_stats[job_id]
            stats["last_run"] = datetime.now(timezone.utc)
            stats["run_count"] += 1
            stats["error_count"] += 1
            stats["last_result"] = {
                "success": False,
                "files_processed": 0,
                "files_changed": 0,
                "duration": None,
                "error_message": str(event.exception)
            }
        
        self.logger.error(
            "Scheduled job failed",
            job_id=job_id,
            error=str(event.exception)
        )
    
    def _job_missed(self, event):
        """Handle job missed event."""
        job_id = event.job_id
        
        self.logger.warning(
            "Scheduled job missed",
            job_id=job_id,
            scheduled_run_time=event.scheduled_run_time
        )