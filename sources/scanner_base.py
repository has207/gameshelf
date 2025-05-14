import logging
import os
import stat
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

from data import Source

# Set up logger
logger = logging.getLogger(__name__)

class SourceScanner(ABC):
    """Base abstract class for all source scanners"""

    def __init__(self, data_handler):
        """
        Initialize the scanner with a data handler

        Args:
            data_handler: The data handler instance to use
        """
        self.data_handler = data_handler

    @abstractmethod
    def scan(self, source: Source, progress_callback: Optional[callable] = None) -> Tuple[int, List[str]]:
        """
        Scan a source for games and add them to the library.

        Args:
            source: The source to scan
            progress_callback: Optional callback function for progress updates

        Returns:
            Tuple of (number of games added/updated, list of error messages)
        """
        pass

    def ensure_secure_token_storage(self, source_id: str) -> Path:
        """
        Create and ensure a secure directory for token storage

        Args:
            source_id: The source ID to create token storage for

        Returns:
            Path to the secure token storage directory
        """
        # Create a tokens directory within the source's directory
        source_dir = self.data_handler.sources_dir / source_id
        tokens_dir = source_dir / "tokens"
        tokens_dir.mkdir(parents=True, exist_ok=True)

        # Set secure permissions (0700 for directory)
        os.chmod(tokens_dir, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

        return tokens_dir