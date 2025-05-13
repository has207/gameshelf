#!/usr/bin/env python3

import json
import os
import requests
import sys
import urllib.parse
import time
import webbrowser
import logging
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

# Set up logger
logger = logging.getLogger(__name__)

class PSNClient:
    """Client for PlayStation Network API, handling authentication and data fetching"""

    # Token storage
    TOKEN_DIR = os.path.expanduser("~/.psn_api_client")
    TOKEN_FILE = os.path.join(TOKEN_DIR, "token.json")

    # API endpoints
    SSO_COOKIE_URL = "https://ca.account.sony.com/api/v1/ssocookie"
    MOBILE_TOKEN_URL = "https://ca.account.sony.com/api/authz/v3/oauth/token"
    MOBILE_CODE_URL = "https://ca.account.sony.com/api/authz/v3/oauth/authorize?access_type=offline&client_id=09515159-7237-4370-9b40-3806e67c0891&redirect_uri=com.scee.psxandroid.scecompcall%3A%2F%2Fredirect&response_type=code&scope=psn%3Amobile.v2.core%20psn%3Aclientapp"
    # Updated to include all platform categories
    MOBILE_PLAYED_GAMES_URL = "https://m.np.playstation.com/api/gamelist/v2/users/me/titles?categories=ps4_game,ps5_native_game,ps3_game,psp_game,ps_vita_game,ps_now_game&limit=200&offset=%d"
    TROPHIES_MOBILE_URL = "https://m.np.playstation.com/api/trophy/v1/users/me/trophyTitles?limit=250&offset=%d"

    # Trophy endpoints
    TROPHIES_DETAIL_URL = "https://m.np.playstation.com/api/trophy/v1/users/me/npCommunicationIds/%s/trophyGroups/%s/trophies"
    TROPHIES_GROUPS_URL = "https://m.np.playstation.com/api/trophy/v1/users/me/npCommunicationIds/%s/trophyGroups"

    # Constants
    MOBILE_TOKEN_AUTH = "MDk1MTUxNTktNzIzNy00MzcwLTliNDAtMzgwNmU2N2MwODkxOnVjUGprYTV0bnRCMktxc1A="
    PAGE_REQUEST_LIMIT = 100

    def __init__(self, token_dir: Optional[str] = None):
        """Initialize the PSN client with token directory"""
        if token_dir:
            self.TOKEN_DIR = os.path.expanduser(token_dir)
            self.TOKEN_FILE = os.path.join(self.TOKEN_DIR, "token.json")

        self.npsso_token = None
        self.mobile_token = None
        self.web_cookies = {}

        # Create token directory if it doesn't exist
        os.makedirs(self.TOKEN_DIR, exist_ok=True)

        # Attempt to load token if exists
        self._load_token()

    @staticmethod
    def verify_npsso_token(token: str) -> bool:
        """
        Verify if a PSN NPSSO token is valid.

        Args:
            token: The NPSSO token to verify

        Returns:
            bool: True if token is valid, False otherwise
        """
        try:
            # Clean up the token
            token = token.strip('"\'')

            # Try to extract token from JSON if the user copied the whole thing
            if token.startswith('{') and '}' in token:
                try:
                    data = json.loads(token)
                    if 'npsso' in data and data['npsso']:
                        token = data['npsso']
                except:
                    pass

            # Basic validation
            if not token or len(token) < 10:
                return False

            # Check authentication with SSO cookie endpoint
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
            }
            cookies = {"npsso": token}

            response = requests.get(
                "https://ca.account.sony.com/api/v1/ssocookie",
                cookies=cookies,
                headers=headers
            )

            if response.status_code == 200:
                try:
                    data = response.json()
                    if 'npsso' in data and data['npsso']:
                        return True
                except:
                    pass

            return False
        except:
            return False

    def _save_token(self, token: str) -> bool:
        """Save the NPSSO token to the token file"""
        try:
            token_data = {
                "npsso": token,
                "saved_at": time.time()
            }

            with open(self.TOKEN_FILE, 'w', encoding='utf-8') as f:
                json.dump(token_data, f)

            # Set secure permissions
            os.chmod(self.TOKEN_FILE, 0o600)  # Only user can read/write

            logger.debug(f"Saved token to {self.TOKEN_FILE}")
            return True
        except Exception as e:
            logger.error(f"Error saving token: {str(e)}")
            return False

    def _load_token(self) -> bool:
        """Load the NPSSO token from the token file if it exists"""
        try:
            if not os.path.exists(self.TOKEN_FILE):
                logger.debug(f"Token file {self.TOKEN_FILE} does not exist")
                return False

            with open(self.TOKEN_FILE, 'r', encoding='utf-8') as f:
                token_data = json.load(f)

            if "npsso" not in token_data:
                logger.debug("Token file does not contain NPSSO token")
                return False

            self.npsso_token = token_data["npsso"]
            self.web_cookies = self._get_web_cookies()

            logger.debug(f"Loaded token from {self.TOKEN_FILE}")
            return True
        except Exception as e:
            logger.error(f"Error loading token: {str(e)}")
            return False

    def _get_web_cookies(self) -> Dict[str, str]:
        """Convert NPSSO token to web cookies"""
        if self.npsso_token:
            return {"npsso": self.npsso_token}
        return {}

    def is_authenticated(self) -> bool:
        """Check if the client has a valid authentication token"""
        if not self.npsso_token:
            logger.debug("No NPSSO token available")
            return False

        # Check if token is valid
        auth_result = self.check_authentication()
        return auth_result.get("authenticated", False)

    def check_authentication(self) -> Dict[str, Any]:
        """
        Check if the NPSSO token is valid and authenticated.
        Returns a dictionary with authentication status.
        """
        result = {
            "authenticated": False,
            "web_auth": False,
        }

        if not self.npsso_token:
            logger.debug("No NPSSO token available")
            return result

        # Check web authentication using SSO cookie endpoint
        try:
            logger.debug("Checking authentication via SSO cookie endpoint")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
            }

            response = requests.get(
                self.SSO_COOKIE_URL,
                cookies=self.web_cookies,
                headers=headers
            )

            logger.debug(f"SSO cookie check response status: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    if 'npsso' in data and data['npsso']:
                        result["web_auth"] = True
                        logger.debug("Valid SSO cookie found")
                except Exception as e:
                    logger.debug(f"Error parsing SSO cookie response: {str(e)}")
            else:
                logger.debug(f"SSO cookie check failed with status {response.status_code}")
        except Exception as e:
            logger.debug(f"Error checking authentication: {str(e)}")

        # Consider authenticated if web auth succeeded
        result["authenticated"] = result["web_auth"]

        return result

    def authenticate(self, token: str) -> bool:
        """
        Authenticate using an NPSSO token
        Returns True if authentication succeeded, False otherwise
        """
        # Clean up the token (remove quotes, handle JSON object)
        token = token.strip('"\'')

        # Try to extract token from JSON if the user copied the whole thing
        if token.startswith('{') and '}' in token:
            try:
                data = json.loads(token)
                if 'npsso' in data and data['npsso']:
                    token = data['npsso']
                    logger.debug("Extracted token from JSON object")
            except Exception as e:
                logger.debug(f"Error parsing JSON token: {str(e)}")

        # Basic validation
        if not token or len(token) < 10:
            logger.debug("Token format is invalid")
            return False

        # Set the token and save
        self.npsso_token = token
        self.web_cookies = self._get_web_cookies()

        # Test if token is valid
        auth_result = self.check_authentication()
        if auth_result["authenticated"]:
            # Save token if it's valid
            self._save_token(token)
            logger.debug("Authentication successful")
            return True
        else:
            logger.debug("Authentication failed - token is invalid")
            self.npsso_token = None
            self.web_cookies = {}
            return False

    def logout(self) -> None:
        """Log out by clearing tokens and removing the token file"""
        self.npsso_token = None
        self.mobile_token = None
        self.web_cookies = {}

        # Remove token file if it exists
        if os.path.exists(self.TOKEN_FILE):
            try:
                os.remove(self.TOKEN_FILE)
                logger.debug(f"Removed token file {self.TOKEN_FILE}")
            except Exception as e:
                logger.debug(f"Error removing token file: {str(e)}")

    def get_mobile_token(self) -> bool:
        """Get mobile API token using NPSSO token"""
        if not self.npsso_token:
            logger.debug("No NPSSO token available")
            return False

        try:
            # First get the authorization code
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36'
            }

            logger.debug(f"Getting authorization code from {self.MOBILE_CODE_URL}")
            code_response = requests.get(
                self.MOBILE_CODE_URL,
                cookies=self.web_cookies,
                headers=headers,
                allow_redirects=False
            )

            logger.debug(f"Authorization code response status: {code_response.status_code}")

            if code_response.status_code == 302:
                # Extract code from redirect URL
                redirect_url = code_response.headers.get('Location', '')
                logger.debug(f"Redirect URL: {redirect_url}")

                # Parse the redirect URL to extract the code parameter
                if 'code=' in redirect_url:
                    query_params = urllib.parse.parse_qs(urllib.parse.urlparse(redirect_url).query)
                    code = query_params.get('code', [None])[0]
                else:
                    code = None

                if not code:
                    logger.debug("Failed to get authorization code")
                    return False

                logger.debug(f"Authorization code obtained: {code[:5]}...")

                # Now exchange code for token
                token_headers = {
                    'Authorization': f'Basic {self.MOBILE_TOKEN_AUTH}',
                    'Content-Type': 'application/x-www-form-urlencoded'
                }

                token_data = {
                    'code': code,
                    'redirect_uri': 'com.scee.psxandroid.scecompcall://redirect',
                    'grant_type': 'authorization_code',
                    'token_format': 'jwt'
                }

                logger.debug(f"Exchanging code for token at {self.MOBILE_TOKEN_URL}")
                token_response = requests.post(
                    self.MOBILE_TOKEN_URL,
                    headers=token_headers,
                    data=token_data
                )

                logger.debug(f"Token response status: {token_response.status_code}")

                if token_response.status_code == 200:
                    self.mobile_token = token_response.json()
                    logger.debug("Mobile token obtained successfully")
                    return True
                else:
                    logger.debug(f"Failed to get mobile token: {token_response.text}")
            else:
                logger.debug(f"Failed to get authorization code: {code_response.text}")

            return False
        except Exception as e:
            logger.debug(f"Error getting mobile token: {str(e)}")
            return False

    def fetch_games(self) -> List[Dict[str, Any]]:
        """
        Fetch all PlayStation games from the user's library.
        Returns a list of game dictionaries with platform info.
        """
        if not self.npsso_token:
            logger.debug("No NPSSO token available")
            return []

        if not self.mobile_token and not self.get_mobile_token():
            logger.debug("Failed to get mobile token")
            return []

        games = []
        offset = 0

        try:
            while True:
                url = self.MOBILE_PLAYED_GAMES_URL % offset

                headers = {
                    'Authorization': f"Bearer {self.mobile_token['access_token']}",
                    'User-Agent': 'PlayStation App/5.43.0 (iPhone; iOS 14.2; Scale/3.00)'
                }

                logger.debug(f"Fetching mobile played games from {url}")
                response = requests.get(
                    url,
                    headers=headers
                )

                logger.debug(f"Mobile played games response status: {response.status_code}")

                if response.status_code != 200:
                    logger.debug(f"Error fetching mobile played games: HTTP {response.status_code}")
                    break

                try:
                    data = response.json()
                except json.JSONDecodeError as e:
                    logger.debug(f"Error parsing mobile played games JSON: {str(e)}")
                    break

                if data is None:
                    logger.debug("Invalid or empty response for mobile played games")
                    break

                current_games = data.get('titles', [])
                if not current_games:
                    break

                # Add platform category for easier filtering
                for game in current_games:
                    platform = "Unknown"
                    category = game.get('category', '')
                    if 'ps5' in category:
                        platform = "PS5"
                    elif 'ps4' in category:
                        platform = "PS4"
                    elif 'ps3' in category:
                        platform = "PS3"
                    elif 'psvita' in category or 'ps_vita' in category:
                        platform = "PS Vita"
                    elif 'psp' in category:
                        platform = "PSP"
                    elif 'ps_now' in category:
                        platform = "PS Now"
                    game['platform'] = platform

                games.extend(current_games)

                next_offset = data.get('nextOffset')
                logger.debug(f"Retrieved {len(current_games)} mobile played games, total: {len(games)}")

                if next_offset is None:
                    break

                offset = next_offset

            return games
        except Exception as e:
            logger.debug(f"Error fetching mobile played games: {str(e)}")
            return []

    def fetch_trophies(self) -> List[Dict[str, Any]]:
        """Fetch trophy data for played games"""
        if not self.npsso_token:
            logger.debug("No NPSSO token available")
            return []

        if not self.mobile_token and not self.get_mobile_token():
            logger.debug("Failed to get mobile token")
            return []

        trophies = []
        offset = 0

        try:
            while True:
                url = self.TROPHIES_MOBILE_URL % offset

                headers = {
                    'Authorization': f"Bearer {self.mobile_token['access_token']}",
                    'User-Agent': 'PlayStation App/5.43.0 (iPhone; iOS 14.2; Scale/3.00)'
                }

                logger.debug(f"Fetching trophies from {url}")
                response = requests.get(
                    url,
                    headers=headers
                )

                logger.debug(f"Trophies response status: {response.status_code}")

                if response.status_code != 200:
                    logger.debug(f"Error fetching trophies: HTTP {response.status_code}")
                    break

                try:
                    data = response.json()
                except json.JSONDecodeError as e:
                    logger.debug(f"Error parsing trophies JSON: {str(e)}")
                    break

                if data is None:
                    logger.debug("Invalid or empty response for trophies")
                    break

                current_trophies = data.get('trophyTitles', [])
                if not current_trophies:
                    break

                trophies.extend(current_trophies)

                next_offset = data.get('nextOffset')
                logger.debug(f"Retrieved {len(current_trophies)} trophy titles, total: {len(trophies)}")

                if next_offset is None:
                    break

                offset = next_offset

            return trophies
        except Exception as e:
            logger.debug(f"Error fetching trophies: {str(e)}")
            return []

    def fetch_all_data(self) -> Dict[str, Any]:
        """Fetch all available data from PSN APIs"""
        result = {
            "games": self.fetch_games(),
            "trophies": self.fetch_trophies()
        }
        return result

    def download_game_cover(self, game_data: Dict[str, Any], output_path: str) -> bool:
        """
        Download a game's cover image to the specified path
        Returns True if successful, False otherwise
        """
        try:
            # Get the image URL from the game data
            image_url = None

            # Try different image sources in priority order
            if 'image' in game_data and game_data['image']:
                image_url = game_data['image']
            elif 'imageUrl' in game_data and game_data['imageUrl']:
                image_url = game_data['imageUrl']
            elif 'images' in game_data and game_data['images']:
                images = game_data['images']
                if len(images) > 0 and 'url' in images[0]:
                    image_url = images[0]['url']

            if not image_url:
                logger.debug(f"No image URL found for game: {game_data.get('name', 'Unknown')}")
                return False

            # Download the image
            response = requests.get(image_url, stream=True)
            if response.status_code != 200:
                logger.debug(f"Error downloading image: HTTP {response.status_code}")
                return False

            # Save to file
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.debug(f"Downloaded cover image to {output_path}")
            return True
        except Exception as e:
            logger.debug(f"Error downloading cover image: {str(e)}")
            return False

    @staticmethod
    def get_auth_instructions() -> str:
        """Instructions for getting an NPSSO token"""
        instructions = (
            "<b>To get your PlayStation Network NPSSO token, follow these steps:</b>\n\n"
            "1. Open your web browser and go to: <a href='https://www.playstation.com/'>https://www.playstation.com/</a>\n"
            "2. Login to your PlayStation account\n"
            "3. Once logged in, open this URL: <a href='https://ca.account.sony.com/api/v1/ssocookie'>https://ca.account.sony.com/api/v1/ssocookie</a>\n"
            "4. You'll see a JSON response with your token, like: {\"npsso\":\"YourTokenHere\"}\n"
            "5. Copy ONLY the value between the quotes after \"npsso\" (do not include the quotes)\n\n"
            "<i>For example, if you see: {\"npsso\":\"abcdef12345\"}, you should paste just: abcdef12345</i>"
        )
        return instructions

# Expose verify_npsso_token at the module level for backward compatibility
def verify_npsso_token(token: str) -> bool:
    """
    Verify if a PSN NPSSO token is valid.

    Args:
        token: The NPSSO token to verify

    Returns:
        bool: True if token is valid, False otherwise
    """
    return PSNClient.verify_npsso_token(token)