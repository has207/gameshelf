import gi
import os
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GdkPixbuf, Gdk, GObject
from data_handler import DataHandler, Game, Runner
from typing import Dict, List, Optional


class SidebarItem(GObject.GObject):
    name = GObject.Property(type=str)
    icon_name = GObject.Property(type=str)

    def __init__(self, name, icon_name="applications-games-symbolic"):
        super().__init__()
        self.name = name
        self.icon_name = icon_name


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "sidebar_row.ui"))
class SidebarRow(Gtk.Box):
    __gtype_name__ = "SidebarRow"
    label: Gtk.Label = Gtk.Template.Child()
    icon: Gtk.Image = Gtk.Template.Child()
    
    def set_icon_name(self, icon_name):
        self.icon.set_from_icon_name(icon_name)


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "details_panel.ui"))
class GameDetailsContent(Gtk.Box):
    __gtype_name__ = "GameDetailsContent"
    title_label: Gtk.Label = Gtk.Template.Child()
    runner_label: Gtk.Label = Gtk.Template.Child()

    @Gtk.Template.Callback()
    def on_close_details_clicked(self, button):
        self.get_ancestor(GameShelfWindow).details_panel.set_reveal_flap(False)

    def set_game(self, game: Game):
        self.title_label.set_text(game.title)
        self.runner_label.set_text(game.runner)


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "window.ui"))
class GameShelfWindow(Adw.ApplicationWindow):
    __gtype_name__ = "GameShelfWindow"

    games_grid: Gtk.GridView = Gtk.Template.Child()
    details_panel: Adw.Flap = Gtk.Template.Child()
    details_content: GameDetailsContent = Gtk.Template.Child()
    sidebar_listview: Gtk.ListView = Gtk.Template.Child()

    def __init__(self, app, controller):
        super().__init__(application=app)
        self.controller = controller
    
        # Debug to see if the UI template is loaded correctly
        print("Sidebar ListView:", self.sidebar_listview)
        print("Games Grid:", self.games_grid)
        print("Details Panel:", self.details_panel)
    
        # Only continue if the template elements exist
        if hasattr(self, 'sidebar_listview') and self.sidebar_listview is not None:
            self.sidebar_store = Gio.ListStore(item_type=SidebarItem)
            self.sidebar_store.append(SidebarItem("Games", "view-grid-symbolic"))
        
            # Add runners with appropriate icons
            for runner in controller.get_runners():
                icon_name = self._get_runner_icon(runner.id)
                self.sidebar_store.append(SidebarItem(runner.id, icon_name))

            factory = Gtk.SignalListItemFactory()
            factory.connect("setup", self._setup_sidebar_item)
            factory.connect("bind", self._bind_sidebar_item)

            selection = Gtk.SingleSelection(model=self.sidebar_store)
            selection.connect("notify::selected", self._on_sidebar_selection)

            self.sidebar_listview.set_model(selection)
            self.sidebar_listview.set_factory(factory)
    
        # Only bind grid if it exists
        if hasattr(self, 'games_grid') and self.games_grid is not None:
            controller.bind_gridview(self.games_grid)
        
        # Only setup details panel if it exists
        if hasattr(self, 'details_panel') and self.details_panel is not None:
            self.details_panel.set_reveal_flap(False)
        
            # Only setup selection model if games_grid exists
            if hasattr(self, 'games_grid') and self.games_grid is not None:
                selection_model = self.games_grid.get_model()
                if isinstance(selection_model, Gtk.SingleSelection):
                    selection_model.connect("notify::selected-item", self._on_game_selected)

    def _get_runner_icon(self, runner_id):
      icon_map = {
        "steam": "steam-symbolic",
        "wine": "wine-symbolic",
        "native": "system-run-symbolic",
        "browser": "web-browser-symbolic",
        "emulator": "media-optical-symbolic",
        # Add more mappings as needed
      }

      # Try to match beginning of runner name to known icons
      for key, icon in icon_map.items():
          if runner_id.lower().startswith(key):
              return icon

      # Default icon for unknown runners
      return "application-x-executable-symbolic"

    def _setup_sidebar_item(self, factory, list_item):
        sidebar_row = SidebarRow()
        list_item.set_child(sidebar_row)

    def _bind_sidebar_item(self, factory, list_item):
        row = list_item.get_child()
        item = list_item.get_item()
        row.label.set_label(item.name.capitalize())
        row.set_icon_name(item.icon_name)

    def _on_game_selected(self, selection, param):
        selected_item = selection.get_selected_item()
        if not selected_item or not selected_item.get_first_child():
            self.details_panel.set_reveal_flap(False)
            return

        game_box = selected_item
        if not game_box or not game_box.get_first_child():
            self.details_panel.set_visible(False)
            return

        if isinstance(game_box, GameItem):
            self.details_content.set_game(game_box.game)
            self.details_panel.set_reveal_flap(True)
        else:
            self.details_panel.set_visible(False)

    def _on_sidebar_selection(self, selection, param):
        index = selection.get_selected()
        if index == -1:
            return

        selected = self.sidebar_store.get_item(index).name
        if selected == "Games":
            self.controller.populate_games()
        else:
            self.controller.populate_games(filter_runner=selected)


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "game_item.ui"))
class GameItem(Gtk.Box):
    __gtype_name__ = "GameItem"
    image: Gtk.Picture = Gtk.Template.Child()
    label: Gtk.Label = Gtk.Template.Child()

    def __init__(self, game: Game, controller):
        super().__init__()
        self.game = game
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
        # Create a simple container box to hold our game items
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        list_item.set_child(box)

    def _on_factory_bind(self, factory, list_item):
        box = list_item.get_child()
        # Remove any existing children
        child = box.get_first_child()
        while child:
            box.remove(child)
            child = box.get_first_child()

        # Add our game item
        position = list_item.get_position()
        if position < self.games_model.get_n_items():
            game_item = self.games_model.get_item(position)
            box.append(game_item)

    def populate_games(self, filter_runner: Optional[str] = None):
        self.games_model.remove_all()
        games = self.get_games()
        if filter_runner:
            games = [g for g in games if g.runner == filter_runner]
        for game in games:
            game_item = self.create_game_widget(game)
            self.games_model.append(game_item)

    def create_game_widget(self, game: Game) -> Gtk.Widget:
        return GameItem(game, self)

    def create_runner_widget(self, runner: Runner) -> Gtk.Widget:
        return RunnerItem(runner, self)

