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

        # Create a new game object
        game = Game(
            id="",  # ID will be assigned by data handler
            title=title,
            hidden=game_data.get("Hidden", False)
        )

        # Process playtime if available
        if "Playtime" in game_data and isinstance(game_data["Playtime"], dict):
            # Extract first value from the playtime dict, ignoring keys
            playtime_values = list(game_data["Playtime"].values())
            if playtime_values:
                try:
                    # Convert playtime to seconds
                    playtime_seconds = int(float(playtime_values[0]))
                    game.play_time = playtime_seconds
                except (ValueError, TypeError):
                    print(f"Invalid playtime value for game '{title}'")

        # Save the game first to get an ID assigned
        if not self.data_handler.save_game(game):
            print(f"Failed to save game '{title}'")
            return False

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
        if "RecentActivity" in game_data and isinstance(game_data["RecentActivity"], dict):
            # Extract first value from the RecentActivity dict, ignoring keys
            activity_values = list(game_data["RecentActivity"].values())
            if activity_values and activity_values[0]:
                try:
                    # Parse ISO format timestamp
                    date_str = activity_values[0]
                    # Handle different date formats
                    try:
                        # Try parsing ISO format with timezone
                        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    except:
                        # Try parsing without timezone
                        if 'T' in date_str:
                            # Split at decimal point if exists
                            if '.' in date_str:
                                date_str = date_str.split('.')[0]
                            dt = datetime.fromisoformat(date_str)
                        else:
                            # Regular date without time
                            dt = datetime.fromisoformat(date_str)

                    # Convert to timestamp and update last played time by incrementing play count
                    timestamp = dt.timestamp()
                    # Set play count to at least 1 to record last played time
                    if game.play_count == 0:
                        game.play_count = 1
                    self.data_handler.update_play_count(game, game.play_count)

                    # Update the timestamp of the play_count file to match the activity date
                    play_count_path = Path(game.get_play_count_path(self.data_handler.data_dir))
                    if play_count_path.exists():
                        os.utime(play_count_path, (timestamp, timestamp))
                except Exception as e:
                    print(f"Failed to process recent activity for '{title}': {str(e)}")

        # Update play time if needed
        if game.play_time > 0:
            self.data_handler.update_play_time(game, game.play_time)

        return True