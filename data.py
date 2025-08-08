from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union, List, Dict, Any
from enum import Enum, auto
import yaml
import psutil
import logging

from data_mapping import CompletionStatus, Platforms, AgeRatings, Features, Genres, Regions

# Set up logger
logger = logging.getLogger(__name__)


class SourceType(Enum):
    """Types of game sources that can be scanned"""
    ROM_DIRECTORY = auto()  # Directory containing ROM files
    XBOX = auto()       # Xbox game library via API
    PLAYSTATION = auto()  # PlayStation Network game library via API
    EPIC = auto()       # Epic Games Store library via API
    STEAM = auto()      # Steam library via local files
    GOG = auto()        # GOG library via API

    @classmethod
    def from_string(cls, value: str) -> 'SourceType':
        """Convert a string to a SourceType enum value"""
        value_upper = value.upper()
        if hasattr(cls, value_upper):
            return getattr(cls, value_upper)
        raise ValueError(f"Invalid source type: {value}")

    def __str__(self) -> str:
        return self.name.lower()


@dataclass
class RomPath:
    def __init__(self, path: str, file_extensions: Optional[List[str]] = None, name_regex: Optional[str] = None):
        self.path = path
        self.file_extensions = file_extensions or []
        # Default regex that strips file extension
        self.name_regex = name_regex or r"^(.+?)(\.[^.]+)?$"

@dataclass
class Source:
    def __init__(self, id: str, name: str, source_type: SourceType,
                 active: bool = True, config: Optional[Dict[str, Any]] = None,
                 rom_paths: Optional[List[RomPath]] = None):
        self.id = id.lower()
        self.name = name
        self.source_type = source_type
        self.active = active
        self.config = config or {}

        # ROM_DIRECTORY specific attributes
        if source_type == SourceType.ROM_DIRECTORY:
            self.rom_paths = rom_paths or []

    def get_source_path(self, data_dir: Path) -> Path:
        """Get the path to the source's configuration file"""
        return data_dir / "sources" / f"{self.id}.yaml"


@dataclass
class Runner:
    def __init__(self, id: str, title: str, image: Optional[str] = None, command: Optional[str] = None,
                 platforms: Optional[List[Union[Platforms, str]]] = None, discord_enabled: bool = True,
                 launcher_type: Optional[List[str]] = None, install_command: Optional[str] = None,
                 uninstall_command: Optional[str] = None):
        self.id = id.lower()
        self.title = title
        self.image = image
        self.command = command
        self.discord_enabled = discord_enabled
        self.launcher_type = launcher_type or []
        self.install_command = install_command
        self.uninstall_command = uninstall_command
        self.platforms = []  # List of platforms this runner supports

        # Handle platforms list
        if platforms:
            self.platforms = []
            for platform in platforms:
                if isinstance(platform, str):
                    try:
                        self.platforms.append(Platforms.from_string(platform))
                    except Exception as e:
                        # Improved error reporting for debugging
                        logger.warning(f"Error with runner '{title}' - invalid platform '{platform}': {e}")
                        # Skip invalid platform strings
                        pass
                elif isinstance(platform, Platforms):
                    self.platforms.append(platform)
                else:
                    # Handle unexpected types with clear error message
                    logger.warning(f"Error with runner '{title}' - platform type '{type(platform).__name__}' is not supported. Expected string or Platforms enum.")
                    # Skip invalid platform types


@dataclass
class Game:
    def __init__(self, id: str, title: str, image: Optional[str] = None,
                 created: Optional[float] = None, hidden: bool = False, description: Optional[str] = None,
                 completion_status: Union[CompletionStatus, str] = CompletionStatus.NOT_PLAYED,
                 platforms: Optional[List[Union[Platforms, str]]] = None,
                 age_ratings: Optional[List[Union[AgeRatings, str]]] = None,
                 features: Optional[List[Union[Features, str]]] = None,
                 genres: Optional[List[Union[Genres, str]]] = None,
                 regions: Optional[List[Union[Regions, str]]] = None,
                 source: Optional[str] = None):
        self.id = id.lower()
        self.title = title
        self.created = created
        self.play_count = None  # Number of times played
        self.play_time = None  # Total play time in seconds
        self.last_played = None  # Timestamp when game was last played
        self.first_played = None  # Timestamp when game was first played
        self.hidden = hidden  # Whether the game is hidden from the main grid
        self.description = description  # Game description text
        self.platforms = []  # List of platforms the game is available on
        self.age_ratings = []  # List of age ratings for the game
        self.features = []  # List of features for the game
        self.genres = []  # List of genres for the game
        self.regions = []  # List of regions for the game
        self.source = source  # Source ID where this game was imported from
        self.launcher_type = None  # Type of external launcher (e.g., 'EGS', 'GOG', 'Steam', 'Amazon')
        self.launcher_id = None  # ID of the game in the launcher's namespace
        self.developer = None  # Game developer
        self.publisher = None  # Game publisher
        self.installation_directory = None  # Directory where game files are located
        self.installation_files = None  # List of file paths relative to directory
        self.installation_size = None  # Total size of all files in bytes

        # Handle string or enum for completion_status
        if isinstance(completion_status, str):
            try:
                self.completion_status = CompletionStatus.from_string(completion_status)
            except Exception as e:
                logger.warning(f"Error with game '{title}' - invalid completion status value '{completion_status}': {e}")
                self.completion_status = CompletionStatus.NOT_PLAYED
        else:
            self.completion_status = completion_status

        # Handle platforms list
        if platforms:
            self.platforms = []
            for platform in platforms:
                if isinstance(platform, str):
                    try:
                        self.platforms.append(Platforms.from_string(platform))
                    except Exception as e:
                        # Improved error reporting for debugging
                        logger.warning(f"Error with game '{title}' - invalid platform '{platform}': {e}")
                        # Skip invalid platform strings
                        pass
                elif isinstance(platform, Platforms):
                    self.platforms.append(platform)
                else:
                    # Handle unexpected types with clear error message
                    logger.warning(f"Error with game '{title}' - platform type '{type(platform).__name__}' is not supported. Expected string or Platforms enum.")
                    # Skip invalid platform types

        # Handle age_ratings list
        if age_ratings:
            self.age_ratings = []
            for rating in age_ratings:
                if isinstance(rating, str):
                    try:
                        self.age_ratings.append(AgeRatings.from_string(rating))
                    except Exception as e:
                        # Improved error reporting for debugging
                        logger.warning(f"Error with game '{title}' - invalid age rating '{rating}': {e}")
                        # Skip invalid age rating strings
                        pass
                elif isinstance(rating, AgeRatings):
                    self.age_ratings.append(rating)
                else:
                    # Handle unexpected types with clear error message
                    logger.warning(f"Error with game '{title}' - age rating type '{type(rating).__name__}' is not supported. Expected string or AgeRatings enum.")
                    # Skip invalid age rating types

        # Handle features list
        if features:
            self.features = []
            for feature in features:
                if isinstance(feature, str):
                    try:
                        self.features.append(Features.from_string(feature))
                    except Exception as e:
                        # Improved error reporting for debugging
                        logger.warning(f"Error with game '{title}' - invalid feature '{feature}': {e}")
                        # Skip invalid feature strings
                        pass
                elif isinstance(feature, Features):
                    self.features.append(feature)
                else:
                    # Handle unexpected types with clear error message
                    logger.warning(f"Error with game '{title}' - feature type '{type(feature).__name__}' is not supported. Expected string or Features enum.")
                    # Skip invalid feature types

        # Handle genres list
        if genres:
            self.genres = []
            for genre in genres:
                if isinstance(genre, str):
                    try:
                        self.genres.append(Genres.from_string(genre))
                    except Exception as e:
                        # Improved error reporting for debugging
                        logger.warning(f"Error with game '{title}' - invalid genre '{genre}': {e}")
                        # Skip invalid genre strings
                        pass
                elif isinstance(genre, Genres):
                    self.genres.append(genre)
                else:
                    # Handle unexpected types with clear error message
                    logger.warning(f"Error with game '{title}' - genre type '{type(genre).__name__}' is not supported. Expected string or Genres enum.")
                    # Skip invalid genre types

        # Handle regions list
        if regions:
            self.regions = []
            for region in regions:
                if isinstance(region, str):
                    try:
                        self.regions.append(Regions.from_string(region))
                    except Exception as e:
                        # Improved error reporting for debugging
                        logger.warning(f"Error with game '{title}' - invalid region '{region}': {e}")
                        # Skip invalid region strings
                        pass
                elif isinstance(region, Regions):
                    self.regions.append(region)
                else:
                    # Handle unexpected types with clear error message
                    logger.warning(f"Error with game '{title}' - region type '{type(region).__name__}' is not supported. Expected string or Regions enum.")
                    # Skip invalid region types

    def _get_game_dir_path(self, data_dir: Path) -> Path:
        """
        Get the game's directory path using the new structured format.
        For example, game ID 23 would be in data/games/000/000/023/
        """
        # Ensure ID is padded to 9 digits
        padded_id = self.id.zfill(9)

        # Split into 3 groups of 3 digits
        dir1, dir2, dir3 = padded_id[:3], padded_id[3:6], padded_id[6:]

        # Return the full path
        return data_dir / "games" / dir1 / dir2 / dir3

    def get_cover_path(self, data_dir: Path) -> str:
        return str(self._get_game_dir_path(data_dir) / "cover.jpg")

    def get_modified_time(self, data_dir: Path) -> Optional[float]:
        game_file = self._get_game_dir_path(data_dir) / "game.yaml"
        if game_file.exists():
            return game_file.stat().st_mtime
        return None

    def get_play_time_path(self, data_dir: Path) -> str:
        return str(self._get_game_dir_path(data_dir) / "playtime.yaml")

    def get_pid_path(self, data_dir: Path) -> str:
        return str(self._get_game_dir_path(data_dir) / "pid.yaml")

    def get_description_path(self, data_dir: Path) -> str:
        """Get the path to the game's description file"""
        return str(self._get_game_dir_path(data_dir) / "description.yaml")


    def get_launcher_path(self, data_dir: Path) -> str:
        """Get the path to the game's launcher data file"""
        return str(self._get_game_dir_path(data_dir) / "launcher.yaml")

    def get_first_played_time(self, data_dir: Path) -> Optional[float]:
        """Get the first played timestamp"""
        return self.first_played

    def get_last_played_time(self, data_dir: Path) -> Optional[float]:
        """Get the last played timestamp from playtime.yaml"""
        return self.last_played

    def should_launch_directory(self) -> bool:
        """Check if this game should be launched with its directory rather than individual files."""
        if self.platforms:
            for platform in self.platforms:
                if platform.name == 'NINTENDO_WIIU':
                    return True
                # Future: Add other platforms that need directory launching here
        return False

    def is_running(self, data_dir: Path) -> bool:
        """
        Check if the game is currently running by verifying the process in pid.yaml is active.
        If the pid file exists but the process is not running, clean up the stale pid file.
        """
        pid_file = Path(self.get_pid_path(data_dir))

        if not pid_file.exists():
            return False

        try:
            # Read PID from file
            with open(pid_file, "r") as f:
                pid_data = yaml.safe_load(f)
                if pid_data and isinstance(pid_data, dict) and "pid" in pid_data:
                    pid = pid_data.get("pid")

                    # Check if process with this PID exists
                    if pid and psutil.pid_exists(pid):
                        try:
                            # Additional check to make sure process is running, not zombie
                            process = psutil.Process(pid)
                            if process.status() != psutil.STATUS_ZOMBIE:
                                return True
                        except psutil.NoSuchProcess:
                            pass

            # PID doesn't exist or process is zombie/dead, clean up the stale file
            pid_file.unlink()
            return False

        except Exception as e:
            logger.error(f"Error checking if game is running: {e}")
            # In case of error, try to clean up
            try:
                pid_file.unlink()
            except:
                pass
            return False
