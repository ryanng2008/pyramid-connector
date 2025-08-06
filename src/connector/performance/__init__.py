"""Performance optimization package."""

from .connection_pool import (
    ConnectionPoolManager,
    get_connection_pool_manager,
    close_global_pools
)
from .batch_processor import (
    BatchProcessor,
    BatchResult,
    get_batch_processor
)
from .metrics import (
    MetricsCollector,
    SystemMetricsCollector,
    PerformanceStats,
    MetricPoint,
    get_metrics_collector,
    get_system_metrics_collector,
    stop_all_metrics
)
from .async_optimizer import (
    AsyncRateLimiter,
    AsyncSemaphorePool,
    ConcurrentExecutor,
    AsyncCircuitBreaker,
    AsyncPool,
    async_cache,
    get_semaphore_pool,
    get_concurrent_executor
)

__all__ = [
    # Connection pool
    "ConnectionPoolManager",
    "get_connection_pool_manager",
    "close_global_pools",
    
    # Batch processing
    "BatchProcessor",
    "BatchResult",
    "get_batch_processor",
    
    # Metrics
    "MetricsCollector",
    "SystemMetricsCollector",
    "PerformanceStats",
    "MetricPoint",
    "get_metrics_collector",
    "get_system_metrics_collector",
    "stop_all_metrics",
    
    # Async optimization
    "AsyncRateLimiter",
    "AsyncSemaphorePool",
    "ConcurrentExecutor",
    "AsyncCircuitBreaker",
    "AsyncPool",
    "async_cache",
    "get_semaphore_pool",
    "get_concurrent_executor",
]