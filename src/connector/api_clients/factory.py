"""API client factory for creating appropriate client instances."""

from typing import Dict, Any, Type, List
from ..config.settings import get_settings
from ..database.models import EndpointType
from .base import BaseAPIClient
from .google_drive import GoogleDriveClient
from .autodesk import AutodeskConstructionCloudClient


class APIClientFactory:
    """Factory for creating API client instances."""
    
    _client_classes: Dict[EndpointType, Type[BaseAPIClient]] = {
        EndpointType.GOOGLE_DRIVE: GoogleDriveClient,
        EndpointType.AUTODESK_CONSTRUCTION_CLOUD: AutodeskConstructionCloudClient,
    }
    
    @classmethod
    def create_client(
        self,
        endpoint_type: EndpointType,
        endpoint_details: Dict[str, Any],
        **kwargs
    ) -> BaseAPIClient:
        """Create an API client instance.
        
        Args:
            endpoint_type: Type of endpoint (google_drive, autodesk, etc.)
            endpoint_details: Configuration specific to this endpoint
            **kwargs: Additional parameters
            
        Returns:
            Configured API client instance
            
        Raises:
            ValueError: If endpoint type is not supported
        """
        settings = get_settings()
        
        if endpoint_type not in self._client_classes:
            raise ValueError(f"Unsupported endpoint type: {endpoint_type}")
        
        client_class = self._client_classes[endpoint_type]
        
        # Add type-specific configuration
        if endpoint_type == EndpointType.GOOGLE_DRIVE:
            kwargs.update({
                "credentials_path": settings.google_drive.credentials_path,
                "application_name": settings.google_drive.application_name
            })
        elif endpoint_type == EndpointType.AUTODESK_CONSTRUCTION_CLOUD:
            kwargs.update({
                "client_id": settings.autodesk.client_id,
                "client_secret": settings.autodesk.client_secret,
                "callback_url": settings.autodesk.callback_url,
                "base_url": settings.autodesk.base_url
            })
        
        return client_class(endpoint_details=endpoint_details, **kwargs)
    
    @classmethod
    def get_supported_types(cls) -> List[EndpointType]:
        """Get list of supported endpoint types."""
        return list(cls._client_classes.keys())
    
    @classmethod
    def register_client(cls, endpoint_type: EndpointType, client_class: Type[BaseAPIClient]):
        """Register a new API client type.
        
        Args:
            endpoint_type: Type of endpoint
            client_class: Client class to register
        """
        cls._client_classes[endpoint_type] = client_class