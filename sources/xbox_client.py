import os
import json
import requests
import subprocess
import sys
import shlex
import traceback
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any

from sources.scanner_base import SourceScanner
from data import Source, Game
from data_mapping import Platforms, Genres, CompletionStatus
from cover_fetch import CoverFetcher

# Set up logger
logger = logging.getLogger(__name__)


class XboxLibrary(SourceScanner):
    """Class to handle Xbox authentication and library management"""

    # Xbox API constants
    CLIENT_ID = "85736097-7c70-4eba-ae9a-0cf0de4391e1"
    REDIRECT_URI = "https://login.live.com/oauth20_desktop.srf"
    SCOPE = "Xboxlive.signin Xboxlive.offline_access"

    def __init__(self, data_handler=None, token_dir=None):
        """
        Initialize the Xbox Library with token storage paths

        Args:
            data_handler: The data handler instance to use (can be None for standalone usage)
            token_dir: Directory to store authentication tokens
                      If None, defaults to ~/.xbox_api_client
        """
        # Initialize SourceScanner if data_handler is provided
        if data_handler:
            super().__init__(data_handler)

        # Set up data directories
        if token_dir:
            self.data_dir = Path(token_dir)
        else:
            self.data_dir = os.path.join(os.path.expanduser("~"), ".xbox_api_client")

        # Create directory if it doesn't exist
        os.makedirs(self.data_dir, exist_ok=True)

        # Set up token paths
        self.live_tokens_path = os.path.join(self.data_dir, "login.json")
        self.xsts_tokens_path = os.path.join(self.data_dir, "xsts.json")

    def authenticate(self):
        """
        Initiate Xbox authentication flow

        Returns:
            bool: True if authentication succeeded, False otherwise
        """
        # Get the path to the auth helper script
        current_dir = Path(__file__).parent
        auth_helper_path = current_dir / "xbox_auth_helper.py"

        # Check if the helper script exists
        if not auth_helper_path.exists():
            logger.error(f"Authentication helper script not found at {auth_helper_path}")
            return False

        try:
            # Make sure the helper script is executable
            os.chmod(auth_helper_path, 0o755)

            # Run the authentication helper as a completely separate process
            # This ensures no GTK version conflicts
            cmd = [
                sys.executable,
                str(auth_helper_path),
                self.CLIENT_ID,
                self.REDIRECT_URI,
                self.SCOPE
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
                # Removed preexec_fn as it was causing issues
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
                logger.warning("Authentication timeout - process took too long")
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
        try:
            logger.info("Getting OAuth tokens...")
            # Get OAuth tokens
            token_response = self._request_oauth_token(auth_code)
            logger.info("OAuth tokens received successfully")

            # Store the Live tokens
            live_login_data = {
                "AccessToken": token_response["access_token"],
                "RefreshToken": token_response["refresh_token"],
                "ExpiresIn": token_response["expires_in"],
                "CreationDate": datetime.now().isoformat(),
                "UserId": token_response["user_id"],
                "TokenType": token_response["token_type"]
            }

            logger.info("Getting Xbox XSTS tokens...")
            # Get Xbox XSTS tokens
            xsts_tokens = self._authenticate_with_xbox(live_login_data["AccessToken"])
            logger.info("XSTS tokens received successfully")

            # Save tokens to files
            logger.info("Saving tokens to files...")

            with open(self.live_tokens_path, 'w') as f:
                json.dump(live_login_data, f, indent=4)

            with open(self.xsts_tokens_path, 'w') as f:
                json.dump(xsts_tokens, f, indent=4)

            # Set secure permissions (0600) for token files
            os.chmod(self.live_tokens_path, 0o600)
            os.chmod(self.xsts_tokens_path, 0o600)

            logger.info("Tokens saved successfully")
            return True

        except Exception as e:
            logger.error(f"Error during authentication: {e}")
            return False

    def is_authenticated(self, try_refresh=True):
        """
        Check if the user is authenticated and refresh tokens if needed

        Args:
            try_refresh: Whether to try refreshing expired tokens

        Returns:
            bool: True if authenticated, False otherwise
        """
        # Check if tokens exist
        if not os.path.exists(self.xsts_tokens_path) or not os.path.exists(self.live_tokens_path):
            return False

        try:
            # Load the XSTS tokens
            with open(self.xsts_tokens_path, 'r') as f:
                tokens = json.load(f)

            # Set up headers
            headers = {
                'x-xbl-contract-version': '2',
                'Authorization': f'XBL3.0 x={tokens["DisplayClaims"]["xui"][0]["uhs"]};{tokens["Token"]}',
                'Accept-Language': 'en-US'
            }

            # Test token validity with a profile request
            request_data = {
                "settings": ["GameDisplayName"],
                "userIds": [int(tokens["DisplayClaims"]["xui"][0]["xid"])]
            }

            response = requests.post(
                'https://profile.xboxlive.com/users/batch/profile/settings',
                json=request_data,
                headers=headers
            )

            # If the request is successful, tokens are valid
            if response.status_code == 200:
                return True

            # If tokens have expired and refresh is requested
            if try_refresh and response.status_code in [401, 403]:
                logger.info("Authentication expired. Refreshing tokens...")
                return self._refresh_tokens()

            return False

        except Exception as e:
            logger.error(f"Error checking authentication: {e}")
            if try_refresh:
                return self._refresh_tokens()
            return False

    def get_game_library(self):
        """
        Get the user's Xbox game library

        Returns:
            list: List of game objects from Xbox API
        """
        # Ensure authenticated, try to refresh tokens if needed
        if not self.is_authenticated():
            raise Exception("User is not authenticated and token refresh failed")

        # Load the XSTS tokens
        with open(self.xsts_tokens_path, 'r') as f:
            tokens = json.load(f)

        # Set up the request headers
        headers = {
            'x-xbl-contract-version': '2',
            'Authorization': f'XBL3.0 x={tokens["DisplayClaims"]["xui"][0]["uhs"]};{tokens["Token"]}',
            'Accept-Language': 'en-US'
        }

        logger.info("Fetching Xbox title history...")

        # Make the request to get the title history
        response = requests.get(
            f'https://titlehub.xboxlive.com/users/xuid({tokens["DisplayClaims"]["xui"][0]["xid"]})/titles/titlehistory/decoration/detail',
            headers=headers
        )

        response.raise_for_status()
        data = response.json()

        # Get the titles
        titles = data.get('titles', [])
        logger.info(f"Retrieved {len(titles)} titles from Xbox")

        # Get playtime for all titles
        if titles:
            try:
                logger.info("Fetching playtime data...")
                # Extract title IDs
                title_ids = [title.get('titleId') for title in titles if title.get('titleId')]

                # Get playtime data
                playtime_stats = self._get_user_stats_minutes_played(title_ids)

                # Add playtime data to titles
                playtime_dict = {stat.get('titleid'): stat.get('value') for stat in playtime_stats}
                for title in titles:
                    title_id = title.get('titleId')
                    if title_id in playtime_dict:
                        title['minutesPlayed'] = playtime_dict[title_id]

                logger.info(f"Added playtime data for {len(playtime_stats)} titles")
            except Exception as e:
                logger.error(f"Error fetching playtime data: {e}")

        # Save library to file for convenience
        library_file = os.path.join(self.data_dir, "game_library.json")
        with open(library_file, 'w') as f:
            json.dump(titles, f, indent=2)

        return titles

    def _request_oauth_token(self, auth_code):
        """Exchange authorization code for OAuth tokens (internal method)"""
        request_data = {
            'grant_type': 'authorization_code',
            'code': auth_code,
            'scope': self.SCOPE,
            'client_id': self.CLIENT_ID,
            'redirect_uri': self.REDIRECT_URI
        }

        response = requests.post(
            'https://login.live.com/oauth20_token.srf',
            data=request_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        response.raise_for_status()
        return response.json()

    def _authenticate_with_xbox(self, access_token):
        """Get Xbox authentication tokens (internal method)"""
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

    def _refresh_tokens(self):
        """Refresh authentication tokens (internal method)"""
        # Check if we have live tokens
        if not os.path.exists(self.live_tokens_path):
            logger.warning("No refresh token available. Need manual re-authentication.")
            return False

        try:
            # Load live tokens
            with open(self.live_tokens_path, 'r') as f:
                live_tokens = json.load(f)

            # Ensure we have a refresh token
            if 'RefreshToken' not in live_tokens:
                logger.warning("No refresh token found. Need manual re-authentication.")
                return False

            # Use refresh token to get new access token
            refresh_token = live_tokens['RefreshToken']

            # Prepare request
            request_data = {
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'scope': self.SCOPE,
                'client_id': self.CLIENT_ID,
                'redirect_uri': self.REDIRECT_URI
            }

            # Request new tokens
            logger.info("Requesting new OAuth tokens...")
            response = requests.post(
                'https://login.live.com/oauth20_token.srf',
                data=request_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )

            if response.status_code != 200:
                logger.error(f"Token refresh failed: {response.status_code}")
                return False

            # Extract new tokens
            token_response = response.json()

            # Update live tokens
            live_login_data = {
                "AccessToken": token_response["access_token"],
                "RefreshToken": token_response["refresh_token"],
                "ExpiresIn": token_response["expires_in"],
                "CreationDate": datetime.now().isoformat(),
                "UserId": token_response["user_id"],
                "TokenType": token_response["token_type"]
            }

            # Get new Xbox XSTS tokens
            logger.info("Authenticating with Xbox Live...")
            xsts_tokens = self._authenticate_with_xbox(live_login_data["AccessToken"])

            # Save updated tokens
            with open(self.live_tokens_path, 'w') as f:
                json.dump(live_login_data, f, indent=4)

            with open(self.xsts_tokens_path, 'w') as f:
                json.dump(xsts_tokens, f, indent=4)

            # Ensure permissions are secure
            os.chmod(self.live_tokens_path, 0o600)
            os.chmod(self.xsts_tokens_path, 0o600)

            logger.info("Token refresh successful!")
            return True

        except Exception as e:
            logger.error(f"Error refreshing tokens: {e}")
            return False

    def _get_user_stats_minutes_played(self, title_ids):
        """Get playtime statistics for a list of titles (internal method)"""
        # Ensure authenticated with automatic token refresh
        if not self.is_authenticated():
            raise Exception("User is not authenticated and token refresh failed")

        # Load the XSTS tokens
        with open(self.xsts_tokens_path, 'r') as f:
            tokens = json.load(f)

        # Set up headers
        headers = {
            'x-xbl-contract-version': '2',
            'Authorization': f'XBL3.0 x={tokens["DisplayClaims"]["xui"][0]["uhs"]};{tokens["Token"]}',
            'Accept-Language': 'en-US'
        }

        # Prepare the request data
        xuid = tokens["DisplayClaims"]["xui"][0]["xid"]
        request_data = {
            "arrangebyfield": "xuid",
            "stats": [
                {
                    "name": "MinutesPlayed",
                    "titleid": title_id
                } for title_id in title_ids
            ],
            "xuids": [xuid]
        }

        # Make the request
        response = requests.post(
            'https://userstats.xboxlive.com/batch',
            json=request_data,
            headers=headers
        )

        response.raise_for_status()
        data = response.json()

        # Extract stats
        stats_collection = data.get('statlistscollection', [])
        if stats_collection and len(stats_collection) > 0:
            return stats_collection[0].get('stats', [])

        return []

    def group_games_by_platform(self, titles):
        """
        Group games by platform type

        Args:
            titles: List of games from the API

        Returns:
            dict: Dictionary with keys 'pc', 'console', 'cross_platform', 'total'
        """
        pc_games = []
        console_games = []
        cross_platform_games = []

        for title in titles:
            if title.get('type') != 'Game':
                continue

            devices = title.get('devices', [])

            if 'PC' in devices and any(device in devices for device in ['Xbox360', 'XboxOne', 'XboxSeries']):
                cross_platform_games.append(title)
            elif 'PC' in devices:
                pc_games.append(title)
            elif any(device in devices for device in ['Xbox360', 'XboxOne', 'XboxSeries']):
                console_games.append(title)

        total_games = len(pc_games) + len(console_games) + len(cross_platform_games)

        return {
            'pc': pc_games,
            'console': console_games,
            'cross_platform': cross_platform_games,
            'total': total_games
        }

    def scan(self, source: Source, progress_callback: Optional[callable] = None) -> Tuple[int, List[str]]:
        """
        Scan an Xbox source for games and add them to the library.
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
                progress_callback(0, 100, "Initializing Xbox client...")
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
                from threading import Thread
                from gi.repository import GLib

                # Create an authentication thread with cleaner synchronization
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
                    progress_callback(30, 100, "Fetching Xbox library...")
                except Exception as e:
                    logger.error(f"Error with progress callback: {e}")

            # Get Xbox library
            xbox_games = self.get_game_library()

            # Get existing games from this source
            existing_games_by_title = {}
            for game in self.data_handler.load_games():
                if game.source == source.id:
                    existing_games_by_title[game.title.lower()] = game

            # Update progress
            total_games = len(xbox_games)
            if progress_callback:
                try:
                    progress_callback(40, 100, f"Processing {total_games} games...")
                except Exception as e:
                    logger.error(f"Error with progress callback: {e}")

            # Process each game
            for index, game_data in enumerate(xbox_games):
                try:
                    # Report progress
                    if progress_callback and index % 10 == 0:
                        try:
                            percentage = 40 + int((index / total_games) * 60)
                            progress_callback(percentage, 100, f"Processing game {index+1}/{total_games}")
                        except Exception as e:
                            logger.error(f"Error with progress callback: {e}")

                    # Check if this is a game (not an app)
                    if game_data.get('type') != 'Game':
                        continue

                    # Get game details
                    title = game_data.get('name', 'Unknown Game')
                    title_id = game_data.get('titleId', '')

                    # Add debug logging
                    logger.info(f"Processing Xbox game: {title} (ID: {title_id})")

                    # Generate unique ID for the game based on Xbox title ID
                    game_key = f"xbox_{title_id}"

                    # Check if game already exists
                    if title.lower() in existing_games_by_title:
                        # Game exists, update metadata if needed
                        # For now, we'll skip updates
                        continue

                    # Create a new game
                    game = Game(
                        id="",  # ID will be assigned by data handler
                        title=title,
                        source=source.id
                    )

                    # Extract platform info
                    platforms = []
                    devices = game_data.get('devices', [])

                    # Map Xbox platforms to our platform enum
                    platform_enums = []

                    try:
                        if 'XboxOne' in devices:
                            platform_enums.append(Platforms.XBOX_ONE)
                        if 'XboxSeries' in devices:
                            platform_enums.append(Platforms.XBOX_SERIES)
                        if 'PC' in devices:
                            platform_enums.append(Platforms.PC_WINDOWS)
                        if 'Xbox360' in devices:
                            platform_enums.append(Platforms.XBOX360)
                        if 'Xbox' in devices:  # Original Xbox
                            platform_enums.append(Platforms.XBOX)

                        game.platforms = platform_enums
                    except Exception as e:
                        logger.error(f"ERROR setting platforms: {e}. For devices: {devices}")

                    # Add genres if available
                    detail = game_data.get('detail', {})
                    if detail:
                        # Add description
                        game.description = detail.get('description', '')

                        # Add genres
                        genres = detail.get('genres', [])
                        genre_enums = []
                        for genre in genres:
                            # Map Xbox genres to our genre enum
                            try:
                                if "Action" in genre:
                                    genre_enums.append(Genres.ACTION)
                                elif "Adventure" in genre:
                                    genre_enums.append(Genres.ADVENTURE)
                                elif "Puzzle" in genre:
                                    genre_enums.append(Genres.PUZZLE)
                                elif "RPG" in genre or "Role" in genre:
                                    genre_enums.append(Genres.ROLE_PLAYING_RPG)
                                elif "Strategy" in genre:
                                    genre_enums.append(Genres.STRATEGY)
                                elif "Sports" in genre:
                                    genre_enums.append(Genres.SPORTS)
                                elif "Racing" in genre:
                                    genre_enums.append(Genres.RACING)
                                elif "Simulation" in genre:
                                    genre_enums.append(Genres.SIMULATOR)
                                elif "Fighting" in genre:
                                    genre_enums.append(Genres.FIGHTING)
                                elif "Platform" in genre:
                                    genre_enums.append(Genres.PLATFORMER)
                                elif "Shooter" in genre:
                                    genre_enums.append(Genres.SHOOTER)
                            except (AttributeError, ValueError) as e:
                                logger.warning(f"Could not map genre '{genre}': {e}")

                        # Use try-except to catch any errors when setting genres
                        try:
                            game.genres = genre_enums
                        except Exception as e:
                            logger.error(f"ERROR setting genres: {e}")

                    # Add playtime if available
                    if 'minutesPlayed' in game_data and game_data['minutesPlayed'] is not None:
                        try:
                            minutes_played = game_data['minutesPlayed']
                            seconds_played = int(minutes_played) * 60  # Convert minutes to seconds
                            game.play_time = seconds_played
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Could not convert minutes played to integer: {e}. Value was: {game_data['minutesPlayed']}")
                            # Default to 0 seconds
                            game.play_time = 0

                    # Check if game has been played
                    if game.play_time > 0:
                        game.play_count = 1
                        # Use the enum value directly
                        game.completion_status = CompletionStatus.PLAYED

                    # Get title history data (for last played date)
                    title_history = game_data.get('titleHistory', {})
                    if title_history and 'lastTimePlayed' in title_history:
                        # We'll handle last played time via the YAML file's modification time
                        # This is handled when we save the game
                        pass

                    # Get cover image URL if available
                    display_image = game_data.get('displayImage')
                    if display_image:

                        # Check if we should download images automatically
                        download_images = source.config.get("download_images", True)

                        if download_images:
                            # Store the URL in the game.image so we can fetch it later
                            logger.debug(f"Cover image URL found: {display_image}")
                            game.image = display_image
                        else:
                            logger.debug(f"Skipping image download (disabled in source settings)")

                    # Save the game
                    if self.data_handler.save_game(game):
                        # After the game is saved with an ID, save the playtime separately
                        if game.play_time > 0:
                            # Use the data_handler method to save play time
                            if not self.data_handler.update_play_time(game, game.play_time):
                                logger.warning(f"Failed to save play time for {game.title}")

                        # Save play count if set
                        if game.play_count > 0:
                            if not self.data_handler.update_play_count(game, game.play_count):
                                logger.warning(f"Failed to save play count for {game.title}")

                        # Download and save the cover image if URL is available
                        if hasattr(game, 'image') and game.image and source.config.get("download_images", True):
                            try:
                                # Use CoverFetcher to download and save the image
                                cover_fetcher = CoverFetcher(self.data_handler)
                                success, error = cover_fetcher.fetch_and_save_for_game(
                                    game.id,
                                    game.image,
                                    source_name="Xbox"
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
                    progress_callback(100, 100, "Complete")
                except Exception as e:
                    logger.error(f"Error with final progress callback: {e}")

            return added_count, errors

        except Exception as e:
            if progress_callback:
                try:
                    progress_callback(100, 100, f"Error: {e}")
                except Exception as callback_error:
                    logger.error(f"Error with error progress callback: {callback_error}")

            return 0, [f"Error syncing Xbox source: {e}"]


# Example usage for direct script execution
class XboxConsoleApp:
    """
    Console application for running the Xbox client directly
    This is used when the module is run as a script
    """
    def __init__(self):
        self.xbox = XboxLibrary()

    def run(self):
        """Run the Xbox client as a standalone application"""
        logger.info("Xbox Authentication and Library Demo")
        logger.info("===================================")

        # For the command-line app, we need to make sure the helper exists
        # and it uses GTK 3.0 for WebKit compatibility
        helper_path = Path(__file__).parent / "xbox_auth_helper.py"
        if not helper_path.exists():
            logger.error(f"Authentication helper script not found at {helper_path}")
            logger.error("Authentication helper script not found.")
            logger.error("Please ensure the helper script is properly installed.")
            sys.exit(1)

        # Check if authenticated
        auth_status = self.xbox.is_authenticated()
        logger.info(f"Authentication status: {'✓ Authenticated' if auth_status else '✗ Not authenticated'}")
        logger.info(f"Authentication status: {auth_status}")

        # Authenticate if needed or requested
        if not auth_status or input("Re-authenticate anyway? (y/n): ").lower() == 'y':
            logger.info("\nStarting authentication...")
            logger.info("Starting authentication process from console app")
            if not self.xbox.authenticate():
                logger.error("\n✗ Authentication failed.")
                logger.error("Authentication failed in console app")
                sys.exit(1)
            logger.info("\n✓ Authentication successful!")
            logger.info("Authentication successful from console app")
            logger.info(f"Tokens saved to {self.xbox.data_dir}")

        # Fetch and display game library
        try:
            logger.info("\nFetching game library...")
            logger.info("Fetching game library from console app")
            titles = self.xbox.get_game_library()

            # Group and display games by platform
            game_groups = self.xbox.group_games_by_platform(titles)

            logger.info(f"\nFound {game_groups['total']} games in your Xbox library:")
            logger.info(f"Found {game_groups['total']} games in Xbox library")

            # Display PC games
            if game_groups['pc']:
                logger.info(f"\n=== PC Games ({len(game_groups['pc'])}) ===")
                for i, game in enumerate(sorted(game_groups['pc'], key=lambda g: g.get('name', '')), 1):
                    if i > 5:
                        break
                    minutes = game.get('minutesPlayed')
                    playtime = f" - {minutes} minutes played" if minutes else ""
                    logger.info(f"{i}. {game.get('name', 'Unknown')}{playtime}")

            # Display console games
            if game_groups['console']:
                logger.info(f"\n=== Console Games ({len(game_groups['console'])}) ===")
                for i, game in enumerate(sorted(game_groups['console'], key=lambda g: g.get('name', '')), 1):
                    if i > 5:
                        break
                    devices = ", ".join(game.get('devices', []))
                    minutes = game.get('minutesPlayed')
                    playtime = f" - {minutes} minutes played" if minutes else ""
                    logger.info(f"{i}. {game.get('name', 'Unknown')} ({devices}){playtime}")

            # Display cross-platform games
            if game_groups['cross_platform']:
                logger.info(f"\n=== Cross-Platform Games ({len(game_groups['cross_platform'])}) ===")
                for i, game in enumerate(sorted(game_groups['cross_platform'], key=lambda g: g.get('name', '')), 1):
                    if i > 5:
                        break
                    minutes = game.get('minutesPlayed')
                    playtime = f" - {minutes} minutes played" if minutes else ""
                    logger.info(f"{i}. {game.get('name', 'Unknown')}{playtime}")

            logger.info(f"\nTotal: {game_groups['total']} games found")
            logger.info(f"\nComplete game library saved to: {os.path.join(self.xbox.data_dir, 'game_library.json')}")
            logger.info(f"Complete game library saved to: {os.path.join(self.xbox.data_dir, 'game_library.json')}")

        except Exception as e:
            logger.error(f"\nError: {e}")
            logger.error(f"Error in console app: {e}")


if __name__ == "__main__":
    # Run the app when script is executed directly
    app = XboxConsoleApp()
    app.run()
