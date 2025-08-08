#!/usr/bin/env python3

import json
import os
import requests
import sys
import urllib.parse
import time
import webbrowser
import logging
import traceback
import re
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from datetime import datetime
import isodate

from sources.scanner_base import SourceScanner
from data import Source, Game
from data_mapping import Platforms, Genres, CompletionStatus, AgeRatings, Features, Regions
from cover_fetch import CoverFetcher

# Set up logger
logger = logging.getLogger(__name__)
# Set logger level to DEBUG to see all messages
#logger.setLevel(logging.DEBUG)

MOBILE_TOKEN_AUTH = "MDk1MTUxNTktNzIzNy00MzcwLTliNDAtMzgwNmU2N2MwODkxOnVjUGprYTV0bnRCMktxc1A="
# Updated to include all platform categories
MOBILE_PLAYED_GAMES_URL = "https://m.np.playstation.com/api/gamelist/v2/users/me/titles?categories=ps4_game,ps5_native_game,ps3_game,psp_game,ps_vita_game,ps_now_game&limit=200&offset=%d"
TROPHIES_MOBILE_URL = "https://m.np.playstation.com/api/trophy/v1/users/me/trophyTitles?limit=250&offset=%d"

# API endpoints
SSO_COOKIE_URL = "https://ca.account.sony.com/api/v1/ssocookie"
MOBILE_TOKEN_URL = "https://ca.account.sony.com/api/authz/v3/oauth/token"
MOBILE_CODE_URL = "https://ca.account.sony.com/api/authz/v3/oauth/authorize?access_type=offline&client_id=09515159-7237-4370-9b40-3806e67c0891&redirect_uri=com.scee.psxandroid.scecompcall%3A%2F%2Fredirect&response_type=code&scope=psn%3Amobile.v2.core%20psn%3Aclientapp"

class PSNClient(SourceScanner):
    """Client for PlayStation Network API, handling authentication and data fetching"""


    def __init__(self, data_handler=None, token_dir: Optional[str] = None):
        """
        Initialize the PSN client with token directory

        Args:
            data_handler: The data handler instance to use (can be None for standalone usage)
            token_dir: Directory to store authentication tokens
        """
        # Initialize SourceScanner if data handler is provided
        if data_handler:
            super().__init__(data_handler)

        self.token_file = "token.json"

        if token_dir:
            token_dir = os.path.expanduser(token_dir)
            # Create token directory if it doesn't exist
            os.makedirs(token_dir, exist_ok=True)
            self.token_file = os.path.join(token_dir, self.token_file)

        self.npsso_token = None
        self.mobile_token = None
        self.web_cookies = {}

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
                SSO_COOKIE_URL,
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

            with open(self.token_file, 'w', encoding='utf-8') as f:
                json.dump(token_data, f)

            # Set secure permissions
            os.chmod(self.token_file, 0o600)  # Only user can read/write

            logger.debug(f"Saved token to {self.token_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving token: {str(e)}")
            return False

    def _load_token(self) -> bool:
        """Load the NPSSO token from the token file if it exists"""
        try:
            if not os.path.exists(self.token_file):
                logger.debug(f"Token file {self.token_file} does not exist")
                return False

            with open(self.token_file, 'r', encoding='utf-8') as f:
                token_data = json.load(f)

            if "npsso" not in token_data:
                logger.debug("Token file does not contain NPSSO token")
                return False

            self.npsso_token = token_data["npsso"]
            self.web_cookies = self._get_web_cookies()

            logger.debug(f"Loaded token from {self.token_file}")
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
                SSO_COOKIE_URL,
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
        if os.path.exists(self.token_file):
            try:
                os.remove(self.token_file)
                logger.debug(f"Removed token file {self.token_file}")
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

            logger.debug(f"Getting authorization code from {MOBILE_CODE_URL}")
            code_response = requests.get(
                MOBILE_CODE_URL,
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
                    'Authorization': f'Basic {MOBILE_TOKEN_AUTH}',
                    'Content-Type': 'application/x-www-form-urlencoded'
                }

                token_data = {
                    'code': code,
                    'redirect_uri': 'com.scee.psxandroid.scecompcall://redirect',
                    'grant_type': 'authorization_code',
                    'token_format': 'jwt'
                }

                logger.debug(f"Exchanging code for token at {MOBILE_TOKEN_URL}")
                token_response = requests.post(
                    MOBILE_TOKEN_URL,
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
                url = MOBILE_PLAYED_GAMES_URL % offset

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
                url = TROPHIES_MOBILE_URL % offset

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

    def get_cover_image_url(self, game_data: Dict[str, Any]) -> Optional[str]:
        """
        Get the cover image URL from the game data

        Args:
            game_data: The game data dictionary

        Returns:
            The URL of the cover image, or None if not found
        """
        # Try different image sources in priority order
        if 'image' in game_data and game_data['image']:
            return game_data['image']
        elif 'imageUrl' in game_data and game_data['imageUrl']:
            return game_data['imageUrl']
        elif 'images' in game_data and game_data['images']:
            images = game_data['images']
            if len(images) > 0 and 'url' in images[0]:
                return images[0]['url']

        logger.debug(f"No image URL found for game: {game_data.get('name', 'Unknown')}")
        return None

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

    def scan(self, source: Source, progress_callback: Optional[callable] = None) -> Tuple[int, List[str]]:
        """
        Scan a PlayStation Network source for games and add them to the library.
        Implements the SourceScanner interface.

        Args:
            source: The source to scan
            progress_callback: Optional callback function for progress updates

        Returns:
            Tuple of (number of games added/updated, list of error messages)
        """
        added_count = 0
        updated_count = 0
        errors = []

        # Initial progress update
        if progress_callback:
            try:
                progress_callback(0, 100, "Initializing PlayStation Network client...")
            except Exception as e:
                logger.error(f"Error with progress callback: {e}")

        try:
            # Check if we need to authenticate
            if not self.is_authenticated():
                # Get detailed auth status to provide better error messages
                auth_status = self.check_authentication()
                logger.debug(f"PSN authentication status: {auth_status}")

                error_message = "PlayStation Network authentication required."

                if progress_callback:
                    try:
                        progress_callback(10, 100, error_message)
                    except Exception as e:
                        logger.error(f"Error with progress callback: {e}")

                # Return error message with instructions
                return 0, [f"{error_message} Please click the 'Authenticate with PlayStation' button in the source settings."]

            # Update progress
            if progress_callback:
                try:
                    progress_callback(30, 100, "Fetching PlayStation Network library...")
                except Exception as e:
                    logger.error(f"Error with progress callback: {e}")

            # Get PSN library data
            psn_data = self.fetch_all_data()
            psn_games = psn_data.get('games', [])
            psn_trophies = psn_data.get('trophies', [])

            # Log trophy data summary
            trophy_pairs = [(t.get('trophyTitleName', 'unknown'), t.get('npCommunicationId', 'unknown')) for t in psn_trophies]
            logger.debug(f"Loaded {len(psn_trophies)} trophy titles, first 5 title-ID pairs:")
            for i, (name, npc_id) in enumerate(trophy_pairs[:5]):
                logger.debug(f"  {i+1}. '{name}' - {npc_id}")

            # Store raw JSON data in the source directory
            source_dir = self.data_handler.sources_dir / source.id
            json_path = source_dir / "psn_data.json"

            try:
                # Save the raw JSON data
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(psn_data, f, indent=2)
                logger.info(f"Saved raw PSN data to {json_path}")
            except Exception as e:
                errors.append(f"Error saving PSN data: {e}")
                logger.error(f"Error saving PSN data to {json_path}: {e}")

            # Get existing games from this source
            existing_games_by_title = {}
            for game in self.data_handler.load_games():
                if game.source == source.id:
                    existing_games_by_title[game.title.lower()] = game

            # Update progress
            total_games = len(psn_games)
            if progress_callback:
                try:
                    progress_callback(40, 100, f"Processing {total_games} games...")
                except Exception as e:
                    logger.error(f"Error with progress callback: {e}")

            # Process each game
            for index, game_data in enumerate(psn_games):
                try:
                    # Report progress
                    if progress_callback and index % 10 == 0:
                        try:
                            percentage = 40 + int((index / total_games) * 60)
                            progress_callback(percentage, 100, f"Processing game {index+1}/{total_games}")
                        except Exception as e:
                            logger.error(f"Error with progress callback: {e}")

                    # Get game details
                    title = game_data.get('name', 'Unknown Game')
                    game_id = game_data.get('titleId', '')

                    # Add debug logging
                    logger.debug(f"Processing PSN game: {title} (ID: {game_id})")

                    # Check if game already exists
                    if title.lower() in existing_games_by_title:
                        # Game exists, update play data which can change when user plays on console
                        existing_game = existing_games_by_title[title.lower()]
                        logger.info(f"Game {title} already exists, updating play data")

                        # Track if any updates were made to this game
                        game_updated = False

                        # Extract and set play duration
                        play_duration_iso = game_data.get('playDuration')
                        if play_duration_iso and isinstance(play_duration_iso, str):
                            try:
                                # Parse ISO 8601 duration format
                                logger.debug(f"Play duration from PSN for {title}: {play_duration_iso}")

                                # Parse using isodate library
                                duration = isodate.parse_duration(play_duration_iso)
                                total_seconds = int(duration.total_seconds())

                                if total_seconds > 0:
                                    # Only update if the new value is greater than the existing one
                                    existing_play_time = existing_game.play_time if existing_game.play_time is not None else 0
                                    if total_seconds > existing_play_time:
                                        logger.debug(f"Updating play time for {title} from {existing_play_time} to {total_seconds} seconds")

                                        # Update play time
                                        if self.data_handler.update_play_time(existing_game, total_seconds):
                                            existing_game.play_time = total_seconds
                                            logger.debug(f"Updated play time for {title}")
                                            game_updated = True
                                        else:
                                            logger.warning(f"Failed to update play time for {title}")
                                    else:
                                        logger.debug(f"PSN play time ({total_seconds}s) not greater than existing play time ({existing_play_time}s), skipping update")
                            except Exception as duration_err:
                                logger.warning(f"Failed to parse play duration for {title}: {duration_err}")

                        # Update play count
                        play_count = game_data.get('playCount', 0)
                        if play_count and isinstance(play_count, int) and play_count > 0:
                            # Only update if the new count is greater than the existing one
                            existing_count = existing_game.play_count if existing_game.play_count is not None else 0
                            if play_count > existing_count:
                                logger.debug(f"Updating play count for {title} from {existing_game.play_count} to {play_count}")

                                # Update play count
                                if self.data_handler.update_play_count(existing_game, play_count):
                                    existing_game.play_count = play_count
                                    logger.debug(f"Updated play count for {title}")
                                    game_updated = True

                                    # Mark as played if not already
                                    if existing_game.completion_status == CompletionStatus.NOT_PLAYED:
                                        if self.data_handler.update_completion_status(existing_game, CompletionStatus.PLAYED):
                                            existing_game.completion_status = CompletionStatus.PLAYED
                                            logger.debug(f"Updated completion status for {title} to PLAYED based on play count")
                                            game_updated = True
                                else:
                                    logger.warning(f"Failed to update play count for {title}")
                            else:
                                logger.debug(f"PSN play count ({play_count}) not greater than existing play count ({existing_game.play_count}), skipping update")

                        # Check trophy data to determine if game is completed or just played (regardless of play count)
                        # Some games don't have npCommunicationId directly in the game data but might be available in trophies
                        playstation_id = game_data.get('npCommunicationId', '')

                        # If we don't have an ID directly, try to find it by normalized title match in trophies
                        if not playstation_id:
                            # Normalize the game title (remove special chars, lowercase)
                            normalized_title = re.sub(r'[^\w\s]', '', title).lower().strip()
                            logger.debug(f"Looking for trophy data with normalized title: '{normalized_title}'")

                            for trophy_title in psn_trophies:
                                trophy_name = trophy_title.get('trophyTitleName', '')
                                # Normalize trophy name
                                normalized_trophy_name = re.sub(r'[^\w\s]', '', trophy_name).lower().strip()

                                if normalized_trophy_name == normalized_title:
                                    playstation_id = trophy_title.get('npCommunicationId', '')
                                    if playstation_id:
                                        logger.debug(f"Found trophy ID {playstation_id} for {title} via normalized title match ('{trophy_name}')")
                                        break

                        logger.debug(f"Checking trophy data for existing game {title}, ID: {playstation_id}")
                        if not playstation_id:
                            logger.debug(f"No trophy ID found for game {title}. Cannot check trophy completion status.")
                        elif playstation_id:
                            # Look for matching trophy data
                            trophy_match_found = False
                            for trophy_title in psn_trophies:
                                if trophy_title.get('npCommunicationId') == playstation_id:
                                    # Check trophy completion using the progress field
                                    progress = trophy_title.get('progress', 0)
                                    logger.debug(f"Trophy progress for {title}: {progress}%")

                                    # Just for logging, get counts if available
                                    trophy_earned = trophy_title.get('earnedTrophies', {}).get('total', 0)
                                    trophy_total = trophy_title.get('definedTrophies', {}).get('total', 0)

                                    # If 100% progress, mark as COMPLETED
                                    if progress == 100:
                                        logger.debug(f"Game {title} has 100% trophy completion: {trophy_earned}/{trophy_total}")
                                        if existing_game.completion_status != CompletionStatus.COMPLETED:
                                            if self.data_handler.update_completion_status(existing_game, CompletionStatus.COMPLETED):
                                                existing_game.completion_status = CompletionStatus.COMPLETED
                                                logger.debug(f"Updated completion status for {title} to COMPLETED (100% trophies)")
                                                game_updated = True
                                        else:
                                            logger.debug(f"Game {title} already marked as COMPLETED, no status update needed")
                                    # Otherwise, mark as PLAYED if not already and we have some trophies
                                    elif trophy_earned > 0 and existing_game.completion_status == CompletionStatus.NOT_PLAYED:
                                        if self.data_handler.update_completion_status(existing_game, CompletionStatus.PLAYED):
                                            existing_game.completion_status = CompletionStatus.PLAYED
                                            logger.debug(f"Updated completion status for {title} to PLAYED (has {trophy_earned} trophies)")
                                            game_updated = True

                                    # Mark that we found a trophy match
                                    trophy_match_found = True
                                    # Break after finding a match
                                    break

                            if not trophy_match_found:
                                logger.debug(f"No trophy data found for game {title} with ID {playstation_id}")

                        # If no trophy data but has play count, mark as PLAYED if not already
                        if (playstation_id is None and existing_game.play_count is not None and
                            existing_game.play_count > 0 and existing_game.completion_status == CompletionStatus.NOT_PLAYED):
                            if self.data_handler.update_completion_status(existing_game, CompletionStatus.PLAYED):
                                existing_game.completion_status = CompletionStatus.PLAYED
                                logger.debug(f"Updated completion status for {title} to PLAYED")
                                game_updated = True

                        # Update last played time if available
                        last_played_iso = game_data.get('lastPlayedDateTime')
                        if last_played_iso and isinstance(last_played_iso, str):
                            try:
                                # Parse ISO 8601 datetime
                                dt = datetime.fromisoformat(last_played_iso.replace('Z', '+00:00'))
                                unix_timestamp = dt.timestamp()

                                # Get current last played time
                                current_last_played = existing_game.get_last_played_time(self.data_handler.data_dir)

                                # Only update if new timestamp is more recent
                                if current_last_played is None or unix_timestamp > current_last_played:
                                    logger.debug(f"Updating last played time for {title} from {current_last_played} to {unix_timestamp}")

                                    # Set last played time
                                    if self.data_handler.set_last_played_time(existing_game, unix_timestamp):
                                        logger.debug(f"Updated last played time for {title} to {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                                        game_updated = True
                                    else:
                                        logger.warning(f"Failed to update last played time for {title}")
                                else:
                                    logger.debug(f"PSN last played time ({dt.strftime('%Y-%m-%d %H:%M:%S')}) not more recent than existing last played time, skipping update")
                            except Exception as dt_err:
                                logger.warning(f"Failed to parse last played date for {title}: {dt_err}")

                        # Update first played time if available and not already set
                        first_played_iso = game_data.get('firstPlayedDateTime')
                        if first_played_iso and isinstance(first_played_iso, str):
                            try:
                                # Parse ISO 8601 datetime
                                dt = datetime.fromisoformat(first_played_iso.replace('Z', '+00:00'))
                                unix_timestamp = dt.timestamp()

                                # Only update if not already set
                                if existing_game.first_played is None:
                                    logger.debug(f"Setting first played time for {title} to {unix_timestamp}")

                                    # Set first played time
                                    if self.data_handler.set_first_played_time(existing_game, unix_timestamp):
                                        logger.debug(f"Set first played time for {title} to {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                                        game_updated = True
                                    else:
                                        logger.warning(f"Failed to set first played time for {title}")
                                else:
                                    logger.debug(f"First played time already set for {title}, skipping update")
                            except Exception as dt_err:
                                logger.warning(f"Failed to parse first played date for {title}: {dt_err}")

                        # If any updates were made to this game, increment the updated count
                        if game_updated:
                            updated_count += 1
                            logger.info(f"Game {title} was successfully updated")

                        # Skip the rest of the processing for existing games
                        continue

                    # Create a new game
                    game = Game(
                        id="",  # ID will be assigned by data handler
                        title=title,
                        source=source.id
                    )

                    # Extract platform info
                    platform_enums = []
                    platform_str = game_data.get('platform', '')

                    try:
                        # Map platform string to our platform enum
                        mapped_platform = Platforms.try_from_string(platform_str)
                        if mapped_platform:
                            platform_enums.append(mapped_platform)
                        else:
                            logger.warning(f"Unable to map platform '{platform_str}'")

                        logger.debug(f"Mapped platforms for {title}: {[p.value for p in platform_enums]}")

                        if platform_enums:
                            game.platforms = platform_enums
                            logger.debug(f"Platforms set successfully for {title}")
                    except Exception as e:
                        logger.error(f"ERROR setting platforms for {title}: {e}. Platform: {platform_str}")
                        # Debug information to help diagnose platform mapping issues
                        logger.debug(f"Platform enum values: {[p.name for p in Platforms]}")

                    # Map genres from concept.genres if available
                    genres_data = []

                    # Check if concept field exists and has genres
                    if 'concept' in game_data and isinstance(game_data['concept'], dict):
                        # Get genres from concept
                        genres_data = game_data['concept'].get('genres', [])

                    logger.debug(f"Game {title} has concept.genres: {genres_data}")

                    if genres_data:
                        genre_enums = []
                        for genre in genres_data:
                            # Convert genre to uppercase for comparison
                            genre_upper = genre.upper() if genre else ""
                            logger.debug(f"Processing genre: '{genre}'")

                            # Use enhanced enum mapping
                            mapped_genre = Genres.try_from_string(genre)
                            if mapped_genre:
                                genre_enums.append(mapped_genre)
                                logger.debug(f"Mapped PSN genre '{genre}' to {mapped_genre.value}")
                            else:
                                logger.warning(f"Unable to map PSN genre '{genre}' for '{title}'")

                        # Set genres if we found any
                        if genre_enums:
                            try:
                                game.genres = genre_enums
                                logger.debug(f"Set genres for {title}: {[g.value for g in genre_enums]}")
                            except Exception as e:
                                logger.error(f"ERROR setting genres for {title}: {e}")
                        else:
                            logger.debug(f"No genres were mapped for {title}")

                    # Map regions from concept.country field
                    region_enums = []

                    # Check if concept field exists
                    if 'concept' in game_data and isinstance(game_data['concept'], dict):
                        # Get country from concept
                        country = game_data['concept'].get('country', '')

                        if country:
                            try:
                                # Map country code to region enum
                                # TODO: Investigate correct values for EU countries and ASIA regions
                                if country == "US":
                                    region_enums.append(Regions.USA)
                                elif country == "JP":
                                    region_enums.append(Regions.JAPAN)
                                else:
                                    logger.warning(f"Unknown country code '{country}' for game {title} - not mapped to any region")

                                logger.debug(f"Mapped country '{country}' to region for {title}")
                            except Exception as e:
                                logger.warning(f"Could not map country '{country}' to region: {e}")

                    # Set regions if we found any
                    if region_enums:
                        try:
                            game.regions = region_enums
                            logger.debug(f"Set regions for {title}: {[r.value for r in region_enums]}")
                        except Exception as e:
                            logger.error(f"ERROR setting regions for {title}: {e}")

                    # Extract play time and last played date if available
                    play_duration_iso = game_data.get('playDuration')
                    if play_duration_iso and isinstance(play_duration_iso, str):
                        try:
                            # Parse ISO 8601 duration format (e.g., "PT241H37M53S")
                            logger.debug(f"Play duration from PSN for {title}: {play_duration_iso}")

                            # Parse using isodate library
                            duration = isodate.parse_duration(play_duration_iso)
                            total_seconds = int(duration.total_seconds())

                            if total_seconds > 0:
                                game.play_time = total_seconds
                                hours, remainder = divmod(total_seconds, 3600)
                                minutes, seconds = divmod(remainder, 60)
                                logger.debug(f"Set play time for {title}: {total_seconds} seconds ({hours}h {minutes}m {seconds}s)")
                        except Exception as duration_err:
                            logger.warning(f"Failed to parse play duration for {title}: {duration_err}")

                    # Extract last played date (will be used when saving play count)
                    last_played = game_data.get('lastPlayedDateTime')
                    play_count = game_data.get('playCount', 0)

                    # If game has been played, set play count
                    if play_count and isinstance(play_count, int) and play_count > 0:
                        game.play_count = play_count
                        logger.debug(f"Set play count for {title}: {play_count}")

                        # If game has been played, mark as played
                        if game.completion_status == CompletionStatus.NOT_PLAYED:
                            game.completion_status = CompletionStatus.PLAYED
                            logger.debug(f"Game {title} marked as played based on play count")

                    # Handle trophy data to determine completion status
                    playstation_id = game_data.get('npCommunicationId', '')

                    # If we don't have an ID directly, try to find it by normalized title match in trophies
                    if not playstation_id:
                        # Normalize the game title (remove special chars, lowercase)
                        normalized_title = re.sub(r'[^\w\s]', '', title).lower().strip()
                        logger.debug(f"Looking for trophy data with normalized title: '{normalized_title}'")

                        for trophy_title in psn_trophies:
                            trophy_name = trophy_title.get('trophyTitleName', '')
                            # Normalize trophy name
                            normalized_trophy_name = re.sub(r'[^\w\s]', '', trophy_name).lower().strip()

                            if normalized_trophy_name == normalized_title:
                                playstation_id = trophy_title.get('npCommunicationId', '')
                                if playstation_id:
                                    logger.debug(f"Found trophy ID {playstation_id} for {title} via normalized title match ('{trophy_name}')")
                                    break

                    logger.debug(f"Checking trophy data for new game {title}, ID: {playstation_id}")
                    if not playstation_id:
                        logger.debug(f"No trophy ID found for game {title}. Cannot check trophy completion status.")
                    elif playstation_id:
                        # Look for matching trophy data
                        for trophy_title in psn_trophies:
                            if trophy_title.get('npCommunicationId') == playstation_id:
                                # Found matching trophy title
                                # Check trophy completion using the progress field
                                progress = trophy_title.get('progress', 0)
                                logger.debug(f"Trophy progress for {title}: {progress}%")

                                # Just for logging, get counts if available
                                trophy_earned = trophy_title.get('earnedTrophies', {}).get('total', 0)
                                trophy_total = trophy_title.get('definedTrophies', {}).get('total', 0)

                                # If 100% progress, mark as COMPLETED
                                if progress == 100:
                                    game.completion_status = CompletionStatus.COMPLETED
                                    logger.debug(f"Game {title} marked as COMPLETED (100% trophies)")

                                    # Set play count to at least 1 if it's not already set
                                    if game.play_count == 0:
                                        game.play_count = 1

                                # Otherwise, mark as PLAYED if trophies earned
                                elif trophy_earned > 0 and game.play_count == 0:
                                        game.play_count = 1
                                        game.completion_status = CompletionStatus.PLAYED
                                        logger.debug(f"Game {title} marked as PLAYED with {trophy_earned} trophies earned")

                                # Stop looking after finding a match
                                break

                    # Get cover image URL if available
                    image_url = self.get_cover_image_url(game_data)

                    if image_url:
                        # Check if we should download images automatically
                        download_images = source.config.get("download_images", True)

                        if download_images:
                            # Store the URL in game.image so we can download it after game is saved
                            logger.debug(f"Found cover image URL for {title}: {image_url}")
                            game.image = image_url
                        else:
                            logger.debug(f"Skipping image download for {title} (disabled in source settings)")

                    # Save the game
                    if self.data_handler.save_game(game):
                        # After the game is saved with an ID, save the playtime separately
                        if hasattr(game, 'play_time') and game.play_time is not None and game.play_time > 0:
                            # Use the data_handler method to save play time
                            if not self.data_handler.update_play_time(game, game.play_time):
                                logger.warning(f"Failed to save play time for {game.title}")
                            else:
                                logger.debug(f"Saved play time of {game.play_time} seconds for {game.title}")

                        # Save play count if set
                        if hasattr(game, 'play_count') and game.play_count is not None and game.play_count > 0:
                            if not self.data_handler.update_play_count(game, game.play_count):
                                logger.warning(f"Failed to save play count for {game.title}")
                            else:
                                logger.debug(f"Saved play count of {game.play_count} for {game.title}")

                                # Handle last played datetime if available
                                last_played_iso = game_data.get('lastPlayedDateTime')
                                if last_played_iso:
                                    logger.debug(f"Last played timestamp from PSN for {game.title}: {last_played_iso}")
                                    try:
                                        # Parse the ISO 8601 datetime and convert to Unix timestamp
                                        # Format example: "2020-09-16T15:02:44.630000Z"
                                        dt = datetime.fromisoformat(last_played_iso.replace('Z', '+00:00'))
                                        unix_timestamp = dt.timestamp()

                                        # Use data_handler to set the last played time
                                        if self.data_handler.set_last_played_time(game, unix_timestamp):
                                            logger.debug(f"Set last played time for {game.title} to {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                                        else:
                                            logger.warning(f"Failed to set last played time for {game.title}")
                                    except Exception as dt_err:
                                        logger.warning(f"Failed to parse last played date for {game.title}: {dt_err}")

                                # Handle first played datetime if available
                                first_played_iso = game_data.get('firstPlayedDateTime')
                                if first_played_iso:
                                    logger.debug(f"First played timestamp from PSN for {game.title}: {first_played_iso}")
                                    try:
                                        # Parse the ISO 8601 datetime and convert to Unix timestamp
                                        # Format example: "2018-06-16T15:00:01.520000Z"
                                        dt = datetime.fromisoformat(first_played_iso.replace('Z', '+00:00'))
                                        unix_timestamp = dt.timestamp()

                                        # Use data_handler to set the first played time
                                        if self.data_handler.set_first_played_time(game, unix_timestamp):
                                            logger.debug(f"Set first played time for {game.title} to {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                                        else:
                                            logger.warning(f"Failed to set first played time for {game.title}")
                                    except Exception as dt_err:
                                        logger.warning(f"Failed to parse first played date for {game.title}: {dt_err}")

                        # Download and save the cover image if URL is available
                        if hasattr(game, 'image') and game.image and source.config.get("download_images", True):
                            try:
                                # Use CoverFetcher to download and save the image
                                cover_fetcher = CoverFetcher(self.data_handler)
                                success, error = cover_fetcher.fetch_and_save_for_game(
                                    game.id,
                                    game.image,
                                    source_name="PlayStation"
                                )

                                if success:
                                    logger.debug(f"Cover image downloaded and saved successfully for {game.title}")
                                else:
                                    logger.warning(f"Failed to download/save cover image for {game.title}: {error}")
                            except Exception as img_err:
                                logger.error(f"Error processing cover image for {game.title}: {img_err}")

                        added_count += 1
                    else:
                        errors.append(f"Failed to save game '{title}'")

                except Exception as e:
                    game_name = game_data.get('name', 'Unknown')
                    logger.error(f"Error processing game {game_name}: {e}")
                    logger.error(traceback.format_exc())
                    errors.append(f"Error processing game {game_name}: {e}")

            # Final progress update
            if progress_callback:
                try:
                    if added_count > 0 and updated_count > 0:
                        message = f"Added {added_count} games, updated {updated_count} games"
                    elif added_count > 0:
                        message = f"Added {added_count} games"
                    elif updated_count > 0:
                        message = f"Updated {updated_count} existing games"
                    else:
                        message = "No changes"

                    progress_callback(100, 100, message)
                except Exception as e:
                    logger.error(f"Error with final progress callback: {e}")

            # Return both added and updated counts separately as a tuple
            return (added_count, updated_count), errors

        except Exception as e:
            if progress_callback:
                try:
                    progress_callback(100, 100, f"Error: {e}")
                except Exception as callback_error:
                    logger.error(f"Error with error progress callback: {callback_error}")

            logger.error(f"Error syncing PSN source: {e}")
            logger.error(traceback.format_exc())
            return (0, 0), [f"Error syncing PSN source: {e}"]
