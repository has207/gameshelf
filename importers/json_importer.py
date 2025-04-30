import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from data_handler import DataHandler, Game


class JsonImporter:
    """
    Imports games from a JSON file into GameShelf.
    Expected JSON format: List of dicts with keys:
    - Name: game title
    - Hidden: whether game is hidden (boolean)
    - CoverImage: relative path to cover image
    - Playtime: dict containing playtime info
    - RecentActivity: dict containing last played info
    """

    def __init__(self, data_handler: DataHandler):
        """Initialize the importer with a data handler"""
        self.data_handler = data_handler

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
                         progress_callback: Optional[callable] = None) -> Tuple[int, List[str]]:
        """
        Import games from a JSON file

        Args:
            json_path: Path to the JSON file
            cover_base_dir: Base directory for cover images
            limit: Optional limit on number of games to import (for testing)
            progress_callback: Optional callback function to report progress
                             Takes (current_index, total_count, game_title) as arguments

        Returns:
            Tuple of (number of games imported, list of error messages)
        """
        if not os.path.exists(json_path):
            return 0, [f"JSON file not found: {json_path}"]

        if not os.path.exists(cover_base_dir):
            return 0, [f"Cover image base directory not found: {cover_base_dir}"]

        # Load the JSON data
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                games_data = json.load(f)

            if not isinstance(games_data, list):
                return 0, ["JSON data is not a list of games"]

        except Exception as e:
            return 0, [f"Error loading JSON file: {str(e)}"]

        # Process each game
        imported_count = 0
        errors = []

        # Apply limit if specified
        if limit is not None and limit > 0:
            games_data = games_data[:limit]
            print(f"Limiting import to {limit} games")

        total_games = len(games_data)

        for index, game_data in enumerate(games_data):
            try:
                # Get game title for progress reporting
                game_title = game_data.get("Name", f"Game {index}")

                # Report progress if callback provided
                if progress_callback:
                    progress_callback(index, total_games, game_title)

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

        return imported_count, errors

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
            print("Skipping game with no title")
            return False

        # Parse creation timestamp (Added field)
        created_timestamp = None
        if "Added" in game_data and isinstance(game_data["Added"], dict):
            try:
                date_str = game_data["Added"].get("$date")
                if date_str:
                    created_timestamp = self._parse_date_to_timestamp(date_str)
            except Exception as e:
                print(f"Failed to parse Added date for '{title}': {str(e)}")

        # Extract description if available
        description = None
        if "Description" in game_data and game_data["Description"]:
            description = game_data["Description"]

        # Extract completion status if available
        completion_status = None
        if "CompletionStatus" in game_data and isinstance(game_data["CompletionStatus"], dict):
            # Map GUID to completion status name
            completion_status_mapping = {
                "03113e48-ab80-4860-ad60-515092cb1d71": "Playing",
                "24e0d267-000d-41fb-96a7-5993c714b989": "On Hold",
                "261c9bdf-a355-474b-8a3a-7f20e060d2b6": "Beaten",
                "37db65b9-4727-4e5d-b6c6-88ec8a03f3ac": "Completed",
                "53df16bc-2c3a-4b3b-9362-d26cf10ccdea": "Not Played",
                "ad05e067-fc33-48d4-b299-7470312ac711": "Played",
                "b0a131bb-df0d-4c7e-9e59-09eafef5e460": "Abandoned",
                "ba3d457a-f685-414d-90e0-07bdac9daf54": "Plan to Play"
            }

            # Check for GUID in ID field
            guid = None
            if "Id" in game_data["CompletionStatus"]:
                guid = game_data["CompletionStatus"]["Id"]
            elif "$oid" in game_data["CompletionStatus"]:
                guid = game_data["CompletionStatus"]["$oid"]

            if guid and guid in completion_status_mapping:
                completion_status = completion_status_mapping[guid]
            elif "Name" in game_data["CompletionStatus"]:
                # Use name directly if available and no mapping found
                completion_status = game_data["CompletionStatus"]["Name"]

        # Create a new game object
        game = Game(
            id="",  # ID will be assigned by data handler
            title=title,
            hidden=game_data.get("Hidden", False),
            created=created_timestamp,  # Use parsed timestamp for creation date
            description=description,
            completion_status=completion_status
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
                print(f"Invalid playtime value for game '{title}': {e}")

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
                print(f"Invalid play count value for game '{title}': {e}")

        # Save the game first to get an ID assigned, preserving the original creation time
        if not self.data_handler.save_game(game, preserve_created_time=True):
            print(f"Failed to save game '{title}'")
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
                print(f"Cover image not found for game '{title}': {full_cover_path}")

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
                        print(f"Failed to parse last played date for '{title}': {str(e)}")

        # Update play count to make sure it reflects correctly
        if game.play_count > 0:
            self.data_handler.update_play_count(game, game.play_count)

            # Set the last played time if available
            if last_played_timestamp:
                play_count_path = Path(game.get_play_count_path(self.data_handler.data_dir))
                if play_count_path.exists():
                    os.utime(play_count_path, (last_played_timestamp, last_played_timestamp))

        # Update play time if needed
        if game.play_time > 0:
            self.data_handler.update_play_time(game, game.play_time)

        # Save description if available
        if game.description:
            self.data_handler.update_game_description(game, game.description)

        # Save completion status if available
        if game.completion_status:
            self.data_handler.update_completion_status(game, game.completion_status)

        # Process modified timestamp
        modified_timestamp = None
        if "Modified" in game_data and isinstance(game_data["Modified"], dict):
            try:
                date_str = game_data["Modified"].get("$date")
                if date_str:
                    modified_timestamp = self._parse_date_to_timestamp(date_str)
            except Exception as e:
                print(f"Failed to parse Modified date for '{title}': {str(e)}")

        # Update file timestamps if we have the data
        if modified_timestamp and game_yaml_path.exists():
            try:
                # Update the game.yaml file mtime to match the Modified date
                os.utime(game_yaml_path, (modified_timestamp, modified_timestamp))
            except Exception as e:
                print(f"Failed to update modified timestamp for '{title}': {str(e)}")

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