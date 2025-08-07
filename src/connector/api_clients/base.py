"""Base API client interface and common functionality."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime
from dataclasses import dataclass

from ..utils.logging import get_logger


@dataclass
class FileMetadata:
    """Standard file metadata structure across all API clients."""
    
    external_file_id: str
    file_name: str
    file_path: Optional[str] = None
    file_link: str = ""
    file_size: Optional[int] = None
    file_type: Optional[str] = None
    external_created_at: Optional[datetime] = None
    external_updated_at: Optional[datetime] = None
    file_metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "external_file_id": self.external_file_id,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "file_link": self.file_link,
            "file_size": self.file_size,
            "file_type": self.file_type,
            "external_created_at": self.external_created_at,
            "external_updated_at": self.external_updated_at,
            "file_metadata": self.file_metadata or {}
        }


class BaseAPIClient(ABC):
    """Abstract base class for all API clients."""
    
    def __init__(self, endpoint_details: Dict[str, Any], **kwargs):
        """Initialize the API client.
        
        Args:
            endpoint_details: Configuration specific to this endpoint
            **kwargs: Additional configuration parameters
        """
        self.endpoint_details = endpoint_details
        self.logger = get_logger(self.__class__.__name__)
        self._authenticated = False
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the API service.
        
        Returns:
            True if authentication successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def list_files(
        self,
        since: Optional[datetime] = None,
        max_results: Optional[int] = None
    ) -> AsyncGenerator[FileMetadata, None]:
        """List files from the API service.
        
        Args:
            since: Only return files modified after this datetime
            max_results: Maximum number of files to return
            
        Yields:
            FileMetadata objects for each file found
        """
        pass
    
    @abstractmethod
    async def get_file_metadata(self, file_id: str) -> Optional[FileMetadata]:
        """Get detailed metadata for a specific file.
        
        Args:
            file_id: External file ID
            
        Returns:
            FileMetadata object or None if file not found
        """
        pass
    
    async def health_check(self) -> bool:
        """Check if the API service is accessible.
        
        Returns:
            True if service is healthy, False otherwise
        """
        try:
            if not self._authenticated:
                authenticated = await self.authenticate()
                if not authenticated:
                    return False
            
            # Try to list a small number of files as a health check
            file_count = 0
            file_iterator = await self.list_files(max_results=1)
            async for _ in file_iterator:
                file_count += 1
                break
            
            self.logger.info("API health check passed", client=self.__class__.__name__)
            return True
            
        except Exception as e:
            self.logger.error(
                "API health check failed",
                client=self.__class__.__name__,
                error=str(e)
            )
            return False
    
    async def get_sync_info(self) -> Dict[str, Any]:
        """Get information about the sync endpoint.
        
        Returns:
            Dictionary with sync endpoint information
        """
        return {
            "client_type": self.__class__.__name__,
            "endpoint_details": self.endpoint_details,
            "authenticated": self._authenticated
        }


class RateLimitError(Exception):
    """Raised when API rate limit is exceeded."""
    
    def __init__(self, message: str, retry_after: Optional[int] = None):
        super().__init__(message)
        self.retry_after = retry_after


class AuthenticationError(Exception):
    """Raised when API authentication fails."""
    pass


class APIConnectionError(Exception):
    """Raised when API connection fails."""
    pass