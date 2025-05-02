import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from data_handler import DataHandler, Game
from data_mapping import CompletionStatus, InvalidCompletionStatusError, Platforms, InvalidPlatformError


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
        completion_status = CompletionStatus.NOT_PLAYED  # Default
        if "CompletionStatus" in game_data and isinstance(game_data["CompletionStatus"], dict):
            # Map GUID to completion status enum
            completion_status_mapping = {
                "03113e48-ab80-4860-ad60-515092cb1d71": CompletionStatus.PLAYING,
                "24e0d267-000d-41fb-96a7-5993c714b989": CompletionStatus.ON_HOLD,
                "261c9bdf-a355-474b-8a3a-7f20e060d2b6": CompletionStatus.BEATEN,
                "37db65b9-4727-4e5d-b6c6-88ec8a03f3ac": CompletionStatus.COMPLETED,
                "53df16bc-2c3a-4b3b-9362-d26cf10ccdea": CompletionStatus.NOT_PLAYED,
                "ad05e067-fc33-48d4-b299-7470312ac711": CompletionStatus.PLAYED,
                "b0a131bb-df0d-4c7e-9e59-09eafef5e460": CompletionStatus.ABANDONED,
                "ba3d457a-f685-414d-90e0-07bdac9daf54": CompletionStatus.PLAN_TO_PLAY
            }

            # Check for GUID in ID field
            guid = None
            if "$guid" in game_data["CompletionStatusId"]:
                guid = game_data["CompletionStatusId"]["$guid"]

            if guid and guid in completion_status_mapping:
                # Use mapped enum directly
                completion_status = completion_status_mapping[guid]

        # Extract platforms if available
        platforms = []
        platform_ids = []

        if "PlatformIds" in game_data:
            # Platform IDs are expected to be a list

            if isinstance(game_data["PlatformIds"], list):
                # Multiple platforms
                for platform_id in game_data["PlatformIds"]:
                    if isinstance(platform_id, dict) and "$guid" in platform_id:
                        platform_ids.append(platform_id["$guid"])
            elif isinstance(game_data["PlatformIds"], dict) and "$guid" in game_data["PlatformIds"]:
                # Single platform
                platform_ids.append(game_data["PlatformIds"]["$guid"])
        # Also check PlatformId (singular) for backwards compatibility
        elif "PlatformId" in game_data:
            # Platform ID might be a single GUID object or a list of them

            if isinstance(game_data["PlatformId"], list):
                # Multiple platforms
                for platform_id in game_data["PlatformId"]:
                    if isinstance(platform_id, dict) and "$guid" in platform_id:
                        platform_ids.append(platform_id["$guid"])
            elif isinstance(game_data["PlatformId"], dict) and "$guid" in game_data["PlatformId"]:
                # Single platform
                platform_ids.append(game_data["PlatformId"]["$guid"])

        # Map GUID to platform enum
        platform_mapping = {
            "089f77c6-a466-404b-9321-e4e8f7b59117": Platforms.COMMODORE_64,
            "08e57df9-8a7a-4f74-b02d-2c8c1fc78263": Platforms.NINTENDO_64,
            "09f9a10d-05bb-4b17-b1e8-b5264680d2b9": Platforms.COMMODORE_AMIGA_CD32,
            "12981385-5cc0-407c-a798-9ad1fd91e22b": Platforms.PC_DOS,
            "182098d7-7f3b-40d4-83c8-99c0b47a3e3f": Platforms.NINTENDO_GAMECUBE,
            "19425498-f998-4682-b3a6-00af0c609688": Platforms.COMMODORE_PET,
            "19796010-7883-4f0b-928e-5150226fef68": Platforms.NINTENDO_WII,
            "1e6ab01b-1d24-4ab6-ae10-f8c764527056": Platforms.NEC_TURBOGRAFX_CD,
            "23237b00-2544-4846-a99d-309af859f2dd": Platforms.NINTENDO_GAMEBOY_COLOR,
            "245f5070-d298-4bcc-bceb-ac22fd083a23": Platforms.SINCLAIR_ZX81,
            "290be302-541f-4190-8983-383fb92db5e4": Platforms.NINTENDO_WIIU,
            "3ca55b8d-cac7-42f4-a373-03afe027b952": Platforms.BANDAI_WONDERSWAN,
            "408f1bd5-add9-41eb-aa55-ff8ed89bbcb3": Platforms.NINTENDO_SNES,
            "420813ba-ee50-4fd3-919e-58a38c98cb72": Platforms.SINCLAIR_ZXSPECTRUM,
            "43411920-27d3-4742-9fd5-867f983a28d9": Platforms.NEC_SUPERGRAFX,
            "45e7b2c5-03b2-4d91-b0f6-db05cd32a805": Platforms.PC_98,
            "495bf338-b96e-4f0f-aa84-b289aec86496": Platforms.COMMODORE_AMIGA,
            "4b21abab-43f7-4ff1-bbe1-9d06b0b67b93": Platforms.COLECO_VISION,
            "4bffcbc4-ed7a-4e1f-acbf-4147c3768e8a": Platforms.NINTENDO_FAMICOM_DISK,
            "5ea532af-7bf2-4bc5-8195-590e54fdf7b5": Platforms.NINTENDO_DS,
            "62c847dc-9de6-40ee-863d-e8d673cf2905": Platforms.XBOX,
            "64bb761c-3340-4ced-a81f-d7430b1377c5": Platforms.SEGA_MASTERSYSTEM,
            "6563d5c0-defa-4fca-9b42-cfa95adcf15b": Platforms.SEGA_CD,
            "67ff2460-e9f3-414f-9f83-48d79e735048": Platforms.SEGA_32X,
            "683134b4-8f19-43fd-b5f6-77ffc0eda1a1": Platforms.ARCADE,
            "6b9bd9e1-5aa2-467a-90e8-326dac67103e": Platforms.BANDAI_WONDERSWAN_COLOR,
            "6e2bfde6-2bbb-41a7-919f-963843105d5c": Platforms.PC_WINDOWS,
            "72dc193d-6230-4f22-ace7-09d92c0c16c3": Platforms.ATARI_8BIT,
            "745982fe-0827-45af-ae05-68eb2bfe34d7": Platforms.SNK_NEOGEOPOCKET_COLOR,
            "75a0b1c8-8252-40cf-9bc4-494049b31c67": Platforms.NINTENDO_GAMEBOY,
            "770f5470-6d82-4f2f-a3a6-d715d27d0489": Platforms.PLAYSTATION3,
            "78270ad3-fa5d-4c1c-b23c-e0311afdbe72": Platforms.COMMODORE_PLUS4,
            "7ac0bc0b-1588-48b6-a2d2-ee6637a584a5": Platforms.ATARI_LYNX,
            "7eae81f8-d0a7-459f-ae98-16a7a4bdb459": Platforms.APPLE_II,
            "82ed8314-efbc-47b4-9d53-6451ed781f4f": Platforms.MATTEL_INTELLIVISION,
            "87d8c0c0-e32c-4c7f-809f-e8dd3b8886f5": Platforms.PLAYSTATION,
            "9492092b-60d2-49db-9282-f70290aa2061": Platforms.ATARI_5200,
            "971c9cad-547a-44e8-b603-f4e9933edaa3": Platforms.PC_LINUX,
            "97e7f5b1-fe82-4a79-b137-269c2e1a1087": Platforms.NINTENDO_NES,
            "99fa8afe-b9b2-4d6c-a0eb-89b687e22378": Platforms.THREE_DO,
            "9ef11ad6-9f3e-4dd8-ae45-ef35b4ad17bf": Platforms.NINTENDO_SWITCH,
            "a1630ad5-7a91-486f-920b-754b10fbe5c6": Platforms.NINTENDO_GAMEBOY_ADVANCE,
            "a2d52c78-47d2-4fb5-9c0c-ca03f6af4f24": Platforms.ATARI_2600,
            "a45bcaff-9086-4185-8739-16626fdbf720": Platforms.NINTENDO_3DS,
            "adb5be6c-e1c6-4d3a-81a7-0d3d390b529f": Platforms.SNK_NEOGEOPOCKET,
            "ae352334-a117-4e86-ace0-6174c9f6851f": Platforms.PLAYSTATION5,
            "afa323da-194e-493b-a1b8-337743f7a10c": Platforms.SEGA_DREAMCAST,
            "b0ef149b-2c92-48ae-906e-82b90072ae63": Platforms.SNK_NEOGEO_CD,
            "b3c02c07-ef17-4194-8d56-6ea02ec0dc56": Platforms.AMSTRAD_CPC,
            "b6aaeb5e-7dcb-48f6-b4aa-30a2628d1a3a": Platforms.ATARI_ST,
            "b758fd35-eee6-4870-a496-82709da47da6": Platforms.WIRELESS,
            "b999e7a7-312d-480d-aabe-a270a0c3cbf2": Platforms.MACINTOSH,
            "bbbb8b28-5a56-4a85-af78-e73bd25de106": Platforms.SEGA_GAMEGEAR,
            "bf9f1fce-5616-4ed3-abcf-549b12e6a053": Platforms.COMMODORE_VIC20,
            "c20ea643-9845-4cf6-8a96-c5be782f5448": Platforms.VECTREX,
            "c4c8b90a-5763-402c-a0e7-4f98c99c763f": Platforms.NEC_TURBOGRAFX_16,
            "c7a23dd5-35e0-454e-84bd-2e9cc8a76abb": Platforms.SEGA_GENESIS,
            "c8c5c6d5-1c62-42a6-ab68-6e0ebefb9c51": Platforms.ATARI_7800,
            "cfdc7708-c03a-48f4-b23b-8d6173b25820": Platforms.XBOX360,
            "d23f2139-92f4-4eaf-aa6a-68516f6d9c80": Platforms.NINTENDO_VIRTUALBOY,
            "d51b7b82-1619-4a18-a7d8-65acf9e6271c": Platforms.XBOX_ONE,
            "d55543c0-6e8a-45e3-9f97-fab70c85e9df": Platforms.ATARI_JAGUAR,
            "df1b9b58-9739-4202-8c10-3e75d6c12c56": Platforms.PLAYSTATION_VITA,
            "e1c13783-627f-4ec4-b92b-7c2d84f7f43c": Platforms.PLAYSTATION4,
            "e201d872-a08d-4aac-8963-ef166348e5a1": Platforms.XBOX_SERIES,
            "e5ce0fed-b4a7-4345-98fa-2ae87c5422f3": Platforms.PSP,
            "efb0f798-4381-499d-8c5b-9863fcceb816": Platforms.NEC_PCFX,
            "f18bb20f-2271-4002-a687-4c8a6598eb80": Platforms.PLAYSTATION2,
            "f8322ae0-69ac-4551-91e8-85f0e8f90c23": Platforms.SEGA_SATURN
        }

        # Convert GUIDs to platform enum values
        for guid in platform_ids:
            if guid in platform_mapping:
                platforms.append(platform_mapping[guid])

        # Create a new game object
        game = Game(
            id="",  # ID will be assigned by data handler
            title=title,
            hidden=game_data.get("Hidden", False),
            created=created_timestamp,  # Use parsed timestamp for creation date
            description=description,
            completion_status=completion_status,
            platforms=platforms
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

        # Save completion status
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
