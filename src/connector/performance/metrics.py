"""Performance metrics collection and monitoring."""

import asyncio
import time
from typing import Dict, Any, Optional, List, Union
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from collections import defaultdict, deque
import statistics
import psutil
import threading

from ..utils.logging import get_logger


@dataclass
class MetricPoint:
    """Individual metric measurement point."""
    
    timestamp: datetime
    value: Union[float, int]
    tags: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metric point to dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "tags": self.tags
        }


@dataclass
class PerformanceStats:
    """Performance statistics for a metric."""
    
    count: int
    min_value: float
    max_value: float
    mean: float
    median: float
    p95: float
    p99: float
    std_dev: float
    total: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "count": self.count,
            "min": self.min_value,
            "max": self.max_value,
            "mean": self.mean,
            "median": self.median,
            "p95": self.p95,
            "p99": self.p99,
            "std_dev": self.std_dev,
            "total": self.total
        }


class MetricsCollector:
    """Collects and aggregates performance metrics."""
    
    def __init__(self, max_points_per_metric: int = 10000, retention_hours: int = 24):
        """Initialize metrics collector.
        
        Args:
            max_points_per_metric: Maximum points to keep per metric
            retention_hours: Hours to retain metric data
        """
        self.max_points_per_metric = max_points_per_metric
        self.retention_hours = retention_hours
        
        self.logger = get_logger(self.__class__.__name__)
        
        # Metric storage: metric_name -> deque of MetricPoint
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_points_per_metric))
        
        # Counters for simple counting metrics
        self._counters: Dict[str, int] = defaultdict(int)
        
        # Gauges for current value metrics
        self._gauges: Dict[str, float] = defaultdict(float)
        
        # Lock for thread safety
        self._lock = threading.RLock()
        
        # Start cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._start_cleanup_task()
        
        self.logger.info(
            "Metrics collector initialized",
            max_points_per_metric=max_points_per_metric,
            retention_hours=retention_hours
        )
    
    def record_timing(
        self,
        metric_name: str,
        duration: float,
        tags: Optional[Dict[str, str]] = None
    ):
        """Record a timing metric.
        
        Args:
            metric_name: Name of the metric
            duration: Duration in seconds
            tags: Optional tags for the metric
        """
        with self._lock:
            point = MetricPoint(
                timestamp=datetime.now(timezone.utc),
                value=duration,
                tags=tags or {}
            )
            self._metrics[metric_name].append(point)
    
    def record_value(
        self,
        metric_name: str,
        value: Union[float, int],
        tags: Optional[Dict[str, str]] = None
    ):
        """Record a value metric.
        
        Args:
            metric_name: Name of the metric
            value: Metric value
            tags: Optional tags for the metric
        """
        with self._lock:
            point = MetricPoint(
                timestamp=datetime.now(timezone.utc),
                value=float(value),
                tags=tags or {}
            )
            self._metrics[metric_name].append(point)
    
    def increment_counter(self, counter_name: str, value: int = 1):
        """Increment a counter metric.
        
        Args:
            counter_name: Name of the counter
            value: Amount to increment by
        """
        with self._lock:
            self._counters[counter_name] += value
    
    def set_gauge(self, gauge_name: str, value: Union[float, int]):
        """Set a gauge metric value.
        
        Args:
            gauge_name: Name of the gauge
            value: Current value
        """
        with self._lock:
            self._gauges[gauge_name] = float(value)
    
    @asynccontextmanager
    async def time_operation(self, metric_name: str, tags: Optional[Dict[str, str]] = None):
        """Context manager for timing operations.
        
        Args:
            metric_name: Name of the timing metric
            tags: Optional tags for the metric
        """
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.record_timing(metric_name, duration, tags)
    
    def get_stats(self, metric_name: str, hours: Optional[int] = None) -> Optional[PerformanceStats]:
        """Get statistics for a metric.
        
        Args:
            metric_name: Name of the metric
            hours: Number of hours to include (None for all)
            
        Returns:
            PerformanceStats or None if metric doesn't exist
        """
        with self._lock:
            if metric_name not in self._metrics:
                return None
            
            points = list(self._metrics[metric_name])
            
            if not points:
                return None
            
            # Filter by time if specified
            if hours is not None:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
                points = [p for p in points if p.timestamp >= cutoff_time]
            
            if not points:
                return None
            
            values = [p.value for p in points]
            
            return PerformanceStats(
                count=len(values),
                min_value=min(values),
                max_value=max(values),
                mean=statistics.mean(values),
                median=statistics.median(values),
                p95=self._percentile(values, 95),
                p99=self._percentile(values, 99),
                std_dev=statistics.stdev(values) if len(values) > 1 else 0.0,
                total=sum(values)
            )
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all current metrics and statistics.
        
        Returns:
            Dictionary with all metrics data
        """
        with self._lock:
            result = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "timings": {},
                "values": {}
            }
            
            # Add statistics for all metrics
            for metric_name in self._metrics:
                stats = self.get_stats(metric_name)
                if stats:
                    if "timing" in metric_name.lower() or "duration" in metric_name.lower():
                        result["timings"][metric_name] = stats.to_dict()
                    else:
                        result["values"][metric_name] = stats.to_dict()
            
            return result
    
    def get_recent_points(
        self,
        metric_name: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent metric points.
        
        Args:
            metric_name: Name of the metric
            limit: Maximum number of points to return
            
        Returns:
            List of recent metric points
        """
        with self._lock:
            if metric_name not in self._metrics:
                return []
            
            points = list(self._metrics[metric_name])
            recent_points = points[-limit:] if len(points) > limit else points
            
            return [point.to_dict() for point in recent_points]
    
    def cleanup_old_metrics(self):
        """Clean up metrics older than retention period."""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.retention_hours)
        cleaned_count = 0
        
        with self._lock:
            for metric_name, points in self._metrics.items():
                original_length = len(points)
                
                # Remove old points
                while points and points[0].timestamp < cutoff_time:
                    points.popleft()
                
                cleaned_count += original_length - len(points)
        
        if cleaned_count > 0:
            self.logger.debug("Cleaned up old metrics", points_removed=cleaned_count)
        
        return cleaned_count
    
    def reset_metrics(self):
        """Reset all metrics."""
        with self._lock:
            self._metrics.clear()
            self._counters.clear()
            self._gauges.clear()
        
        self.logger.info("All metrics reset")
    
    def _percentile(self, values: List[float], percentile: float) -> float:
        """Calculate percentile value."""
        if not values:
            return 0.0
        
        sorted_values = sorted(values)
        k = (len(sorted_values) - 1) * (percentile / 100.0)
        f = int(k)
        c = k - f
        
        if f == len(sorted_values) - 1:
            return sorted_values[f]
        else:
            return sorted_values[f] * (1 - c) + sorted_values[f + 1] * c
    
    def _start_cleanup_task(self):
        """Start the background cleanup task."""
        try:
            loop = asyncio.get_event_loop()
            self._cleanup_task = loop.create_task(self._cleanup_loop())
        except RuntimeError:
            # No event loop running yet
            pass
    
    async def _cleanup_loop(self):
        """Background task for periodic cleanup."""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                self.cleanup_old_metrics()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.warning("Error in metrics cleanup", error=str(e))
    
    async def stop(self):
        """Stop the metrics collector and cleanup tasks."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Metrics collector stopped")


class SystemMetricsCollector:
    """Collects system performance metrics."""
    
    def __init__(self, metrics_collector: MetricsCollector):
        """Initialize system metrics collector.
        
        Args:
            metrics_collector: MetricsCollector instance to use
        """
        self.metrics = metrics_collector
        self.logger = get_logger(self.__class__.__name__)
        
        # Monitoring task
        self._monitoring_task: Optional[asyncio.Task] = None
        self._monitoring_interval = 60  # 1 minute
        
        self.logger.info("System metrics collector initialized")
    
    async def start_monitoring(self, interval_seconds: int = 60):
        """Start continuous system monitoring.
        
        Args:
            interval_seconds: Monitoring interval in seconds
        """
        self._monitoring_interval = interval_seconds
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
        
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        self.logger.info("System monitoring started", interval=interval_seconds)
    
    async def stop_monitoring(self):
        """Stop system monitoring."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("System monitoring stopped")
    
    def collect_system_metrics(self):
        """Collect current system metrics."""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            self.metrics.set_gauge("system.cpu.percent", cpu_percent)
            self.metrics.set_gauge("system.cpu.count", cpu_count)
            
            # Memory metrics
            memory = psutil.virtual_memory()
            self.metrics.set_gauge("system.memory.total", memory.total)
            self.metrics.set_gauge("system.memory.available", memory.available)
            self.metrics.set_gauge("system.memory.percent", memory.percent)
            self.metrics.set_gauge("system.memory.used", memory.used)
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            self.metrics.set_gauge("system.disk.total", disk.total)
            self.metrics.set_gauge("system.disk.used", disk.used)
            self.metrics.set_gauge("system.disk.free", disk.free)
            self.metrics.set_gauge("system.disk.percent", (disk.used / disk.total) * 100)
            
            # Network metrics (if available)
            try:
                network = psutil.net_io_counters()
                self.metrics.set_gauge("system.network.bytes_sent", network.bytes_sent)
                self.metrics.set_gauge("system.network.bytes_recv", network.bytes_recv)
                self.metrics.set_gauge("system.network.packets_sent", network.packets_sent)
                self.metrics.set_gauge("system.network.packets_recv", network.packets_recv)
            except Exception:
                pass  # Network metrics might not be available
            
            # Process-specific metrics
            process = psutil.Process()
            process_memory = process.memory_info()
            
            self.metrics.set_gauge("process.memory.rss", process_memory.rss)
            self.metrics.set_gauge("process.memory.vms", process_memory.vms)
            self.metrics.set_gauge("process.cpu.percent", process.cpu_percent())
            self.metrics.set_gauge("process.threads", process.num_threads())
            
            # File descriptors (Unix only)
            try:
                self.metrics.set_gauge("process.file_descriptors", process.num_fds())
            except (AttributeError, OSError):
                pass  # Not available on all platforms
            
        except Exception as e:
            self.logger.warning("Failed to collect system metrics", error=str(e))
    
    async def _monitoring_loop(self):
        """Background monitoring loop."""
        while True:
            try:
                self.collect_system_metrics()
                await asyncio.sleep(self._monitoring_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.warning("Error in monitoring loop", error=str(e))
                await asyncio.sleep(self._monitoring_interval)


# Global metrics collector instance
_global_metrics_collector: Optional[MetricsCollector] = None
_global_system_metrics: Optional[SystemMetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance.
    
    Returns:
        Global MetricsCollector instance
    """
    global _global_metrics_collector
    
    if _global_metrics_collector is None:
        _global_metrics_collector = MetricsCollector()
    
    return _global_metrics_collector


def get_system_metrics_collector() -> SystemMetricsCollector:
    """Get the global system metrics collector instance.
    
    Returns:
        Global SystemMetricsCollector instance
    """
    global _global_system_metrics, _global_metrics_collector
    
    if _global_system_metrics is None:
        if _global_metrics_collector is None:
            _global_metrics_collector = MetricsCollector()
        _global_system_metrics = SystemMetricsCollector(_global_metrics_collector)
    
    return _global_system_metrics


async def stop_all_metrics():
    """Stop all global metrics collectors."""
    global _global_metrics_collector, _global_system_metrics
    
    if _global_system_metrics:
        await _global_system_metrics.stop_monitoring()
    
    if _global_metrics_collector:
        await _global_metrics_collector.stop()
    
    _global_metrics_collector = None
    _global_system_metrics = None