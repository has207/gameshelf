import os
import yaml
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from data import Source, SourceType, Game
from data_handler import DataHandler


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
        for source_file in self.sources_dir.glob("*.yaml"):
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
                        id=source_file.stem,
                        name=source_data.get("name", source_file.stem),
                        path=source_data.get("path", ""),
                        source_type=source_type,
                        active=source_data.get("active", True),
                        file_extensions=file_extensions,
                        config=source_data.get("config", {})
                    )
                    sources.append(source)
            except Exception as e:
                print(f"Error loading source {source_file}: {e}")
        return sources

    def save_source(self, source: Source) -> bool:
        """
        Save a source to disk.

        Args:
            source: The source to save

        Returns:
            True if successful, False otherwise
        """
        if not source.id:
            source.id = source.name.lower().replace(" ", "_")

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
            source_file = self.sources_dir / f"{source.id}.yaml"
            with open(source_file, "w") as f:
                yaml.dump(source_data, f)
            return True
        except Exception as e:
            print(f"Error saving source {source.id}: {e}")
            return False

    def remove_source(self, source: Source) -> bool:
        """
        Remove a source from the sources directory.

        Args:
            source: The source to remove

        Returns:
            True if successful, False otherwise
        """
        source_file = self.sources_dir / f"{source.id}.yaml"

        try:
            if source_file.exists():
                source_file.unlink()
                return True
            else:
                print(f"Source file {source_file} not found")
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
        # This is a more advanced version of scan_source that also handles updating and removing
        # For now, we'll just call scan_source which only adds new games
        return self.scan_source(source, progress_callback)