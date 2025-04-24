import sys
import gi
import os
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, GdkPixbuf, Gdk
from data_handler import DataHandler, Game, Runner
from controller import GameShelfController


class GameItem(Gtk.Box):
    def __init__(self, game: Game, controller: GameShelfController):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        # Image
        self.image = Gtk.Picture()
        self.image.set_size_request(200, 260)
        self.image.set_content_fit(Gtk.ContentFit.SCALE_DOWN)

        pixbuf = controller.get_game_pixbuf(game)
        if pixbuf:
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            self.image.set_paintable(texture)

        # Title
        self.label = Gtk.Label(label=game.title)
        self.label.set_wrap(True)
        self.label.set_max_width_chars(20)
        self.label.set_justify(Gtk.Justification.CENTER)

        # Add widgets to box
        self.append(self.image)
        self.append(self.label)


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "window.ui"))
class GameShelfWindow(Adw.ApplicationWindow):
    __gtype_name__ = "GameShelfWindow"

    games_grid: Gtk.GridView = Gtk.Template.Child()

    def __init__(self, app, controller: GameShelfController):

        super().__init__(application=app)
        self.controller = controller

        # Set up your model and factory
        self.games_model = Gio.ListStore(item_type=Gtk.Widget)
        self.factory = Gtk.SignalListItemFactory()
        self.factory.connect("setup", self._on_factory_setup)
        self.factory.connect("bind", self._on_factory_bind)

        selection_model = Gtk.SingleSelection(model=self.games_model)
        self.games_grid.set_model(selection_model)
        self.games_grid.set_factory(self.factory)

        # Load the games
        self.load_games()

    def _on_factory_setup(self, factory, list_item):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        list_item.set_child(box)

    def _on_factory_bind(self, factory, list_item):
        box = list_item.get_child()
        # Clear existing children first to prevent duplicate appends
        while box.get_first_child():
            box.remove(box.get_first_child())

        # Get the game item and append it
        game_item = self.games_model.get_item(list_item.get_position())
        box.append(game_item)

    def load_games(self):
        self.games_model.remove_all()
        games = self.controller.get_games()

        print(f"Loading {len(games)} games")

        for game in games:
            game_item = GameItem(game, self.controller)
            self.games_model.append(game_item)


class GameShelfApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.example.GameShelf",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)

        # Initialize the data handler and controller
        self.data_handler = DataHandler()
        self.controller = GameShelfController(self.data_handler)

        # Connect signals
        self.connect('activate', self.on_activate)

    def on_activate(self, app):
        # Create the main window
        self.win = GameShelfWindow(self, self.controller)
        self.win.present()


# Run the application
if __name__ == "__main__":
    # Initialize Adwaita
    app = GameShelfApp()
    app.run(sys.argv)

