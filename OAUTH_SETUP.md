# Autodesk OAuth Setup Guide

## Error: "The requesting client does not have redirect URIs configured"

This error occurs because your Autodesk Platform Services (APS) application needs to have the redirect URI configured.

## Solution Steps:

### 1. Configure Redirect URI in APS Portal

1. Go to https://aps.autodesk.com/
2. Sign in with your Autodesk account
3. Navigate to your developer console/dashboard
4. Find your application (Client ID: `awA50yf9uZm4XH4sKx83MwoGDwZBc8zMGBnHtw6Pt09cKdcr`)
5. Look for one of these sections:
   - "General Settings"
   - "Callback URLs" 
   - "Redirect URIs"
   - "App Settings"
6. Add this exact URL: `http://localhost:8080/oauth/callback`
7. Save the changes

### 2. Alternative: Use Manual Token Method

If you can't find the redirect URI settings, you can manually obtain tokens:

1. Visit this URL in your browser (replace with your actual client_id):
```
https://developer.api.autodesk.com/authentication/v2/authorize?response_type=code&client_id=awA50yf9uZm4XH4sKx83MwoGDwZBc8zMGBnHtw6Pt09cKdcr&redirect_uri=http://localhost:8080/oauth/callback&scope=data:read+data:write+account:read
```

2. After authorization, you'll be redirected to a URL like:
```
http://localhost:8080/oauth/callback?code=AUTHORIZATION_CODE&state=STATE
```

3. Copy the `AUTHORIZATION_CODE` from the URL

4. Use the manual token script (run this):
```bash
python scripts/manual_token_exchange.py AUTHORIZATION_CODE
```

### 3. Common Redirect URI Options

If `http://localhost:8080/oauth/callback` doesn't work, try these alternatives:

- `http://localhost:8080/callback`
- `http://127.0.0.1:8080/oauth/callback`
- `http://localhost:3000/oauth/callback`
- `urn:ietf:wg:oauth:2.0:oob` (for out-of-band flow)

### 4. App Type Considerations

Make sure your app type supports the redirect URI:
- **Web App**: Supports custom redirect URIs
- **Server-to-Server**: May not support user redirect URIs
- **Desktop/Mobile**: May have restrictions

If your app is Server-to-Server type, you might need to create a new app as "Web App" type.

## Next Steps

1. Configure the redirect URI in your APS app
2. Run the test again: `python scripts/test_oauth.py`
3. If issues persist, use the manual token method above