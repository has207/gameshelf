#!/usr/bin/env python3
"""
Helper module to complete OAuth 2.0 authentication flow for Xbox
when we already have the auth code from the WebKit authentication UI.
"""

import os
import json
import requests
import logging
from datetime import datetime
from pathlib import Path

# Get a logger for this module
logger = logging.getLogger(__name__)

class XboxAuthCodeWrapper:
    """Wrapper to complete Xbox authentication flow with an existing auth code"""

    # Xbox API constants
    CLIENT_ID = "85736097-7c70-4eba-ae9a-0cf0de4391e1"
    REDIRECT_URI = "https://login.live.com/oauth20_desktop.srf"
    SCOPE = "Xboxlive.signin Xboxlive.offline_access"

    def __init__(self, tokens_dir):
        """
        Initialize with a token directory

        Args:
            tokens_dir: Path to directory for storing tokens
        """
        self.tokens_dir = Path(tokens_dir)
        self.tokens_dir.mkdir(parents=True, exist_ok=True)
        self.live_tokens_path = self.tokens_dir / "login.json"
        self.xsts_tokens_path = self.tokens_dir / "xsts.json"

    def complete_auth_with_code(self, auth_code):
        """
        Complete the Xbox authentication flow using an auth code

        Args:
            auth_code: The OAuth 2.0 authorization code

        Returns:
            bool: True if authentication succeeded, False otherwise
        """
        try:
            # Exchange the code for tokens
            token_response = self._request_oauth_token(auth_code)
            if not token_response:
                logger.error("Failed to exchange code for token")
                return False

            # Store the Live tokens
            live_login_data = {
                "AccessToken": token_response["access_token"],
                "RefreshToken": token_response["refresh_token"],
                "ExpiresIn": token_response["expires_in"],
                "CreationDate": datetime.now().isoformat(),
                "UserId": token_response["user_id"],
                "TokenType": token_response["token_type"]
            }

            # Get Xbox XSTS tokens
            xsts_tokens = self._authenticate_with_xbox(live_login_data["AccessToken"])
            if not xsts_tokens:
                logger.error("Failed to get XSTS tokens")
                return False

            # Save tokens to files
            with open(self.live_tokens_path, 'w') as f:
                json.dump(live_login_data, f, indent=4)

            with open(self.xsts_tokens_path, 'w') as f:
                json.dump(xsts_tokens, f, indent=4)

            # Set secure permissions (0600) for token files
            os.chmod(self.live_tokens_path, 0o600)
            os.chmod(self.xsts_tokens_path, 0o600)

            return True

        except Exception as e:
            logger.error(f"Error completing Xbox authentication: {e}")
            return False

    def _request_oauth_token(self, auth_code):
        """Exchange authorization code for OAuth tokens"""
        request_data = {
            'grant_type': 'authorization_code',
            'code': auth_code,
            'scope': self.SCOPE,
            'client_id': self.CLIENT_ID,
            'redirect_uri': self.REDIRECT_URI
        }

        try:
            response = requests.post(
                'https://login.live.com/oauth20_token.srf',
                data=request_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )

            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error requesting OAuth token: {e}")
            return None

    def _authenticate_with_xbox(self, access_token):
        """Get Xbox authentication tokens"""
        try:
            # First authenticate with Xbox Live
            auth_request_data = {
                "RelyingParty": "http://auth.xboxlive.com",
                "TokenType": "JWT",
                "Properties": {
                    "AuthMethod": "RPS",
                    "SiteName": "user.auth.xboxlive.com",
                    "RpsTicket": f"d={access_token}"
                }
            }

            auth_response = requests.post(
                'https://user.auth.xboxlive.com/user/authenticate',
                json=auth_request_data,
                headers={'x-xbl-contract-version': '1'}
            )

            auth_response.raise_for_status()
            auth_tokens = auth_response.json()

            # Then authorize with XSTS
            auth_request_data = {
                "RelyingParty": "http://xboxlive.com",
                "TokenType": "JWT",
                "Properties": {
                    "SandboxId": "RETAIL",
                    "UserTokens": [auth_tokens["Token"]]
                }
            }

            auth_response = requests.post(
                'https://xsts.auth.xboxlive.com/xsts/authorize',
                json=auth_request_data,
                headers={'x-xbl-contract-version': '1'}
            )

            auth_response.raise_for_status()
            return auth_response.json()
        except Exception as e:
            logger.error(f"Error authenticating with Xbox: {e}")
            return None