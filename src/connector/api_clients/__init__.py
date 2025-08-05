"""API clients package for external service integrations."""

from .base import (
    BaseAPIClient,
    FileMetadata,
    RateLimitError,
    AuthenticationError,
    APIConnectionError
)

from .google_drive import GoogleDriveClient
from .autodesk import AutodeskConstructionCloudClient
from .factory import APIClientFactory

__all__ = [
    # Base classes and exceptions
    "BaseAPIClient",
    "FileMetadata",
    "RateLimitError",
    "AuthenticationError", 
    "APIConnectionError",
    
    # Client implementations
    "GoogleDriveClient",
    "AutodeskConstructionCloudClient",
    
    # Factory
    "APIClientFactory"
]
