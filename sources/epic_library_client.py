import os
import json
import requests
import logging
import traceback
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional, Dict, Any
import subprocess
import sys

from sources.scanner_base import SourceScanner
from data import Source, Game
from data_mapping import Platforms, Genres, CompletionStatus, LauncherType
from cover_fetch import CoverFetcher

# Import necessary components from the epic_library module
from sources.epic_library import EpicLibraryClient as EpicLibClientBase

# Set up logger
logger = logging.getLogger(__name__)

class EpicLibraryClient(SourceScanner):
    """Class to handle Epic Games Store authentication and library management"""

    def __init__(self, data_handler=None, token_dir=None):
        """
        Initialize the Epic Games Library with token storage paths

        Args:
            data_handler: The data handler instance to use (can be None for standalone usage)
            token_dir: Directory to store authentication tokens
                      If None, defaults to ~/.epic_library
        """
        # Initialize SourceScanner if data_handler is provided
        if data_handler:
            super().__init__(data_handler)

        # Create the base Epic client
        self.epic_client = EpicLibClientBase(data_dir=token_dir)

    def authenticate(self):
        """
        Initiate Epic Games authentication flow

        Returns:
            bool: True if authentication succeeded, False otherwise
        """
        return self.epic_client.authenticate()

    def is_authenticated(self):
        """
        Check if the user is authenticated and tokens are valid

        Returns:
            bool: True if authenticated with valid tokens, False otherwise
        """
        return self.epic_client.is_authenticated()

    def get_owned_games(self, show_progress=True, optimize_catalog=True, skip_catalog=True):
        """
        Get all games owned by the authenticated user

        Args:
            show_progress: Whether to display progress information
            optimize_catalog: Use batch catalog requests for better performance
            skip_catalog: Skip fetching detailed catalog data for fastest performance
                        (Default: True for best performance)

        Returns:
            list: List of game dictionaries with metadata
        """
        return self.epic_client.get_owned_games(
            show_progress=show_progress,
            skip_catalog=skip_catalog,
            optimize_catalog=optimize_catalog
        )

    def scan(self, source: Source, progress_callback: Optional[callable] = None) -> Tuple[int, List[str]]:
        """
        Scan an Epic Games source for games and add them to the library.
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
                progress_callback(0, 100, "Initializing Epic Games client...")
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
                    progress_callback(30, 100, "Fetching Epic Games library...")
                except Exception as e:
                    logger.error(f"Error with progress callback: {e}")

            # Get Epic Games library with optimize_catalog=True
            # This provides both good performance and accurate game list
            # by using batch requests but avoiding per-namespace processing
            epic_games = self.get_owned_games(
                show_progress=True,
                optimize_catalog=True,  # Use the batch optimization
                skip_catalog=False      # Don't skip catalog data to ensure proper game detection
            )

            # Get existing games from this source
            existing_games_by_title = {}
            for game in self.data_handler.load_games():
                if game.source == source.id:
                    existing_games_by_title[game.title.lower()] = game

            # Update progress
            total_games = len(epic_games)
            if progress_callback:
                try:
                    progress_callback(40, 100, f"Processing {total_games} games...")
                except Exception as e:
                    logger.error(f"Error with progress callback: {e}")

            # Process each game
            for index, game_data in enumerate(epic_games):
                try:
                    # Report progress
                    if progress_callback and index % 10 == 0:
                        try:
                            percentage = 40 + int((index / total_games) * 60)
                            progress_callback(percentage, 100, f"Processing game {index+1}/{total_games}")
                        except Exception as e:
                            logger.error(f"Error with progress callback: {e}")

                    # Get game details
                    title = game_data.get('title', 'Unknown Game')
                    app_id = game_data.get('id', '')
                    namespace = game_data.get('namespace', '')
                    catalog_item_id = game_data.get('catalog_item_id', '')

                    # Add debug logging
                    logger.debug(f"Processing Epic game: {title} (ID: {app_id}, Namespace: {namespace})")

                    # Generate unique ID for the game based on Epic app ID
                    game_key = f"epic_{namespace}_{app_id}"

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

                    # Set launcher data before saving
                    game.launcher_type = "EPIC"
                    game.launcher_id = app_id

                    # Extract platform info
                    platform_enums = []

                    try:
                        # Add platforms based on game data
                        if 'platforms' in game_data:
                            platforms = game_data['platforms']
                            if isinstance(platforms, list):
                                for platform in platforms:
                                    # Use enum mapping infrastructure
                                    mapped_platform = Platforms.try_from_string(platform)
                                    if mapped_platform:
                                        platform_enums.append(mapped_platform)
                            else:
                                # Default to Windows if platform info is unexpected
                                platform_enums.append(Platforms.PC_WINDOWS)
                        else:
                            # Default to Windows if no platform info
                            platform_enums.append(Platforms.PC_WINDOWS)

                        game.platforms = platform_enums
                    except Exception as e:
                        logger.error(f"ERROR setting platforms: {e}. For game: {title}")
                        # Default to Windows
                        game.platforms = [Platforms.PC_WINDOWS]

                    # Add description if available
                    if 'description' in game_data:
                        game.description = game_data['description']

                    # Add developer if available
                    if 'developer' in game_data:
                        # Store developer in description if it's not already included
                        if game.description and 'Developer:' not in game.description:
                            game.description = f"Developer: {game_data['developer']}\n\n{game.description}"
                        elif not game.description:
                            game.description = f"Developer: {game_data['developer']}"

                    # Add playtime if available
                    if 'playtime' in game_data and game_data['playtime'] is not None:
                        try:
                            minutes_played = game_data['playtime']
                            seconds_played = int(minutes_played) * 60  # Convert minutes to seconds
                            game.play_time = seconds_played
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Could not convert minutes played to integer: {e}. Value was: {game_data['playtime']}")
                            # Default to 0 seconds
                            game.play_time = 0

                    # Check if game has been played
                    if game.play_time is not None and game.play_time > 0:
                        game.play_count = 1
                        # Use the enum value directly
                        game.completion_status = CompletionStatus.PLAYED

                    # Get release date if available
                    if 'release_date' in game_data:
                        # Store release date in description if available
                        release_date = game_data.get('release_date', '')
                        if release_date and game.description:
                            game.description = f"{game.description}\n\nRelease Date: {release_date}"
                        elif release_date:
                            game.description = f"Release Date: {release_date}"

                    # Get cover image URL if available
                    cover_image = None
                    # We prefer cover_image, but fall back to other image formats if needed
                    if 'cover_image' in game_data:
                        cover_image = game_data['cover_image']
                    elif 'box_tall_image' in game_data:
                        cover_image = game_data['box_tall_image']
                    elif 'thumbnail' in game_data:
                        cover_image = game_data['thumbnail']
                    elif 'box_image' in game_data:
                        cover_image = game_data['box_image']
                    elif 'images' in game_data and isinstance(game_data['images'], dict):
                        # Look for any suitable cover in the images dictionary
                        images = game_data['images']
                        # Try to find the best image
                        for img_type in ['OfferImageWide', 'DieselGameBoxTall', 'Thumbnail', 'DieselGameBox']:
                            if img_type in images:
                                cover_image = images[img_type]
                                break

                    if cover_image:
                        # Check if we should download images automatically
                        download_images = source.config.get("download_images", True)

                        if download_images:
                            # Store the URL in the game.image so we can fetch it later
                            logger.debug(f"Cover image URL found: {cover_image}")
                            game.image = cover_image
                        else:
                            logger.debug(f"Skipping image download (disabled in source settings)")

                    # Save the game
                    if self.data_handler.save_game(game):
                        # After the game is saved with an ID, save the playtime separately
                        if game.play_time is not None and game.play_time > 0:
                            # Use the data_handler method to save play time
                            if not self.data_handler.update_play_time(game, game.play_time):
                                logger.warning(f"Failed to save play time for {game.title}")

                        # Save play count if set
                        if game.play_count is not None and game.play_count > 0:
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
                                    source_name="Epic"
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

            return added_count, errors

        except Exception as e:
            if progress_callback:
                try:
                    progress_callback(100, 100, f"Error: {e}")
                except Exception as callback_error:
                    logger.error(f"Error with error progress callback: {callback_error}")

            logger.error(f"Error scanning Epic Games source: {e}")
            logger.error(traceback.format_exc())
            return 0, [f"Error syncing Epic Games source: {e}"]
