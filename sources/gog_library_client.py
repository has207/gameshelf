#!/usr/bin/env python3
"""
GOG Library Client

This script provides functionality to authenticate with GOG and retrieve a user's
owned games. It runs authentication in a separate process to avoid GTK version conflicts.
"""

import os
import sys
import json
import time
import subprocess
import requests
import logging
import traceback
import fcntl
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from sources.scanner_base import SourceScanner
from data import Source, Game
from data_mapping import Platforms, Genres, CompletionStatus
from cover_fetch import CoverFetcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class GogLibraryClient(SourceScanner):
    """Client for GOG authentication and game library retrieval"""

    def __init__(self, data_handler=None, data_dir: Optional[str] = None):
        """
        Initialize the GOG client

        Args:
            data_handler: The data handler instance to use (can be None for standalone usage)
            data_dir: Directory to store authentication tokens and cache
                     If None, defaults to ~/.gog_library
        """
        # Initialize SourceScanner if data_handler is provided
        if data_handler:
            super().__init__(data_handler)

        # Set up data directory
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path.home() / ".gog_library"

        # Create directory if it doesn't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Set up token and cache paths
        self.tokens_path = self.data_dir / "gog_tokens.json"

        # GOG OAuth constants
        self.client_id = "46899977096215655"
        self.client_secret = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9"
        self.redirect_uri = "https://embed.gog.com/on_login_success?origin=client"

        # GOG API endpoints
        self.token_url = "https://auth.gog.com/token"
        self.embed_api_url = "https://embed.gog.com/account/getFilteredProducts"
        self.user_data_url = "https://embed.gog.com/userData.json"

    def authenticate(self):
        """
        Initiate GOG authentication flow using GTK WebView in a separate process

        Returns:
            bool: True if authentication succeeded, False otherwise
        """
        logger.info("Starting GOG authentication process...")

        # Get the path to the auth helper script
        current_dir = Path(__file__).parent
        auth_helper_path = current_dir / "gog_auth_helper.py"

        # Check if the helper script exists
        if not auth_helper_path.exists():
            logger.error(f"Error: Authentication helper script not found at {auth_helper_path}")
            return False

        try:
            # Make sure the helper script is executable
            os.chmod(auth_helper_path, 0o755)

            # Run the authentication helper as a completely separate process
            # This ensures no GTK version conflicts
            cmd = [
                sys.executable,
                str(auth_helper_path)
            ]

            logger.info("Starting authentication process in separate process...")

            # Use Popen instead of run so we can detach the process
            # This prevents the main app from waiting and becoming unresponsive
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                # Set start_new_session=True to completely detach the process
                start_new_session=True
            )

            # Wait for the process to complete, but don't let it hang
            # the main application if it takes too long
            try:
                stdout, stderr = process.communicate(timeout=5*60)  # 5 minute timeout
                exit_code = process.returncode

                if exit_code != 0:
                    logger.error(f"Authentication process failed with exit code {exit_code}")
                    logger.error(f"Error: {stderr}")
                    return False

                # Parse the JSON output from the helper script
                try:
                    # Remove any extra text before the JSON
                    json_start = stdout.find('{')
                    if json_start >= 0:
                        json_str = stdout[json_start:]
                        auth_result = json.loads(json_str)
                        if 'error' in auth_result:
                            logger.error(f"Authentication error: {auth_result['error']}")
                            return False
                        elif 'code' in auth_result:
                            auth_code = auth_result['code']
                        else:
                            logger.error("Unexpected authentication result")
                            return False
                    else:
                        logger.error("No JSON found in authentication output")
                        logger.debug(f"Output: {stdout}")
                        return False
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse authentication result: {e}")
                    logger.debug(f"Output: {stdout}")
                    logger.debug(f"Error: {stderr}")
                    return False

            except subprocess.TimeoutExpired:
                # Process took too long, the user probably closed the window
                logger.error("Authentication timeout - process took too long")
                process.terminate()
                try:
                    process.wait(timeout=5)  # Give it 5 seconds to terminate gracefully
                except subprocess.TimeoutExpired:
                    process.kill()  # Force kill if it doesn't terminate
                return False

        except Exception as e:
            logger.error(f"Error running authentication: {e}")
            return False

        try:
            # Check if we got an authorization code
            if not auth_code:
                logger.error("Authentication failed or was cancelled.")
                return False
        except UnboundLocalError:
            # Handle case where auth_code was never set
            logger.error("Authentication process did not complete properly")
            return False

        # Exchange the code for tokens
        return self._authenticate_with_auth_code(auth_code)

    def _authenticate_with_auth_code(self, auth_code: str) -> bool:
        """
        Exchange an authorization code for OAuth tokens

        Args:
            auth_code: The authorization code from the login process

        Returns:
            bool: True if token exchange succeeded, False otherwise
        """
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

            response = requests.post(self.token_url, data=data, headers=headers)
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
                'created_at': time.time(),
                'refresh_count': 0
            }

            # Save the tokens atomically
            self._save_tokens_atomic(tokens)

            logger.info("Authentication successful, tokens saved")
            return True

        except Exception as e:
            logger.error(f"Failed to exchange auth code for tokens: {e}")
            return False

    def is_authenticated(self) -> bool:
        """
        Enhanced authentication check with integrity validation and automatic refresh

        Returns:
            bool: True if authenticated with valid tokens, False otherwise
        """
        tokens = self._load_tokens()
        if not tokens or not self._validate_token_integrity(tokens):
            return False

        if self._is_token_expired(tokens):
            return self._refresh_tokens(tokens)

        return True

    def _validate_token_integrity(self, tokens: Dict[str, Any]) -> bool:
        """
        Validate token structure and required fields

        Args:
            tokens: Token dictionary to validate

        Returns:
            bool: True if token structure is valid
        """
        required_fields = ['access_token', 'refresh_token', 'expires_at', 'token_type']
        return all(field in tokens and tokens[field] for field in required_fields)

    def _is_token_expired(self, tokens: Dict[str, Any], buffer_seconds: int = 300) -> bool:
        """
        Check if token is expired with configurable buffer

        Args:
            tokens: Token dictionary to check
            buffer_seconds: Safety buffer in seconds (default: 5 minutes)

        Returns:
            bool: True if token is expired or will expire soon
        """
        expires_at = tokens.get('expires_at', 0)
        return time.time() >= (expires_at - buffer_seconds)

    def _refresh_tokens(self, tokens: Dict[str, Any], max_retries: int = 3) -> bool:
        """
        Enhanced token refresh with retry logic and rotation support

        Args:
            tokens: The current tokens dictionary
            max_retries: Maximum number of retry attempts

        Returns:
            bool: True if token refresh succeeded, False otherwise
        """
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            logger.error("No refresh token available")
            return False

        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting to refresh tokens (attempt {attempt + 1}/{max_retries})")

                data = {
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'grant_type': 'refresh_token',
                    'refresh_token': refresh_token
                }

                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'User-Agent': 'GOGGalaxyClient/2.0.12.3 (GameShelf)'
                }

                response = requests.post(
                    self.token_url,
                    data=data,
                    headers=headers,
                    timeout=10
                )
                response.raise_for_status()

                token_data = response.json()

                # Handle token rotation - use new refresh token if provided
                new_refresh_token = token_data.get('refresh_token', refresh_token)

                updated_tokens = {
                    'access_token': token_data['access_token'],
                    'refresh_token': new_refresh_token,
                    'token_type': token_data.get('token_type', 'Bearer'),
                    'expires_in': token_data.get('expires_in', 3600),
                    'expires_at': time.time() + token_data.get('expires_in', 3600),
                    'scope': token_data.get('scope', ''),
                    'updated_at': time.time(),
                    'refresh_count': tokens.get('refresh_count', 0) + 1
                }

                self._save_tokens_atomic(updated_tokens)
                logger.info("Successfully refreshed authentication tokens")
                return True

            except requests.exceptions.RequestException as e:
                logger.warning(f"Token refresh attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                else:
                    logger.error("All token refresh attempts failed")

        return False

    def _load_tokens(self) -> Optional[Dict[str, Any]]:
        """
        Enhanced token loading with backup recovery

        Returns:
            dict: Dictionary of token data or None if not found/valid
        """
        try:
            return self._load_tokens_safe()
        except Exception as e:
            logger.warning(f"Failed to load tokens, attempting backup restoration: {e}")
            if self._restore_from_backup():
                return self._load_tokens_safe()
            return None

    def _load_tokens_safe(self) -> Optional[Dict[str, Any]]:
        """
        Safely load tokens with file locking

        Returns:
            dict: Dictionary of token data or None if not found/valid
        """
        if not self.tokens_path.exists():
            return None

        try:
            with open(self.tokens_path, 'r') as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)  # Shared lock for reading
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load tokens: {e}")
            return None

    def _save_tokens_atomic(self, tokens: Dict[str, Any]) -> None:
        """
        Atomically save tokens to prevent corruption from concurrent access

        Args:
            tokens: Token dictionary to save
        """
        # Create backup before saving new tokens
        self._backup_tokens()

        # Create a temporary file in the same directory
        temp_path = self.tokens_path.with_suffix('.tmp')

        try:
            with open(temp_path, 'w') as f:
                # Lock the file for exclusive access
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                json.dump(tokens, f, indent=4)
                f.flush()
                os.fsync(f.fileno())  # Force write to disk

            # Atomic move to final location
            temp_path.replace(self.tokens_path)

            # Set secure permissions
            os.chmod(self.tokens_path, 0o600)

        except Exception as e:
            logger.error(f"Failed to save tokens: {e}")
            if temp_path.exists():
                temp_path.unlink()
            raise

    def _backup_tokens(self) -> bool:
        """
        Create a backup of current tokens

        Returns:
            bool: True if backup was successful
        """
        if not self.tokens_path.exists():
            return False

        backup_path = self.tokens_path.with_suffix('.backup')
        try:
            shutil.copy2(self.tokens_path, backup_path)
            os.chmod(backup_path, 0o600)
            return True
        except Exception as e:
            logger.debug(f"Failed to backup tokens: {e}")
            return False

    def _restore_from_backup(self) -> bool:
        """
        Restore tokens from backup if main file is corrupted

        Returns:
            bool: True if restoration was successful
        """
        backup_path = self.tokens_path.with_suffix('.backup')
        if not backup_path.exists():
            return False

        try:
            with open(backup_path, 'r') as f:
                tokens = json.load(f)

            if self._validate_token_integrity(tokens):
                shutil.copy2(backup_path, self.tokens_path)
                logger.info("Successfully restored tokens from backup")
                return True
        except Exception as e:
            logger.error(f"Failed to restore from backup: {e}")

        return False

    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Get basic account information."""
        if not self.is_authenticated():
            return None

        tokens = self._load_tokens()
        if not tokens:
            return None

        try:
            headers = {
                'Authorization': f"Bearer {tokens['access_token']}",
                'User-Agent': 'GOGGalaxyClient/2.0.12.3 (Windows 10)',
                'Accept': 'application/json'
            }

            # Try the embed account info endpoint
            response = requests.get(self.user_data_url, headers=headers)
            if response.status_code == 200:
                user_data = response.json()
                username = user_data.get('username') or user_data.get('nick') or user_data.get('publicName')
                return {
                    'username': username,
                    'userId': user_data.get('userId'),
                    'email': user_data.get('email')
                }

            # Return a default response if we can't get user info
            return {'username': 'GOG User'}

        except requests.RequestException as e:
            logger.debug(f"Failed to get account info: {e}")
            return {'username': 'GOG User'}

    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """
        Get basic user account information including galaxyUserId

        Returns:
            dict: User account info or None if failed
        """
        if not self.is_authenticated():
            return None

        tokens = self._load_tokens()

        try:
            headers = {
                'Authorization': f"Bearer {tokens['access_token']}",
                'User-Agent': 'Mozilla/5.0'
            }

            response = requests.get(self.user_data_url, headers=headers)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            return None

    def get_game_playtime(self, game_id: str) -> Optional[int]:
        """
        Get playtime for a specific game using GOG's gameplay API

        Args:
            game_id: GOG game ID

        Returns:
            int: Playtime in minutes, or None if failed
        """
        if not self.is_authenticated():
            return None

        user_info = self.get_user_info()
        if not user_info or 'galaxyUserId' not in user_info:
            logger.warning("No galaxyUserId available for playtime lookup")
            return None

        tokens = self._load_tokens()
        galaxy_user_id = user_info['galaxyUserId']

        try:
            headers = {
                'Authorization': f"Bearer {tokens['access_token']}",
                'User-Agent': 'Mozilla/5.0'
            }

            url = f"https://gameplay.gog.com/games/{game_id}/users/{galaxy_user_id}/sessions"
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            playtime_minutes = data.get('time_sum', 0)

            if playtime_minutes > 0:
                logger.debug(f"Retrieved playtime for {game_id}: {playtime_minutes} minutes")

            return playtime_minutes

        except Exception as e:
            logger.debug(f"Failed to get playtime for {game_id}: {e}")
            return None

    def get_owned_games_with_stats(self, show_progress=True) -> List[Dict[str, Any]]:
        """
        Get all games owned by the authenticated user with playtime stats

        This will prompt the user to log in via webview to fetch playtime stats.

        Args:
            show_progress: Whether to display progress information

        Returns:
            list: List of game dictionaries with metadata and stats
        """
        if not self.is_authenticated():
            raise Exception("User is not authenticated. Please run login command first.")

        # First get user info to get username
        user_info = self.get_user_info()
        if not user_info or 'username' not in user_info:
            logger.warning("Could not get username, falling back to basic library fetch")
            return self.get_owned_games(show_progress)

        username = user_info['username']

        try:
            if show_progress:
                logger.info("Fetching GOG library with playtime stats (may require web login)...")

            # Use webview helper to fetch stats with authentication
            success, stats_data = self._fetch_stats_with_webview(username)

            if success and stats_data:
                if show_progress:
                    logger.info(f"Retrieved {len(stats_data)} games with stats from GOG")
                return stats_data
            else:
                logger.warning(f"Failed to fetch stats with webview: {stats_data}")
                if show_progress:
                    logger.info("Falling back to basic library without stats")
                return self.get_owned_games(show_progress)

        except Exception as e:
            logger.error(f"Error fetching games with stats: {e}")
            if show_progress:
                logger.info("Falling back to basic library without stats")
            return self.get_owned_games(show_progress)

    def _fetch_stats_with_webview(self, username: str) -> Tuple[bool, Any]:
        """
        Use webview helper to fetch stats data

        Args:
            username: GOG username

        Returns:
            tuple: (success, data_or_error_message)
        """
        try:
            # Get the path to the stats helper script
            current_dir = Path(__file__).parent
            stats_helper_path = current_dir / "gog_stats_helper.py"

            if not stats_helper_path.exists():
                return False, "Stats helper script not found"

            # Make sure the helper script is executable
            os.chmod(stats_helper_path, 0o755)

            # Run the stats helper as a separate process
            cmd = [sys.executable, str(stats_helper_path), username]

            logger.debug(f"Running stats helper: {' '.join(cmd)}")

            # Run with timeout
            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120  # 2 minute timeout
            )

            if process.returncode == 0:
                # Parse JSON output
                try:
                    stats_data = json.loads(process.stdout)
                    return True, stats_data
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse stats JSON: {e}")
                    return False, f"JSON parse error: {e}"
            else:
                error_msg = process.stderr.strip() if process.stderr else "Unknown error"
                logger.error(f"Stats helper failed: {error_msg}")
                return False, error_msg

        except subprocess.TimeoutExpired:
            logger.error("Stats helper timed out")
            return False, "Timeout waiting for stats data"
        except Exception as e:
            logger.error(f"Error running stats helper: {e}")
            return False, str(e)

    def get_owned_game_ids(self) -> List[str]:
        """
        Get list of owned game IDs using the more efficient embed API endpoint

        Returns:
            list: List of owned game ID strings
        """
        if not self.is_authenticated():
            raise Exception("User is not authenticated. Please run login command first.")

        tokens = self._load_tokens()

        try:
            headers = {
                'Authorization': f"Bearer {tokens['access_token']}",
                'User-Agent': 'Mozilla/5.0'
            }

            url = "https://embed.gog.com/user/data/games"
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            data = response.json()
            owned_ids = data.get('owned', [])
            logger.info(f"Retrieved {len(owned_ids)} owned game IDs from GOG")

            return [str(game_id) for game_id in owned_ids]

        except Exception as e:
            logger.error(f"Failed to get owned game IDs: {e}")
            return []

    def get_owned_games(self, show_progress=True, page=1) -> List[Dict[str, Any]]:
        """
        Get all games owned by the authenticated user

        Args:
            show_progress: Whether to display progress information
            page: Page number to fetch (default: fetch all pages)

        Returns:
            list: List of game dictionaries with metadata

        Raises:
            Exception: If the user is not authenticated
        """
        if not self.is_authenticated():
            raise Exception("User is not authenticated. Please run login command first.")

        all_games = []
        tokens = self._load_tokens()

        try:
            headers = {
                'Authorization': f"Bearer {tokens['access_token']}",
                'User-Agent': 'GOGGalaxyClient/2.0.12.3 (Windows 10)',
                'Accept': 'application/json'
            }

            current_page = 1
            while True:
                if show_progress:
                    logger.info(f"Fetching page {current_page} of GOG games...")

                params = {
                    'hiddenFlag': '0',
                    'mediaType': '1',
                    'page': current_page,
                    'sortBy': 'title'
                }

                response = requests.get(self.embed_api_url, params=params, headers=headers)
                response.raise_for_status()

                games_data = response.json()

                # Handle different API response formats
                if 'products' in games_data:
                    games = games_data['products']
                    total_pages = games_data.get('totalPages', 1)
                else:
                    # No games found or different format
                    break

                all_games.extend(games)

                if current_page >= total_pages:
                    break

                current_page += 1

            if show_progress:
                logger.info(f"Found {len(all_games)} games in GOG library")

            return all_games

        except Exception as e:
            logger.error(f"Error fetching GOG games: {e}")
            return []

    def get_game_details(self, game_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed game information from GOG's v2 API including portrait cover

        Args:
            game_id: The GOG game ID

        Returns:
            dict: Detailed game information with portrait cover and rich metadata
        """
        try:
            url = f"https://api.gog.com/v2/games/{game_id}"
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.debug(f"Failed to get game details for {game_id}: {e}")
            return None

    def scan(self, source: Source, progress_callback: Optional[callable] = None) -> Tuple[int, List[str]]:
        """
        Scan a GOG source for games and add them to the library.
        Implements the SourceScanner interface.

        Args:
            source: The source to scan
            progress_callback: Optional callback function for progress updates

        Returns:
            Tuple of (number of games added/updated, list of error messages)
        """
        added_count = 0
        errors = []

        # Initial progress update
        if progress_callback:
            try:
                progress_callback(0, 100, "Initializing GOG client...")
            except Exception as e:
                logger.error(f"Error with progress callback: {e}")

        try:
            # Check if we need to authenticate
            if not self.is_authenticated():
                if progress_callback:
                    try:
                        progress_callback(10, 100, "Need to authenticate, launching login flow...")
                    except Exception as e:
                        logger.error(f"Error with progress callback: {e}")

                # We should never get here if the source was properly created
                # through the UI, as it requires authentication before saving
                # But just in case, we'll handle it gracefully
                import threading
                auth_event = threading.Event()
                auth_result = [False]  # Use a list to store result from the thread

                # Function to run authentication in a thread
                def run_auth():
                    try:
                        auth_result[0] = self.authenticate()
                    except Exception as e:
                        logger.error(f"Authentication thread error: {e}")
                        auth_result[0] = False
                    finally:
                        auth_event.set()  # Signal that auth is complete

                # Start auth thread
                auth_thread = threading.Thread(target=run_auth)
                auth_thread.daemon = True
                auth_thread.start()

                # Wait for authentication with periodic progress updates
                import time
                start_time = time.time()
                while not auth_event.is_set() and time.time() - start_time < 300:  # 5 min timeout
                    # Update progress and message periodically
                    if progress_callback:
                        try:
                            elapsed = time.time() - start_time
                            progress_callback(10, 100, f"Authentication in progress ({int(elapsed)}s)...")
                        except Exception as e:
                            logger.error(f"Error with progress callback: {e}")
                    # Use shorter sleep to be more responsive
                    time.sleep(0.2)  # Sleep briefly to not hammer the CPU

                # Check authentication result
                if not auth_result[0]:
                    return 0, ["Authentication failed. Please try again."]

            # Update progress
            if progress_callback:
                try:
                    progress_callback(30, 100, "Fetching GOG library...")
                except Exception as e:
                    logger.error(f"Error with progress callback: {e}")

            # Get GOG library
            gog_games = self.get_owned_games(show_progress=True)

            # Get existing games from this source
            existing_games_by_title = {}
            for game in self.data_handler.load_games():
                if game.source == source.id:
                    existing_games_by_title[game.title.lower()] = game

            # Update progress
            total_games = len(gog_games)
            if progress_callback:
                try:
                    progress_callback(40, 100, f"Processing {total_games} games...")
                except Exception as e:
                    logger.error(f"Error with progress callback: {e}")

            # Process each game
            for index, game_data in enumerate(gog_games):
                try:
                    # Report progress
                    if progress_callback and index % 10 == 0:
                        try:
                            percentage = 40 + int((index / total_games) * 60)
                            progress_callback(percentage, 100, f"Processing game {index+1}/{total_games}")
                        except Exception as e:
                            logger.error(f"Error with progress callback: {e}")

                    # Get basic game details
                    title = game_data.get('title', 'Unknown Game')
                    game_id = str(game_data.get('id', ''))

                    # Add debug logging
                    logger.debug(f"Processing GOG game: {title} (ID: {game_id})")

                    # Check if game already exists
                    existing_game = existing_games_by_title.get(title.lower())
                    if existing_game:
                        # Game exists, skip for now (playtime updates handled separately if enabled)
                        continue

                    # Get detailed game info from v2 API - only proceed if this succeeds
                    # This filters out non-games (goodies collections, extras, etc.)
                    game_details = self.get_game_details(game_id)
                    if not game_details:
                        logger.debug(f"Skipping {title} - no v2 API details (likely bonus content)")
                        continue

                    # Create a new game
                    game = Game(
                        id="",  # ID will be assigned by data handler
                        title=title,
                        source=source.id
                    )

                    # Set launcher data before saving
                    game.launcher_type = "GOG"
                    game.launcher_id = game_id

                    # Enhanced description from v2 API
                    if 'description' in game_details:
                        game.description = game_details['description'].replace('<br><br>', '\n\n').replace('<br>', '\n')

                    # Extract platforms from supportedOperatingSystems
                    platform_enums = []
                    if '_embedded' in game_details and 'supportedOperatingSystems' in game_details['_embedded']:
                        supported_os = game_details['_embedded']['supportedOperatingSystems']
                        for os_info in supported_os:
                            os_name = os_info.get('operatingSystem', {}).get('name', '').lower()
                            if 'windows' in os_name:
                                platform_enums.append(Platforms.PC_WINDOWS)
                            elif 'mac' in os_name or 'osx' in os_name:
                                platform_enums.append(Platforms.PC_MAC)
                            elif 'linux' in os_name:
                                platform_enums.append(Platforms.PC_LINUX)

                    # Default to Windows if no platform info
                    if not platform_enums:
                        platform_enums.append(Platforms.PC_WINDOWS)

                    game.platforms = platform_enums

                    # Enhanced genres from tags
                    if '_embedded' in game_details and 'tags' in game_details['_embedded']:
                        tags = game_details['_embedded']['tags']
                        genre_enums = []
                        for tag in tags[:5]:  # Limit to first 5 tags
                            tag_name = tag.get('name', '')
                            mapped_genre = Genres.try_from_string(tag_name)
                            if mapped_genre:
                                genre_enums.append(mapped_genre)
                        if genre_enums:
                            game.genres = genre_enums

                    # Enhanced developer/publisher info
                    if '_embedded' in game_details:
                        embedded = game_details['_embedded']
                        if 'developers' in embedded and embedded['developers']:
                            game.developer = embedded['developers'][0].get('name')
                        if 'publisher' in embedded:
                            game.publisher = embedded['publisher'].get('name')

                    # Note: Playtime fetching is now handled separately to avoid API rate limits

                    # Get portrait cover image from v2 API
                    cover_image = None
                    if '_links' in game_details and 'boxArtImage' in game_details['_links']:
                        box_art_link = game_details['_links']['boxArtImage']
                        if box_art_link and 'href' in box_art_link:
                            cover_image = box_art_link['href']

                    if cover_image:
                        # Check if we should download images automatically
                        download_images = source.config.get("download_images", True)

                        if download_images:
                            # Store the URL in the game.image so we can fetch it later
                            logger.debug(f"Portrait cover image URL found: {cover_image}")
                            game.image = cover_image
                        else:
                            logger.debug(f"Skipping image download (disabled in source settings)")

                    # Save the game
                    if self.data_handler.save_game(game):
                        # Save enhanced description from v2 API
                        if game.description:
                            try:
                                self.data_handler.update_game_description(game, game.description)
                                logger.debug(f"Description saved for {game.title}")
                            except Exception as desc_err:
                                logger.error(f"Error saving description for {game.title}: {desc_err}")

                        # Download and save the cover image if URL is available
                        if hasattr(game, 'image') and game.image and source.config.get("download_images", True):
                            try:
                                # Use CoverFetcher to download and save the image
                                cover_fetcher = CoverFetcher(self.data_handler)
                                success, error = cover_fetcher.fetch_and_save_for_game(
                                    game.id,
                                    game.image,
                                    source_name="GOG"
                                )

                                if success:
                                    logger.debug(f"Cover image downloaded and saved successfully for {game.title}")
                                else:
                                    logger.warning(f"Failed to download/save cover image for {game.title}: {error}")
                            except Exception as img_err:
                                logger.error(f"Error processing cover image for {game.title}: {img_err}")

                        added_count += 1
                        logger.debug(f"Successfully imported GOG game: {game.title} with enhanced metadata")
                    else:
                        errors.append(f"Failed to save game '{title}'")

                except Exception as e:
                    game_name = game_data.get('title', 'Unknown')
                    logger.error(f"Error processing game {game_name}: {e}")
                    logger.error(traceback.format_exc())
                    errors.append(f"Error processing game {game_name}: {e}")

            # Final progress update
            if progress_callback:
                try:
                    progress_callback(100, 100, "Complete")
                except Exception as e:
                    logger.error(f"Error with final progress callback: {e}")

            # Playtime updates can be performed separately using update_playtime_for_games() method
            # This avoids slow syncs and heavy API usage during the main library sync

            return added_count, errors

        except Exception as e:
            if progress_callback:
                try:
                    progress_callback(100, 100, f"Error: {e}")
                except Exception as callback_error:
                    logger.error(f"Error with error progress callback: {callback_error}")

            logger.error(f"Error scanning GOG source: {e}")
            logger.error(traceback.format_exc())
            return 0, [f"Error syncing GOG source: {e}"]

    def update_playtime_for_games(self, source: Source, progress_callback: Optional[callable] = None) -> Tuple[int, List[str]]:
        """
        Update playtime data for existing GOG games. This makes individual API calls per game.

        Warning: This will make one API call per game to GOG's gameplay API.
        For large libraries, this may take some time and could trigger rate limiting.

        Args:
            source: The GOG source to update playtime for
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (number of games updated, list of error messages)
        """
        updated_count = 0
        errors = []

        try:
            # Get existing games from this source
            existing_games = []
            for game in self.data_handler.load_games():
                if game.source == source.id and game.launcher_type == "GOG" and game.launcher_id:
                    existing_games.append(game)

            if not existing_games:
                logger.info("No existing GOG games found to update playtime")
                return 0, []

            logger.info(f"Updating playtime for {len(existing_games)} GOG games (this may take a while)...")

            for i, game in enumerate(existing_games):
                try:
                    # Update progress
                    if progress_callback:
                        progress = int((i / len(existing_games)) * 100)
                        progress_callback(progress, 100, f"Updating playtime {i+1}/{len(existing_games)}: {game.title}")

                    # Small delay to be respectful to GOG's API
                    time.sleep(0.2)

                    playtime_minutes = self.get_game_playtime(game.launcher_id)

                    if playtime_minutes is not None and playtime_minutes > 0:
                        playtime_seconds = playtime_minutes * 60

                        # Check if playtime has actually changed
                        if game.play_time != playtime_seconds:
                            game.play_time = playtime_seconds

                            # Update completion status to PLAYED if it's currently NOT_PLAYED
                            if game.completion_status == CompletionStatus.NOT_PLAYED:
                                game.completion_status = CompletionStatus.PLAYED
                                logger.debug(f"Updated completion status to PLAYED for {game.title}")

                            # Save the updated game
                            self.data_handler.save_game(game, preserve_created_time=True)
                            logger.debug(f"Updated playtime for {game.title}: {playtime_minutes} minutes")
                            updated_count += 1

                except Exception as e:
                    error_msg = f"Failed to update playtime for {game.title}: {e}"
                    logger.warning(error_msg)
                    errors.append(error_msg)

            # Final progress update
            if progress_callback:
                progress_callback(100, 100, f"Playtime update complete: {updated_count} games updated")

            logger.info(f"Playtime update complete: {updated_count}/{len(existing_games)} games updated")
            return updated_count, errors

        except Exception as e:
            error_msg = f"Error in playtime update: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            return updated_count, errors
