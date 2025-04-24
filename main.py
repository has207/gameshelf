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


class GameShelfWindow(Adw.ApplicationWindow):
    def __init__(self, app, controller: GameShelfController):
        super().__init__(application=app, title="GameShelf")
        self.controller = controller
        
        # Set default window size
        self.set_default_size(1000, 700)
        
        # Create main layout
        self.setup_ui()
        
        # Load games
        self.load_games()
    
    def setup_ui(self):
        # Create main box with vertical orientation
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        
        # Create header
        header = Adw.HeaderBar()
        main_box.append(header)
        
        # Create content area that will contain the grid
        content_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content_area.set_vexpand(True)
        content_area.set_hexpand(True)
        main_box.append(content_area)
        
        # Create scrolled window that should expand to fill available space
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        content_area.append(scrolled)
        
        # Set up the grid view for games
        self.games_grid = Gtk.GridView()
        self.games_grid.set_vexpand(True)
        self.games_grid.set_hexpand(True)
        
        # Configure the grid
        self.games_grid.set_min_columns(2)
        self.games_grid.set_max_columns(10)
        
        # Create model and factory for grid items
        self.games_model = Gio.ListStore(item_type=Gtk.Widget)
        self.factory = Gtk.SignalListItemFactory()
        self.factory.connect("setup", self._on_factory_setup)
        self.factory.connect("bind", self._on_factory_bind)
        
        # Set up selection model
        selection_model = Gtk.SingleSelection(model=self.games_model)
        self.games_grid.set_model(selection_model)
        self.games_grid.set_factory(self.factory)
        
        # Add grid to scrolled window
        scrolled.set_child(self.games_grid)
        
        # Set the main box as the content of the window
        self.set_content(main_box)
        
        # Print debug info - using a safer approach
        print("Window created and UI set up")
    
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

