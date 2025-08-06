"""Async optimization utilities for improved performance."""

import asyncio
from typing import List, Callable, Any, Optional, Dict, TypeVar, Generic, Union, Awaitable
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from functools import wraps
from contextlib import asynccontextmanager

from ..utils.logging import get_logger


T = TypeVar('T')
R = TypeVar('R')


class AsyncRateLimiter:
    """Rate limiter for async operations."""
    
    def __init__(self, max_calls: int, time_window: float):
        """Initialize rate limiter.
        
        Args:
            max_calls: Maximum number of calls in the time window
            time_window: Time window in seconds
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []
        self.lock = asyncio.Lock()
        
        self.logger = get_logger(f"{self.__class__.__name__}")
    
    async def acquire(self):
        """Acquire permission to make a call."""
        async with self.lock:
            now = time.time()
            
            # Remove calls outside the time window
            self.calls = [call_time for call_time in self.calls if now - call_time < self.time_window]
            
            # Check if we're at the limit
            if len(self.calls) >= self.max_calls:
                # Calculate wait time
                oldest_call = min(self.calls)
                wait_time = self.time_window - (now - oldest_call)
                
                if wait_time > 0:
                    self.logger.debug(f"Rate limit reached, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                    return await self.acquire()  # Recursive call after waiting
            
            # Add current call
            self.calls.append(now)
    
    @asynccontextmanager
    async def limit(self):
        """Context manager for rate limiting."""
        await self.acquire()
        yield


class AsyncSemaphorePool:
    """Pool of semaphores for different resource types."""
    
    def __init__(self):
        """Initialize semaphore pool."""
        self.semaphores: Dict[str, asyncio.Semaphore] = {}
        self.logger = get_logger(self.__class__.__name__)
    
    def get_semaphore(self, name: str, limit: int) -> asyncio.Semaphore:
        """Get or create a semaphore for the given name.
        
        Args:
            name: Semaphore name/identifier
            limit: Maximum concurrent operations
            
        Returns:
            Asyncio semaphore
        """
        if name not in self.semaphores:
            self.semaphores[name] = asyncio.Semaphore(limit)
            self.logger.debug(f"Created semaphore '{name}' with limit {limit}")
        
        return self.semaphores[name]
    
    @asynccontextmanager
    async def acquire(self, name: str, limit: int):
        """Acquire semaphore for the given resource.
        
        Args:
            name: Resource name
            limit: Maximum concurrent operations
        """
        semaphore = self.get_semaphore(name, limit)
        async with semaphore:
            yield


class ConcurrentExecutor:
    """Executor for running concurrent async operations with optimization."""
    
    def __init__(
        self,
        max_concurrent: int = 10,
        rate_limit_calls: Optional[int] = None,
        rate_limit_window: Optional[float] = None
    ):
        """Initialize concurrent executor.
        
        Args:
            max_concurrent: Maximum concurrent operations
            rate_limit_calls: Rate limit - max calls per window
            rate_limit_window: Rate limit - time window in seconds
        """
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        self.rate_limiter = None
        if rate_limit_calls and rate_limit_window:
            self.rate_limiter = AsyncRateLimiter(rate_limit_calls, rate_limit_window)
        
        self.logger = get_logger(self.__class__.__name__)
        
        self.logger.info(
            "Concurrent executor initialized",
            max_concurrent=max_concurrent,
            rate_limited=self.rate_limiter is not None
        )
    
    async def execute_batch(
        self,
        tasks: List[Callable[[], Awaitable[T]]],
        return_exceptions: bool = False
    ) -> List[Union[T, Exception]]:
        """Execute a batch of async tasks concurrently.
        
        Args:
            tasks: List of async callables
            return_exceptions: Whether to return exceptions instead of raising
            
        Returns:
            List of results
        """
        async def execute_single(task_func):
            async with self.semaphore:
                if self.rate_limiter:
                    async with self.rate_limiter.limit():
                        return await task_func()
                else:
                    return await task_func()
        
        # Create coroutines for all tasks
        coroutines = [execute_single(task) for task in tasks]
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*coroutines, return_exceptions=return_exceptions)
        
        self.logger.debug(
            "Batch execution completed",
            total_tasks=len(tasks),
            successful=len([r for r in results if not isinstance(r, Exception)])
        )
        
        return results
    
    async def execute_with_retries(
        self,
        task_func: Callable[[], Awaitable[T]],
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        exceptions_to_retry: Optional[List[type]] = None
    ) -> T:
        """Execute a task with retry logic.
        
        Args:
            task_func: Async callable to execute
            max_retries: Maximum number of retries
            backoff_factor: Backoff multiplier for delays
            exceptions_to_retry: List of exception types to retry on
            
        Returns:
            Task result
        """
        exceptions_to_retry = exceptions_to_retry or [Exception]
        
        for attempt in range(max_retries + 1):
            try:
                async with self.semaphore:
                    if self.rate_limiter:
                        async with self.rate_limiter.limit():
                            return await task_func()
                    else:
                        return await task_func()
            
            except Exception as e:
                if attempt == max_retries:
                    self.logger.error(
                        "Task failed after all retries",
                        attempts=attempt + 1,
                        error=str(e)
                    )
                    raise
                
                # Check if we should retry this exception
                should_retry = any(isinstance(e, exc_type) for exc_type in exceptions_to_retry)
                
                if not should_retry:
                    self.logger.error("Task failed with non-retryable error", error=str(e))
                    raise
                
                # Calculate backoff delay
                delay = backoff_factor * (2 ** attempt)
                
                self.logger.warning(
                    "Task failed, retrying",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    delay=delay,
                    error=str(e)
                )
                
                await asyncio.sleep(delay)
        
        # This should never be reached
        raise RuntimeError("Unexpected end of retry loop")


class AsyncCircuitBreaker:
    """Circuit breaker pattern for async operations."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: float = 60.0,
        success_threshold: int = 3
    ):
        """Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            timeout_seconds: Timeout before attempting to close circuit
            success_threshold: Number of successes needed to close circuit
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.success_threshold = success_threshold
        
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
        self.lock = asyncio.Lock()
        self.logger = get_logger(self.__class__.__name__)
    
    async def call(self, func: Callable[[], Awaitable[T]]) -> T:
        """Call function through circuit breaker.
        
        Args:
            func: Async function to call
            
        Returns:
            Function result
        """
        async with self.lock:
            # Check if circuit should transition from OPEN to HALF_OPEN
            if self.state == "OPEN":
                if (time.time() - self.last_failure_time) > self.timeout_seconds:
                    self.state = "HALF_OPEN"
                    self.success_count = 0
                    self.logger.info("Circuit breaker transitioning to HALF_OPEN")
                else:
                    raise Exception(f"Circuit breaker is OPEN (failure count: {self.failure_count})")
        
        try:
            result = await func()
            
            async with self.lock:
                # Success handling
                if self.state == "HALF_OPEN":
                    self.success_count += 1
                    if self.success_count >= self.success_threshold:
                        self.state = "CLOSED"
                        self.failure_count = 0
                        self.logger.info("Circuit breaker closed after successful recovery")
                elif self.state == "CLOSED":
                    self.failure_count = 0  # Reset failure count on success
            
            return result
        
        except Exception as e:
            async with self.lock:
                # Failure handling
                self.failure_count += 1
                self.last_failure_time = time.time()
                
                if self.state == "CLOSED" and self.failure_count >= self.failure_threshold:
                    self.state = "OPEN"
                    self.logger.warning(
                        "Circuit breaker opened due to failures",
                        failure_count=self.failure_count
                    )
                elif self.state == "HALF_OPEN":
                    self.state = "OPEN"
                    self.logger.warning("Circuit breaker reopened during recovery")
            
            raise


def async_cache(ttl_seconds: float = 300):
    """Decorator for caching async function results.
    
    Args:
        ttl_seconds: Time to live for cached results
    """
    def decorator(func):
        cache = {}
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Create cache key
            key = str(args) + str(sorted(kwargs.items()))
            
            # Check cache
            if key in cache:
                result, timestamp = cache[key]
                if time.time() - timestamp < ttl_seconds:
                    return result
                else:
                    del cache[key]
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            cache[key] = (result, time.time())
            
            return result
        
        return wrapper
    
    return decorator


class AsyncPool:
    """Pool for managing reusable async resources."""
    
    def __init__(self, create_func: Callable[[], Awaitable[T]], max_size: int = 10):
        """Initialize async pool.
        
        Args:
            create_func: Function to create new resources
            max_size: Maximum pool size
        """
        self.create_func = create_func
        self.max_size = max_size
        self.pool: asyncio.Queue = asyncio.Queue(maxsize=max_size)
        self.created_count = 0
        
        self.logger = get_logger(self.__class__.__name__)
    
    async def acquire(self) -> T:
        """Acquire a resource from the pool."""
        try:
            # Try to get from pool immediately
            resource = self.pool.get_nowait()
            return resource
        except asyncio.QueueEmpty:
            # Create new resource if under limit
            if self.created_count < self.max_size:
                self.created_count += 1
                resource = await self.create_func()
                self.logger.debug(f"Created new resource (total: {self.created_count})")
                return resource
            else:
                # Wait for resource to become available
                return await self.pool.get()
    
    async def release(self, resource: T):
        """Release a resource back to the pool."""
        try:
            self.pool.put_nowait(resource)
        except asyncio.QueueFull:
            # Pool is full, discard resource
            pass
    
    @asynccontextmanager
    async def get_resource(self):
        """Context manager for acquiring and releasing resources."""
        resource = await self.acquire()
        try:
            yield resource
        finally:
            await self.release(resource)
    
    def stats(self) -> Dict[str, Any]:
        """Get pool statistics."""
        return {
            "created_count": self.created_count,
            "max_size": self.max_size,
            "available_count": self.pool.qsize(),
            "in_use_count": self.created_count - self.pool.qsize()
        }


# Global instances
_global_semaphore_pool: Optional[AsyncSemaphorePool] = None
_global_executor: Optional[ConcurrentExecutor] = None


def get_semaphore_pool() -> AsyncSemaphorePool:
    """Get global semaphore pool."""
    global _global_semaphore_pool
    
    if _global_semaphore_pool is None:
        _global_semaphore_pool = AsyncSemaphorePool()
    
    return _global_semaphore_pool


def get_concurrent_executor(
    max_concurrent: int = 10,
    rate_limit_calls: Optional[int] = None,
    rate_limit_window: Optional[float] = None
) -> ConcurrentExecutor:
    """Get global concurrent executor."""
    global _global_executor
    
    if _global_executor is None:
        _global_executor = ConcurrentExecutor(
            max_concurrent=max_concurrent,
            rate_limit_calls=rate_limit_calls,
            rate_limit_window=rate_limit_window
        )
    
    return _global_executor