import re
import logging
import os
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

from data import Source, Game, SourceType, RomPath
from data_mapping import Platforms, AgeRatings
from sources.scanner_base import SourceScanner
from providers.launchbox_client import LaunchBoxMetadata
from cover_fetch import CoverFetcher

# Set up logger
logger = logging.getLogger(__name__)

class DirectoryScanner(SourceScanner):
    """Scanner for directory/ROM type sources"""

    def __init__(self, data_handler):
        """
        Initialize the scanner with a data handler and metadata provider

        Args:
            data_handler: The data handler instance to use
        """
        super().__init__(data_handler)
        # Initialize the LaunchBox metadata provider with the same data directory
        self.metadata_provider = LaunchBoxMetadata(str(data_handler.data_dir))
        # Initialize the cover fetcher for downloading images
        self.cover_fetcher = CoverFetcher(data_handler)

    def scan(self, source: Source, progress_callback: Optional[callable] = None) -> Tuple[int, List[str]]:
        """
        Scan a directory source for games and add them to the library.
        For RomDirectory sources with platform info, automatically fetches metadata from LaunchBox.

        Args:
            source: The source to scan
            progress_callback: Optional callback function for progress updates

        Returns:
            Tuple of (number of games added/updated, list of error messages)
        """
        if source.source_type != SourceType.ROM_DIRECTORY:
            return 0, ["Source is not a ROM directory source"]

        # Check if we have paths to scan
        if not hasattr(source, "rom_paths") or not source.rom_paths:
            return 0, ["No paths configured for this source"]

        added_count = 0
        errors = []

        # Extract platform from source config
        platform = None
        if source.config and "platform" in source.config:
            # Look up platform enum from string value
            platform_value = source.config["platform"]
            for p in Platforms:
                if p.value == platform_value:
                    platform = p
                    break

            if not platform:
                logger.warning(f"Unknown platform '{platform_value}' specified for source {source.name}")
                # We'll continue without a platform in this case

        # Dictionary to store game entries, keyed by parent folder or file name
        game_entries = {}

        # Scan each path in the source
        for path_index, rom_path in enumerate(source.rom_paths):
            if not rom_path.path or not Path(rom_path.path).exists():
                errors.append(f"Path does not exist: {rom_path.path}")
                continue

            source_path = Path(rom_path.path)

            # Update progress for path
            if progress_callback:
                try:
                    progress_callback(path_index, len(source.rom_paths),
                                     f"Scanning path {path_index+1}/{len(source.rom_paths)}: {source_path}")
                except Exception as e:
                    logger.error(f"Error with progress callback: {e}")

            # Special handling for Wii U games based on folder structure
            if platform and platform == Platforms.NINTENDO_WIIU:
                logger.info(f"Scanning for Wii U games in directory: {rom_path.path}")
                self._scan_wiiu_games(source_path, game_entries, rom_path, progress_callback)
            else:
                # Standard file extension based scanning for other platforms
                self._scan_file_extensions(source_path, game_entries, rom_path, progress_callback)

        # Initial progress update for processing
        total_games = len(game_entries)
        if progress_callback and total_games > 0:
            try:
                progress_callback(0, total_games, "Starting processing...")
            except Exception as e:
                logger.error(f"Error with progress callback: {e}")

        # Get list of existing games from this source
        existing_games_by_path = {}
        for game in self.data_handler.load_games():
            if game.source == source.id:
                # Use installation directory and files as the key for identification
                # This is more robust than using title which can be changed by users
                if hasattr(game, 'installation_directory') and hasattr(game, 'installation_files') and game.installation_directory and game.installation_files:
                    # Create a unique key based on directory and files
                    files_key = "|".join(sorted(game.installation_files)) if isinstance(game.installation_files, list) else str(game.installation_files)
                    path_key = f"{game.installation_directory}::{files_key}"
                    existing_games_by_path[path_key] = game

        # Process each game entry
        index = 0
        for game_key, entry in game_entries.items():
            try:
                # Report progress if callback provided
                if progress_callback and index % 5 == 0:  # Update every 5 games
                    try:
                        progress_callback(index, total_games, f"Processing {entry['title']}...")
                    except Exception as e:
                        logger.error(f"Error with progress callback: {e}")

                index += 1

                title = entry["title"]

                # Check if we already have this game from this source using installation path
                files_key = "|".join(sorted(entry["files"])) if isinstance(entry["files"], list) else str(entry["files"])
                path_key = f"{entry['directory']}::{files_key}"
                if path_key in existing_games_by_path:
                    # Game already exists, skip it
                    continue

                # Create a new game
                game = Game(
                    id="",  # ID will be assigned by data handler
                    title=title,
                    source=source.id
                )

                # Set installation data directly on the game object
                game.installation_directory = entry["directory"]
                game.installation_files = entry["files"]
                game.installation_size = entry["size"]

                # Set platform for ROM_DIRECTORY sources if we have a platform specified
                platform_value = ""
                if platform:
                    game.platforms = [platform]
                    platform_value = platform.value
                    logger.info(f"Setting platform '{platform_value}' for game '{title}'")

                # Try to fetch metadata from LaunchBox if platform is specified
                metadata_game = None
                if platform_value:
                    try:
                        # Search for the game by title and platform
                        logger.info(f"Searching for metadata for '{title}' on platform '{platform_value}'")
                        metadata_game = self.metadata_provider.search_by_title_and_platform(title, platform_value)

                        if metadata_game:
                            # If the metadata game name is different from our title, log the match
                            if metadata_game.name.lower() != title.lower():
                                logger.info(f"Found metadata for '{title}' as '{metadata_game.name}'")
                            else:
                                logger.info(f"Found metadata for '{title}'")

                            # Update game with metadata
                            if metadata_game.description:
                                game.description = metadata_game.description

                            # Add genres if available and valid
                            if metadata_game.genres:
                                genre_names = [genre.name for genre in metadata_game.genres if hasattr(genre, 'name')]
                                if genre_names:
                                    logger.info(f"Found genres for '{title}': {genre_names}")

                                # Use metadata provider's mapping method
                                mapped_genres = self.metadata_provider.map_genres(metadata_game.genres)
                                if mapped_genres:
                                    game.genres = mapped_genres
                                    logger.debug(f"Mapped {len(mapped_genres)} genres for '{title}'")

                            # Extract developer and publisher from companies if available
                            if hasattr(metadata_game, 'companies') and metadata_game.companies:
                                for company in metadata_game.companies:
                                    if hasattr(company, 'type') and hasattr(company, 'name'):
                                        if company.type.lower() == 'developer' and not game.developer:
                                            game.developer = company.name
                                            logger.info(f"Set developer '{company.name}' for '{title}'")
                                        elif company.type.lower() == 'publisher' and not game.publisher:
                                            game.publisher = company.name
                                            logger.info(f"Set publisher '{company.name}' for '{title}'")

                            # Try to map age ratings if available
                            if hasattr(metadata_game, 'rating') and metadata_game.rating:
                                rating_str = metadata_game.rating
                                mapped_rating = self.metadata_provider.map_single_age_rating(rating_str)
                                if mapped_rating:
                                    game.age_ratings = [mapped_rating]
                                    logger.info(f"Mapped metadata rating '{rating_str}' to {mapped_rating.value} for '{title}'")
                                else:
                                    logger.warning(f"Unable to map metadata age rating '{rating_str}' for '{title}'")

                            # Try to extract and map regions if available
                            if hasattr(metadata_game, 'region') and metadata_game.region:
                                region_str = metadata_game.region
                                mapped_region = self.metadata_provider.map_single_region(region_str)
                                if mapped_region:
                                    game.regions = [mapped_region]
                                    logger.info(f"Mapped metadata region '{region_str}' to {mapped_region.value} for '{title}'")
                                else:
                                    logger.warning(f"Unable to map metadata region '{region_str}' for '{title}'")

                            # We already set the platform from source config, so we don't override it
                    except Exception as e:
                        logger.error(f"Error fetching metadata for '{title}': {e}")

                # Save the game (installation data is now included in the game object)
                if self.data_handler.save_game(game):

                    # If we found metadata with cover art, try to download the cover image
                    if metadata_game and metadata_game.images and metadata_game.images.box:
                        try:
                            image_url = metadata_game.images.box.url
                            if image_url:
                                logger.info(f"Downloading cover image for '{title}' from {image_url}")
                                success, error = self.cover_fetcher.fetch_and_save_for_game(game.id, image_url, "LaunchBox")
                                if not success:
                                    logger.warning(f"{title} - {error}")
                        except Exception as e:
                            logger.error(f"Error downloading cover image for '{title}': {e}")

                    # If we found a description, save it separately
                    if metadata_game and metadata_game.description:
                        try:
                            self.data_handler.update_game_description(game, metadata_game.description)
                        except Exception as e:
                            logger.error(f"Error saving description for '{title}': {e}")

                    added_count += 1
                else:
                    errors.append(f"Failed to save game '{title}'")

            except Exception as e:
                errors.append(f"Error processing game {game_key}: {e}")

        # Final progress update
        if progress_callback:
            try:
                progress_callback(total_games, total_games, "Complete")
            except Exception as e:
                logger.error(f"Error with final progress callback: {e}")

        # Log statistics
        single_disc_count = sum(1 for entry in game_entries.values() if len(entry["files"]) == 1)
        multi_disc_count = sum(1 for entry in game_entries.values() if len(entry["files"]) > 1)
        logger.info(f"Scan complete. Found {single_disc_count} single-file games and {multi_disc_count} multi-disc games.")
        logger.info(f"Added {added_count} new games. Errors: {len(errors)}.")

        return added_count, errors

    def _scan_wiiu_games(self, source_path: Path, game_entries: dict, rom_path: RomPath,
                         progress_callback: Optional[callable] = None) -> None:
        """
        Scan for Wii U games by looking for folders with content/meta/code structure

        Args:
            source_path: Path to scan
            game_entries: Dictionary to populate with game entries
            rom_path: Rom path configuration
            progress_callback: Optional callback for progress updates
        """
        try:
            # Get all immediate subdirectories
            subdirs = [d for d in source_path.iterdir() if d.is_dir()]

            # Initial progress update
            total_dirs = len(subdirs)
            if progress_callback and total_dirs > 0:
                try:
                    progress_callback(0, total_dirs, "Scanning for Wii U games...")
                except Exception as e:
                    logger.error(f"Error with progress callback: {e}")

            # Process each directory to check if it's a Wii U game
            for index, game_dir in enumerate(subdirs):
                # Report progress if callback provided
                if progress_callback and index % 5 == 0:  # Update every 5 directories
                    try:
                        progress_callback(index, total_dirs, f"Checking {game_dir.name}...")
                    except Exception as e:
                        logger.error(f"Error with progress callback: {e}")

                # Check if this directory has the Wii U game structure
                # A valid Wii U game folder contains 'content', 'meta', and 'code' subdirectories
                if (game_dir / "content").is_dir() and (game_dir / "meta").is_dir() and (game_dir / "code").is_dir():
                    folder_name = game_dir.name
                    game_key = folder_name

                    # Extract title from folder name
                    name_regex = rom_path.name_regex or "^(.+?)$"

                    try:
                        # Apply regex to extract title from folder name
                        match = re.match(name_regex, folder_name)
                        if match and match.group(1):
                            title = match.group(1)
                            logger.debug(f"Extracted title '{title}' from folder '{folder_name}' using regex: {name_regex}")
                        else:
                            title = folder_name
                            logger.debug(f"Regex didn't match folder name, using fallback title: {title}")
                    except Exception as e:
                        title = folder_name
                        logger.error(f"Error applying name regex '{name_regex}' to folder '{folder_name}': {e}")

                    # Calculate total size of the game directory
                    total_size = 0
                    for root, _, files in os.walk(game_dir):
                        for file in files:
                            file_path = Path(root) / file
                            try:
                                total_size += file_path.stat().st_size
                            except Exception as e:
                                logger.warning(f"Error getting size of {file_path}: {e}")

                    logger.debug(f"Found Wii U game: {title} (key: {game_key})")
                    game_entries[game_key] = {
                        "title": title,
                        "directory": str(game_dir),
                        "files": ["content", "meta", "code"],  # The main subdirectories
                        "size": total_size
                    }

            # Final progress update for scanning phase
            if progress_callback:
                try:
                    progress_callback(total_dirs, total_dirs, "Wii U scan complete")
                except Exception as e:
                    logger.error(f"Error with final scan progress callback: {e}")

            logger.info(f"Found {len(game_entries)} Wii U games in {source_path}")

        except Exception as e:
            logger.error(f"Error scanning Wii U game directories: {e}", exc_info=True)

    def _scan_file_extensions(self, source_path: Path, game_entries: dict, rom_path: RomPath,
                             progress_callback: Optional[callable] = None) -> None:
        """
        Scan for games based on file extensions

        Args:
            source_path: Path to scan
            game_entries: Dictionary to populate with game entries
            rom_path: Rom path configuration
            progress_callback: Optional callback for progress updates
        """
        # Get the list of files matching the specified extensions
        if not rom_path.file_extensions:
            # Default to common game file extensions if none are specified
            extensions = [".exe", ".lnk", ".url", ".desktop"]
        else:
            extensions = [f".{ext.lstrip('.')}" for ext in rom_path.file_extensions]

        logger.info(f"Scanning directory source: {rom_path.path}")
        logger.info(f"Using extensions: {extensions}")

        # Get all files first to match extensions in a case-insensitive way
        try:
            # Use ** pattern to get all files recursively
            all_files = list(source_path.glob("**/*"))

            # Create lowercase versions of extensions for case-insensitive matching
            lowercase_extensions = [ext.lower() for ext in extensions]

            # Filter files that have matching extensions (case-insensitive)
            matched_files = []
            for file_path in all_files:
                if file_path.is_file():
                    file_ext = os.path.splitext(file_path.name)[1].lower()
                    if file_ext in lowercase_extensions:
                        matched_files.append(file_path)

            # Process each matching file
            for file_path in matched_files:
                # Determine if this is a multi-disc game in a subfolder
                rel_path = file_path.relative_to(source_path)
                parts = list(rel_path.parts)

                # If file is directly in the root directory, treat as a single game
                if len(parts) == 1:
                    # Get the filename and stem for identifying the game
                    filename = file_path.name
                    file_stem = file_path.stem

                    # Extract the game title using the name regex
                    # Use default regex that strips extension if not specified
                    name_regex = rom_path.name_regex or r"^(.+?)(\.[^.]+)?$"

                    try:
                        # Apply the regex to extract the game title
                        match = re.match(name_regex, filename)
                        if match and match.group(1):
                            # Use the first captured group as the title
                            title = match.group(1)
                            logger.debug(f"Extracted title '{title}' from '{filename}' using regex: {name_regex}")
                        else:
                            # Fallback if regex doesn't match
                            title = file_stem
                            logger.debug(f"Regex didn't match, using fallback title: {title}")
                    except Exception as e:
                        # Fallback in case of regex error
                        title = file_stem
                        logger.error(f"Error applying name regex '{name_regex}' to '{filename}': {e}")

                    game_key = file_stem  # Use stem for the dictionary key to avoid duplicates

                    if game_key not in game_entries:
                        logger.debug(f"Found single-file game: {title} (key: {game_key})")
                        game_entries[game_key] = {
                            "title": title,
                            "directory": str(source_path),
                            "files": [str(rel_path)],
                            "size": file_path.stat().st_size
                        }
                    else:
                        # This is unlikely but handle it just in case
                        # A game with multiple files at the root with the same name but different extensions
                        logger.debug(f"Adding additional file to single-game: {title} (key: {game_key}), file: {rel_path}")
                        game_entries[game_key]["files"].append(str(rel_path))
                        game_entries[game_key]["size"] += file_path.stat().st_size

                # If file is in a subfolder, treat all files in that subfolder as part of the same game
                else:
                    folder_name = parts[0]  # The subfolder name
                    game_key = folder_name  # Use folder name as key in dictionary
                    game_subfolder = source_path / parts[0]  # Full path to the game's subfolder
                    # For multi-disc games, we want the file path to be relative to the game subfolder
                    rel_to_game_subfolder = "/".join(parts[1:])

                    # Extract the game title from the folder name using regex
                    # Use default regex that strips extension if not specified
                    name_regex = rom_path.name_regex or r"^(.+?)(\.[^.]+)?$"

                    try:
                        # Apply the regex to extract the title from folder name
                        match = re.match(name_regex, folder_name)
                        if match and match.group(1):
                            # Use the first captured group as the title
                            title = match.group(1)
                            logger.debug(f"Extracted title '{title}' from folder '{folder_name}' using regex: {name_regex}")
                        else:
                            # Fallback if regex doesn't match
                            title = folder_name
                            logger.debug(f"Regex didn't match folder name, using fallback title: {title}")
                    except Exception as e:
                        # Fallback in case of regex error
                        title = folder_name
                        logger.error(f"Error applying name regex '{name_regex}' to folder '{folder_name}': {e}")

                    if game_key not in game_entries:
                        logger.debug(f"Found multi-disc game: {title} (key: {game_key}), first file: {rel_to_game_subfolder}")
                        game_entries[game_key] = {
                            "title": title,
                            "directory": str(game_subfolder),  # Use the game subfolder instead of source_path
                            "files": [rel_to_game_subfolder],  # Store path relative to the game subfolder
                            "size": file_path.stat().st_size
                        }
                    else:
                        # Add this file to the multi-disc game entry
                        logger.debug(f"Adding disc to multi-disc game: {game_key}, file: {rel_to_game_subfolder}")
                        game_entries[game_key]["files"].append(rel_to_game_subfolder)
                        game_entries[game_key]["size"] += file_path.stat().st_size

        except Exception as e:
            logger.error(f"Error searching for files with extensions {extensions}: {e}")
