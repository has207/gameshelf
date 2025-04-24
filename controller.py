import gi
import os
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GdkPixbuf, Gdk
from data_handler import DataHandler, Game, Runner
from typing import Dict, List, Optional


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

    def get_runners(self) -> List[Runner]:
        return list(self.runners.values())

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

    def get_runner_pixbuf(self, runner: Runner, width: int = 64, height: int = 64) -> Optional[GdkPixbuf.Pixbuf]:
        try:
            if not runner.image or not os.path.exists(runner.image):
                return None
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                runner.image, width, height, True)
        except Exception as e:
            print(f"Error loading image for {runner.title}: {e}")
            return None

    def bind_gridview(self, grid_view: Gtk.GridView):
        self.games_model = Gio.ListStore(item_type=Gtk.Widget)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_factory_setup)
        factory.connect("bind", self._on_factory_bind)

        selection_model = Gtk.SingleSelection(model=self.games_model)
        grid_view.set_model(selection_model)
        grid_view.set_factory(factory)

        self.populate_games()

    def _on_factory_setup(self, factory, list_item):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        list_item.set_child(box)

    def _on_factory_bind(self, factory, list_item):
        box = list_item.get_child()
        while box.get_first_child():
            box.remove(box.get_first_child())
        game_item = self.games_model.get_item(list_item.get_position())
        box.append(game_item)

    def populate_games(self):
        self.games_model.remove_all()
        for game in self.get_games():
            game_item = self.create_game_widget(game)
            self.games_model.append(game_item)

    def create_game_widget(self, game: Game) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        image = Gtk.Picture()
        image.set_size_request(200, 260)
        image.set_content_fit(Gtk.ContentFit.SCALE_DOWN)

        pixbuf = self.get_game_pixbuf(game)
        if pixbuf:
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            image.set_paintable(texture)

        label = Gtk.Label(label=game.title)
        label.set_wrap(True)
        label.set_max_width_chars(20)
        label.set_justify(Gtk.Justification.CENTER)

        box.append(image)
        box.append(label)
        return box

    def create_runner_widget(self, runner: Runner) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        image = Gtk.Picture()
        image.set_size_request(64, 64)
        image.set_content_fit(Gtk.ContentFit.SCALE_DOWN)

        pixbuf = self.get_runner_pixbuf(runner)
        if pixbuf:
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            image.set_paintable(texture)

        label = Gtk.Label(label=runner.title)
        label.set_xalign(0)

        box.append(image)
        box.append(label)
        return box

