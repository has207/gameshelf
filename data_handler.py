import os
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class Runner:
    title: str
    image: str
    command: str
    id: str = ""


@dataclass
class Game:
    title: str
    image: str
    runner: Optional[str] = None
    id: str = ""


class DataHandler:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.games_dir = self.data_dir / "games"
        self.runners_dir = self.data_dir / "runners"
        
        # Ensure directories exist
        self.games_dir.mkdir(parents=True, exist_ok=True)
        self.runners_dir.mkdir(parents=True, exist_ok=True)
    
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
