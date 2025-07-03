#!/usr/bin/env python3
"""
GOG Authentication Code Wrapper

Handles OAuth token management for GOG authentication including:
- Token storage and retrieval
- Token refresh functionality
- Authentication code exchange

Based on the GOG Library extension for Playnite.
"""

import json
import os
import sys
import time
import logging
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Set up logging
logger = logging.getLogger(__name__)


class GogAuthCodeWrapper:
    """Handles GOG OAuth token management and storage."""

    def __init__(self, tokens_dir: Path):
        self.tokens_dir = Path(tokens_dir)
        self.tokens_dir.mkdir(parents=True, exist_ok=True)

        self.tokens_file = self.tokens_dir / "gog_tokens.json"
        self.session = self._create_session()

        # GOG OAuth constants
        self.client_id = "46899977096215655"
        self.client_secret = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9"
        self.redirect_uri = "https://embed.gog.com/on_login_success?origin=client"

        # GOG API endpoints
        self.token_url = "https://auth.gog.com/token"

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy."""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def is_token_valid(self) -> bool:
        """Check if the stored access token is still valid."""
        try:
            tokens = self._load_tokens()
            if not tokens:
                return False

            # Check if access token exists and is not expired
            access_token = tokens.get('access_token')
            expires_at = tokens.get('expires_at')

            if not access_token or not expires_at:
                return False

            # Check if token is still valid (with 5 minute buffer)
            current_time = time.time()
            return current_time < (expires_at - 300)  # 5 minute buffer

        except Exception as e:
            logger.error(f"Error checking token validity: {e}")
            return False

    def get_valid_access_token(self) -> Optional[str]:
        """Get a valid access token, refreshing if necessary."""
        try:
            # Check if current token is valid
            if self.is_token_valid():
                tokens = self._load_tokens()
                return tokens.get('access_token')

            # Try to refresh the token
            if self.refresh_access_token():
                tokens = self._load_tokens()
                return tokens.get('access_token')

            return None

        except Exception as e:
            logger.error(f"Error getting valid access token: {e}")
            return None

    def refresh_access_token(self) -> bool:
        """Attempt to refresh the access token using the refresh token."""
        try:
            tokens = self._load_tokens()
            if not tokens:
                return False

            refresh_token = tokens.get('refresh_token')
            if not refresh_token:
                return False

            logger.info("Attempting to refresh GOG access token...")

            # Prepare refresh token request
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token
            }

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'GOGGalaxyClient/2.0.12.3 (Windows 10)'
            }

            response = self.session.post(self.token_url, data=data, headers=headers)
            response.raise_for_status()

            token_data = response.json()

            # Calculate expiration time
            expires_in = token_data.get('expires_in', 3600)
            expires_at = time.time() + expires_in

            # Update tokens with new data
            updated_tokens = {
                'access_token': token_data['access_token'],
                'refresh_token': token_data.get('refresh_token', refresh_token),  # Use new or keep old
                'token_type': token_data.get('token_type', 'Bearer'),
                'expires_in': expires_in,
                'expires_at': expires_at,
                'scope': token_data.get('scope', ''),
                'updated_at': time.time()
            }

            self._save_tokens(updated_tokens)
            logger.info("Successfully refreshed GOG access token")
            return True

        except requests.RequestException as e:
            logger.error(f"HTTP error refreshing token: {e}")
            return False
        except Exception as e:
            logger.error(f"Error refreshing access token: {e}")
            return False

    def complete_auth_with_code(self, auth_code: str) -> bool:
        """Complete OAuth flow by exchanging auth code for tokens."""
        try:
            logger.info("Exchanging authorization code for access token...")

            # Prepare token exchange request
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'authorization_code',
                'code': auth_code,
                'redirect_uri': self.redirect_uri
            }

            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'GOGGalaxyClient/2.0.12.3 (Windows 10)'
            }

            response = self.session.post(self.token_url, data=data, headers=headers)
            response.raise_for_status()

            token_data = response.json()

            # Calculate expiration time
            expires_in = token_data.get('expires_in', 3600)
            expires_at = time.time() + expires_in

            # Store tokens
            tokens = {
                'access_token': token_data['access_token'],
                'refresh_token': token_data['refresh_token'],
                'token_type': token_data.get('token_type', 'Bearer'),
                'expires_in': expires_in,
                'expires_at': expires_at,
                'scope': token_data.get('scope', ''),
                'created_at': time.time()
            }

            self._save_tokens(tokens)
            logger.info("Successfully stored GOG authentication tokens")
            return True

        except requests.RequestException as e:
            logger.error(f"HTTP error during token exchange: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Error completing authentication: {e}")
            return False

    def _load_tokens(self) -> Optional[Dict[str, Any]]:
        """Load tokens from storage file."""
        try:
            if not self.tokens_file.exists():
                return None

            with open(self.tokens_file, 'r') as f:
                return json.load(f)

        except Exception as e:
            logger.error(f"Error loading tokens: {e}")
            return None

    def _save_tokens(self, tokens: Dict[str, Any]) -> bool:
        """Save tokens to storage file."""
        try:
            # Ensure directory exists
            self.tokens_dir.mkdir(parents=True, exist_ok=True)

            # Save tokens to file with secure permissions
            with open(self.tokens_file, 'w') as f:
                json.dump(tokens, f, indent=2)

            # Set secure file permissions (readable/writable by owner only)
            os.chmod(self.tokens_file, 0o600)

            return True

        except Exception as e:
            logger.error(f"Error saving tokens: {e}")
            return False

    def clear_tokens(self) -> bool:
        """Clear stored authentication tokens."""
        try:
            if self.tokens_file.exists():
                self.tokens_file.unlink()
            return True
        except Exception as e:
            logger.error(f"Error clearing tokens: {e}")
            return False