"""Autodesk Construction Cloud API client implementation."""

import asyncio
import json
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime, timezone, timedelta
import aiohttp
from urllib.parse import urlencode

from .base import BaseAPIClient, FileMetadata, RateLimitError, AuthenticationError, APIConnectionError
from ..utils.logging import log_async_execution_time
from ..auth.oauth_handler import get_autodesk_token


class AutodeskConstructionCloudClient(BaseAPIClient):
    """Autodesk Construction Cloud API client for file synchronization."""
    
    def __init__(
        self,
        endpoint_details: Dict[str, Any],
        client_id: str,
        client_secret: str,
        callback_url: str,
        base_url: str = "https://developer.api.autodesk.com",
        **kwargs
    ):
        """Initialize Autodesk Construction Cloud client.
        
        Args:
            endpoint_details: Configuration for this endpoint
            client_id: Autodesk app client ID
            client_secret: Autodesk app client secret
            callback_url: OAuth callback URL
            base_url: Base API URL
            **kwargs: Additional configuration parameters
        """
        super().__init__(endpoint_details, **kwargs)
        
        self.client_id = client_id
        self.client_secret = client_secret
        self.callback_url = callback_url
        self.base_url = base_url.rstrip('/')
        
        # Configuration from endpoint_details
        self.project_id = endpoint_details.get("project_id")
        self.folder_id = endpoint_details.get("folder_id")  # None = root folder
        self.include_subfolders = endpoint_details.get("include_subfolders", True)
        self.file_types = endpoint_details.get("file_types", ["*"])  # ["*"] = all types
        self.max_results_per_request = min(endpoint_details.get("max_results", 200), 200)
        
        # Authentication
        self.access_token = None
        self.token_expires_at = None
        self.session = None
        
        # API endpoints
        self.auth_url = "https://developer.api.autodesk.com/authentication/v2/authorize"
        self.token_url = "https://developer.api.autodesk.com/authentication/v2/token"
        
        # Remove 'b.' prefix from project ID for submittals API
        clean_project_id = self.project_id.replace('b.', '') if self.project_id else None
        self.data_api_base = f"{self.base_url}/construction/submittals/v2/projects/{clean_project_id}"
        
        # Required scopes for file access
        self.scopes = [
            "data:read",
            "data:write",
            "data:create",
            "data:search"
        ]
        
        self.logger.info(
            "Autodesk Construction Cloud client initialized",
            project_id=self.project_id,
            folder_id=self.folder_id,
            include_subfolders=self.include_subfolders,
            file_types=self.file_types
        )
    
    async def __aenter__(self):
        """Async context manager entry."""
        connector = aiohttp.TCPConnector(ssl=False)  # Disable SSL verification for testing
        self.session = aiohttp.ClientSession(connector=connector)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    @log_async_execution_time
    async def authenticate(self) -> bool:
        """Authenticate with Autodesk Construction Cloud API using 3-legged OAuth.
        
        This method will handle the complete OAuth flow including user consent
        if needed, and automatically refresh tokens when they expire.
        """
        try:
            if not self.session:
                connector = aiohttp.TCPConnector(ssl=False)
                self.session = aiohttp.ClientSession(connector=connector)
            
            # Get a valid access token using the OAuth handler
            self.access_token = await get_autodesk_token(
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=self.scopes
            )
            
            if not self.access_token:
                raise AuthenticationError("Failed to obtain access token")
            
            # Set token expiration (the OAuth handler manages refresh automatically)
            # We set a short expiration here so the handler will refresh as needed
            self.token_expires_at = datetime.now() + timedelta(minutes=55)  # Refresh every 55 minutes
            
            self._authenticated = True
            self.logger.info("Autodesk Construction Cloud authentication successful")
            
            return True
                
        except Exception as e:
            error_msg = f"Authentication failed: {e}"
            self.logger.error("Autodesk authentication failed", error=error_msg)
            raise AuthenticationError(error_msg)
    
    async def _ensure_authenticated(self):
        """Ensure we have a valid access token."""
        if not self._authenticated or not self.access_token:
            await self.authenticate()
            return
        
        # Check if token is expired
        if self.token_expires_at and datetime.now() >= self.token_expires_at:
            self.logger.info("Access token expired, refreshing...")
            # The OAuth handler will automatically refresh the token if needed
            self.access_token = await get_autodesk_token(
                client_id=self.client_id,
                client_secret=self.client_secret,
                scopes=self.scopes
            )
            self.token_expires_at = datetime.now() + timedelta(minutes=55)
    
    async def _make_api_request(self, url: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make an authenticated API request."""
        await self._ensure_authenticated()
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }
        
        try:
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 401:
                    raise AuthenticationError("Invalid or expired access token")
                elif response.status == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    raise RateLimitError("Rate limit exceeded", retry_after)
                elif response.status != 200:
                    error_text = await response.text()
                    raise APIConnectionError(f"API request failed: {response.status} - {error_text}")
                
                return await response.json()
                
        except aiohttp.ClientError as e:
            raise APIConnectionError(f"Network error: {e}")
    
    async def _list_files_impl(
        self,
        since: Optional[datetime] = None,
        max_results: Optional[int] = None
    ) -> AsyncGenerator[FileMetadata, None]:
        """Internal implementation of file listing."""
        if not self.project_id:
            raise ValueError("project_id is required for Autodesk Construction Cloud")
        
        await self._ensure_authenticated()
        
        files_returned = 0
        target_max = max_results or float('inf')
        offset = 0
        
        self.logger.info(
            "Starting Autodesk Construction Cloud file listing",
            project_id=self.project_id,
            folder_id=self.folder_id,
            max_results=max_results,
            since=since
        )
        
        try:
            while files_returned < target_max:
                # Build request parameters
                params = {
                    "limit": min(self.max_results_per_request, int(target_max - files_returned)),
                    "offset": offset
                }
                
                # Add folder filter if specified
                if self.folder_id:
                    params["filter[parentId]"] = self.folder_id
                
                # Add date filter if specified
                if since:
                    # Convert to ISO format
                    since_str = since.isoformat()
                    params["filter[lastModifiedTime]"] = f"{since_str}.."
                
                # Construct API URL for submittals items
                url = f"{self.data_api_base}/items"
                
                # Execute API request
                result = await self._make_api_request(url, params)
                
                items = result.get("data", [])
                pagination = result.get("jsonapi", {}).get("meta", {})
                
                self.logger.debug(
                    "Retrieved Autodesk files page",
                    items_count=len(items),
                    offset=offset,
                    total_results=pagination.get("totalResults")
                )
                
                if not items:
                    break
                
                # Process files
                for item_data in items:
                    if files_returned >= target_max:
                        break
                    
                    # Skip folders unless we want to recurse into them
                    if item_data.get("type") == "folders":
                        if self.include_subfolders:
                            # TODO: Implement recursive folder traversal
                            pass
                        continue
                    
                    # Skip if not a file
                    if item_data.get("type") != "items":
                        continue
                    
                    # Skip if file type filter doesn't match
                    if not self._matches_file_type_filter(item_data):
                        continue
                    
                    try:
                        file_metadata = self._convert_to_file_metadata(item_data)
                        yield file_metadata
                        files_returned += 1
                        
                    except Exception as e:
                        self.logger.error(
                            "Failed to process file metadata",
                            error=str(e),
                            item_data=item_data
                        )
                        continue
                
                # Update offset for next page
                offset += len(items)
                
        except Exception as e:
            self.logger.error("Error during file listing", error=str(e))
            raise

    class FileListIterator:
        """Helper class to implement async iterator protocol."""
        def __init__(self, client, since=None, max_results=None):
            self.client = client
            self.since = since
            self.max_results = max_results
            self._impl = None

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._impl:
                self._impl = self.client._list_files_impl(since=self.since, max_results=self.max_results)
            try:
                return await self._impl.__anext__()
            except StopAsyncIteration:
                raise

    @log_async_execution_time
    async def list_files(
        self,
        since: Optional[datetime] = None,
        max_results: Optional[int] = None
    ) -> AsyncGenerator[FileMetadata, None]:
        """List files from Autodesk Construction Cloud.
        
        Args:
            since: Only return files modified after this datetime
            max_results: Maximum number of files to return
            
        Returns:
            Async iterator yielding FileMetadata objects
        """
        return self.FileListIterator(self, since=since, max_results=max_results)
    
    @log_async_execution_time
    async def get_file_metadata(self, file_id: str) -> Optional[FileMetadata]:
        """Get metadata for a specific file.
        
        Args:
            file_id: The ID of the file to get metadata for
            
        Returns:
            FileMetadata object or None if not found
        """
        if not self.project_id:
            raise ValueError("project_id is required for Autodesk Construction Cloud")
        
        await self._ensure_authenticated()
        
        try:
            url = f"{self.data_api_base}/items/{file_id}"
            result = await self._make_api_request(url)
            
            if not result or "data" not in result:
                return None
            
            item_data = result["data"]
            return self._convert_to_file_metadata(item_data)
            
        except Exception as e:
            self.logger.error(
                "Failed to get file metadata",
                file_id=file_id,
                error=str(e)
            )
            return None
    
    def _matches_file_type_filter(self, item_data: Dict[str, Any]) -> bool:
        """Check if a file matches the configured file type filter."""
        if "*" in self.file_types:
            return True
        
        file_type = item_data.get("attributes", {}).get("fileType", "").lower()
        return file_type in [ft.lower() for ft in self.file_types]
    
    def _convert_to_file_metadata(self, item_data: Dict[str, Any]) -> FileMetadata:
        """Convert Autodesk API response to FileMetadata."""
        attributes = item_data.get("attributes", {})
        
        return FileMetadata(
            title=attributes.get("displayName") or attributes.get("name"),
            path=self._get_file_path(item_data),
            external_id=item_data.get("id"),
            date_created=self._parse_timestamp(attributes.get("createTime")),
            date_updated=self._parse_timestamp(attributes.get("lastModifiedTime")),
            size_bytes=attributes.get("size"),
            mime_type=attributes.get("contentType"),
            download_url=self._get_download_link(item_data),
            parent_folder_id=self._get_parent_folder_id(item_data),
            metadata={
                "version": attributes.get("versionNumber"),
                "creator": attributes.get("createdBy"),
                "last_modifier": attributes.get("lastModifiedBy"),
                "file_type": attributes.get("fileType"),
                "status": attributes.get("status")
            }
        )
    
    def _get_file_path(self, item_data: Dict[str, Any]) -> Optional[str]:
        """Get the file path from item data."""
        attributes = item_data.get("attributes", {})
        return attributes.get("displayName") or attributes.get("name")
    
    def _get_parent_folder_id(self, item_data: Dict[str, Any]) -> Optional[str]:
        """Get the parent folder ID from item data."""
        relationships = item_data.get("relationships", {})
        parent = relationships.get("parent", {}).get("data", {})
        return parent.get("id") if parent else None
    
    def _get_download_link(self, item_data: Dict[str, Any]) -> str:
        """Get the download link for a file."""
        file_id = item_data.get("id")
        return f"{self.data_api_base}/items/{file_id}/download"
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse an ISO timestamp string to datetime."""
        if not timestamp_str:
            return None
        try:
            return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None
    
    async def get_project_info(self) -> Dict[str, Any]:
        """Get information about the current project.
        
        Returns:
            Dictionary containing project information
        """
        if not self.project_id:
            raise ValueError("project_id is required for Autodesk Construction Cloud")
        
        await self._ensure_authenticated()
        
        try:
            url = f"{self.data_api_base}"
            result = await self._make_api_request(url)
            
            return {
                "id": self.project_id,
                "name": result.get("name", "Unknown Project"),
                "status": result.get("status", "unknown"),
                "created_at": result.get("created_at"),
                "updated_at": result.get("updated_at")
            }
            
        except Exception as e:
            self.logger.error("Failed to get project info", error=str(e))
            return {
                "id": self.project_id,
                "name": "Unknown Project",
                "status": "error",
                "error": str(e)
            }
    
    async def get_sync_info(self) -> Dict[str, Any]:
        """Get information about the sync configuration.
        
        Returns:
            Dictionary containing sync configuration details
        """
        return {
            "project_id": self.project_id,
            "folder_id": self.folder_id,
            "include_subfolders": self.include_subfolders,
            "file_types": self.file_types,
            "max_results_per_request": self.max_results_per_request
        }