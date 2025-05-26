import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from data_handler import DataHandler, Game
from data_mapping import (
    CompletionStatus, InvalidCompletionStatusError,
    Platforms, InvalidPlatformError,
    AgeRatings, InvalidAgeRatingError,
    Features, InvalidFeatureError,
    Genres, InvalidGenreError,
    Regions, InvalidRegionError
)

# Set up logger
logger = logging.getLogger(__name__)


class JsonImporter:
    """
    Imports games from a JSON file into GameShelf.
    Expected JSON format: List of dicts with keys:
    - Name: game title
    - Hidden: whether game is hidden (boolean)
    - CoverImage: relative path to cover image
    - Playtime: dict containing playtime info
    - RecentActivity: dict containing last played info
    - CompletionStatus: string value matching CompletionStatus enum values (e.g. "Playing", "Completed")
    - Platform: list of platform strings matching Platform enum values
    - AgeRating: list of age rating strings matching AgeRatings enum values
    - Feature: list of feature strings matching Features enum values
    - Genre: list of genre strings matching Genres enum values
    - Region: list of region strings matching Regions enum values
    """

    def __init__(self, data_handler: DataHandler, existing_games: Optional[List[Game]] = None):
        """
        Initialize the importer with a data handler and optional list of existing games

        Args:
            data_handler: DataHandler instance for saving games
            existing_games: Optional list of existing games for duplicate checking
        """
        self.data_handler = data_handler
        # Store existing games for duplicate checking
        self.existing_games = existing_games or []
        # Create a dictionary of existing games by title for faster lookup
        self.existing_games_by_title = {}
        if existing_games:
            for game in existing_games:
                if game.title.lower() not in self.existing_games_by_title:
                    self.existing_games_by_title[game.title.lower()] = []
                self.existing_games_by_title[game.title.lower()].append(game)

    def get_game_count(self, json_path: str) -> int:
        """
        Get the number of games in a JSON file without importing them

        Args:
            json_path: Path to the JSON file

        Returns:
            Number of games in the file, or 0 if file is invalid
        """
        try:
            if not os.path.exists(json_path):
                return 0

            with open(json_path, 'r', encoding='utf-8') as f:
                games_data = json.load(f)

            if isinstance(games_data, list):
                return len(games_data)
            return 0
        except Exception:
            return 0

    def import_from_file(self, json_path: str, cover_base_dir: str, limit: Optional[int] = None,
                         progress_callback: Optional[callable] = None) -> Tuple[int, int, List[str]]:
        """
        Import games from a JSON file

        Args:
            json_path: Path to the JSON file
            cover_base_dir: Base directory for cover images
            limit: Optional limit on number of games to import (for testing)
            progress_callback: Optional callback function to report progress
                             Takes (current_index, total_count, game_title) as arguments

        Returns:
            Tuple of (number of games imported, number of games skipped, list of error messages)
        """
        if not os.path.exists(json_path):
            return 0, 0, [f"JSON file not found: {json_path}"]

        if not os.path.exists(cover_base_dir):
            return 0, 0, [f"Cover image base directory not found: {cover_base_dir}"]

        # Load the JSON data
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                games_data = json.load(f)

            if not isinstance(games_data, list):
                return 0, 0, ["JSON data is not a list of games"]

        except Exception as e:
            return 0, 0, [f"Error loading JSON file: {str(e)}"]

        # Process each game
        imported_count = 0
        skipped_count = 0
        errors = []

        # Apply limit if specified
        if limit is not None and limit > 0:
            games_data = games_data[:limit]
            logger.info(f"Limiting import to {limit} games")

        total_games = len(games_data)

        for index, game_data in enumerate(games_data):
            try:
                # Get game title for progress reporting and tracking
                game_title = game_data.get("Name", f"Game {index}")

                # Report progress if callback provided
                if progress_callback:
                    progress_callback(index, total_games, game_title)

                # Check if the game is a duplicate based on multiple attributes
                if self._is_duplicate_game(game_data):
                    logger.info(f"Skipping duplicate game: {game_title}")
                    skipped_count += 1
                    # Still report progress
                    if progress_callback:
                        progress_callback(index, total_games, f"{game_title} (skipped)")
                else:
                    # Try to import the game
                    result = self._import_game(game_data, cover_base_dir)
                    if result:
                        imported_count += 1
                    else:
                        errors.append(f"Failed to import game at index {index}")
            except Exception as e:
                errors.append(f"Error importing game at index {index}: {str(e)}")

        # Final progress update (100%)
        if progress_callback:
            progress_callback(total_games, total_games, "Complete")

        return imported_count, skipped_count, errors

    def _import_game(self, game_data: Dict[str, Any], cover_base_dir: str) -> bool:
        """
        Import a single game from JSON data

        Args:
            game_data: Dictionary containing game data
            cover_base_dir: Base directory for cover images

        Returns:
            True if import was successful, False otherwise
        """
        # Extract required fields
        title = game_data.get("Name")
        if not title:
            logger.warning("Skipping game with no title")
            return False

        # We already checked for duplicates before calling this method, so no need to check again

        # Parse creation timestamp (Added field)
        created_timestamp = None
        if "Added" in game_data and isinstance(game_data["Added"], dict):
            try:
                date_str = game_data["Added"].get("$date")
                if date_str:
                    created_timestamp = self._parse_date_to_timestamp(date_str)
            except Exception as e:
                logger.warning(f"Failed to parse Added date for '{title}': {str(e)}")

        # Extract description if available
        description = None
        if "Description" in game_data and game_data["Description"]:
            description = game_data["Description"]

        # Extract completion status if available
        completion_status = CompletionStatus.NOT_PLAYED  # Default
        if "CompletionStatus" in game_data:
            if isinstance(game_data["CompletionStatus"], str):
                # Direct string value
                try:
                    completion_status = CompletionStatus.from_string(game_data["CompletionStatus"])
                except InvalidCompletionStatusError:
                    logger.warning(f"Invalid completion status '{game_data['CompletionStatus']}' for game '{title}', using default")
            elif isinstance(game_data["CompletionStatus"], dict) and "Value" in game_data["CompletionStatus"]:
                # Dictionary with "Value" key containing the string
                try:
                    completion_status = CompletionStatus.from_string(game_data["CompletionStatus"]["Value"])
                except InvalidCompletionStatusError:
                    logger.warning(f"Invalid completion status '{game_data['CompletionStatus']['Value']}' for game '{title}', using default")

        # Extract platforms using string values directly from the Platform field
        platforms = []
        if "Platform" in game_data and isinstance(game_data["Platform"], list):
            for platform_str in game_data["Platform"]:
                try:
                    platform = Platforms.from_string(platform_str)
                    platforms.append(platform)
                except InvalidPlatformError:
                    # Skip invalid platforms
                    logger.warning(f"Skipping invalid platform '{platform_str}' for game '{title}'")

        # Extract age ratings using string values directly from the AgeRating field
        age_ratings = []
        if "AgeRating" in game_data and isinstance(game_data["AgeRating"], list):
            for rating_str in game_data["AgeRating"]:
                try:
                    rating = AgeRatings.from_string(rating_str)
                    age_ratings.append(rating)
                except InvalidAgeRatingError:
                    # Skip invalid age ratings
                    logger.warning(f"Skipping invalid age rating '{rating_str}' for game '{title}'")

        # Extract features using string values directly from the Feature field
        features = []
        if "Feature" in game_data and isinstance(game_data["Feature"], list):
            for feature_str in game_data["Feature"]:
                try:
                    feature = Features.from_string(feature_str)
                    features.append(feature)
                except InvalidFeatureError:
                    # Skip invalid features
                    logger.warning(f"Skipping invalid feature '{feature_str}' for game '{title}'")

        # Extract genres using string values directly from the Genre field
        genres = []
        if "Genre" in game_data and isinstance(game_data["Genre"], list):
            for genre_str in game_data["Genre"]:
                try:
                    genre = Genres.from_string(genre_str)
                    genres.append(genre)
                except InvalidGenreError:
                    # Skip invalid genres
                    logger.warning(f"Skipping invalid genre '{genre_str}' for game '{title}'")

        # Extract regions using string values directly from the Region field
        regions = []
        if "Region" in game_data and isinstance(game_data["Region"], list):
            for region_str in game_data["Region"]:
                try:
                    region = Regions.from_string(region_str)
                    regions.append(region)
                except InvalidRegionError:
                    # Skip invalid regions
                    logger.warning(f"Skipping invalid region '{region_str}' for game '{title}'")

        # Extract source if available
        source = None
        if "Source" in game_data and game_data["Source"]:
            source = game_data["Source"]

        # Create a new game object
        game = Game(
            id="",  # ID will be assigned by data handler
            title=title,
            hidden=game_data.get("Hidden", False),
            created=created_timestamp,  # Use parsed timestamp for creation date
            description=description,
            completion_status=completion_status,
            platforms=platforms,
            age_ratings=age_ratings,
            features=features,
            genres=genres,
            regions=regions,
            source=source
        )

        # Process playtime if available
        if "Playtime" in game_data:
            try:
                if isinstance(game_data["Playtime"], dict) and "$numberLong" in game_data["Playtime"]:
                    # Handle $numberLong format
                    playtime_seconds = int(game_data["Playtime"]["$numberLong"])
                    game.play_time = playtime_seconds
                elif isinstance(game_data["Playtime"], dict):
                    # Extract first value from dict, ignoring keys (legacy format)
                    playtime_values = list(game_data["Playtime"].values())
                    if playtime_values:
                        playtime_seconds = int(float(playtime_values[0]))
                        game.play_time = playtime_seconds
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid playtime value for game '{title}': {e}")

        # Process play count if available
        if "PlayCount" in game_data:
            try:
                if isinstance(game_data["PlayCount"], dict) and "$numberLong" in game_data["PlayCount"]:
                    # Handle $numberLong format
                    play_count = int(game_data["PlayCount"]["$numberLong"])
                    game.play_count = play_count
                elif isinstance(game_data["PlayCount"], (int, float)):
                    # Direct numeric value
                    game.play_count = int(game_data["PlayCount"])
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid play count value for game '{title}': {e}")

        # Save the game first to get an ID assigned, preserving the original creation time
        if not self.data_handler.save_game(game, preserve_created_time=True):
            logger.error(f"Failed to save game '{title}'")
            return False

        # Get the game's yaml file path to update its modification time later
        game_yaml_path = Path(self._get_game_yaml_path(game))

        # Process cover image if available
        cover_path = game_data.get("CoverImage")
        if cover_path:
            # Normalize path separators - handle Windows backslashes
            cover_path = cover_path.replace('\\', os.path.sep)
            full_cover_path = os.path.join(cover_base_dir, cover_path)
            if os.path.exists(full_cover_path):
                self.data_handler.save_game_image(full_cover_path, game.id)
            else:
                logger.warning(f"Cover image not found for game '{title}': {full_cover_path}")

        # Process recent activity (last played time)
        last_played_timestamp = None
        if "RecentActivity" in game_data or "LastActivity" in game_data:
            activity_dict = game_data.get("RecentActivity") or game_data.get("LastActivity")
            if isinstance(activity_dict, dict):
                date_str = activity_dict.get("$date")
                if date_str:
                    try:
                        last_played_timestamp = self._parse_date_to_timestamp(date_str)

                        # Make sure play count is at least 1 if the game has been played
                        if game.play_count == 0:
                            game.play_count = 1
                    except Exception as e:
                        logger.warning(f"Failed to parse last played date for '{title}': {str(e)}")

        # Update play count to make sure it reflects correctly
        if game.play_count > 0:
            self.data_handler.update_play_count(game, game.play_count)

            # Set the last played time if available
            if last_played_timestamp:
                self.data_handler.set_last_played_time(game, last_played_timestamp)

        # Update play time if needed
        if game.play_time > 0:
            self.data_handler.update_play_time(game, game.play_time)

        # Save description if available
        if game.description:
            self.data_handler.update_game_description(game, game.description)

        # Save completion status
        self.data_handler.update_completion_status(game, game.completion_status)

        # Save platforms if available
        if game.platforms:
            self.data_handler.update_platforms(game, game.platforms)

        # Save age ratings if available
        if game.age_ratings:
            self.data_handler.update_age_ratings(game, game.age_ratings)

        # Save features if available
        if game.features:
            self.data_handler.update_features(game, game.features)

        # Save genres if available
        if game.genres:
            self.data_handler.update_genres(game, game.genres)

        # Save regions if available
        if game.regions:
            self.data_handler.update_regions(game, game.regions)

        # Process modified timestamp
        modified_timestamp = None
        if "Modified" in game_data and isinstance(game_data["Modified"], dict):
            try:
                date_str = game_data["Modified"].get("$date")
                if date_str:
                    modified_timestamp = self._parse_date_to_timestamp(date_str)
            except Exception as e:
                logger.warning(f"Failed to parse Modified date for '{title}': {str(e)}")

        # Update file timestamps if we have the data
        if modified_timestamp and game_yaml_path.exists():
            try:
                # Update the game.yaml file mtime to match the Modified date
                os.utime(game_yaml_path, (modified_timestamp, modified_timestamp))
            except Exception as e:
                logger.warning(f"Failed to update modified timestamp for '{title}': {str(e)}")

        return True

    def _parse_date_to_timestamp(self, date_str: str) -> float:
        """
        Parse a date string to Unix timestamp.
        Handles various ISO formats including those with timezone info.

        Args:
            date_str: Date string to parse

        Returns:
            Unix timestamp (seconds since epoch)
        """
        try:
            # Try parsing ISO format with timezone
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.timestamp()
        except:
            # Try parsing without timezone
            if 'T' in date_str:
                # Split at decimal point if exists
                if '.' in date_str:
                    parts = date_str.split('.')
                    # Keep only the first 6 digits of the decimal part (microseconds)
                    if len(parts) > 1 and parts[1]:
                        decimal_part = parts[1]
                        if len(decimal_part) > 6:
                            decimal_part = decimal_part[:6]
                        date_str = f"{parts[0]}.{decimal_part}"
                dt = datetime.fromisoformat(date_str.replace('Z', ''))
                return dt.timestamp()
            else:
                # Regular date without time
                dt = datetime.fromisoformat(date_str)
                return dt.timestamp()

    def _is_duplicate_game(self, game_data: Dict[str, Any]) -> bool:
        """
        Check if a game is a duplicate based on title, source, platforms, and regions

        Args:
            game_data: Dictionary containing game data from the JSON file

        Returns:
            True if the game is a duplicate, False otherwise
        """
        title = game_data.get("Name")
        if not title or title.lower() not in self.existing_games_by_title:
            return False

        # Get source if available
        source = game_data.get("Source", "")

        # Extract platforms from game data
        platforms = []
        if "Platform" in game_data and isinstance(game_data["Platform"], list):
            for platform_str in game_data["Platform"]:
                try:
                    platform = Platforms.from_string(platform_str)
                    platforms.append(platform.value)
                except InvalidPlatformError:
                    pass

        # Sort platforms to ensure consistent comparison
        platforms.sort()

        # Extract regions from game data
        regions = []
        if "Region" in game_data and isinstance(game_data["Region"], list):
            for region_str in game_data["Region"]:
                try:
                    region = Regions.from_string(region_str)
                    regions.append(region.value)
                except InvalidRegionError:
                    pass

        # Sort regions to ensure consistent comparison
        regions.sort()

        # Check against all existing games with the same title
        potential_matches = self.existing_games_by_title.get(title.lower(), [])
        for existing_game in potential_matches:
            # Check if source matches (if both have a source)
            if source and existing_game.source and source != existing_game.source:
                continue

            # Compare platforms
            existing_platforms = sorted([p.value for p in existing_game.platforms])
            if platforms and existing_platforms and platforms != existing_platforms:
                continue

            # Compare regions
            existing_regions = sorted([r.value for r in existing_game.regions])
            if regions and existing_regions and regions != existing_regions:
                continue

            # If we got here, the game is a duplicate (title matches and other attributes don't conflict)
            return True

        return False

    def _get_game_yaml_path(self, game: Game) -> str:
        """
        Get the path to a game's YAML file.

        Args:
            game: The game object

        Returns:
            Path to the game's YAML file
        """
        game_dir = self.data_handler._get_game_dir_from_id(game.id)
        return str(game_dir / "game.yaml")