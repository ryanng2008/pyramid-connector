"""Google Drive API client implementation."""

import asyncio
import os
from typing import List, Dict, Any, Optional, AsyncGenerator
from datetime import datetime, timezone
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import google.auth.exceptions

from .base import BaseAPIClient, FileMetadata, RateLimitError, AuthenticationError, APIConnectionError
from ..utils.logging import log_async_execution_time
from ..performance import get_metrics_collector, get_concurrent_executor, AsyncRateLimiter


class GoogleDriveClient(BaseAPIClient):
    """Google Drive API client for file synchronization."""
    
    def __init__(self, endpoint_details: Dict[str, Any], credentials_path: str, **kwargs):
        """Initialize Google Drive client.
        
        Args:
            endpoint_details: Configuration for this endpoint
            credentials_path: Path to service account credentials JSON file
            **kwargs: Additional configuration parameters
        """
        super().__init__(endpoint_details, **kwargs)
        self.credentials_path = credentials_path
        self.service = None
        self.credentials = None
        
        # Performance optimization components
        self.metrics = get_metrics_collector()
        self.rate_limiter = AsyncRateLimiter(
            max_calls=endpoint_details.get("rate_limit_calls", 100),
            time_window=endpoint_details.get("rate_limit_window", 100.0)  # 100 calls per 100 seconds
        )
        
        # Configuration from endpoint_details
        self.folder_id = endpoint_details.get("folder_id")  # None = root folder
        self.include_shared = endpoint_details.get("include_shared", True)
        self.file_types = endpoint_details.get("file_types", ["*"])  # ["*"] = all types
        self.max_results_per_request = min(endpoint_details.get("max_results", 1000), 1000)
        
        # API configuration
        self.scopes = ["https://www.googleapis.com/auth/drive.readonly"]
        self.api_version = "v3"
        
        self.logger.info(
            "Google Drive client initialized",
            folder_id=self.folder_id,
            include_shared=self.include_shared,
            file_types=self.file_types
        )
    
    @log_async_execution_time
    async def authenticate(self) -> bool:
        """Authenticate with Google Drive API using service account."""
        try:
            # Check if credentials file exists
            if not os.path.exists(self.credentials_path):
                self.logger.error(
                    "Google Drive credentials file not found",
                    path=self.credentials_path
                )
                raise AuthenticationError(f"Credentials file not found: {self.credentials_path}")
            
            # Load service account credentials
            self.credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=self.scopes
            )
            
            # Build the Drive service
            self.service = build("drive", self.api_version, credentials=self.credentials)
            
            # Test authentication with a simple request
            about = self.service.about().get(fields="user").execute()
            user_email = about.get("user", {}).get("emailAddress", "Unknown")
            
            self._authenticated = True
            self.logger.info(
                "Google Drive authentication successful",
                user_email=user_email
            )
            
            return True
            
        except FileNotFoundError:
            error_msg = f"Credentials file not found: {self.credentials_path}"
            self.logger.error("Google Drive authentication failed", error=error_msg)
            raise AuthenticationError(error_msg)
            
        except json.JSONDecodeError as e:
            error_msg = f"Invalid credentials file format: {e}"
            self.logger.error("Google Drive authentication failed", error=error_msg)
            raise AuthenticationError(error_msg)
            
        except google.auth.exceptions.DefaultCredentialsError as e:
            error_msg = f"Invalid credentials: {e}"
            self.logger.error("Google Drive authentication failed", error=error_msg)
            raise AuthenticationError(error_msg)
            
        except HttpError as e:
            error_msg = f"Google API error during authentication: {e}"
            self.logger.error("Google Drive authentication failed", error=error_msg)
            raise AuthenticationError(error_msg)
            
        except Exception as e:
            error_msg = f"Unexpected error during authentication: {e}"
            self.logger.error("Google Drive authentication failed", error=error_msg)
            raise AuthenticationError(error_msg)
    
    @log_async_execution_time
    async def list_files(
        self,
        since: Optional[datetime] = None,
        max_results: Optional[int] = None
    ) -> AsyncGenerator[FileMetadata, None]:
        """List files from Google Drive.
        
        Args:
            since: Only return files modified after this datetime
            max_results: Maximum number of files to return
            
        Yields:
            FileMetadata objects for each file found
        """
        if not self._authenticated:
            await self.authenticate()
        
        query = self._build_query(since)
        page_token = None
        files_returned = 0
        target_max = max_results or float('inf')
        
        self.logger.info(
            "Starting Google Drive file listing",
            query=query,
            max_results=max_results,
            since=since
        )
        
        try:
            while files_returned < target_max:
                # Calculate page size for this request
                page_size = min(
                    self.max_results_per_request,
                    int(target_max - files_returned)
                )
                
                # Execute API request with rate limiting and metrics
                async with self.rate_limiter.limit():
                    async with self.metrics.time_operation(
                        "google_drive.api_request",
                        tags={"operation": "list_files", "page_size": str(page_size)}
                    ):
                        request = self.service.files().list(
                            q=query,
                            fields=(
                                "nextPageToken, files(id, name, parents, webViewLink, "
                                "size, mimeType, createdTime, modifiedTime, ownedByMe, "
                                "shared, permissions, thumbnailLink, exportLinks)"
                            ),
                            pageSize=page_size,
                            pageToken=page_token,
                            includeItemsFromAllDrives=self.include_shared,
                            supportsAllDrives=self.include_shared
                        )
                        
                        # Run in thread pool to avoid blocking
                        result = await asyncio.get_event_loop().run_in_executor(
                            None, self._execute_request, request
                        )
                
                # Record API call metrics
                self.metrics.increment_counter("google_drive.api_calls")
                self.metrics.record_value("google_drive.files_per_page", len(result.get("files", [])))
                
                files = result.get("files", [])
                page_token = result.get("nextPageToken")
                
                self.logger.debug(
                    "Retrieved Google Drive files page",
                    files_count=len(files),
                    has_next_page=bool(page_token)
                )
                
                # Process files
                for file_data in files:
                    if files_returned >= target_max:
                        break
                    
                    # Skip if file type filter doesn't match
                    if not self._matches_file_type_filter(file_data):
                        continue
                    
                    try:
                        file_metadata = self._convert_to_file_metadata(file_data)
                        yield file_metadata
                        files_returned += 1
                        
                        # Record successful file processing
                        self.metrics.increment_counter("google_drive.files_processed")
                        
                    except Exception as e:
                        self.logger.warning(
                            "Failed to process file metadata",
                            file_id=file_data.get("id"),
                            error=str(e)
                        )
                        # Record processing error
                        self.metrics.increment_counter("google_drive.processing_errors")
                        continue
                
                # Break if no more pages
                if not page_token:
                    break
                
                # Add small delay to respect rate limits
                await asyncio.sleep(0.1)
        
        except HttpError as e:
            if e.resp.status == 429:  # Rate limit exceeded
                retry_after = int(e.resp.headers.get("Retry-After", 60))
                self.metrics.increment_counter("google_drive.rate_limit_errors")
                raise RateLimitError("Google Drive rate limit exceeded", retry_after)
            else:
                self.metrics.increment_counter("google_drive.api_errors")
                raise APIConnectionError(f"Google Drive API error: {e}")
        
        except Exception as e:
            self.logger.error("Error listing Google Drive files", error=str(e))
            raise APIConnectionError(f"Error listing files: {e}")
        
        self.logger.info(
            "Completed Google Drive file listing",
            files_returned=files_returned,
            query=query
        )
    
    @log_async_execution_time
    async def get_file_metadata(self, file_id: str) -> Optional[FileMetadata]:
        """Get detailed metadata for a specific file.
        
        Args:
            file_id: Google Drive file ID
            
        Returns:
            FileMetadata object or None if file not found
        """
        if not self._authenticated:
            await self.authenticate()
        
        try:
            request = self.service.files().get(
                fileId=file_id,
                fields=(
                    "id, name, parents, webViewLink, size, mimeType, "
                    "createdTime, modifiedTime, ownedByMe, shared, "
                    "permissions, thumbnailLink, exportLinks"
                ),
                supportsAllDrives=self.include_shared
            )
            
            file_data = await asyncio.get_event_loop().run_in_executor(
                None, self._execute_request, request
            )
            
            return self._convert_to_file_metadata(file_data)
            
        except HttpError as e:
            if e.resp.status == 404:
                self.logger.warning("File not found", file_id=file_id)
                return None
            elif e.resp.status == 429:
                retry_after = int(e.resp.headers.get("Retry-After", 60))
                raise RateLimitError("Google Drive rate limit exceeded", retry_after)
            else:
                raise APIConnectionError(f"Google Drive API error: {e}")
        
        except Exception as e:
            self.logger.error("Error getting file metadata", file_id=file_id, error=str(e))
            raise APIConnectionError(f"Error getting file metadata: {e}")
    
    def _build_query(self, since: Optional[datetime] = None) -> str:
        """Build Google Drive API query string."""
        query_parts = []
        
        # Exclude trashed files
        query_parts.append("trashed=false")
        
        # Folder restriction
        if self.folder_id:
            query_parts.append(f"'{self.folder_id}' in parents")
        
        # Date filter
        if since:
            # Convert to RFC 3339 format
            since_str = since.isoformat()
            query_parts.append(f"modifiedTime > '{since_str}'")
        
        # File type filter (if not all types)
        if self.file_types and self.file_types != ["*"]:
            mime_conditions = []
            for file_type in self.file_types:
                if file_type.startswith("application/") or file_type.startswith("image/") or file_type.startswith("text/"):
                    # Full MIME type
                    mime_conditions.append(f"mimeType='{file_type}'")
                else:
                    # File extension
                    mime_conditions.append(f"name contains '.{file_type}'")
            
            if mime_conditions:
                query_parts.append(f"({' or '.join(mime_conditions)})")
        
        query = " and ".join(query_parts)
        self.logger.debug("Built Google Drive query", query=query)
        
        return query
    
    def _matches_file_type_filter(self, file_data: Dict[str, Any]) -> bool:
        """Check if file matches the file type filter."""
        if not self.file_types or self.file_types == ["*"]:
            return True
        
        file_name = file_data.get("name", "")
        mime_type = file_data.get("mimeType", "")
        
        for file_type in self.file_types:
            # Check MIME type match
            if mime_type.startswith(file_type):
                return True
            
            # Check file extension match
            if file_name.lower().endswith(f".{file_type.lower()}"):
                return True
        
        return False
    
    def _convert_to_file_metadata(self, file_data: Dict[str, Any]) -> FileMetadata:
        """Convert Google Drive file data to FileMetadata object."""
        file_id = file_data["id"]
        file_name = file_data.get("name", "")
        
        # Determine file path
        file_path = self._get_file_path(file_data)
        
        # Parse timestamps
        created_at = self._parse_timestamp(file_data.get("createdTime"))
        modified_at = self._parse_timestamp(file_data.get("modifiedTime"))
        
        # File size (might be None for some file types like Google Docs)
        file_size = None
        if "size" in file_data:
            try:
                file_size = int(file_data["size"])
            except (ValueError, TypeError):
                pass
        
        # MIME type
        mime_type = file_data.get("mimeType")
        
        # Generate file link (prefer download link if available)
        file_link = self._get_file_link(file_data)
        
        # Additional metadata
        metadata = {
            "mime_type": mime_type,
            "owned_by_me": file_data.get("ownedByMe", False),
            "shared": file_data.get("shared", False),
            "web_view_link": file_data.get("webViewLink"),
            "thumbnail_link": file_data.get("thumbnailLink"),
            "export_links": file_data.get("exportLinks", {}),
            "permissions_count": len(file_data.get("permissions", [])),
            "google_drive_id": file_id
        }
        
        return FileMetadata(
            external_file_id=file_id,
            file_name=file_name,
            file_path=file_path,
            file_link=file_link,
            file_size=file_size,
            file_type=mime_type,
            external_created_at=created_at,
            external_updated_at=modified_at,
            file_metadata=metadata
        )
    
    def _get_file_path(self, file_data: Dict[str, Any]) -> Optional[str]:
        """Construct file path from parent folder information."""
        parents = file_data.get("parents", [])
        if not parents:
            return f"/{file_data.get('name', '')}"
        
        # For now, just return the file name with first parent
        # In a full implementation, we'd traverse the folder hierarchy
        return f"/{file_data.get('name', '')}"
    
    def _get_file_link(self, file_data: Dict[str, Any]) -> str:
        """Get the best available file link."""
        # Prefer export links for Google Workspace files
        export_links = file_data.get("exportLinks", {})
        if export_links:
            # Prefer PDF export if available
            if "application/pdf" in export_links:
                return export_links["application/pdf"]
            # Otherwise use the first available export link
            return next(iter(export_links.values()))
        
        # Fall back to web view link
        return file_data.get("webViewLink", "")
    
    def _parse_timestamp(self, timestamp_str: Optional[str]) -> Optional[datetime]:
        """Parse Google Drive timestamp string to datetime object."""
        if not timestamp_str:
            return None
        
        try:
            # Google Drive uses RFC 3339 format
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            self.logger.warning("Failed to parse timestamp", timestamp=timestamp_str)
            return None
    
    def _execute_request(self, request):
        """Execute Google API request (to be run in thread pool)."""
        return request.execute()
    
    async def get_quota_info(self) -> Dict[str, Any]:
        """Get Google Drive quota information."""
        if not self._authenticated:
            await self.authenticate()
        
        try:
            request = self.service.about().get(fields="storageQuota")
            about = await asyncio.get_event_loop().run_in_executor(
                None, self._execute_request, request
            )
            
            quota = about.get("storageQuota", {})
            return {
                "limit": quota.get("limit"),
                "usage": quota.get("usage"),
                "usage_in_drive": quota.get("usageInDrive"),
                "usage_in_drive_trash": quota.get("usageInDriveTrash")
            }
            
        except Exception as e:
            self.logger.error("Error getting quota info", error=str(e))
            return {}
    
    async def get_sync_info(self) -> Dict[str, Any]:
        """Get information about the Google Drive sync endpoint."""
        base_info = await super().get_sync_info()
        
        # Add Google Drive specific information
        base_info.update({
            "folder_id": self.folder_id,
            "include_shared": self.include_shared,
            "file_types": self.file_types,
            "credentials_path": self.credentials_path
        })
        
        if self._authenticated:
            try:
                quota_info = await self.get_quota_info()
                base_info["quota_info"] = quota_info
            except Exception:
                pass  # Don't fail sync_info if quota check fails
        
        return base_info