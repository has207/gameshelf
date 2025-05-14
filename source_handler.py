import os
import yaml
import json
import time
import stat
import shutil
import logging
import threading
import traceback
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from threading import Thread
from gi.repository import GLib

from data import Source, SourceType, Game
from data_handler import DataHandler
from data_mapping import Platforms, Genres, CompletionStatus
from sources.xbox_client import XboxLibrary
from sources.psn_client import PSNClient
from sources.directory_scanner import DirectoryScanner
from sources.scanner_base import SourceScanner
from cover_fetch import CoverFetcher

# Set up logger
logger = logging.getLogger(__name__)


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
                                    logger.warning(f"Invalid source type in {source_file}, defaulting to ROM_DIRECTORY")
                                    source_type = SourceType.ROM_DIRECTORY
                            else:
                                source_type = SourceType.ROM_DIRECTORY

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
                        logger.error(f"Error loading source {source_file}: {e}")

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
            logger.error(f"Error saving source {source.id}: {e}")
            return False

    def remove_source(self, source: Source) -> bool:
        """
        Remove a source and its directory from the sources directory.

        Args:
            source: The source to remove

        Returns:
            True if successful, False otherwise
        """
        logger.debug(f"remove_source called for source: {source.id} ({source.name})")

        source_dir = self.sources_dir / source.id
        logger.debug(f"source directory path: {source_dir}")
        logger.debug(f"source directory exists: {source_dir.exists()}")
        logger.debug(f"sources dir exists: {self.sources_dir.exists()}")
        logger.debug(f"sources dir contents: {list(self.sources_dir.glob('*'))}")

        try:
            if source_dir.exists():
                logger.debug(f"Attempting to remove directory {source_dir}")
                # Remove all files in the directory
                for file in source_dir.glob("*"):
                    file.unlink()
                # Remove the directory
                source_dir.rmdir()
                logger.debug(f"Directory successfully removed")
                return True
            else:
                logger.warning(f"Source directory {source_dir} not found")
                return False
        except Exception as e:
            logger.error(f"Error removing source {source.id}: {e}")
            return False


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

    def _create_xbox_scanner(self, source):
        """
        Create an Xbox scanner with token directory for the given source

        Args:
            source: The source to create a scanner for

        Returns:
            An initialized Xbox scanner
        """
        token_dir = self.ensure_secure_token_storage(source.id)
        return XboxLibrary(self.data_handler, token_dir=token_dir)

    def _create_psn_scanner(self, source):
        """
        Create a PlayStation Network scanner with token directory for the given source

        Args:
            source: The source to create a scanner for

        Returns:
            An initialized PSN scanner
        """
        token_dir = self.ensure_secure_token_storage(source.id)
        return PSNClient(self.data_handler, token_dir=str(token_dir))

    def get_scanner(self, source_type: SourceType, source_id: str = None) -> SourceScanner:
        """
        Get a scanner for the specified source type, properly initialized with tokens dir if needed

        Args:
            source_type: The type of source to get a scanner for
            source_id: Optional source ID for setting up token directory

        Returns:
            An initialized scanner for the specified source type
        """
        if source_type == SourceType.ROM_DIRECTORY:
            return DirectoryScanner(self.data_handler)
        elif source_type == SourceType.XBOX:
            # For Xbox, set up token directory if source_id is provided
            token_dir = None
            if source_id:
                token_dir = self.ensure_secure_token_storage(source_id)
            return XboxLibrary(self.data_handler, token_dir=token_dir)
        elif source_type == SourceType.PLAYSTATION:
            # For PSN, set up token directory if source_id is provided
            token_dir = None
            if source_id:
                token_dir = self.ensure_secure_token_storage(source_id)
            return PSNClient(self.data_handler, token_dir=str(token_dir) if token_dir else None)
        else:
            raise ValueError(f"Unsupported source type: {source_type}")
