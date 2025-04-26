import os
import yaml
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
    def __init__(self, id: str, title: str, image: Optional[str] = None, runner: Optional[str] = None):
        self.id = id.lower()
        self.title = title
        self.runner = runner.lower() if runner else ""

    def get_cover_path(self, data_dir: Path) -> str:
        return str(data_dir / "games" / self.id / "cover.jpg")


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
        # Look for game.yaml files inside subdirectories of the games directory
        for game_file in self.games_dir.glob("*/game.yaml"):
            try:
                # The game ID is the name of the parent directory
                game_id = game_file.parent.name

                with open(game_file, "r") as f:
                    game_data = yaml.safe_load(f)
                    game = Game(
                        title=game_data.get("title", "Unknown Game"),
                        runner=game_data.get("runner"),
                        id=game_id
                    )
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
            # Only generate a numeric ID if one doesn't exist
            next_id = self.get_next_game_id()
            game.id = str(next_id)

        game_data = {
            "title": game.title,
        }

        if game.runner:
            game_data["runner"] = game.runner

        try:
            # Create the game's directory if it doesn't exist
            game_dir = self.games_dir / game.id
            game_dir.mkdir(parents=True, exist_ok=True)

            # Save the game data to game.yaml inside the game directory
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

        # Create the game object
        game = Game(
            id=game_id,
            title=title,
            runner=runner_id
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
