import os
import yaml
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple


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
        self.image = image
        self.runner = runner.lower()


class DataHandler:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.games_dir = self.data_dir / "games"
        self.runners_dir = self.data_dir / "runners"
        
        # Get the project root directory for finding media directory
        self.project_root = Path(__file__).parent
        self.media_dir = self.project_root / "media" / "images"
        
        # Ensure directories exist
        self.games_dir.mkdir(parents=True, exist_ok=True)
        self.runners_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
    
    def load_games(self) -> List[Game]:
        games = []
        for game_file in self.games_dir.glob("*.yaml"):
            try:
                with open(game_file, "r") as f:
                    game_data = yaml.safe_load(f)
                    game = Game(
                        title=game_data.get("title", "Unknown Game"),
                        image=game_data.get("image", ""),
                        runner=game_data.get("runner"),
                        id=game_file.stem
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
            game.id = game.title.lower().replace(" ", "_")
        
        game_data = {
            "title": game.title,
            "image": game.image,
        }
        
        if game.runner:
            game_data["runner"] = game.runner
        
        try:
            with open(self.games_dir / f"{game.id}.yaml", "w") as f:
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
            
    def save_game_image(self, source_path: str, game_id: str) -> Optional[str]:
        """
        Copy a game image to the media directory and return the destination path.
        
        Args:
            source_path: Path to the source image
            game_id: ID of the game for naming the destination file
            
        Returns:
            The path to the saved image, or None if the operation failed
        """
        if not source_path or not os.path.exists(source_path):
            return None
            
        try:
            # Generate unique filename
            ext = os.path.splitext(source_path)[1]
            unique_filename = f"{game_id}{ext}"
            dest_path = self.media_dir / unique_filename
            
            # Copy the file
            shutil.copy2(source_path, dest_path)
            return str(dest_path)
        except Exception as e:
            print(f"Error copying image: {e}")
            return None
            
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
        # Generate a game ID
        game_id = title.lower().replace(" ", "-")
        
        # Save image if provided
        final_image_path = None
        if image_path:
            final_image_path = self.save_game_image(image_path, game_id)
        
        # Create and return the game object
        return Game(
            id=game_id,
            title=title,
            image=final_image_path,
            runner=runner_id
        )
