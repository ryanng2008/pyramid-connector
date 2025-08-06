"""Tests for performance optimization components."""

import asyncio
import pytest
import time
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from connector.performance import (
    ConnectionPoolManager,
    BatchProcessor,
    BatchResult,
    MetricsCollector,
    SystemMetricsCollector,
    AsyncRateLimiter,
    ConcurrentExecutor,
    AsyncCircuitBreaker,
    AsyncPool,
    async_cache
)


class TestConnectionPoolManager:
    """Test connection pool management."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.pool_manager = ConnectionPoolManager(
            max_connections=10,
            max_connections_per_host=5,
            timeout_seconds=5
        )
    
    async def teardown_method(self):
        """Clean up after tests."""
        await self.pool_manager.close_all_pools()
    
    @pytest.mark.asyncio
    async def test_get_session(self):
        """Test getting sessions from pool."""
        session1 = await self.pool_manager.get_session("test_service")
        session2 = await self.pool_manager.get_session("test_service")
        
        # Should return the same session for same service
        assert session1 is session2
        assert not session1.closed
    
    @pytest.mark.asyncio
    async def test_pool_stats(self):
        """Test pool statistics collection."""
        # Get session to create a pool
        await self.pool_manager.get_session("test_service")
        
        stats = self.pool_manager.get_pool_stats()
        
        assert "test_service" in stats
        assert stats["test_service"]["request_count"] >= 1
        assert stats["test_service"]["is_active"] is True
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check functionality."""
        # Create a pool
        await self.pool_manager.get_session("test_service")
        
        health = await self.pool_manager.health_check()
        
        assert health["status"] in ["healthy", "degraded"]
        assert health["total_pools"] >= 1
        assert "test_service" in health["pools"]


class TestBatchProcessor:
    """Test batch processing functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.processor = BatchProcessor(
            default_batch_size=3,
            max_concurrent_batches=2
        )
    
    @pytest.mark.asyncio
    async def test_process_batches_sync(self):
        """Test batch processing with synchronous function."""
        def multiply_by_two(items):
            return [item * 2 for item in items]
        
        items = [1, 2, 3, 4, 5, 6, 7]
        result = await self.processor.process_batches(items, multiply_by_two, batch_size=3)
        
        assert isinstance(result, BatchResult)
        assert result.total_items == len(items)
        assert result.successful_items == len(items)
        assert result.failed_items == 0
        assert result.success_rate == 100.0
        assert result.batch_size == 3
    
    @pytest.mark.asyncio
    async def test_process_batches_async(self):
        """Test batch processing with async function."""
        async def async_multiply(items):
            await asyncio.sleep(0.01)  # Simulate async work
            return [item * 3 for item in items]
        
        items = [1, 2, 3, 4, 5]
        result = await self.processor.process_batches(items, async_multiply, batch_size=2)
        
        assert result.total_items == len(items)
        assert result.successful_items == len(items)
        assert result.processing_time > 0
        assert result.items_per_second > 0
    
    @pytest.mark.asyncio
    async def test_process_with_retries(self):
        """Test batch processing with retry logic."""
        call_count = 0
        
        def failing_function(items):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("First attempt fails")
            return [item for item in items]
        
        items = [1, 2, 3]
        result = await self.processor.process_with_retries(
            items, failing_function, max_retries=2
        )
        
        assert result.total_items == len(items)
        assert call_count >= 1  # Should have retried
    
    @pytest.mark.asyncio
    async def test_process_stream(self):
        """Test stream processing."""
        async def async_generator():
            for i in range(5):
                yield i
                await asyncio.sleep(0.001)
        
        def process_batch(items):
            return [item * 2 for item in items]
        
        results = []
        async for batch_result in self.processor.process_stream(
            async_generator(), process_batch, batch_size=2
        ):
            results.append(batch_result)
        
        assert len(results) >= 1  # Should have at least one batch
        total_processed = sum(r.successful_items for r in results)
        assert total_processed == 5


class TestMetricsCollector:
    """Test metrics collection functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.metrics = MetricsCollector(max_points_per_metric=100, retention_hours=1)
    
    async def teardown_method(self):
        """Clean up after tests."""
        await self.metrics.stop()
    
    def test_record_timing(self):
        """Test timing metric recording."""
        self.metrics.record_timing("test.timing", 1.5, {"operation": "test"})
        
        stats = self.metrics.get_stats("test.timing")
        assert stats is not None
        assert stats.count == 1
        assert stats.mean == 1.5
        assert stats.min_value == 1.5
        assert stats.max_value == 1.5
    
    def test_record_value(self):
        """Test value metric recording."""
        values = [10, 20, 30, 40, 50]
        for value in values:
            self.metrics.record_value("test.value", value)
        
        stats = self.metrics.get_stats("test.value")
        assert stats.count == len(values)
        assert stats.mean == 30.0
        assert stats.min_value == 10
        assert stats.max_value == 50
    
    def test_counters_and_gauges(self):
        """Test counter and gauge metrics."""
        self.metrics.increment_counter("test.counter", 5)
        self.metrics.increment_counter("test.counter", 3)
        self.metrics.set_gauge("test.gauge", 42.5)
        
        all_metrics = self.metrics.get_all_metrics()
        
        assert all_metrics["counters"]["test.counter"] == 8
        assert all_metrics["gauges"]["test.gauge"] == 42.5
    
    @pytest.mark.asyncio
    async def test_time_operation_context(self):
        """Test timing context manager."""
        async with self.metrics.time_operation("test.context", {"type": "async"}):
            await asyncio.sleep(0.01)
        
        stats = self.metrics.get_stats("test.context")
        assert stats is not None
        assert stats.count == 1
        assert stats.mean >= 0.01


class TestAsyncOptimizers:
    """Test async optimization utilities."""
    
    @pytest.mark.asyncio
    async def test_rate_limiter(self):
        """Test async rate limiter."""
        limiter = AsyncRateLimiter(max_calls=3, time_window=1.0)
        
        start_time = time.time()
        
        # First 3 calls should be immediate
        for _ in range(3):
            await limiter.acquire()
        
        # 4th call should be delayed
        await limiter.acquire()
        
        elapsed = time.time() - start_time
        assert elapsed >= 0.5  # Should have some delay
    
    @pytest.mark.asyncio
    async def test_concurrent_executor(self):
        """Test concurrent executor."""
        executor = ConcurrentExecutor(max_concurrent=2)
        
        async def slow_task():
            await asyncio.sleep(0.05)
            return "completed"
        
        tasks = [slow_task for _ in range(4)]
        
        start_time = time.time()
        results = await executor.execute_batch(tasks)
        elapsed = time.time() - start_time
        
        assert len(results) == 4
        assert all(r == "completed" for r in results)
        # Should take roughly 2 * 0.05 = 0.1s due to concurrency limit
        assert elapsed >= 0.08
    
    @pytest.mark.asyncio
    async def test_circuit_breaker(self):
        """Test circuit breaker pattern."""
        breaker = AsyncCircuitBreaker(failure_threshold=2, timeout_seconds=0.1)
        
        call_count = 0
        
        async def failing_function():
            nonlocal call_count
            call_count += 1
            raise Exception("Always fails")
        
        # First two calls should fail and open the circuit
        with pytest.raises(Exception):
            await breaker.call(failing_function)
        
        with pytest.raises(Exception):
            await breaker.call(failing_function)
        
        # Third call should be blocked by open circuit
        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            await breaker.call(failing_function)
        
        assert call_count == 2  # Third call was blocked
    
    @pytest.mark.asyncio
    async def test_async_pool(self):
        """Test async resource pool."""
        async def create_resource():
            return {"id": time.time()}
        
        pool = AsyncPool(create_resource, max_size=2)
        
        # Test acquiring and releasing resources
        async with pool.get_resource() as resource1:
            async with pool.get_resource() as resource2:
                assert resource1 != resource2
                
                stats = pool.stats()
                assert stats["in_use_count"] == 2
                assert stats["available_count"] == 0
        
        # After context managers exit, resources should be back in pool
        final_stats = pool.stats()
        assert final_stats["in_use_count"] == 0
        assert final_stats["available_count"] == 2
    
    def test_async_cache_decorator(self):
        """Test async cache decorator."""
        call_count = 0
        
        @async_cache(ttl_seconds=1.0)
        async def cached_function(value):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return value * 2
        
        # Test that function is cached
        async def test_caching():
            result1 = await cached_function(5)
            result2 = await cached_function(5)
            
            assert result1 == 10
            assert result2 == 10
            assert call_count == 1  # Function called only once due to caching
        
        asyncio.run(test_caching())


class TestSystemMetrics:
    """Test system metrics collection."""
    
    @pytest.mark.asyncio
    async def test_system_metrics_collection(self):
        """Test collecting system metrics."""
        metrics_collector = MetricsCollector()
        system_metrics = SystemMetricsCollector(metrics_collector)
        
        # Collect metrics once
        system_metrics.collect_system_metrics()
        
        # Check that system metrics were recorded
        all_metrics = metrics_collector.get_all_metrics()
        
        # Should have CPU, memory, and process metrics
        assert "system.cpu.percent" in all_metrics["gauges"]
        assert "system.memory.percent" in all_metrics["gauges"]
        assert "process.memory.rss" in all_metrics["gauges"]
        
        await metrics_collector.stop()
    
    @pytest.mark.asyncio
    async def test_system_monitoring_lifecycle(self):
        """Test system monitoring start/stop."""
        metrics_collector = MetricsCollector()
        system_metrics = SystemMetricsCollector(metrics_collector)
        
        # Start monitoring with short interval
        await system_metrics.start_monitoring(interval_seconds=0.1)
        
        # Wait a bit for monitoring to run
        await asyncio.sleep(0.15)
        
        # Stop monitoring
        await system_metrics.stop_monitoring()
        
        # Verify metrics were collected
        all_metrics = metrics_collector.get_all_metrics()
        assert len(all_metrics["gauges"]) > 0
        
        await metrics_collector.stop()


# Integration test
@pytest.mark.asyncio
async def test_performance_integration():
    """Test integration of performance components."""
    # Initialize components
    metrics = MetricsCollector()
    batch_processor = BatchProcessor(default_batch_size=5)
    executor = ConcurrentExecutor(max_concurrent=3)
    
    # Simulate a workload
    async def process_item(item):
        await asyncio.sleep(0.01)
        metrics.increment_counter("items.processed")
        metrics.record_timing("item.processing_time", 0.01)
        return item * 2
    
    # Process items in batches with concurrent execution
    items = list(range(20))
    
    async def process_batch(batch):
        tasks = [lambda item=item: process_item(item) for item in batch]
        return await executor.execute_batch(tasks)
    
    start_time = time.time()
    result = await batch_processor.process_batches(items, process_batch)
    processing_time = time.time() - start_time
    
    # Verify results
    assert result.total_items == 20
    assert result.successful_items == 20
    assert result.success_rate == 100.0
    assert processing_time < 1.0  # Should be fast due to concurrency
    
    # Verify metrics were collected
    all_metrics = metrics.get_all_metrics()
    assert all_metrics["counters"]["items.processed"] == 20
    
    # Clean up
    await metrics.stop()


if __name__ == "__main__":
    pytest.main([__file__])