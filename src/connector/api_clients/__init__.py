"""API clients package for external service integrations."""

from .base import (
    BaseAPIClient,
    FileMetadata,
    RateLimitError,
    AuthenticationError,
    APIConnectionError
)

from .google_drive import GoogleDriveClient
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
    
    # Factory
    "APIClientFactory"
]
