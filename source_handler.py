import os
import yaml
import json
import time
import stat
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from data import Source, SourceType, Game
from data_handler import DataHandler
from sources.xbox_client import XboxLibrary
from sources.psn_client import PSNClient


class SourceHandler:
    """Handles operations related to game sources and scanning"""

    def __init__(self, data_handler: DataHandler):
        """
        Initialize the source handler with a data handler

        Args:
            data_handler: The data handler instance to use
        """
        self.data_handler = data_handler
        self.sources_dir = self.data_handler.sources_dir

    def load_sources(self) -> List[Source]:
        """
        Load all sources from the sources directory.

        Returns:
            List of Source objects
        """
        sources = []

        # Look for source directories (numeric IDs)
        for source_dir in self.sources_dir.glob("*"):
            if source_dir.is_dir():
                source_file = source_dir / "source.yaml"
                if source_file.exists():
                    try:
                        with open(source_file, "r") as f:
                            source_data = yaml.safe_load(f)

                            # Handle source type conversion
                            if "type" in source_data:
                                try:
                                    source_type = SourceType.from_string(source_data["type"])
                                except ValueError:
                                    print(f"Invalid source type in {source_file}, defaulting to DIRECTORY")
                                    source_type = SourceType.DIRECTORY
                            else:
                                source_type = SourceType.DIRECTORY

                            # Process file extensions
                            file_extensions = source_data.get("file_extensions", [])
                            if isinstance(file_extensions, str):
                                file_extensions = [ext.strip() for ext in file_extensions.split(",") if ext.strip()]

                            source = Source(
                                id=source_dir.name,  # Use directory name as the ID
                                name=source_data.get("name", source_dir.name),
                                path=source_data.get("path", ""),
                                source_type=source_type,
                                active=source_data.get("active", True),
                                file_extensions=file_extensions,
                                config=source_data.get("config", {})
                            )
                            sources.append(source)
                    except Exception as e:
                        print(f"Error loading source {source_file}: {e}")

        # No need to handle legacy format sources anymore since you mentioned you'll recreate them

        return sources

    def _get_next_source_id(self) -> int:
        """
        Get the next available numeric ID for a source.

        Returns:
            The next available numeric ID
        """
        # Check existing source directories
        existing_ids = []
        for source_dir in self.sources_dir.glob("*"):
            if source_dir.is_dir() and source_dir.name.isdigit():
                existing_ids.append(int(source_dir.name))

        # If no IDs exist, start with 1
        if not existing_ids:
            return 1

        # Otherwise, return the next available ID
        return max(existing_ids) + 1

    def save_source(self, source: Source) -> bool:
        """
        Save a source to disk.

        Args:
            source: The source to save

        Returns:
            True if successful, False otherwise
        """
        # Assign a numeric ID if this is a new source
        if not source.id:
            next_id = self._get_next_source_id()
            source.id = str(next_id)

        # Check if the ID is numeric (new format) or string-based (old format)
        source_dir = self.sources_dir / source.id

        # Create source directory if it doesn't exist
        source_dir.mkdir(parents=True, exist_ok=True)

        source_data = {
            "name": source.name,
            "path": source.path,
            "type": str(source.source_type),
            "active": source.active
        }

        if source.file_extensions:
            source_data["file_extensions"] = source.file_extensions

        if source.config:
            source_data["config"] = source.config

        try:
            source_file = source_dir / "source.yaml"
            with open(source_file, "w") as f:
                yaml.dump(source_data, f)
            return True
        except Exception as e:
            print(f"Error saving source {source.id}: {e}")
            return False

    def remove_source(self, source: Source) -> bool:
        """
        Remove a source and its directory from the sources directory.

        Args:
            source: The source to remove

        Returns:
            True if successful, False otherwise
        """
        print(f"DEBUG: remove_source called for source: {source.id} ({source.name})")

        source_dir = self.sources_dir / source.id
        print(f"DEBUG: source directory path: {source_dir}")
        print(f"DEBUG: source directory exists: {source_dir.exists()}")
        print(f"DEBUG: sources dir exists: {self.sources_dir.exists()}")
        print(f"DEBUG: sources dir contents: {list(self.sources_dir.glob('*'))}")

        try:
            if source_dir.exists():
                print(f"DEBUG: Attempting to remove directory {source_dir}")
                # Remove all files in the directory
                for file in source_dir.glob("*"):
                    file.unlink()
                # Remove the directory
                source_dir.rmdir()
                print(f"DEBUG: Directory successfully removed")
                return True
            else:
                print(f"Source directory {source_dir} not found")
                return False
        except Exception as e:
            print(f"Error removing source {source.id}: {e}")
            return False

    def scan_source(self, source: Source, progress_callback: Optional[callable] = None) -> Tuple[int, List[str]]:
        """
        Scan a source for games and add them to the library.

        Args:
            source: The source to scan
            progress_callback: Optional callback function for progress updates

        Returns:
            Tuple of (number of games added/updated, list of error messages)
        """
        # Special handling for different source types
        if source.source_type == SourceType.XBOX:
            # For Xbox sources, we use sync_xbox_source instead
            return self.sync_xbox_source(source, progress_callback)
        elif source.source_type == SourceType.PLAYSTATION:
            # For PSN sources, use sync_psn_source
            return self.sync_psn_source(source, progress_callback)

        # For directory type sources, validate the path
        if not source.path or not Path(source.path).exists():
            return 0, [f"Source path does not exist: {source.path}"]

        source_path = Path(source.path)
        added_count = 0
        errors = []

        # Get the list of files matching the specified extensions
        matching_files = []

        if not source.file_extensions:
            # Default to common game file extensions if none are specified
            extensions = [".exe", ".lnk", ".url", ".desktop"]
        else:
            extensions = [f".{ext.lstrip('.')}" for ext in source.file_extensions]

        # Build a glob pattern for each extension
        for ext in extensions:
            pattern = f"**/*{ext}"
            try:
                matching_files.extend(list(source_path.glob(pattern)))
            except Exception as e:
                errors.append(f"Error searching for {pattern}: {e}")

        # Initial progress update
        total_files = len(matching_files)
        if progress_callback and total_files > 0:
            try:
                progress_callback(0, total_files, "Starting scan...")
            except Exception as e:
                print(f"Error with progress callback: {e}")

        # Get list of existing games from this source
        existing_games_by_path = {}
        for game in self.data_handler.load_games():
            if game.source == source.id:
                # Extract the path if it's in the title or description
                # This is a simple approach - in a more advanced implementation,
                # we might store the original file path separately
                existing_games_by_path[game.title] = game

        # Process each file
        for index, file_path in enumerate(matching_files):
            try:
                # Report progress if callback provided
                if progress_callback and index % 5 == 0:  # Update every 5 files
                    try:
                        progress_callback(index, total_files, str(file_path))
                    except Exception as e:
                        print(f"Error with progress callback: {e}")

                # Generate a title from the filename
                title = file_path.stem

                # Check if we already have this game from this source
                if title in existing_games_by_path:
                    # Game already exists, skip it
                    continue

                # Create a new game
                game = Game(
                    id="",  # ID will be assigned by data handler
                    title=title,
                    source=source.id
                )

                # Save the game
                if self.data_handler.save_game(game):
                    added_count += 1
                else:
                    errors.append(f"Failed to save game '{title}'")

            except Exception as e:
                errors.append(f"Error processing file {file_path}: {e}")

        # Final progress update
        if progress_callback:
            try:
                progress_callback(total_files, total_files, "Complete")
            except Exception as e:
                print(f"Error with final progress callback: {e}")

        return added_count, errors

    def sync_source(self, source: Source, progress_callback: Optional[callable] = None) -> Tuple[int, List[str]]:
        """
        Scan a source for games and sync them with the library (add new games, update existing ones).

        Args:
            source: The source to sync
            progress_callback: Optional callback function for progress updates

        Returns:
            Tuple of (number of games added/updated, list of error messages)
        """
        # Handle different source types
        if source.source_type == SourceType.XBOX:
            return self.sync_xbox_source(source, progress_callback)
        elif source.source_type == SourceType.PLAYSTATION:
            return self.sync_psn_source(source, progress_callback)
        else:
            # Default to standard scan for directory sources
            return self.scan_source(source, progress_callback)

    def ensure_secure_token_storage(self, source_id: str) -> Path:
        """
        Ensure token storage directory exists with proper permissions (0700).

        Args:
            source_id: The source ID to create storage for

        Returns:
            Path to the secure token storage directory
        """
        # Create a tokens directory within the source's directory
        # This keeps all source data together and makes the tokens stable with source renaming
        source_dir = self.sources_dir / source_id
        tokens_dir = source_dir / "tokens"
        tokens_dir.mkdir(parents=True, exist_ok=True)

        # Set secure permissions (0700 for directory)
        os.chmod(tokens_dir, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

        return tokens_dir

    def sync_xbox_source(self, source: Source, progress_callback: Optional[callable] = None) -> Tuple[int, List[str]]:
        """
        Sync Xbox games with the library.

        Args:
            source: The Xbox source to sync
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
                print(f"Error with progress callback: {e}")

        try:
            # Create secure token storage
            tokens_dir = self.ensure_secure_token_storage(source.id)

            # Create Xbox Library instance with our token directory
            xbox = XboxLibrary(token_dir=tokens_dir)

            # Check if we need to authenticate
            if not xbox.is_authenticated():
                if progress_callback:
                    try:
                        progress_callback(10, 100, "Need to authenticate, launching login flow...")
                    except Exception as e:
                        print(f"Error with progress callback: {e}")

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
                        auth_result[0] = xbox.authenticate()
                    except Exception as e:
                        print(f"Authentication thread error: {e}")
                        auth_result[0] = False
                    finally:
                        auth_event.set()  # Signal that auth is complete

                # Start auth thread
                auth_thread = threading.Thread(target=run_auth)
                auth_thread.daemon = True
                auth_thread.start()

                # Wait for authentication with periodic progress updates
                start_time = time.time()
                while not auth_event.is_set() and time.time() - start_time < 300:  # 5 min timeout
                    # Update progress and message periodically
                    if progress_callback:
                        try:
                            elapsed = time.time() - start_time
                            progress_callback(10, 100, f"Authentication in progress ({int(elapsed)}s)...")
                        except Exception as e:
                            print(f"Error with progress callback: {e}")
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
                    print(f"Error with progress callback: {e}")

            # Get Xbox library
            xbox_games = xbox.get_game_library()

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
                    print(f"Error with progress callback: {e}")

            # Process each game
            for index, game_data in enumerate(xbox_games):
                try:
                    # Report progress
                    if progress_callback and index % 10 == 0:
                        try:
                            percentage = 40 + int((index / total_games) * 60)
                            progress_callback(percentage, 100, f"Processing game {index+1}/{total_games}")
                        except Exception as e:
                            print(f"Error with progress callback: {e}")

                    # Check if this is a game (not an app)
                    if game_data.get('type') != 'Game':
                        continue

                    # Get game details
                    title = game_data.get('name', 'Unknown Game')
                    title_id = game_data.get('titleId', '')

                    # Add debug logging
                    print(f"Processing Xbox game: {title} (ID: {title_id})")

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

                    print(f"  - Devices: {devices}")

                    # Map Xbox platforms to our platform enum using correct values from Platforms enum
                    from data_mapping import Platforms

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

                        print(f"  - Mapped platforms: {[p.value for p in platform_enums]}")

                        game.platforms = platform_enums
                        print(f"  - Platforms set successfully")
                    except Exception as e:
                        print(f"  - ERROR setting platforms: {e}. For devices: {devices}")
                        # Debug information to help diagnose platform mapping issues
                        print(f"  - Platform enum values: {[p.name for p in Platforms]}")

                    # Add genres if available
                    detail = game_data.get('detail', {})
                    if detail:
                        # Add description
                        game.description = detail.get('description', '')

                        # Add genres
                        from data_mapping import Genres

                        genres = detail.get('genres', [])
                        print(f"  - Original genres: {genres}")

                        genre_enums = []
                        for genre in genres:
                            # Map Xbox genres to our genre enum using correct values from Genres enum
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
                                print(f"  - WARNING: Could not map genre '{genre}': {e}")

                        print(f"  - Mapped genres: {[g.value for g in genre_enums]}")

                        # Use try-except to catch any errors when setting genres
                        try:
                            game.genres = genre_enums
                            print(f"  - Genres set successfully")
                        except Exception as e:
                            print(f"  - ERROR setting genres: {e}")
                            # Debug information to help diagnose genre mapping issues
                            print(f"  - Genre enum values: {[g.name for g in Genres]}")

                    # Add playtime if available
                    if 'minutesPlayed' in game_data and game_data['minutesPlayed'] is not None:
                        try:
                            minutes_played = game_data['minutesPlayed']
                            seconds_played = int(minutes_played) * 60  # Convert minutes to seconds
                            game.play_time = seconds_played
                            print(f"  - Set play time: {game.play_time} seconds (from {minutes_played} minutes)")
                        except (ValueError, TypeError) as e:
                            print(f"  - WARNING: Could not convert minutes played to integer: {e}. Value was: {game_data['minutesPlayed']}")
                            # Default to 0 seconds
                            game.play_time = 0

                    # Check if game has been played
                    if game.play_time > 0:
                        game.play_count = 1
                        # Use the enum value directly instead of a string
                        from data_mapping import CompletionStatus
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
                        # Store the URL in config for reference
                        if 'game_covers' not in source.config:
                            source.config['game_covers'] = {}

                        source.config['game_covers'][title] = display_image
                        self.save_source(source)

                        # Download and save the cover image immediately
                        try:
                            print(f"  - Downloading cover image from URL: {display_image}")
                            import requests
                            import tempfile

                            # Download the image to a temporary file
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                                response = requests.get(display_image, stream=True, timeout=10)
                                response.raise_for_status()  # Raise error for bad status codes

                                # Write the image data to the temporary file
                                for chunk in response.iter_content(chunk_size=8192):
                                    temp_file.write(chunk)

                                temp_path = temp_file.name

                            # Use the temporary file for the game image
                            game.image = temp_path
                            print(f"  - Image downloaded to temporary file: {temp_path}")
                        except Exception as img_err:
                            print(f"  - ERROR downloading cover image: {img_err}")

                    # Save the game
                    if self.data_handler.save_game(game):
                        # After the game is saved with an ID, save the playtime separately
                        if game.play_time > 0:
                            # Use the data_handler method to save play time
                            if not self.data_handler.update_play_time(game, game.play_time):
                                print(f"  - WARNING: Failed to save play time for {game.title}")

                        # Save play count if set
                        if game.play_count > 0:
                            if not self.data_handler.update_play_count(game, game.play_count):
                                print(f"  - WARNING: Failed to save play count for {game.title}")

                        # Save the cover image if it was downloaded to a temporary file
                        if hasattr(game, 'image') and game.image:
                            try:
                                # Use data_handler to save the cover image
                                if self.data_handler.save_game_image(game.image, game.id):
                                    print(f"  - Cover image saved successfully for {game.title}")
                                else:
                                    print(f"  - WARNING: Failed to save cover image for {game.title}")

                                # Clean up the temporary file
                                import os
                                try:
                                    os.unlink(game.image)
                                    print(f"  - Temporary image file deleted: {game.image}")
                                except Exception as del_err:
                                    print(f"  - WARNING: Failed to delete temporary image file: {del_err}")
                            except Exception as img_save_err:
                                print(f"  - ERROR saving cover image: {img_save_err}")

                        added_count += 1
                    else:
                        errors.append(f"Failed to save game '{title}'")

                except Exception as e:
                    game_name = game_data.get('name', 'Unknown')
                    print(f"ERROR processing game {game_name}: {e}")
                    import traceback
                    traceback.print_exc()
                    errors.append(f"Error processing game {game_name}: {e}")

            # Final progress update
            if progress_callback:
                try:
                    progress_callback(100, 100, "Complete")
                except Exception as e:
                    print(f"Error with final progress callback: {e}")

            return added_count, errors

        except Exception as e:
            if progress_callback:
                try:
                    progress_callback(100, 100, f"Error: {e}")
                except Exception as callback_error:
                    print(f"Error with error progress callback: {callback_error}")

            return 0, [f"Error syncing Xbox source: {e}"]

    def sync_psn_source(self, source: Source, progress_callback: Optional[callable] = None) -> Tuple[int, List[str]]:
        """
        Sync PlayStation Network games with the library.

        Args:
            source: The PSN source to sync
            progress_callback: Optional callback function for progress updates

        Returns:
            Tuple of (number of games added/updated, list of error messages)
        """
        added_count = 0
        errors = []

        # Initial progress update
        if progress_callback:
            try:
                progress_callback(0, 100, "Initializing PlayStation Network client...")
            except Exception as e:
                print(f"Error with progress callback: {e}")

        try:
            # Create secure token storage
            tokens_dir = self.ensure_secure_token_storage(source.id)

            # Create PSN client with our token directory
            psn = PSNClient(token_dir=str(tokens_dir), debug=True)

            # Check if we need to authenticate
            if not psn.is_authenticated():
                if progress_callback:
                    try:
                        progress_callback(10, 100, "PlayStation Network token missing or invalid. Authentication required.")
                    except Exception as e:
                        print(f"Error with progress callback: {e}")

                # Return error if not authenticated - requires manual token entry
                # We don't include the full instructions here as they're shown in the authentication dialog
                return 0, ["PlayStation Network authentication required. Please click the 'Authenticate with PlayStation' button in the source settings."]

            # Update progress
            if progress_callback:
                try:
                    progress_callback(30, 100, "Fetching PlayStation Network library...")
                except Exception as e:
                    print(f"Error with progress callback: {e}")

            # Get PSN library data
            psn_data = psn.fetch_all_data()
            psn_games = psn_data.get('games', [])
            psn_trophies = psn_data.get('trophies', [])

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
                    print(f"Error with progress callback: {e}")

            # Process each game
            for index, game_data in enumerate(psn_games):
                try:
                    # Report progress
                    if progress_callback and index % 10 == 0:
                        try:
                            percentage = 40 + int((index / total_games) * 60)
                            progress_callback(percentage, 100, f"Processing game {index+1}/{total_games}")
                        except Exception as e:
                            print(f"Error with progress callback: {e}")

                    # Get game details
                    title = game_data.get('name', 'Unknown Game')
                    game_id = game_data.get('titleId', '')

                    # Add debug logging
                    print(f"Processing PSN game: {title} (ID: {game_id})")

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
                    from data_mapping import Platforms

                    platform_enums = []
                    platform_str = game_data.get('platform', '')

                    try:
                        # Map platform string to our platform enum
                        if platform_str == "PS5":
                            platform_enums.append(Platforms.PLAYSTATION5)
                        elif platform_str == "PS4":
                            platform_enums.append(Platforms.PLAYSTATION4)
                        elif platform_str == "PS3":
                            platform_enums.append(Platforms.PLAYSTATION3)
                        elif platform_str == "PS Vita":
                            platform_enums.append(Platforms.PLAYSTATION_VITA)
                        elif platform_str == "PSP":
                            platform_enums.append(Platforms.PSP)

                        print(f"  - Mapped platforms: {[p.value for p in platform_enums]}")

                        if platform_enums:
                            game.platforms = platform_enums
                            print(f"  - Platforms set successfully")
                    except Exception as e:
                        print(f"  - ERROR setting platforms: {e}. Platform: {platform_str}")
                        # Debug information to help diagnose platform mapping issues
                        print(f"  - Platform enum values: {[p.name for p in Platforms]}")

                    # Add description if available
                    description = game_data.get('description', '')
                    if description:
                        game.description = description

                    # Handle play time from trophies data
                    # For PS games, we estimate play time based on trophy data if available
                    playstation_id = game_data.get('npCommunicationId', '')
                    if playstation_id:
                        # Look for matching trophy data
                        for trophy_title in psn_trophies:
                            if trophy_title.get('npCommunicationId') == playstation_id:
                                # Found matching trophy title
                                trophy_progress = trophy_title.get('progress', 0)
                                trophy_earned = trophy_title.get('earnedTrophies', {}).get('total', 0)

                                # If we have earned trophies or made progress, mark as played
                                if trophy_earned > 0 or trophy_progress > 0:
                                    from data_mapping import CompletionStatus
                                    game.play_count = 1
                                    game.completion_status = CompletionStatus.PLAYED

                                    # Rough play time estimate based on trophies (very approximate)
                                    if trophy_progress > 0:
                                        # Estimate: 1 hour per 10% progress (very rough)
                                        estimated_hours = (trophy_progress / 10.0) * 1.0
                                        game.play_time = int(estimated_hours * 3600)  # Convert to seconds
                                        print(f"  - Estimated play time: {game.play_time} seconds (from {trophy_progress}% trophy progress)")

                                # Stop looking after finding a match
                                break

                    # Get cover image if available
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

                    if image_url:
                        # Store the URL in config for reference
                        if 'game_covers' not in source.config:
                            source.config['game_covers'] = {}

                        source.config['game_covers'][title] = image_url
                        self.save_source(source)

                        # Download and save the cover image immediately
                        try:
                            print(f"  - Downloading cover image from URL: {image_url}")
                            import requests
                            import tempfile

                            # Download the image to a temporary file
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                                response = requests.get(image_url, stream=True, timeout=10)
                                response.raise_for_status()  # Raise error for bad status codes

                                # Write the image data to the temporary file
                                for chunk in response.iter_content(chunk_size=8192):
                                    temp_file.write(chunk)

                                temp_path = temp_file.name

                            # Use the temporary file for the game image
                            game.image = temp_path
                            print(f"  - Image downloaded to temporary file: {temp_path}")
                        except Exception as img_err:
                            print(f"  - ERROR downloading cover image: {img_err}")

                    # Save the game
                    if self.data_handler.save_game(game):
                        # After the game is saved with an ID, save the playtime separately
                        if hasattr(game, 'play_time') and game.play_time > 0:
                            # Use the data_handler method to save play time
                            if not self.data_handler.update_play_time(game, game.play_time):
                                print(f"  - WARNING: Failed to save play time for {game.title}")

                        # Save play count if set
                        if hasattr(game, 'play_count') and game.play_count > 0:
                            if not self.data_handler.update_play_count(game, game.play_count):
                                print(f"  - WARNING: Failed to save play count for {game.title}")

                        # Save the cover image if it was downloaded to a temporary file
                        if hasattr(game, 'image') and game.image:
                            try:
                                # Use data_handler to save the cover image
                                if self.data_handler.save_game_image(game.image, game.id):
                                    print(f"  - Cover image saved successfully for {game.title}")
                                else:
                                    print(f"  - WARNING: Failed to save cover image for {game.title}")

                                # Clean up the temporary file
                                import os
                                try:
                                    os.unlink(game.image)
                                    print(f"  - Temporary image file deleted: {game.image}")
                                except Exception as del_err:
                                    print(f"  - WARNING: Failed to delete temporary image file: {del_err}")
                            except Exception as img_save_err:
                                print(f"  - ERROR saving cover image: {img_save_err}")

                        added_count += 1
                    else:
                        errors.append(f"Failed to save game '{title}'")

                except Exception as e:
                    game_name = game_data.get('name', 'Unknown')
                    print(f"ERROR processing game {game_name}: {e}")
                    import traceback
                    traceback.print_exc()
                    errors.append(f"Error processing game {game_name}: {e}")

            # Final progress update
            if progress_callback:
                try:
                    progress_callback(100, 100, "Complete")
                except Exception as e:
                    print(f"Error with final progress callback: {e}")

            return added_count, errors

        except Exception as e:
            if progress_callback:
                try:
                    progress_callback(100, 100, f"Error: {e}")
                except Exception as callback_error:
                    print(f"Error with error progress callback: {callback_error}")

            return 0, [f"Error syncing PSN source: {e}"]