#!/usr/bin/env python3
"""
Test script for Autodesk 3-legged OAuth authentication.

This script tests the OAuth flow and token management.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
from connector.auth.oauth_handler import get_autodesk_token
from connector.utils.logging import setup_logging


async def test_oauth_flow():
    """Test the complete OAuth flow."""
    # Load environment variables
    load_dotenv()
    
    # Setup logging
    setup_logging(log_level="INFO", log_format="console")
    
    # Get credentials from environment
    client_id = os.getenv("CONNECTOR_AUTODESK_CLIENT_ID")
    client_secret = os.getenv("CONNECTOR_AUTODESK_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        print("Error: Please set CONNECTOR_AUTODESK_CLIENT_ID and CONNECTOR_AUTODESK_CLIENT_SECRET in your .env file")
        return False
    
    print("Starting Autodesk OAuth test...")
    print(f"Client ID: {client_id[:8]}...")
    
    try:
        # Test getting a token
        token = await get_autodesk_token(
            client_id=client_id,
            client_secret=client_secret,
            scopes=["data:read", "data:write", "account:read"]
        )
        
        print(f"✅ Successfully obtained access token!")
        print(f"Token (first 20 chars): {token[:20]}...")
        
        # Test getting the token again (should use cached/refreshed token)
        print("\nTesting token reuse...")
        token2 = await get_autodesk_token(
            client_id=client_id,
            client_secret=client_secret,
            scopes=["data:read", "data:write", "account:read"]
        )
        
        print(f"✅ Successfully reused/refreshed token!")
        print(f"Token (first 20 chars): {token2[:20]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ OAuth test failed: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_oauth_flow())
    sys.exit(0 if success else 1)