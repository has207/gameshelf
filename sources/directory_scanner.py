import re
import logging
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

from data import Source, Game, SourceType
from data_mapping import Platforms
from sources.scanner_base import SourceScanner

# Set up logger
logger = logging.getLogger(__name__)

class DirectoryScanner(SourceScanner):
    """Scanner for directory/ROM type sources"""

    def scan(self, source: Source, progress_callback: Optional[callable] = None) -> Tuple[int, List[str]]:
        """
        Scan a directory source for games and add them to the library.

        Args:
            source: The source to scan
            progress_callback: Optional callback function for progress updates

        Returns:
            Tuple of (number of games added/updated, list of error messages)
        """
        # Validate the path
        if not source.path or not Path(source.path).exists():
            return 0, [f"Source path does not exist: {source.path}"]

        source_path = Path(source.path)
        added_count = 0
        errors = []

        # Extract platform from source config for ROM_DIRECTORY sources
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

        # Get the list of files matching the specified extensions
        if not source.file_extensions:
            # Default to common game file extensions if none are specified
            extensions = [".exe", ".lnk", ".url", ".desktop"]
        else:
            extensions = [f".{ext.lstrip('.')}" for ext in source.file_extensions]

        logger.info(f"Scanning directory source: {source.path}")
        logger.info(f"Using extensions: {extensions}")

        # Dictionary to store game entries, keyed by parent folder or file name
        # For multi-disc games in subfolders, the key will be the subfolder name
        # For standalone files at the root, the key will be the file stem
        game_entries = {}

        # Build a glob pattern for each extension
        for ext in extensions:
            pattern = f"**/*{ext}"
            try:
                matched_files = list(source_path.glob(pattern))

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
                        name_regex = source.config.get("name_regex", "^(.+?)(\.[^.]+)?$")

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
                        name_regex = source.config.get("name_regex", "^(.+?)(\.[^.]+)?$")

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
                errors.append(f"Error searching for {pattern}: {e}")

        # Initial progress update
        total_games = len(game_entries)
        if progress_callback and total_games > 0:
            try:
                progress_callback(0, total_games, "Starting scan...")
            except Exception as e:
                logger.error(f"Error with progress callback: {e}")

        # Get list of existing games from this source
        existing_games_by_path = {}
        for game in self.data_handler.load_games():
            if game.source == source.id:
                # Extract the path if it's in the title or description
                # This is a simple approach - in a more advanced implementation,
                # we might store the original file path separately
                existing_games_by_path[game.title] = game

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

                # Set platform for ROM_DIRECTORY sources if we have a platform specified
                if platform:
                    game.platforms = [platform]
                    logger.info(f"Setting platform '{platform.value}' for game '{title}'")

                # Save the game
                if self.data_handler.save_game(game):
                    # Save installation data
                    installation_success = self.data_handler.save_installation_data(
                        game,
                        entry["directory"],
                        entry["files"],
                        entry["size"]
                    )

                    if not installation_success:
                        logger.warning(f"Failed to save installation data for '{title}'")

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