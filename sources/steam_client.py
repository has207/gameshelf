#!/usr/bin/env python3

import os
import re
import json
import time
import math
import yaml
import logging
import vdf
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union

from data import Source, Game, SourceType
from data_mapping import Platforms, Genres, CompletionStatus
from sources.scanner_base import SourceScanner
from cover_fetch import CoverFetcher

# Set up logger
logger = logging.getLogger(__name__)

# Default paths for Steam
DEFAULT_STEAM_PATH = Path.home() / ".steam" / "debian-installation"
DEFAULT_STEAMAPPS_PATH = DEFAULT_STEAM_PATH / "steamapps"

class SteamCLI:
    def __init__(self, steam_path: Optional[Path] = None, api_key: Optional[str] = None, steam_id: Optional[str] = None):
        """
        Initialize the Steam client with the given path and API credentials

        Args:
            steam_path: Path to Steam installation directory. If None, uses default location
            api_key: Optional Steam Web API key
            steam_id: Optional Steam ID
        """
        self.steamapps_path = steam_path or DEFAULT_STEAMAPPS_PATH
        self.api_key = api_key
        self.steam_id = steam_id

    def get_library_folders(self) -> List[Path]:
        """Get all Steam library folders."""
        library_folders = [self.steamapps_path]

        # Parse libraryfolders.vdf to find additional libraries
        vdf_path = self.steamapps_path / "libraryfolders.vdf"

        if vdf_path.exists():
            try:
                with open(vdf_path, 'r', encoding='utf-8') as f:
                    library_data = vdf.load(f)

                # Handle Steam format with numbered keys (older format)
                if "libraryfolders" in library_data:
                    folders_data = library_data["libraryfolders"]

                    for key, value in folders_data.items():
                        if key.isdigit():
                            if isinstance(value, dict) and "path" in value:
                                # Newer format
                                path = Path(value["path"]) / "steamapps"
                                if path.exists() and path not in library_folders:
                                    library_folders.append(path)
                            elif isinstance(value, str):
                                # Older format
                                path = Path(value) / "steamapps"
                                if path.exists() and path not in library_folders:
                                    library_folders.append(path)
            except Exception as e:
                logger.error(f"Error parsing library folders: {e}")

        return library_folders

    def get_installed_games(self) -> Dict[str, Dict]:
        """Get all installed Steam games from all library folders."""
        installed_games = {}
        library_folders = self.get_library_folders()

        for library in library_folders:
            logger.info(f"Checking library: {library}")

            if not library.exists():
                logger.warning(f"Library folder does not exist: {library}")
                continue

            # Look for appmanifest_*.acf files
            for manifest_file in library.glob("appmanifest_*.acf"):
                if manifest_file.name.endswith('.tmp'):
                    continue

                try:
                    with open(manifest_file, 'r', encoding='utf-8') as f:
                        app_data = vdf.load(f)

                    if "AppState" not in app_data:
                        continue

                    app_state = app_data["AppState"]

                    # Check if game is fully installed
                    state_flags = int(app_state.get("StateFlags", 0))
                    if not (state_flags & 4):  # 4 = FullyInstalled
                        continue

                    app_id = app_state.get("appid", "")
                    if not app_id:
                        continue

                    # Get name from various possible locations
                    name = app_state.get("name", "")
                    if not name and "UserConfig" in app_state and "name" in app_state["UserConfig"]:
                        name = app_state["UserConfig"]["name"]

                    # Get install directory
                    install_dir = app_state.get("installdir", "")
                    full_path = library / "common" / install_dir
                    if not full_path.exists():
                        full_path = library / "music" / install_dir
                        if not full_path.exists():
                            full_path = None

                    # Skip soundtracks and content that isn't properly installed
                    if not full_path or "steamapps/music" in str(full_path):
                        logger.info(f"Skipping {name} (not properly installed or soundtrack)")
                        continue

                    # Create game entry
                    installed_games[app_id] = {
                        "app_id": app_id,
                        "name": name,
                        "install_dir": str(full_path),
                        "manifest_path": str(manifest_file),
                        "size": int(app_state.get("SizeOnDisk", 0))
                    }

                except Exception as e:
                    logger.error(f"Error parsing manifest {manifest_file}: {e}")

        return installed_games

    def get_owned_games(self, include_free_games: bool = True) -> List[Dict[str, Any]]:
        """
        Get user's owned games from Steam API

        Args:
            include_free_games: Whether to include free games

        Returns:
            List of games with details
        """
        if not self.api_key or not self.steam_id:
            logger.warning("API key and Steam ID are required to get owned games")
            return []

        logger.info(f"Getting owned games for Steam ID {self.steam_id} with API key {self.api_key[:4]}...")

        url = "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
        params = {
            "key": self.api_key,
            "steamid": self.steam_id,
            "include_appinfo": 1,
            "include_played_free_games": 1 if include_free_games else 0,
            "include_free_sub": 1 if include_free_games else 0,
            "format": "json"
        }

        logger.debug(f"API request URL: {url}")
        logger.debug(f"API request params: {params}")

        try:
            logger.info("Sending request to Steam API...")
            response = requests.get(url, params=params)
            logger.info(f"Got response with status code: {response.status_code}")

            if response.status_code != 200:
                logger.error(f"API request failed with status code {response.status_code}")
                logger.error(f"Response content: {response.text[:1000]}")
                return []

            data = response.json()
            logger.debug(f"Response JSON keys: {list(data.keys())}")

            if "response" in data:
                logger.debug(f"Response data keys: {list(data['response'].keys())}")

                if "games" in data["response"]:
                    games = data["response"]["games"]
                    logger.info(f"Found {len(games)} owned games in Steam library")
                    # Log a sample of the first game if available
                    if games:
                        logger.debug(f"Sample game data: {games[0]}")
                    return games
                else:
                    # Sometimes the API returns an empty response with no games key
                    # This can happen if the profile is private or there are no games
                    logger.warning("No 'games' key found in API response")
                    logger.debug(f"Response content: {data['response']}")

                    # Check if there's a message about the profile being private
                    if "message" in data["response"]:
                        logger.warning(f"API message: {data['response']['message']}")

                    return []
            else:
                logger.warning("Invalid API response format: No 'response' key")
                logger.debug(f"Full response: {data}")
                return []
        except Exception as e:
            logger.error(f"Error fetching owned games: {e}", exc_info=True)
            return []

    def get_game_details(self, app_id: str, title: str) -> Dict[str, Any]:
        """
        Get game details from Steam store API

        Args:
            app_id: The Steam app ID

        Returns:
            Game details dictionary
        """
        url = "https://store.steampowered.com/api/appdetails"
        params = {
            "appids": app_id
        }

        try:
            response = requests.get(url, params=params)
            data = response.json()

            if app_id in data and data[app_id]["success"]:
                return data[app_id]["data"]
            else:
                logger.debug(f"No details found for {title}")
                return {}
        except Exception as e:
            logger.error(f"Error fetching game details for {app_id}: {e}")
            return {}

    def get_artwork_urls(self, app_id: str) -> Dict[str, Any]:
        """Get artwork URLs for a specific game."""
        # Prepare artwork URLs without needing API access
        artwork = {
            "header": f"https://steamcdn-a.akamaihd.net/steam/apps/{app_id}/header.jpg",
            "background": f"https://steamcdn-a.akamaihd.net/steam/apps/{app_id}/page_bg_generated.jpg",
            "cover": f"https://steamcdn-a.akamaihd.net/steam/apps/{app_id}/library_600x900.jpg",
            "capsule": f"https://steamcdn-a.akamaihd.net/steam/apps/{app_id}/capsule_616x353.jpg",
            "logo": f"https://steamcdn-a.akamaihd.net/steam/apps/{app_id}/logo.png",
            "hero": f"https://steamcdn-a.akamaihd.net/steam/apps/{app_id}/library_hero.jpg",
            "store_page": f"https://store.steampowered.com/app/{app_id}/",
        }

        # Get Steam directory (parent of steamapps)
        steam_dir = self.steamapps_path.parent

        # Check for cached artwork in librarycache
        cache_dir = steam_dir / "appcache" / "librarycache"

        # Add local cache information if directory exists
        if cache_dir.exists():
            artwork["local_cache"] = {
                "directory": str(cache_dir),
                "files": []
            }

            # Look for any files with app_id in the name
            for file_path in cache_dir.glob(f"{app_id}*"):
                artwork["local_cache"]["files"].append(str(file_path))

        return artwork

    def _format_size(self, size_bytes):
        """Format size in bytes to human-readable format."""
        if size_bytes == 0:
            return "0 B"
        size_names = ("B", "KB", "MB", "GB", "TB")
        i = int(math.log(size_bytes, 1024))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"

class SteamScanner(SourceScanner):
    """Scanner for Steam libraries"""

    def __init__(self, data_handler):
        """Initialize the scanner with a data handler"""
        super().__init__(data_handler)
        self.cover_fetcher = CoverFetcher(data_handler)
        self.total_games_found = 0  # Track total number of games found during scan

    def scan(self, source: Source, progress_callback: Optional[callable] = None) -> Tuple[int, List[str]]:
        """
        Scan a Steam source for games and add them to the library.

        Args:
            source: The source to scan
            progress_callback: Optional callback function for progress updates

        Returns:
            Tuple of (number of games added/updated, list of error messages)
        """
        if source.source_type != SourceType.STEAM:
            return 0, ["Source is not a Steam source"]

        # Get Steam path from source config
        steam_path = DEFAULT_STEAMAPPS_PATH
        if source.config and "steam_path" in source.config:
            steam_path = Path(source.config["steam_path"])

        # Get API credentials if available
        api_key = None
        steam_id = None
        include_online_games = False

        if source.config:
            if "include_online_games" in source.config:
                include_online_games = source.config["include_online_games"]

            if include_online_games and "api_key" in source.config and "steam_id" in source.config:
                api_key = source.config["api_key"]
                steam_id = source.config["steam_id"]

        # Initialize the Steam client
        steam_client = SteamCLI(steam_path, api_key, steam_id)

        added_count = 0
        errors = []

        # Get existing games from this source
        existing_games_by_id = {}
        for game in self.data_handler.load_games():
            if game.source == source.id and game.launcher_type == "STEAM":
                existing_games_by_id[game.launcher_id] = game

        # Combined dictionary of all games (installed + online library)
        all_games = {}

        # Scan installed games
        try:
            if progress_callback:
                progress_callback(0, 3, "Finding Steam libraries...")

            installed_games = steam_client.get_installed_games()

            if progress_callback:
                progress_callback(1, 3, f"Found {len(installed_games)} installed Steam games")

            # Add installed games to all_games dictionary
            for app_id, game_info in installed_games.items():
                all_games[app_id] = {
                    "app_id": app_id,
                    "title": game_info["name"],
                    "is_installed": True,
                    "install_dir": game_info.get("install_dir", ""),
                    "size": game_info.get("size", 0)
                }

            # If API is available and we want online games, add them too
            if include_online_games and api_key and steam_id:
                if progress_callback:
                    progress_callback(2, 3, "Fetching online library...")

                logger.info(f"Attempting to fetch online games with API key: {api_key[:4]}... and Steam ID: {steam_id}")

                try:
                    online_games = steam_client.get_owned_games()
                    logger.info(f"Fetched {len(online_games)} games from online library")

                    # Add online games to all_games dictionary
                    for game in online_games:
                        app_id = str(game.get("appid", ""))
                        if not app_id:
                            continue

                        logger.debug(f"Processing online game: {game.get('name', 'Unknown')} (ID: {app_id})")

                        # Check if this game is already in the dictionary (i.e., it's installed)
                        if app_id in all_games:
                            # Update existing entry with additional info
                            all_games[app_id]["playtime_minutes"] = game.get("playtime_forever", 0)
                            all_games[app_id]["playtime_2weeks"] = game.get("playtime_2weeks", 0)
                            logger.debug(f"Updated existing game entry with play time data")
                        else:
                            # Add new entry for online-only game
                            all_games[app_id] = {
                                "app_id": app_id,
                                "title": game.get("name", f"Unknown Game ({app_id})"),
                                "is_installed": False,
                                "playtime_minutes": game.get("playtime_forever", 0),
                                "playtime_2weeks": game.get("playtime_2weeks", 0)
                            }
                            logger.debug(f"Added new online-only game entry")
                except Exception as e:
                    logger.error(f"Error fetching online games: {e}", exc_info=True)
                    errors.append(f"Failed to fetch online games: {e}")

                if progress_callback:
                    progress_callback(3, 3, f"Found {len(all_games)} total Steam games")

            # Process all games
            index = 0
            total_games = len(all_games)

            for app_id, game_info in all_games.items():
                try:
                    # Report progress
                    if progress_callback:
                        title = game_info.get("title", f"Game {app_id}")
                        progress_callback(index, total_games, f"Processing {title}...")

                    index += 1

                    # Check if we already have this game from this source
                    if app_id in existing_games_by_id:
                        # Game already exists, skip it
                        continue

                    # Create a new game
                    game = Game(
                        id="",  # ID will be assigned by data handler
                        title=game_info["title"],
                        source=source.id,
                        platforms=[Platforms.PC_WINDOWS]  # Steam games are primarily Windows games
                    )

                    # Set launcher data before saving
                    game.launcher_type = "STEAM"
                    game.launcher_id = app_id

                    # Set installation data for installed games
                    if game_info.get("is_installed", False) and "install_dir" in game_info:
                        game.installation_directory = game_info["install_dir"]
                        game.installation_files = []  # No individual files, just the directory
                        game.installation_size = game_info.get("size", 0)

                    # Try to save the game
                    if self.data_handler.save_game(game):
                        # Set play time if available
                        if "playtime_minutes" in game_info and game_info["playtime_minutes"] > 0:
                            # Convert minutes to seconds
                            play_time_seconds = game_info["playtime_minutes"] * 60
                            self.data_handler.update_play_time(game, play_time_seconds)

                            # Also set play count based on play time
                            play_count = max(1, game_info["playtime_minutes"] // 30)  # Roughly 1 count per half hour
                            self.data_handler.update_play_count(game, play_count)

                        # Try to fetch game details for description, developer, and publisher
                        description = None
                        developer = None
                        publisher = None
                        if api_key:  # Only if we have API access
                            try:
                                game_details = steam_client.get_game_details(app_id, game_info["title"])
                                if game_details:
                                    if "short_description" in game_details:
                                        description = game_details["short_description"]
                                    if "developers" in game_details and game_details["developers"]:
                                        developer = game_details["developers"][0]  # Take first developer
                                    if "publishers" in game_details and game_details["publishers"]:
                                        publisher = game_details["publishers"][0]  # Take first publisher
                            except Exception as e:
                                logger.warning(f"Error fetching details for game {app_id}: {e}")

                        # Save description if we got one
                        if description:
                            self.data_handler.update_game_description(game, description)

                        # Update developer and publisher if we got them
                        if developer or publisher:
                            if developer:
                                game.developer = developer
                            if publisher:
                                game.publisher = publisher
                            # Re-save the game to update developer/publisher data
                            self.data_handler.save_game(game)

                        # Try to fetch cover image from Steam CDN
                        try:
                            artwork = steam_client.get_artwork_urls(app_id)
                            if artwork and "cover" in artwork:
                                image_url = artwork["cover"]
                                logger.debug(f"Downloading cover image for '{game_info['title']}' from {image_url}")
                                success, error = self.cover_fetcher.fetch_and_save_for_game(game.id, image_url, "Steam")
                                if not success:
                                    logger.warning(f"{game_info.get('title')} - {error}")
                        except Exception as e:
                            logger.error(f"Error downloading cover image for '{game_info['title']}': {e}")

                        added_count += 1
                    else:
                        errors.append(f"Failed to save game '{game_info['title']}'")

                except Exception as e:
                    errors.append(f"Error processing game {app_id}: {e}")

            # Final progress update
            if progress_callback:
                progress_callback(total_games, total_games, "Complete")

        except Exception as e:
            errors.append(f"Error scanning Steam library: {e}")
            logger.error(f"Error scanning Steam library: {e}", exc_info=True)

        # Log statistics
        installed_count = sum(1 for g in all_games.values() if g.get("is_installed", False))
        online_only_count = len(all_games) - installed_count

        # Store total games found for reporting purposes
        self.total_games_found = len(all_games)

        logger.info(f"Scan complete. Found {self.total_games_found} Steam games.")
        logger.info(f"  - {installed_count} installed games")
        logger.info(f"  - {online_only_count} online-only games")
        logger.info(f"Added {added_count} new games. Errors: {len(errors)}.")

        return added_count, errors
