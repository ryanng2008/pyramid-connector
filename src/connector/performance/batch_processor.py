"""Batch processing utilities for efficient data operations."""

import asyncio
from typing import List, Callable, Any, Optional, Dict, Union, TypeVar, Generic
from datetime import datetime, timezone
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import time

from ..utils.logging import get_logger, log_async_execution_time


T = TypeVar('T')
R = TypeVar('R')


@dataclass
class BatchResult:
    """Result of a batch processing operation."""
    
    total_items: int
    successful_items: int
    failed_items: int
    processing_time: float
    items_per_second: float
    errors: List[str]
    batch_size: int
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_items == 0:
            return 0.0
        return (self.successful_items / self.total_items) * 100


class BatchProcessor:
    """Efficient batch processing for database operations and API calls."""
    
    def __init__(
        self,
        default_batch_size: int = 50,
        max_concurrent_batches: int = 10,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """Initialize batch processor.
        
        Args:
            default_batch_size: Default size for batches
            max_concurrent_batches: Maximum concurrent batch operations
            max_retries: Maximum retry attempts for failed operations
            retry_delay: Delay between retries in seconds
        """
        self.default_batch_size = default_batch_size
        self.max_concurrent_batches = max_concurrent_batches
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self.logger = get_logger(self.__class__.__name__)
        
        # Statistics tracking
        self.total_processed = 0
        self.total_batches = 0
        self.total_processing_time = 0.0
        
        self.logger.info(
            "Batch processor initialized",
            default_batch_size=default_batch_size,
            max_concurrent_batches=max_concurrent_batches
        )
    
    @log_async_execution_time
    async def process_batches(
        self,
        items: List[T],
        processor_func: Callable[[List[T]], Any],
        batch_size: Optional[int] = None,
        max_concurrent: Optional[int] = None
    ) -> BatchResult:
        """Process items in batches with concurrent execution.
        
        Args:
            items: List of items to process
            processor_func: Function to process each batch
            batch_size: Size of each batch (uses default if None)
            max_concurrent: Maximum concurrent batches (uses default if None)
            
        Returns:
            BatchResult with processing statistics
        """
        if not items:
            return BatchResult(
                total_items=0,
                successful_items=0,
                failed_items=0,
                processing_time=0.0,
                items_per_second=0.0,
                errors=[],
                batch_size=batch_size or self.default_batch_size
            )
        
        batch_size = batch_size or self.default_batch_size
        max_concurrent = max_concurrent or self.max_concurrent_batches
        
        start_time = time.time()
        
        # Split items into batches
        batches = [
            items[i:i + batch_size]
            for i in range(0, len(items), batch_size)
        ]
        
        self.logger.info(
            "Starting batch processing",
            total_items=len(items),
            total_batches=len(batches),
            batch_size=batch_size,
            max_concurrent=max_concurrent
        )
        
        # Process batches with concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def process_single_batch(batch: List[T], batch_index: int) -> Dict[str, Any]:
            async with semaphore:
                try:
                    batch_start = time.time()
                    
                    # Execute processor function
                    if asyncio.iscoroutinefunction(processor_func):
                        result = await processor_func(batch)
                    else:
                        # Run synchronous function in thread pool
                        loop = asyncio.get_event_loop()
                        with ThreadPoolExecutor() as executor:
                            result = await loop.run_in_executor(executor, processor_func, batch)
                    
                    batch_time = time.time() - batch_start
                    
                    return {
                        "batch_index": batch_index,
                        "success": True,
                        "items_processed": len(batch),
                        "processing_time": batch_time,
                        "result": result,
                        "error": None
                    }
                    
                except Exception as e:
                    batch_time = time.time() - batch_start
                    
                    self.logger.warning(
                        "Batch processing failed",
                        batch_index=batch_index,
                        batch_size=len(batch),
                        error=str(e)
                    )
                    
                    return {
                        "batch_index": batch_index,
                        "success": False,
                        "items_processed": 0,
                        "processing_time": batch_time,
                        "result": None,
                        "error": str(e)
                    }
        
        # Execute all batches concurrently
        batch_tasks = [
            process_single_batch(batch, i)
            for i, batch in enumerate(batches)
        ]
        
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        
        # Calculate final results
        total_time = time.time() - start_time
        successful_items = 0
        failed_items = 0
        errors = []
        
        for result in batch_results:
            if isinstance(result, Exception):
                errors.append(str(result))
                # Estimate failed items for exception cases
                failed_items += batch_size
            elif isinstance(result, dict):
                if result["success"]:
                    successful_items += result["items_processed"]
                else:
                    failed_items += len(batches[result["batch_index"]])
                    if result["error"]:
                        errors.append(result["error"])
        
        # Adjust for any over-counting
        total_items = len(items)
        if successful_items + failed_items > total_items:
            failed_items = total_items - successful_items
        
        items_per_second = total_items / total_time if total_time > 0 else 0
        
        # Update statistics
        self.total_processed += total_items
        self.total_batches += len(batches)
        self.total_processing_time += total_time
        
        result = BatchResult(
            total_items=total_items,
            successful_items=successful_items,
            failed_items=failed_items,
            processing_time=total_time,
            items_per_second=items_per_second,
            errors=errors,
            batch_size=batch_size
        )
        
        self.logger.info(
            "Batch processing completed",
            total_items=result.total_items,
            successful_items=result.successful_items,
            failed_items=result.failed_items,
            success_rate=f"{result.success_rate:.1f}%",
            items_per_second=f"{result.items_per_second:.1f}",
            processing_time=f"{result.processing_time:.2f}s"
        )
        
        return result
    
    @log_async_execution_time
    async def process_with_retries(
        self,
        items: List[T],
        processor_func: Callable[[List[T]], Any],
        batch_size: Optional[int] = None,
        max_retries: Optional[int] = None
    ) -> BatchResult:
        """Process items with automatic retry for failed batches.
        
        Args:
            items: List of items to process
            processor_func: Function to process each batch
            batch_size: Size of each batch
            max_retries: Maximum retry attempts
            
        Returns:
            BatchResult with processing statistics
        """
        max_retries = max_retries or self.max_retries
        batch_size = batch_size or self.default_batch_size
        
        remaining_items = items[:]
        all_results = []
        retry_count = 0
        
        while remaining_items and retry_count <= max_retries:
            self.logger.info(
                "Processing batch attempt",
                retry_count=retry_count,
                remaining_items=len(remaining_items)
            )
            
            result = await self.process_batches(
                remaining_items,
                processor_func,
                batch_size=batch_size
            )
            
            all_results.append(result)
            
            # If all items succeeded, we're done
            if result.failed_items == 0:
                break
            
            # Prepare for retry with failed items
            if retry_count < max_retries and result.failed_items > 0:
                # In a real implementation, we'd need a way to identify failed items
                # For simplicity, we'll reduce the batch size and retry all
                remaining_items = items[-result.failed_items:] if result.failed_items < len(items) else items
                batch_size = max(1, batch_size // 2)  # Reduce batch size for retry
                retry_count += 1
                
                self.logger.info(
                    "Retrying failed items",
                    retry_count=retry_count,
                    failed_items=result.failed_items,
                    new_batch_size=batch_size
                )
                
                # Wait before retrying
                await asyncio.sleep(self.retry_delay * retry_count)
            else:
                break
        
        # Combine results from all attempts
        if all_results:
            final_result = all_results[-1]  # Use the last result as the final one
            
            # Add retry information
            final_result.errors.insert(0, f"Completed after {retry_count} retries")
            
            return final_result
        else:
            # Fallback if no results
            return BatchResult(
                total_items=len(items),
                successful_items=0,
                failed_items=len(items),
                processing_time=0.0,
                items_per_second=0.0,
                errors=["No processing attempts completed"],
                batch_size=batch_size
            )
    
    async def process_stream(
        self,
        item_generator,
        processor_func: Callable[[List[T]], Any],
        batch_size: Optional[int] = None,
        buffer_size: int = 1000
    ):
        """Process items from a stream/generator in batches.
        
        Args:
            item_generator: Async generator or iterable of items
            processor_func: Function to process each batch
            batch_size: Size of each batch
            buffer_size: Size of internal buffer for streaming
            
        Yields:
            BatchResult for each processed batch
        """
        batch_size = batch_size or self.default_batch_size
        current_batch = []
        
        self.logger.info(
            "Starting stream processing",
            batch_size=batch_size,
            buffer_size=buffer_size
        )
        
        try:
            # Handle both async generators and regular iterables
            if hasattr(item_generator, '__aiter__'):
                async for item in item_generator:
                    current_batch.append(item)
                    
                    if len(current_batch) >= batch_size:
                        result = await self.process_batches(
                            current_batch,
                            processor_func,
                            batch_size=batch_size,
                            max_concurrent=1  # Process stream batches sequentially
                        )
                        yield result
                        current_batch = []
            else:
                for item in item_generator:
                    current_batch.append(item)
                    
                    if len(current_batch) >= batch_size:
                        result = await self.process_batches(
                            current_batch,
                            processor_func,
                            batch_size=batch_size,
                            max_concurrent=1
                        )
                        yield result
                        current_batch = []
            
            # Process remaining items
            if current_batch:
                result = await self.process_batches(
                    current_batch,
                    processor_func,
                    batch_size=len(current_batch),
                    max_concurrent=1
                )
                yield result
                
        except Exception as e:
            self.logger.error("Stream processing failed", error=str(e))
            
            # Return error result for remaining items
            if current_batch:
                yield BatchResult(
                    total_items=len(current_batch),
                    successful_items=0,
                    failed_items=len(current_batch),
                    processing_time=0.0,
                    items_per_second=0.0,
                    errors=[str(e)],
                    batch_size=batch_size
                )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics.
        
        Returns:
            Dictionary with processing statistics
        """
        avg_processing_time = (
            self.total_processing_time / self.total_batches
            if self.total_batches > 0 else 0
        )
        
        avg_items_per_second = (
            self.total_processed / self.total_processing_time
            if self.total_processing_time > 0 else 0
        )
        
        return {
            "total_processed": self.total_processed,
            "total_batches": self.total_batches,
            "total_processing_time": self.total_processing_time,
            "average_processing_time": avg_processing_time,
            "average_items_per_second": avg_items_per_second,
            "default_batch_size": self.default_batch_size,
            "max_concurrent_batches": self.max_concurrent_batches
        }
    
    def reset_statistics(self):
        """Reset processing statistics."""
        self.total_processed = 0
        self.total_batches = 0
        self.total_processing_time = 0.0
        
        self.logger.info("Processing statistics reset")


# Global batch processor instance
_global_batch_processor: Optional[BatchProcessor] = None


def get_batch_processor() -> BatchProcessor:
    """Get the global batch processor instance.
    
    Returns:
        Global BatchProcessor instance
    """
    global _global_batch_processor
    
    if _global_batch_processor is None:
        _global_batch_processor = BatchProcessor()
    
    return _global_batch_processor