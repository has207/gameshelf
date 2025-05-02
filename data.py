from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union, List

from data_mapping import CompletionStatus, Platforms


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
                 platforms: Optional[List[Union[Platforms, str]]] = None):
        self.id = id.lower()
        self.title = title
        self.runner = runner.lower() if runner else ""
        self.created = created
        self.play_count = 0
        self.play_time = 0  # Total play time in seconds
        self.hidden = hidden  # Whether the game is hidden from the main grid
        self.description = description  # Game description text
        self.platforms = []  # List of platforms the game is available on

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
                    except Exception:
                        # Skip invalid platform strings
                        pass
                elif isinstance(platform, Platforms):
                    self.platforms.append(platform)

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
