import os
import tempfile
import logging
import requests
import shutil
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, Union

from data_handler import get_media_filename_for_url

# Set up logger
logger = logging.getLogger(__name__)

class CoverFetcher:
    """
    Class for downloading and managing game cover images.

    This class handles the process of:
    1. Downloading images from URLs
    2. Saving them to temporary files
    3. Moving them to the correct game directory
    4. Cleaning up temporary files

    Each source can instantiate its own CoverFetcher when needed,
    making it thread-safe for concurrent downloads.
    """

    def __init__(self, data_handler, timeout: int = 10, max_retries: int = 2):
        """
        Initialize the cover fetcher

        Args:
            data_handler: The data handler for saving game images
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.data_handler = data_handler
        self.session = requests.Session()

        # Configure session for retries
        adapter = requests.adapters.HTTPAdapter(max_retries=max_retries)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        # Set up media directory
        self.media_dir = Path(data_handler.data_dir) / "media"
        self.media_dir.mkdir(parents=True, exist_ok=True)

    def fetch_to_temp(self, url: str, source_name: str = None,
                   headers: Dict[str, str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Fetch a cover image from a URL and save it to a temporary file

        Args:
            url: The URL of the image to fetch
            source_name: Optional name of the source (for logging)
            headers: Optional headers to send with the request

        Returns:
            Tuple of (success, file_path, error_message)
            - success: True if download was successful, False otherwise
            - file_path: Path to the temporary file containing the image, or None if failed
            - error_message: Error message if download failed, or None if successful
        """
        try:
            source_info = f" from {source_name}" if source_name else ""
            logger.debug(f"Downloading cover image{source_info} from URL: {url}")

            # Create a temporary file with a sensible suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                temp_path = temp_file.name

                # Send GET request with proper timeout and headers
                response = self.session.get(
                    url,
                    stream=True,
                    timeout=self.timeout,
                    headers=headers
                )
                response.raise_for_status()  # Raise exception for bad status codes

                # Check content type to ensure it's an image
                content_type = response.headers.get('Content-Type', '')
                if not content_type.startswith('image/'):
                    logger.warning(f"Unexpected content type: {content_type} for URL: {url}")

                # Write the image data to the temporary file
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)

            logger.debug(f"Cover image downloaded successfully to: {temp_path}")
            return True, temp_path, None

        except requests.exceptions.RequestException as e:
            error_msg = f"Network error downloading cover image: {str(e)}"
            return False, None, error_msg

        except Exception as e:
            error_msg = f"Error downloading cover image: {str(e)}"
            return False, None, error_msg

    def fetch_and_save_for_game(self, game_id: str, url: str, source_name: str = None,
                               headers: Dict[str, str] = None) -> Tuple[bool, Optional[str]]:
        """
        Fetch a cover image and save it to the centralized media directory,
        then create a symlink in the game's directory

        Args:
            game_id: The ID of the game to save the cover for
            url: The URL of the image to fetch
            source_name: Optional name of the source (for logging)
            headers: Optional headers to send with the request

        Returns:
            Tuple of (success, error_message)
            - success: True if download and save was successful, False otherwise
            - error_message: Error message if failed, or None if successful
        """
        # Check if we already have this image in the media directory
        media_path = self._get_media_path_for_url(url)

        if media_path.exists():
            logger.debug(f"Cover image already exists in media directory: {media_path}")
            # Create symlink to existing image
            return self._create_game_symlink(game_id, media_path)

        # First fetch to a temporary file
        success, temp_path, error = self.fetch_to_temp(url, source_name, headers)

        if not success or not temp_path:
            return False, error

        try:
            # Move the image to the media directory
            shutil.move(temp_path, media_path)
            logger.debug(f"Cover image saved to media directory: {media_path}")

            # Create symlink in game directory
            return self._create_game_symlink(game_id, media_path)

        except Exception as e:
            # Clean up the temporary file if we have an exception
            self.cleanup_temp_file(temp_path)
            error_msg = f"Error saving cover image for game ID {game_id}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def cleanup_temp_file(self, file_path: str) -> bool:
        """
        Clean up a temporary file

        Args:
            file_path: The path to the temporary file

        Returns:
            True if cleanup was successful, False otherwise
        """
        if not file_path:
            return False

        try:
            os.unlink(file_path)
            logger.debug(f"Temporary image file deleted: {file_path}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete temporary image file: {e}")
            return False

    def _get_media_path_for_url(self, url: str) -> Path:
        """
        Generate a media file path for a given URL using URL hash

        Args:
            url: The URL to generate a path for

        Returns:
            Path to the media file
        """
        return self.media_dir / get_media_filename_for_url(url)

    def _create_game_symlink(self, game_id: str, media_path: Path) -> Tuple[bool, Optional[str]]:
        """
        Create a symlink from the game directory to the media file

        Args:
            game_id: The ID of the game
            media_path: Path to the media file

        Returns:
            Tuple of (success, error_message)
        """
        try:
            game_dir = self.data_handler._get_game_dir_from_id(game_id)
            game_dir.mkdir(parents=True, exist_ok=True)

            cover_symlink = game_dir / "cover.jpg"

            # Remove existing cover file/symlink if it exists
            if cover_symlink.exists() or cover_symlink.is_symlink():
                cover_symlink.unlink()

            # Create relative symlink to media file
            # Calculate relative path from game directory to media file
            relative_media_path = os.path.relpath(media_path, game_dir)
            cover_symlink.symlink_to(relative_media_path)

            logger.debug(f"Created symlink for game {game_id}: {cover_symlink} -> {relative_media_path}")
            return True, None

        except Exception as e:
            error_msg = f"Error creating symlink for game {game_id}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
