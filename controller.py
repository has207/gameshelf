import gi
import os
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, GdkPixbuf
from data_handler import DataHandler, Game, Runner
from typing import Dict, List, Optional, Callable


class GameShelfController:
    def __init__(self, data_handler: DataHandler):
        self.data_handler = data_handler
        self.games: List[Game] = []
        self.runners: Dict[str, Runner] = {}
        self.reload_data()
        
    def reload_data(self):
        self.games = self.data_handler.load_games()
        self.runners = {runner.id: runner for runner in self.data_handler.load_runners()}
    
    def get_games(self) -> List[Game]:
        return self.games
    
    def get_runner(self, runner_id: str) -> Optional[Runner]:
        return self.runners.get(runner_id)
    
    def add_game(self, game: Game) -> bool:
        result = self.data_handler.save_game(game)
        if result:
            self.reload_data()
        return result
    
    def add_runner(self, runner: Runner) -> bool:
        result = self.data_handler.save_runner(runner)
        if result:
            self.reload_data()
        return result
    
    def get_game_pixbuf(self, game: Game, width: int = 200, height: int = 260) -> Optional[GdkPixbuf.Pixbuf]:
        try:
            if not game.image or not os.path.exists(game.image):
                return None
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                game.image, width, height, True)
        except Exception as e:
            print(f"Error loading image for {game.title}: {e}")
            return None
