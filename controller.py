import gi
import os
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GdkPixbuf, Gdk
from data_handler import DataHandler, Game, Runner
from typing import Dict, List, Optional


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "window.ui"))
class GameShelfWindow(Adw.ApplicationWindow):
    __gtype_name__ = "GameShelfWindow"

    games_grid: Gtk.GridView = Gtk.Template.Child()

    def __init__(self, app, controller):
        super().__init__(application=app)
        controller.bind_gridview(self.games_grid)


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "game_item.ui"))
class GameItem(Gtk.Box):
    __gtype_name__ = "GameItem"
    image: Gtk.Picture = Gtk.Template.Child()
    label: Gtk.Label = Gtk.Template.Child()

    def __init__(self, game: Game, controller):
        super().__init__()
        self.label.set_label(game.title)
        pixbuf = controller.get_game_pixbuf(game)
        if pixbuf:
            self.image.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "runner_item.ui"))
class RunnerItem(Gtk.Box):
    __gtype_name__ = "RunnerItem"
    image: Gtk.Picture = Gtk.Template.Child()
    label: Gtk.Label = Gtk.Template.Child()

    def __init__(self, runner: Runner, controller):
        super().__init__()
        self.label.set_label(runner.title)
        pixbuf = controller.get_runner_pixbuf(runner)
        if pixbuf:
            self.image.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))


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
        return GameItem(game, self)

    def create_runner_widget(self, runner: Runner) -> Gtk.Widget:
        return RunnerItem(runner, self)

