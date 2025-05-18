#!/usr/bin/env python3
"""
Helper module to complete OAuth 2.0 authentication flow for Epic Games
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

class EpicAuthCodeWrapper:
    """Wrapper to complete Epic Games authentication flow with an existing auth code"""

    def __init__(self, tokens_dir):
        """
        Initialize with a token directory

        Args:
            tokens_dir: Path to directory for storing tokens
        """
        self.tokens_dir = Path(tokens_dir)
        self.tokens_dir.mkdir(parents=True, exist_ok=True)
        self.tokens_path = self.tokens_dir / "tokens.json"

        # Authentication constants
        self.auth_encoded_string = "MzRhMDJjZjhmNDQxNGUyOWIxNTkyMTg3NmRhMzZmOWE6ZGFhZmJjY2M3Mzc3NDUwMzlkZmZlNTNkOTRmYzc2Y2Y="
        self.client_id = "34a02cf8f4414e29b15921876da36f9a"  # Epic Games client ID

        # API endpoints
        self.oauth_url = "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/token"

    def complete_auth_with_code(self, auth_code):
        """
        Complete the Epic Games authentication flow using an auth code

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

            # Save the tokens
            with open(self.tokens_path, 'w') as f:
                json.dump(token_response, f, indent=4)

            # Set secure permissions for token file
            os.chmod(self.tokens_path, 0o600)

            return True

        except Exception as e:
            logger.error(f"Error completing Epic authentication: {e}")
            return False

    def _request_oauth_token(self, auth_code):
        """Exchange authorization code for OAuth tokens"""
        try:
            # Set up the request headers
            headers = {
                "Authorization": f"basic {self.auth_encoded_string}",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            # Set up the request data
            data = {
                "grant_type": "authorization_code",
                "code": auth_code,
                "token_type": "eg1"
            }

            # Make the token request
            response = requests.post(self.oauth_url, headers=headers, data=data)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to request OAuth token: {e}")
            return None