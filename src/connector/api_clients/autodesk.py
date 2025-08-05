"""Autodesk Construction Cloud API client implementation."""

import asyncio
import json
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime, timezone, timedelta
import aiohttp
from urllib.parse import urlencode

from .base import BaseAPIClient, FileMetadata, RateLimitError, AuthenticationError, APIConnectionError
from ..utils.logging import log_async_execution_time


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
        self.auth_url = "https://developer.api.autodesk.com/authentication/v1/authorize"
        self.token_url = "https://developer.api.autodesk.com/authentication/v1/gettoken"
        self.data_api_base = f"{self.base_url}/data/v1"
        
        # Required scopes for file access
        self.scopes = ["data:read"]
        
        self.logger.info(
            "Autodesk Construction Cloud client initialized",
            project_id=self.project_id,
            folder_id=self.folder_id,
            include_subfolders=self.include_subfolders,
            file_types=self.file_types
        )
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    @log_async_execution_time
    async def authenticate(self) -> bool:
        """Authenticate with Autodesk Construction Cloud API using OAuth 2.0.
        
        Note: This implementation uses client credentials flow.
        In a production environment, you would implement the full OAuth flow.
        """
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # Use client credentials flow for app-only access
            auth_data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
                "scope": " ".join(self.scopes)
            }
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json"
            }
            
            async with self.session.post(
                self.token_url,
                data=urlencode(auth_data),
                headers=headers
            ) as response:
                
                if response.status == 401:
                    raise AuthenticationError("Invalid client credentials")
                elif response.status == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    raise RateLimitError("Rate limit exceeded during authentication", retry_after)
                elif response.status != 200:
                    error_text = await response.text()
                    raise AuthenticationError(f"Authentication failed: {response.status} - {error_text}")
                
                token_data = await response.json()
                
                self.access_token = token_data.get("access_token")
                expires_in = token_data.get("expires_in", 3600)
                
                if not self.access_token:
                    raise AuthenticationError("No access token received")
                
                # Calculate expiration time
                self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 300)  # 5 min buffer
                
                self._authenticated = True
                self.logger.info(
                    "Autodesk Construction Cloud authentication successful",
                    expires_in=expires_in
                )
                
                return True
                
        except aiohttp.ClientError as e:
            error_msg = f"Network error during authentication: {e}"
            self.logger.error("Autodesk authentication failed", error=error_msg)
            raise AuthenticationError(error_msg)
            
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON response during authentication: {e}"
            self.logger.error("Autodesk authentication failed", error=error_msg)
            raise AuthenticationError(error_msg)
            
        except Exception as e:
            error_msg = f"Unexpected error during authentication: {e}"
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
            await self.authenticate()
    
    async def _make_api_request(self, url: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make an authenticated API request."""
        await self._ensure_authenticated()
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }
        
        try:
            async with self.session.get(url, headers=headers, params=params) as response:
                
                if response.status == 401:
                    # Token might be expired, try to refresh
                    self.logger.info("Received 401, attempting to refresh token...")
                    await self.authenticate()
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    
                    # Retry the request
                    async with self.session.get(url, headers=headers, params=params) as retry_response:
                        if retry_response.status == 401:
                            raise AuthenticationError("Authentication failed after token refresh")
                        elif retry_response.status == 429:
                            retry_after = int(retry_response.headers.get("Retry-After", 60))
                            raise RateLimitError("Rate limit exceeded", retry_after)
                        elif retry_response.status >= 400:
                            error_text = await retry_response.text()
                            raise APIConnectionError(f"API request failed: {retry_response.status} - {error_text}")
                        
                        return await retry_response.json()
                
                elif response.status == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    raise RateLimitError("Rate limit exceeded", retry_after)
                elif response.status >= 400:
                    error_text = await response.text()
                    raise APIConnectionError(f"API request failed: {response.status} - {error_text}")
                
                return await response.json()
                
        except aiohttp.ClientError as e:
            raise APIConnectionError(f"Network error: {e}")
    
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
            
        Yields:
            FileMetadata objects for each file found
        """
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
                
                # Construct API URL for project contents
                url = f"{self.data_api_base}/projects/{self.project_id}/contents"
                
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
                        self.logger.warning(
                            "Failed to process file metadata",
                            item_id=item_data.get("id"),
                            error=str(e)
                        )
                        continue
                
                # Check if we have more pages
                total_results = pagination.get("totalResults", 0)
                if offset + len(items) >= total_results:
                    break
                
                offset += len(items)
                
                # Add small delay to respect rate limits
                await asyncio.sleep(0.1)
        
        except Exception as e:
            self.logger.error("Error listing Autodesk Construction Cloud files", error=str(e))
            if not isinstance(e, (RateLimitError, APIConnectionError, AuthenticationError)):
                raise APIConnectionError(f"Error listing files: {e}")
            raise
        
        self.logger.info(
            "Completed Autodesk Construction Cloud file listing",
            files_returned=files_returned,
            project_id=self.project_id
        )
    
    @log_async_execution_time
    async def get_file_metadata(self, file_id: str) -> Optional[FileMetadata]:
        """Get detailed metadata for a specific file.
        
        Args:
            file_id: Autodesk file/item ID
            
        Returns:
            FileMetadata object or None if file not found
        """
        await self._ensure_authenticated()
        
        try:
            url = f"{self.data_api_base}/projects/{self.project_id}/items/{file_id}"
            result = await self._make_api_request(url)
            
            item_data = result.get("data")
            if not item_data:
                return None
            
            return self._convert_to_file_metadata(item_data)
            
        except APIConnectionError as e:
            if "404" in str(e):
                self.logger.warning("File not found", file_id=file_id)
                return None
            raise
        
        except Exception as e:
            self.logger.error("Error getting file metadata", file_id=file_id, error=str(e))
            raise APIConnectionError(f"Error getting file metadata: {e}")
    
    def _matches_file_type_filter(self, item_data: Dict[str, Any]) -> bool:
        """Check if file matches the file type filter."""
        if not self.file_types or self.file_types == ["*"]:
            return True
        
        attributes = item_data.get("attributes", {})
        file_name = attributes.get("displayName", "")
        
        # Get file extension
        if "." in file_name:
            extension = file_name.split(".")[-1].lower()
            
            for file_type in self.file_types:
                if file_type.lower() == extension:
                    return True
        
        return False
    
    def _convert_to_file_metadata(self, item_data: Dict[str, Any]) -> FileMetadata:
        """Convert Autodesk item data to FileMetadata object."""
        item_id = item_data["id"]
        attributes = item_data.get("attributes", {})
        
        file_name = attributes.get("displayName", "")
        
        # Determine file path - construct from parent relationships
        file_path = self._get_file_path(item_data)
        
        # Parse timestamps
        created_at = self._parse_timestamp(attributes.get("createTime"))
        modified_at = self._parse_timestamp(attributes.get("lastModifiedTime"))
        
        # File size
        file_size = attributes.get("storageSize")
        if file_size:
            try:
                file_size = int(file_size)
            except (ValueError, TypeError):
                file_size = None
        
        # File type/extension
        file_type = None
        if "." in file_name:
            file_type = file_name.split(".")[-1].lower()
        
        # Generate download link
        file_link = self._get_download_link(item_data)
        
        # Additional metadata
        metadata = {
            "autodesk_item_id": item_id,
            "version_number": attributes.get("versionNumber"),
            "create_user_id": attributes.get("createUserId"),
            "last_modified_user_id": attributes.get("lastModifiedUserId"),
            "mime_type": attributes.get("mimeType"),
            "file_type": attributes.get("fileType"),
            "project_id": self.project_id,
            "parent_folder_id": self._get_parent_folder_id(item_data)
        }
        
        return FileMetadata(
            external_file_id=item_id,
            file_name=file_name,
            file_path=file_path,
            file_link=file_link,
            file_size=file_size,
            file_type=file_type,
            external_created_at=created_at,
            external_updated_at=modified_at,
            file_metadata=metadata
        )
    
    def _get_file_path(self, item_data: Dict[str, Any]) -> Optional[str]:
        """Construct file path from item data."""
        attributes = item_data.get("attributes", {})
        file_name = attributes.get("displayName", "")
        
        # For now, just return the file name
        # In a full implementation, we'd traverse the folder hierarchy
        return f"/{file_name}"
    
    def _get_parent_folder_id(self, item_data: Dict[str, Any]) -> Optional[str]:
        """Extract parent folder ID from item data."""
        relationships = item_data.get("relationships", {})
        parent = relationships.get("parent", {})
        parent_data = parent.get("data")
        
        if parent_data:
            return parent_data.get("id")
        
        return None
    
    def _get_download_link(self, item_data: Dict[str, Any]) -> str:
        """Generate download link for the file."""
        item_id = item_data["id"]
        # Construct a download URL - this would need to be a signed URL in production
        return f"{self.data_api_base}/projects/{self.project_id}/items/{item_id}/content"
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse Autodesk timestamp string to datetime object."""
        if not timestamp_str:
            return None
        
        try:
            # Autodesk uses ISO 8601 format
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            self.logger.warning("Failed to parse timestamp", timestamp=timestamp_str)
            return None
    
    async def get_project_info(self) -> Dict[str, Any]:
        """Get information about the project."""
        await self._ensure_authenticated()
        
        try:
            url = f"{self.data_api_base}/projects/{self.project_id}"
            result = await self._make_api_request(url)
            
            project_data = result.get("data", {})
            attributes = project_data.get("attributes", {})
            
            return {
                "project_id": self.project_id,
                "name": attributes.get("name"),
                "status": attributes.get("status"),
                "created_at": self._parse_timestamp(attributes.get("createdAt")),
                "updated_at": self._parse_timestamp(attributes.get("updatedAt"))
            }
            
        except Exception as e:
            self.logger.error("Error getting project info", error=str(e))
            return {}
    
    async def get_sync_info(self) -> Dict[str, Any]:
        """Get information about the Autodesk Construction Cloud sync endpoint."""
        base_info = await super().get_sync_info()
        
        # Add Autodesk-specific information
        base_info.update({
            "project_id": self.project_id,
            "folder_id": self.folder_id,
            "include_subfolders": self.include_subfolders,
            "file_types": self.file_types,
            "client_id": self.client_id
        })
        
        if self._authenticated:
            try:
                project_info = await self.get_project_info()
                base_info["project_info"] = project_info
            except Exception:
                pass  # Don't fail sync_info if project check fails
        
        return base_info