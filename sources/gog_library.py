import os
import json
import requests
import logging
import traceback
import concurrent.futures
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
import subprocess
import sys

from sources.scanner_base import SourceScanner
from data import Source, Game
from data_mapping import Platforms, Genres, CompletionStatus, LauncherType
from cover_fetch import CoverFetcher

# Import necessary components from the gog_library_client module
from sources.gog_library_client import GogLibraryClient as GogLibClientBase

# Set up logger
logger = logging.getLogger(__name__)

class GogLibraryClient(SourceScanner):
    """Class to handle GOG authentication and library management"""

    def __init__(self, data_handler=None, token_dir=None):
        """
        Initialize the GOG Library with token storage paths

        Args:
            data_handler: The data handler instance to use (can be None for standalone usage)
            token_dir: Directory to store authentication tokens
                      If None, defaults to ~/.gog_library
        """
        # Initialize SourceScanner if data_handler is provided
        if data_handler:
            super().__init__(data_handler)

        # Create the base GOG client
        self.gog_client = GogLibClientBase(data_dir=token_dir)

    def authenticate(self):
        """
        Initiate GOG authentication flow

        Returns:
            bool: True if authentication succeeded, False otherwise
        """
        return self.gog_client.authenticate()

    def is_authenticated(self):
        """
        Check if the user is authenticated and tokens are valid

        Returns:
            bool: True if authenticated with valid tokens, False otherwise
        """
        return self.gog_client.is_authenticated()

    def get_owned_games(self, show_progress=True):
        """
        Get all games owned by the authenticated user

        Args:
            show_progress: Whether to display progress information

        Returns:
            list: List of game dictionaries with metadata
        """
        return self.gog_client.get_owned_games(show_progress=show_progress)

    def get_owned_games_with_stats(self, show_progress=True):
        """
        Get all games owned by the authenticated user with playtime stats

        Args:
            show_progress: Whether to display progress information

        Returns:
            list: List of game dictionaries with metadata and stats
        """
        return self.gog_client.get_owned_games_with_stats(show_progress=show_progress)

    def get_game_details(self, game_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed game information from GOG's v2 API including portrait cover

        Args:
            game_id: The GOG game ID

        Returns:
            dict: Detailed game information with portrait cover and rich metadata
        """
        try:
            import requests
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
            gog_games = self.gog_client.get_owned_games(show_progress=True)

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

                    playtime_minutes = self.gog_client.get_game_playtime(game.launcher_id)

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
