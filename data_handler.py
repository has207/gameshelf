import os
import yaml
import time
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple

import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf


@dataclass
class Runner:
    def __init__(self, id: str, title: str, image: Optional[str] = None, command: Optional[str] = None):
        self.id = id.lower()
        self.title = title
        self.image = image
        self.command = command


@dataclass
class Game:
    def __init__(self, id: str, title: str, image: Optional[str] = None, runner: Optional[str] = None, created: Optional[float] = None):
        self.id = id.lower()
        self.title = title
        self.runner = runner.lower() if runner else ""
        self.created = created
        self.play_count = 0
        self.play_time = 0  # Total play time in seconds

    def get_cover_path(self, data_dir: Path) -> str:
        return str(data_dir / "games" / self.id / "cover.jpg")

    def get_modified_time(self, data_dir: Path) -> Optional[float]:
        game_file = data_dir / "games" / self.id / "game.yaml"
        if game_file.exists():
            return game_file.stat().st_mtime
        return None

    def get_play_count_path(self, data_dir: Path) -> str:
        return str(data_dir / "games" / self.id / "play_count.yaml")

    def get_play_time_path(self, data_dir: Path) -> str:
        return str(data_dir / "games" / self.id / "playtime.yaml")

    def get_pid_path(self, data_dir: Path) -> str:
        return str(data_dir / "games" / self.id / "pid.yaml")

    def get_last_played_time(self, data_dir: Path) -> Optional[float]:
        play_count_file = Path(self.get_play_count_path(data_dir))
        if play_count_file.exists():
            return play_count_file.stat().st_mtime
        return None

    def is_running(self, data_dir: Path) -> bool:
        """Check if the game is currently running by looking for a pid.yaml file"""
        pid_file = Path(self.get_pid_path(data_dir))
        return pid_file.exists()


class DataHandler:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.games_dir = self.data_dir / "games"
        self.runners_dir = self.data_dir / "runners"

        # Get the project root directory for finding media directory
        self.project_root = Path(__file__).parent
        self.media_dir = self.project_root / "media" / "images"

        # Runner icon mapping
        self.runner_icon_map = {
            "steam": "steam-symbolic",
            "wine": "wine-symbolic",
            "native": "system-run-symbolic",
            "browser": "web-browser-symbolic",
            "emulator": "media-optical-symbolic",
        }

        # Ensure directories exist
        self.games_dir.mkdir(parents=True, exist_ok=True)
        self.runners_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)

    def load_games(self) -> List[Game]:
        games = []
        for game_file in self.games_dir.glob("*/game.yaml"):
            try:
                game_id = game_file.parent.name

                with open(game_file, "r") as f:
                    game_data = yaml.safe_load(f)
                    game = Game(
                        title=game_data.get("title", "Unknown Game"),
                        runner=game_data.get("runner"),
                        id=game_id,
                        created=game_data.get("created")
                    )

                    # Load play count if exists
                    play_count_file = game_file.parent / "play_count.yaml"
                    if play_count_file.exists():
                        try:
                            with open(play_count_file, "r") as pc_file:
                                play_data = yaml.safe_load(pc_file)
                                if play_data and isinstance(play_data, dict):
                                    game.play_count = play_data.get("count", 0)
                        except Exception as pc_err:
                            print(f"Error loading play count for {game_id}: {pc_err}")

                    # Load play time if exists
                    play_time_file = game_file.parent / "playtime.yaml"
                    if play_time_file.exists():
                        try:
                            with open(play_time_file, "r") as pt_file:
                                play_time_data = yaml.safe_load(pt_file)
                                if play_time_data and isinstance(play_time_data, dict):
                                    game.play_time = play_time_data.get("seconds", 0)
                        except Exception as pt_err:
                            print(f"Error loading play time for {game_id}: {pt_err}")

                    games.append(game)
            except Exception as e:
                print(f"Error loading game {game_file}: {e}")
        return games

    def load_runners(self) -> List[Runner]:
        runners = []
        for runner_file in self.runners_dir.glob("*.yaml"):
            try:
                with open(runner_file, "r") as f:
                    runner_data = yaml.safe_load(f)
                    runner = Runner(
                        title=runner_data.get("title", "Unknown Runner"),
                        image=runner_data.get("image", ""),
                        command=runner_data.get("command", ""),
                        id=runner_file.stem
                    )
                    runners.append(runner)
            except Exception as e:
                print(f"Error loading runner {runner_file}: {e}")
        return runners

    def save_game(self, game: Game) -> bool:
        if not game.id:
            next_id = self.get_next_game_id()
            game.id = str(next_id)
            game.created = time.time()

        game_data = {
            "title": game.title,
        }

        if game.runner:
            game_data["runner"] = game.runner
        if game.created:
            game_data["created"] = game.created

        try:
            game_dir = self.games_dir / game.id
            game_dir.mkdir(parents=True, exist_ok=True)

            game_file = game_dir / "game.yaml"
            with open(game_file, "w") as f:
                yaml.dump(game_data, f)
            return True
        except Exception as e:
            print(f"Error saving game {game.id}: {e}")
            return False

    def save_runner(self, runner: Runner) -> bool:
        if not runner.id:
            runner.id = runner.title.lower().replace(" ", "_")

        runner_data = {
            "title": runner.title,
            "image": runner.image,
            "command": runner.command
        }

        try:
            with open(self.runners_dir / f"{runner.id}.yaml", "w") as f:
                yaml.dump(runner_data, f)
            return True
        except Exception as e:
            print(f"Error saving runner {runner.id}: {e}")
            return False

    def save_game_image(self, source_path: str, game_id: str) -> bool:
        """
        Copy a game image to the game's directory as cover.jpg.

        Args:
            source_path: Path to the source image
            game_id: ID of the game

        Returns:
            True if the image was successfully saved, False otherwise
        """
        if not source_path or not os.path.exists(source_path):
            return False

        try:
            # Create game directory if it doesn't exist
            game_dir = self.games_dir / game_id
            game_dir.mkdir(parents=True, exist_ok=True)

            # Always save as cover.jpg
            dest_path = game_dir / "cover.jpg"

            # Copy the file
            shutil.copy2(source_path, dest_path)
            return True
        except Exception as e:
            print(f"Error copying image: {e}")
            return False

    def create_game_with_image(self, title: str, runner_id: Optional[str], image_path: Optional[str] = None) -> Game:
        """
        Create a new game object with an image, handling ID generation and image copying.

        Args:
            title: The title of the game
            runner_id: The ID of the runner to use
            image_path: Optional path to an image file

        Returns:
            A new Game object
        """
        # Get the next numeric game ID
        next_id = self.get_next_game_id()
        game_id = str(next_id)

        # Create the game object with creation timestamp
        game = Game(
            id=game_id,
            title=title,
            runner=runner_id,
            created=time.time()
        )

        # Save image if provided
        if image_path:
            self.save_game_image(image_path, game_id)

        return game

    def get_runner_icon(self, runner_id: str) -> str:
        """
        Get the icon name for a given runner ID.

        Args:
            runner_id: The ID of the runner

        Returns:
            The name of the icon to use for the runner
        """
        if not runner_id:
            return "application-x-executable-symbolic"

        # Try to match beginning of runner name to known icons
        for key, icon in self.runner_icon_map.items():
            if runner_id.lower().startswith(key):
                return icon

        # Default icon for unknown runners
        return "application-x-executable-symbolic"

    def load_game_image(self, game: Game, width: int = 200, height: int = 260) -> Optional[GdkPixbuf.Pixbuf]:
        """
        Load a game's image as a pixbuf, scaled to the specified dimensions.

        Args:
            game: The game to load the image for
            width: The desired width of the image
            height: The desired height of the image

        Returns:
            A pixbuf containing the game's image, or None if no image is available
        """
        try:
            cover_path = game.get_cover_path(self.data_dir)
            if not os.path.exists(cover_path):
                return None
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                cover_path, width, height, True)
        except Exception as e:
            print(f"Error loading image for {game.title}: {e}")
            return None

    def get_default_icon_paintable(self, icon_name: str, size: int = 128) -> 'Gdk.Paintable':
        """
        Get a default icon as a paintable for use with GtkPicture widgets.

        Args:
            icon_name: The name of the icon to get
            size: The size of the icon

        Returns:
            A paintable that can be used with GtkPicture widgets
        """
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Gdk', '4.0')
        from gi.repository import Gtk, Gdk

        display = Gdk.Display.get_default()
        icon_theme = Gtk.IconTheme.get_for_display(display)
        # The empty list is for icon sizes, 1 is scale factor, Gtk.TextDirection.LTR is text direction
        return icon_theme.lookup_icon(icon_name, [], size, 1, Gtk.TextDirection.LTR, 0)

    def get_next_game_id(self) -> int:
        """
        Get the next available game ID by finding the highest existing numeric ID
        and incrementing it by 1.

        Returns:
            The next available numeric ID for a game
        """
        try:
            # Look for the highest existing ID in the games directory
            highest_id = -1
            for game_dir in self.games_dir.iterdir():
                # Only consider directories
                if not game_dir.is_dir():
                    continue

                # Check if the directory has a game.yaml file (it's a game directory)
                if not (game_dir / "game.yaml").exists():
                    continue

                # Extract the ID from the directory name and see if it's a number
                dir_id = game_dir.name
                if dir_id.isdigit():
                    highest_id = max(highest_id, int(dir_id))

            # Start from the next ID after the highest found, or 0 if no numeric IDs exist
            return highest_id + 1
        except Exception as e:
            print(f"Error getting next game ID: {e}")
            return 0

    def load_runner_image(self, runner: Runner, width: int = 64, height: int = 64) -> Optional[GdkPixbuf.Pixbuf]:
        """
        Load a runner's image as a pixbuf, scaled to the specified dimensions.

        Args:
            runner: The runner to load the image for
            width: The desired width of the image
            height: The desired height of the image

        Returns:
            A pixbuf containing the runner's image, or None if no image is available
        """
        try:
            if not runner.image or not os.path.exists(runner.image):
                return None
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                runner.image, width, height, True)
        except Exception as e:
            print(f"Error loading image for {runner.title}: {e}")
            return None

    def increment_play_count(self, game: Game) -> bool:
        """
        Increment the play count for a game and update the play_count.yaml file.
        The file modification time will serve as the 'last played' timestamp.

        Args:
            game: The game to increment the play count for

        Returns:
            True if the play count was successfully incremented, False otherwise
        """
        game_dir = self.games_dir / game.id
        play_count_file = game_dir / "play_count.yaml"

        try:
            # Increment the play count in the game object
            game.play_count += 1

            # Create the play count data
            play_data = {"count": game.play_count}

            # Write to the file (this also updates the modification time)
            with open(play_count_file, "w") as f:
                yaml.dump(play_data, f)

            return True
        except Exception as e:
            print(f"Error incrementing play count for {game.id}: {e}")
            return False

    def update_play_time(self, game: Game, seconds: int) -> bool:
        """
        Update the play time for a game and save it to the playtime.yaml file.

        Args:
            game: The game to update the play time for
            seconds: The number of seconds to add to the play time

        Returns:
            True if the play time was successfully updated, False otherwise
        """
        if seconds <= 0:
            return True  # Nothing to update

        game_dir = self.games_dir / game.id
        play_time_file = game_dir / "playtime.yaml"

        try:
            # Add the new play time to the existing total
            game.play_time += seconds

            # Create the play time data
            play_time_data = {"seconds": game.play_time}

            # Write to the file
            with open(play_time_file, "w") as f:
                yaml.dump(play_time_data, f)

            return True
        except Exception as e:
            print(f"Error updating play time for {game.id}: {e}")
            return False

    def save_game_pid(self, game: Game, pid: int) -> bool:
        """
        Save the PID of a running game process to a pid.yaml file.

        Args:
            game: The game being played
            pid: The process ID of the game

        Returns:
            True if the PID was successfully saved, False otherwise
        """
        game_dir = self.games_dir / game.id
        pid_file = game_dir / "pid.yaml"

        try:
            # Create the PID data
            pid_data = {"pid": pid}

            # Write to the file
            with open(pid_file, "w") as f:
                yaml.dump(pid_data, f)

            return True
        except Exception as e:
            print(f"Error saving PID for {game.id}: {e}")
            return False

    def get_game_pid(self, game: Game) -> Optional[int]:
        """
        Get the PID of a running game process from the pid.yaml file.

        Args:
            game: The game to check

        Returns:
            The PID if the game is running, None otherwise
        """
        pid_file = Path(game.get_pid_path(self.data_dir))

        if not pid_file.exists():
            return None

        try:
            with open(pid_file, "r") as f:
                pid_data = yaml.safe_load(f)
                if pid_data and isinstance(pid_data, dict):
                    return pid_data.get("pid")
        except Exception as e:
            print(f"Error getting PID for {game.id}: {e}")

        return None

    def clear_game_pid(self, game: Game) -> bool:
        """
        Remove the pid.yaml file for a game.

        Args:
            game: The game to clear the PID for

        Returns:
            True if the PID file was successfully removed, False otherwise
        """
        pid_file = Path(game.get_pid_path(self.data_dir))

        if not pid_file.exists():
            return True

        try:
            pid_file.unlink()
            return True
        except Exception as e:
            print(f"Error clearing PID for {game.id}: {e}")
            return False

    def remove_game(self, game: Game) -> bool:
        """
        Remove a game from the games directory.

        Args:
            game: The game to remove

        Returns:
            True if the game was successfully removed, False otherwise
        """
        game_dir = self.games_dir / game.id

        try:
            if game_dir.exists():
                # Remove the entire game directory (which includes the cover image)
                shutil.rmtree(game_dir)
                return True
            else:
                print(f"Game directory {game_dir} not found")
                return False
        except Exception as e:
            print(f"Error removing game {game.id}: {e}")
            return False
