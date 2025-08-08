#!/usr/bin/env python3
"""
Manual token exchange script for Autodesk OAuth.

Use this when the automatic OAuth flow doesn't work due to redirect URI issues.
"""

import asyncio
import base64
import json
import os
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import aiohttp
from dotenv import load_dotenv


async def exchange_code_manually(authorization_code: str):
    """Manually exchange authorization code for tokens."""
    load_dotenv()
    
    client_id = os.getenv("CONNECTOR_AUTODESK_CLIENT_ID")
    client_secret = os.getenv("CONNECTOR_AUTODESK_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        print("Error: Please set CONNECTOR_AUTODESK_CLIENT_ID and CONNECTOR_AUTODESK_CLIENT_SECRET in your .env file")
        return False
    
    # Create Basic Auth header
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {encoded_credentials}"
    }
    
    data = {
        "grant_type": "authorization_code",
        "code": authorization_code,
        "redirect_uri": "http://localhost:8080/oauth/callback"
    }
    
    token_url = "https://developer.api.autodesk.com/authentication/v2/token"
    
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            print(f"Exchanging authorization code: {authorization_code[:20]}...")
            
            async with session.post(token_url, headers=headers, data=data) as response:
                response_text = await response.text()
                
                if response.status == 200:
                    token_data = await response.json()
                    
                    # Save tokens to file
                    tokens_dir = Path("./tokens")
                    tokens_dir.mkdir(exist_ok=True)
                    
                    tokens_file = tokens_dir / "autodesk_tokens.json"
                    
                    # Add timestamps
                    import time
                    from datetime import datetime
                    
                    token_data["expires_at"] = int(time.time()) + token_data.get("expires_in", 3600)
                    token_data["obtained_at"] = datetime.now().isoformat()
                    
                    with open(tokens_file, 'w') as f:
                        json.dump(token_data, f, indent=2)
                    
                    print("✅ Success! Tokens saved to tokens/autodesk_tokens.json")
                    print(f"Access token (first 20 chars): {token_data['access_token'][:20]}...")
                    print(f"Expires in: {token_data.get('expires_in')} seconds")
                    
                    if "refresh_token" in token_data:
                        print(f"Refresh token available: {token_data['refresh_token'][:20]}...")
                    
                    return True
                else:
                    print(f"❌ Token exchange failed: {response.status}")
                    print(f"Response: {response_text}")
                    return False
                    
        except Exception as e:
            print(f"❌ Error during token exchange: {e}")
            return False


def print_usage():
    """Print usage instructions."""
    print("Manual Token Exchange for Autodesk OAuth")
    print("=" * 50)
    print("\nUsage:")
    print("  python scripts/manual_token_exchange.py <authorization_code>")
    print("\nHow to get authorization code:")
    print("1. Visit this URL in your browser:")
    
    load_dotenv()
    client_id = os.getenv("CONNECTOR_AUTODESK_CLIENT_ID", "YOUR_CLIENT_ID")
    
    auth_url = (
        f"https://developer.api.autodesk.com/authentication/v2/authorize?"
        f"response_type=code&"
        f"client_id={client_id}&"
        f"redirect_uri=http://localhost:8080/oauth/callback&"
        f"scope=data:read+data:write+account:read"
    )
    
    print(f"\n{auth_url}\n")
    print("2. After authorization, copy the 'code' parameter from the redirect URL")
    print("3. Run this script with that code")
    print("\nExample:")
    print("  python scripts/manual_token_exchange.py DgK8pixFrHk8N_7tym_EVhDcHnaTV9SR6yoWmOyb")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print_usage()
        sys.exit(1)
    
    authorization_code = sys.argv[1]
    
    if not authorization_code or len(authorization_code) < 10:
        print("❌ Invalid authorization code provided")
        print_usage()
        sys.exit(1)
    
    success = asyncio.run(exchange_code_manually(authorization_code))
    
    if success:
        print("\n🎉 You can now test the connection:")
        print("  python scripts/test_oauth.py")
    
    sys.exit(0 if success else 1)