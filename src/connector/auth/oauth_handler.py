#!/usr/bin/env python3
"""
OAuth Handler for Autodesk 3-Legged Authentication

This module handles the 3-legged OAuth flow for Autodesk Platform Services (APS),
including authorization, token exchange, and token refresh.
"""

import asyncio
import base64
import json
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import aiohttp
from aiohttp import web
import structlog

logger = structlog.get_logger(__name__)


class AutodeskOAuthHandler:
    """Handles 3-legged OAuth flow for Autodesk APS."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str = "http://localhost:8081/oauth/callback",
        scopes: Optional[list] = None,
        token_storage_path: str = "./tokens/autodesk_tokens.json"
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = scopes or ["data:read", "data:write", "account:read"]
        self.token_storage_path = Path(token_storage_path)
        
        # OAuth endpoints
        self.auth_url = "https://developer.api.autodesk.com/authentication/v2/authorize"
        self.token_url = "https://developer.api.autodesk.com/authentication/v2/token"
        
        # Session management
        self.session: Optional[aiohttp.ClientSession] = None
        self.oauth_state = None
        self.server = None
        self.server_runner = None
        
        # Ensure token storage directory exists
        self.token_storage_path.parent.mkdir(parents=True, exist_ok=True)

    async def __aenter__(self):
        """Async context manager entry."""
        if not self.session:
            # Use a session with SSL verification disabled for local/dev testing to avoid
            # certificate issues in corporate proxies. Production should enable SSL verify.
            connector = aiohttp.TCPConnector(ssl=False)
            self.session = aiohttp.ClientSession(connector=connector)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
            self.session = None

    def get_authorization_url(self) -> Tuple[str, str]:
        """
        Generate the authorization URL for the user to visit.
        
        Returns:
            Tuple of (authorization_url, state) where state should be stored
            to validate the callback.
        """
        # Generate a random state parameter for security
        self.oauth_state = secrets.token_urlsafe(32)
        
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "state": self.oauth_state
        }
        
        auth_url = f"{self.auth_url}?{urllib.parse.urlencode(params)}"
        
        logger.info(
            "Generated authorization URL",
            client_id=self.client_id[:8] + "...",
            scopes=self.scopes,
            redirect_uri=self.redirect_uri
        )
        
        return auth_url, self.oauth_state

    async def exchange_code_for_token(self, authorization_code: str) -> Dict:
        """
        Exchange authorization code for access and refresh tokens.
        
        Args:
            authorization_code: The code received from the callback
            
        Returns:
            Dictionary containing token information
        """
        if not self.session:
            # Create session with SSL verification disabled for testing
            connector = aiohttp.TCPConnector(ssl=False)
            self.session = aiohttp.ClientSession(connector=connector)

        # Create Basic Auth header
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}"
        }
        
        data = {
            "grant_type": "authorization_code",
            "code": authorization_code,
            "redirect_uri": self.redirect_uri
        }
        
        logger.info("Exchanging authorization code for tokens")
        
        try:
            async with self.session.post(
                self.token_url,
                headers=headers,
                data=data
            ) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    token_data = await response.json()
                    
                    # Add expiration timestamp
                    token_data["expires_at"] = int(time.time()) + token_data.get("expires_in", 3600)
                    token_data["obtained_at"] = datetime.now().isoformat()
                    
                    # Save tokens to file
                    await self.save_tokens(token_data)
                    
                    logger.info(
                        "Successfully obtained tokens",
                        expires_in=token_data.get("expires_in"),
                        scopes=token_data.get("scope", "unknown")
                    )
                    
                    return token_data
                else:
                    logger.error(
                        "Failed to exchange code for token",
                        status=response.status,
                        response=response_text
                    )
                    raise Exception(f"Token exchange failed: {response.status} - {response_text}")
                    
        except Exception as e:
            logger.error("Error during token exchange", error=str(e))
            raise

    async def refresh_access_token(self, refresh_token: str) -> Dict:
        """
        Refresh the access token using the refresh token.
        
        Args:
            refresh_token: The refresh token
            
        Returns:
            Dictionary containing new token information
        """
        if not self.session:
            # Create session with SSL verification disabled for testing (to match exchange_code_for_token)
            connector = aiohttp.TCPConnector(ssl=False)
            self.session = aiohttp.ClientSession(connector=connector)

        # Create Basic Auth header
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {encoded_credentials}"
        }
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }
        
        logger.info("Refreshing access token")
        
        try:
            async with self.session.post(
                self.token_url,
                headers=headers,
                data=data
            ) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    token_data = await response.json()
                    
                    # Add expiration timestamp
                    token_data["expires_at"] = int(time.time()) + token_data.get("expires_in", 3600)
                    token_data["refreshed_at"] = datetime.now().isoformat()
                    
                    # Preserve the refresh token if not provided in response
                    if "refresh_token" not in token_data:
                        token_data["refresh_token"] = refresh_token
                    
                    # Save updated tokens
                    await self.save_tokens(token_data)
                    
                    logger.info(
                        "Successfully refreshed token",
                        expires_in=token_data.get("expires_in")
                    )
                    
                    return token_data
                else:
                    logger.error(
                        "Failed to refresh token",
                        status=response.status,
                        response=response_text
                    )
                    raise Exception(f"Token refresh failed: {response.status} - {response_text}")
                    
        except Exception as e:
            logger.error("Error during token refresh", error=str(e))
            raise

    async def get_valid_access_token(self) -> Optional[str]:
        """
        Get a valid access token, refreshing if necessary.
        
        Returns:
            Valid access token or None if authentication is needed
        """
        tokens = await self.load_tokens()
        
        if not tokens:
            logger.info("No tokens found, authentication required")
            return None
        
        # Check if token is still valid (with 5-minute buffer)
        current_time = int(time.time())
        expires_at = tokens.get("expires_at", 0)
        
        if current_time < (expires_at - 300):  # 5-minute buffer
            logger.debug("Using existing valid token")
            return tokens["access_token"]
        
        # Token is expired or about to expire, try to refresh
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            logger.warning("No refresh token available, re-authentication required")
            return None
        
        try:
            new_tokens = await self.refresh_access_token(refresh_token)
            return new_tokens["access_token"]
        except Exception as e:
            logger.error("Failed to refresh token, re-authentication required", error=str(e))
            return None

    async def save_tokens(self, token_data: Dict) -> None:
        """Save tokens to file."""
        try:
            with open(self.token_storage_path, 'w') as f:
                json.dump(token_data, f, indent=2)
            logger.debug("Tokens saved successfully")
        except Exception as e:
            logger.error("Failed to save tokens", error=str(e))
            raise

    async def load_tokens(self) -> Optional[Dict]:
        """Load tokens from file."""
        try:
            if self.token_storage_path.exists():
                with open(self.token_storage_path, 'r') as f:
                    tokens = json.load(f)
                logger.debug("Tokens loaded successfully")
                return tokens
            return None
        except Exception as e:
            logger.error("Failed to load tokens", error=str(e))
            return None

    async def start_oauth_server(self, port: int = 8080) -> str:
        """
        Start a temporary web server to handle the OAuth callback.
        
        Args:
            port: Port to run the server on
            
        Returns:
            The authorization URL for the user to visit
        """
        auth_url, state = self.get_authorization_url()
        
        # Create the callback handler
        async def oauth_callback(request):
            """Handle the OAuth callback."""
            try:
                # Extract query parameters
                code = request.query.get('code')
                returned_state = request.query.get('state')
                error = request.query.get('error')
                
                if error:
                    logger.error("OAuth error received", error=error)
                    return web.Response(
                        text=f"<html><body><h1>Authentication Failed</h1><p>Error: {error}</p></body></html>",
                        content_type='text/html',
                        status=400
                    )
                
                if not code:
                    logger.error("No authorization code received")
                    return web.Response(
                        text="<html><body><h1>Authentication Failed</h1><p>No authorization code received</p></body></html>",
                        content_type='text/html',
                        status=400
                    )
                
                if returned_state != self.oauth_state:
                    logger.error("State mismatch in OAuth callback")
                    return web.Response(
                        text="<html><body><h1>Authentication Failed</h1><p>State mismatch</p></body></html>",
                        content_type='text/html',
                        status=400
                    )
                
                # Exchange code for tokens
                try:
                    token_data = await self.exchange_code_for_token(code)
                    
                    # Schedule server shutdown
                    asyncio.create_task(self.stop_oauth_server())
                    
                    return web.Response(
                        text="""
                        <html>
                        <body>
                            <h1>Authentication Successful!</h1>
                            <p>You can now close this window and return to the application.</p>
                            <script>
                                setTimeout(function() {
                                    window.close();
                                }, 3000);
                            </script>
                        </body>
                        </html>
                        """,
                        content_type='text/html'
                    )
                except Exception as e:
                    logger.error("Failed to exchange code for tokens", error=str(e))
                    return web.Response(
                        text=f"<html><body><h1>Authentication Failed</h1><p>Token exchange failed: {str(e)}</p></body></html>",
                        content_type='text/html',
                        status=500
                    )
                    
            except Exception as e:
                logger.error("Unexpected error in OAuth callback", error=str(e))
                return web.Response(
                    text=f"<html><body><h1>Authentication Failed</h1><p>Unexpected error: {str(e)}</p></body></html>",
                    content_type='text/html',
                    status=500
                )
        
        # Create web application
        app = web.Application()
        app.router.add_get('/oauth/callback', oauth_callback)
        
        # Start server
        self.server_runner = web.AppRunner(app)
        await self.server_runner.setup()
        
        site = web.TCPSite(self.server_runner, 'localhost', port)
        await site.start()
        
        logger.info(f"OAuth server started on port {port}")
        logger.info(f"Please visit the following URL to authorize the application:")
        logger.info(f"{auth_url}")
        
        return auth_url

    async def stop_oauth_server(self):
        """Stop the OAuth server."""
        if self.server_runner:
            await asyncio.sleep(1)  # Give time for response to be sent
            await self.server_runner.cleanup()
            self.server_runner = None
            logger.info("OAuth server stopped")

    async def authenticate_user(self, port: int = 8081, timeout: int = 300) -> Dict:
        """
        Complete user authentication flow.
        
        Args:
            port: Port to run the callback server on
            timeout: Timeout in seconds to wait for user authentication
            
        Returns:
            Token data dictionary
        """
        logger.info("Starting user authentication flow")
        
        # Check if we already have valid tokens
        existing_token = await self.get_valid_access_token()
        if existing_token:
            tokens = await self.load_tokens()
            logger.info("Using existing valid tokens")
            return tokens
        
        # Start OAuth server and get authorization URL
        auth_url = await self.start_oauth_server(port)
        
        print(f"\n{'='*60}")
        print("AUTODESK AUTHENTICATION REQUIRED")
        print(f"{'='*60}")
        print(f"Please visit the following URL to authorize the application:")
        print(f"\n{auth_url}\n")
        print("Waiting for authentication... (this window will auto-close)")
        print(f"Timeout: {timeout} seconds")
        print(f"{'='*60}\n")
        
        # Wait for authentication with timeout
        start_time = time.time()
        while time.time() - start_time < timeout:
            tokens = await self.load_tokens()
            if tokens and tokens.get("access_token"):
                logger.info("Authentication completed successfully")
                return tokens
            await asyncio.sleep(1)
        
        # Cleanup on timeout
        await self.stop_oauth_server()
        raise TimeoutError(f"Authentication timed out after {timeout} seconds")


# Utility functions for easy integration

async def get_autodesk_token(
    client_id: str,
    client_secret: str,
    scopes: Optional[list] = None,
    force_reauth: bool = False
) -> str:
    """
    Get a valid Autodesk access token, handling authentication as needed.
    
    Args:
        client_id: Autodesk client ID
        client_secret: Autodesk client secret
        scopes: List of required scopes
        force_reauth: Force re-authentication even if tokens exist
        
    Returns:
        Valid access token
    """
    async with AutodeskOAuthHandler(
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes
    ) as oauth_handler:
        
        if force_reauth:
            # Remove existing tokens
            if oauth_handler.token_storage_path.exists():
                oauth_handler.token_storage_path.unlink()
        
        # Try to get existing valid token
        token = await oauth_handler.get_valid_access_token()
        if token:
            return token
        
        # Need to authenticate
        tokens = await oauth_handler.authenticate_user()
        return tokens["access_token"]


if __name__ == "__main__":
    """Test the OAuth handler."""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    async def test_oauth():
        client_id = os.getenv("CONNECTOR_AUTODESK_CLIENT_ID")
        client_secret = os.getenv("CONNECTOR_AUTODESK_CLIENT_SECRET")
        
        if not client_id or not client_secret:
            print("Please set CONNECTOR_AUTODESK_CLIENT_ID and CONNECTOR_AUTODESK_CLIENT_SECRET")
            return
        
        try:
            token = await get_autodesk_token(
                client_id=client_id,
                client_secret=client_secret,
                scopes=["data:read", "data:write", "account:read"]
            )
            print(f"Successfully obtained token: {token[:20]}...")
        except Exception as e:
            print(f"Authentication failed: {e}")
    
    asyncio.run(test_oauth())