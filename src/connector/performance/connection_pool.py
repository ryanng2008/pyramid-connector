"""Connection pool management for efficient API client connections."""

import asyncio
from typing import Dict, Any, Optional, List, Union
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import aiohttp
from aiohttp import ClientSession, ClientTimeout, TCPConnector, ClientConnectorError

from ..utils.logging import get_logger


class ConnectionPoolManager:
    """Manages connection pools for different API services."""
    
    def __init__(
        self,
        max_connections: int = 100,
        max_connections_per_host: int = 30,
        timeout_seconds: int = 30,
        keepalive_timeout: int = 30,
        enable_cleanup_closed: bool = True
    ):
        """Initialize connection pool manager.
        
        Args:
            max_connections: Maximum total connections across all hosts
            max_connections_per_host: Maximum connections per host
            timeout_seconds: Request timeout in seconds
            keepalive_timeout: Keep-alive timeout for connections
            enable_cleanup_closed: Enable automatic cleanup of closed connections
        """
        self.max_connections = max_connections
        self.max_connections_per_host = max_connections_per_host
        self.timeout_seconds = timeout_seconds
        self.keepalive_timeout = keepalive_timeout
        self.enable_cleanup_closed = enable_cleanup_closed
        
        self.logger = get_logger(self.__class__.__name__)
        
        # Connection pools by service type
        self._pools: Dict[str, ClientSession] = {}
        self._pool_stats: Dict[str, Dict[str, Any]] = {}
        
        # Global session for shared connections
        self._global_session: Optional[ClientSession] = None
        
        self.logger.info(
            "Connection pool manager initialized",
            max_connections=max_connections,
            max_connections_per_host=max_connections_per_host,
            timeout_seconds=timeout_seconds
        )
    
    async def get_session(self, service_type: str = "default") -> ClientSession:
        """Get or create a session for the specified service type.
        
        Args:
            service_type: Service type identifier (e.g., 'google_drive', 'autodesk')
            
        Returns:
            Configured aiohttp ClientSession
        """
        if service_type not in self._pools:
            await self._create_pool(service_type)
        
        session = self._pools[service_type]
        
        # Update usage statistics
        if service_type not in self._pool_stats:
            self._pool_stats[service_type] = {
                "created_at": datetime.now(timezone.utc),
                "request_count": 0,
                "error_count": 0,
                "last_used": None
            }
        
        self._pool_stats[service_type]["request_count"] += 1
        self._pool_stats[service_type]["last_used"] = datetime.now(timezone.utc)
        
        return session
    
    @asynccontextmanager
    async def request(
        self,
        method: str,
        url: str,
        service_type: str = "default",
        **kwargs
    ):
        """Make an HTTP request using the connection pool.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            service_type: Service type for connection pooling
            **kwargs: Additional arguments for the request
            
        Yields:
            aiohttp ClientResponse
        """
        session = await self.get_session(service_type)
        
        try:
            async with session.request(method, url, **kwargs) as response:
                yield response
        except ClientConnectorError as e:
            self._pool_stats[service_type]["error_count"] += 1
            self.logger.warning(
                "Connection error in pool request",
                service_type=service_type,
                error=str(e),
                url=url
            )
            raise
        except Exception as e:
            self._pool_stats[service_type]["error_count"] += 1
            self.logger.error(
                "Request error in pool",
                service_type=service_type,
                error=str(e),
                url=url
            )
            raise
    
    async def _create_pool(self, service_type: str):
        """Create a new connection pool for the service type.
        
        Args:
            service_type: Service type identifier
        """
        # Create connector with connection pooling settings
        connector = TCPConnector(
            limit=self.max_connections,
            limit_per_host=self.max_connections_per_host,
            keepalive_timeout=self.keepalive_timeout,
            enable_cleanup_closed=self.enable_cleanup_closed,
            use_dns_cache=True,
            ttl_dns_cache=300,  # 5 minutes DNS cache
            limit_per_host=self.max_connections_per_host
        )
        
        # Create timeout configuration
        timeout = ClientTimeout(total=self.timeout_seconds)
        
        # Create session
        session = ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                "User-Agent": f"FileConnector/1.0 ({service_type})"
            }
        )
        
        self._pools[service_type] = session
        
        self.logger.info(
            "Created connection pool",
            service_type=service_type,
            max_connections=self.max_connections,
            max_per_host=self.max_connections_per_host
        )
    
    async def close_pool(self, service_type: str):
        """Close a specific connection pool.
        
        Args:
            service_type: Service type identifier
        """
        if service_type in self._pools:
            session = self._pools[service_type]
            await session.close()
            del self._pools[service_type]
            
            self.logger.info("Closed connection pool", service_type=service_type)
    
    async def close_all_pools(self):
        """Close all connection pools."""
        for service_type in list(self._pools.keys()):
            await self.close_pool(service_type)
        
        if self._global_session:
            await self._global_session.close()
            self._global_session = None
        
        self.logger.info("Closed all connection pools")
    
    def get_pool_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all connection pools.
        
        Returns:
            Dictionary of pool statistics by service type
        """
        stats = {}
        
        for service_type, pool_stats in self._pool_stats.items():
            session = self._pools.get(service_type)
            connector_info = {}
            
            if session and hasattr(session.connector, '_conns'):
                # Get connector statistics if available
                try:
                    connector = session.connector
                    connector_info = {
                        "active_connections": len(connector._conns),
                        "acquired_connections": getattr(connector, '_acquired', 0),
                        "pool_size": connector.limit,
                        "per_host_limit": connector.limit_per_host
                    }
                except Exception:
                    # Fallback if connector stats are not accessible
                    connector_info = {
                        "active_connections": "unknown",
                        "pool_size": self.max_connections,
                        "per_host_limit": self.max_connections_per_host
                    }
            
            stats[service_type] = {
                **pool_stats,
                "connector_info": connector_info,
                "is_active": service_type in self._pools
            }
        
        return stats
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on connection pools.
        
        Returns:
            Health check results
        """
        health = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc),
            "total_pools": len(self._pools),
            "pools": {},
            "issues": []
        }
        
        for service_type, session in self._pools.items():
            pool_health = {
                "status": "healthy",
                "session_closed": session.closed,
                "connector_closed": session.connector.closed if session.connector else True
            }
            
            # Check if session or connector is closed
            if session.closed or (session.connector and session.connector.closed):
                pool_health["status"] = "unhealthy"
                health["issues"].append(f"Pool {service_type} has closed connections")
                health["status"] = "degraded"
            
            # Check error rate
            stats = self._pool_stats.get(service_type, {})
            request_count = stats.get("request_count", 0)
            error_count = stats.get("error_count", 0)
            
            if request_count > 0:
                error_rate = error_count / request_count
                pool_health["error_rate"] = error_rate
                
                if error_rate > 0.1:  # More than 10% errors
                    pool_health["status"] = "degraded"
                    health["issues"].append(f"Pool {service_type} has high error rate: {error_rate:.2%}")
                    health["status"] = "degraded"
            
            health["pools"][service_type] = pool_health
        
        return health
    
    async def cleanup_idle_connections(self):
        """Clean up idle connections across all pools."""
        cleaned_count = 0
        
        for service_type, session in self._pools.items():
            if session.connector and hasattr(session.connector, '_cleanup'):
                try:
                    # Trigger connector cleanup
                    await session.connector._cleanup()
                    cleaned_count += 1
                    
                    self.logger.debug(
                        "Cleaned up idle connections",
                        service_type=service_type
                    )
                except Exception as e:
                    self.logger.warning(
                        "Failed to cleanup connections",
                        service_type=service_type,
                        error=str(e)
                    )
        
        self.logger.info("Connection cleanup completed", pools_cleaned=cleaned_count)
        return cleaned_count


# Global connection pool manager instance
_global_pool_manager: Optional[ConnectionPoolManager] = None


def get_connection_pool_manager() -> ConnectionPoolManager:
    """Get the global connection pool manager instance.
    
    Returns:
        Global ConnectionPoolManager instance
    """
    global _global_pool_manager
    
    if _global_pool_manager is None:
        _global_pool_manager = ConnectionPoolManager()
    
    return _global_pool_manager


async def close_global_pools():
    """Close all global connection pools."""
    global _global_pool_manager
    
    if _global_pool_manager:
        await _global_pool_manager.close_all_pools()
        _global_pool_manager = None