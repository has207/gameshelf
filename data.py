from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union, List, Dict, Any
from enum import Enum, auto

from data_mapping import CompletionStatus, Platforms, AgeRatings, Features, Genres, Regions


class SourceType(Enum):
    """Types of game sources that can be scanned"""
    DIRECTORY = auto()  # Generic directory of files
    XBOX = auto()       # Xbox game library via API

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
class Source:
    def __init__(self, id: str, name: str, path: str, source_type: SourceType = SourceType.DIRECTORY,
                 active: bool = True, file_extensions: Optional[List[str]] = None, config: Optional[Dict[str, Any]] = None):
        self.id = id.lower()
        self.name = name
        self.path = path
        self.source_type = source_type
        self.active = active
        self.file_extensions = file_extensions or []
        self.config = config or {}

    def get_source_path(self, data_dir: Path) -> Path:
        """Get the path to the source's configuration file"""
        return data_dir / "sources" / f"{self.id}.yaml"


@dataclass
class Runner:
    def __init__(self, id: str, title: str, image: Optional[str] = None, command: Optional[str] = None):
        self.id = id.lower()
        self.title = title
        self.image = image
        self.command = command


@dataclass
class Game:
    def __init__(self, id: str, title: str, image: Optional[str] = None, runner: Optional[str] = None,
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
        self.runner = runner.lower() if runner else ""
        self.created = created
        self.play_count = 0
        self.play_time = 0  # Total play time in seconds
        self.hidden = hidden  # Whether the game is hidden from the main grid
        self.description = description  # Game description text
        self.platforms = []  # List of platforms the game is available on
        self.age_ratings = []  # List of age ratings for the game
        self.features = []  # List of features for the game
        self.genres = []  # List of genres for the game
        self.regions = []  # List of regions for the game
        self.source = source  # Source ID where this game was imported from

        # Handle string or enum for completion_status
        if isinstance(completion_status, str):
            try:
                self.completion_status = CompletionStatus.from_string(completion_status)
            except Exception as e:
                print(f"Error with game '{title}' - invalid completion status value '{completion_status}': {e}")
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
                        print(f"Error with game '{title}' - invalid platform '{platform}': {e}")
                        # Skip invalid platform strings
                        pass
                elif isinstance(platform, Platforms):
                    self.platforms.append(platform)
                else:
                    # Handle unexpected types with clear error message
                    print(f"Error with game '{title}' - platform type '{type(platform).__name__}' is not supported. Expected string or Platforms enum.")
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
                        print(f"Error with game '{title}' - invalid age rating '{rating}': {e}")
                        # Skip invalid age rating strings
                        pass
                elif isinstance(rating, AgeRatings):
                    self.age_ratings.append(rating)
                else:
                    # Handle unexpected types with clear error message
                    print(f"Error with game '{title}' - age rating type '{type(rating).__name__}' is not supported. Expected string or AgeRatings enum.")
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
                        print(f"Error with game '{title}' - invalid feature '{feature}': {e}")
                        # Skip invalid feature strings
                        pass
                elif isinstance(feature, Features):
                    self.features.append(feature)
                else:
                    # Handle unexpected types with clear error message
                    print(f"Error with game '{title}' - feature type '{type(feature).__name__}' is not supported. Expected string or Features enum.")
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
                        print(f"Error with game '{title}' - invalid genre '{genre}': {e}")
                        # Skip invalid genre strings
                        pass
                elif isinstance(genre, Genres):
                    self.genres.append(genre)
                else:
                    # Handle unexpected types with clear error message
                    print(f"Error with game '{title}' - genre type '{type(genre).__name__}' is not supported. Expected string or Genres enum.")
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
                        print(f"Error with game '{title}' - invalid region '{region}': {e}")
                        # Skip invalid region strings
                        pass
                elif isinstance(region, Regions):
                    self.regions.append(region)
                else:
                    # Handle unexpected types with clear error message
                    print(f"Error with game '{title}' - region type '{type(region).__name__}' is not supported. Expected string or Regions enum.")
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

    def get_play_count_path(self, data_dir: Path) -> str:
        return str(self._get_game_dir_path(data_dir) / "play_count.yaml")

    def get_play_time_path(self, data_dir: Path) -> str:
        return str(self._get_game_dir_path(data_dir) / "playtime.yaml")

    def get_pid_path(self, data_dir: Path) -> str:
        return str(self._get_game_dir_path(data_dir) / "pid.yaml")

    def get_description_path(self, data_dir: Path) -> str:
        """Get the path to the game's description file"""
        return str(self._get_game_dir_path(data_dir) / "description.yaml")


    def get_last_played_time(self, data_dir: Path) -> Optional[float]:
        play_count_file = Path(self.get_play_count_path(data_dir))
        if play_count_file.exists():
            return play_count_file.stat().st_mtime
        return None

    def is_running(self, data_dir: Path) -> bool:
        """Check if the game is currently running by looking for a pid.yaml file"""
        pid_file = Path(self.get_pid_path(data_dir))
        return pid_file.exists()
