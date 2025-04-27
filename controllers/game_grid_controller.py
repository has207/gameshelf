import os
from typing import List, Optional

from gi.repository import Gtk, Gio, Gdk
from data_handler import Game, Runner

from controllers.sidebar_controller import SidebarItem


@Gtk.Template(filename=os.path.join(os.path.dirname(os.path.dirname(__file__)), "layout", "game_item.ui"))
class GameItem(Gtk.Box):
    __gtype_name__ = "GameItem"
    image: Gtk.Picture = Gtk.Template.Child()
    label: Gtk.Label = Gtk.Template.Child()

    def __init__(self, game: Game, controller):
        super().__init__()
        self.game = game
        self.controller = controller
        self.label.set_label(game.title)

        # Try to load the game image
        pixbuf = controller.get_game_pixbuf(game)
        if pixbuf:
            self.image.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
        else:
            # Get a default icon paintable from the data handler
            icon_paintable = controller.data_handler.get_default_icon_paintable("applications-games-symbolic")
            self.image.set_paintable(icon_paintable)

        # Add left-click gesture for showing details panel
        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("released", self._on_clicked)
        self.add_controller(click_gesture)

        # Add right-click gesture for context menu
        right_click = Gtk.GestureClick.new()
        right_click.set_button(3)  # Right mouse button
        right_click.connect("pressed", self._on_right_click)
        self.add_controller(right_click)

    def _create_context_menu(self):
        # Create a context menu from the template
        from controllers.dialogs_controller import GameContextMenu
        context_menu = GameContextMenu(self.game, self)
        context_menu.set_parent(self)
        return context_menu

    def _on_right_click(self, gesture, n_press, x, y):
        # Show context menu at pointer position
        menu = self._create_context_menu()
        if not menu:
            return

        # Find the main window
        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if window:
            # Store the selected game to maintain state
            window.current_selected_game = self.game

        # Set the position to be at the mouse pointer
        rect = Gdk.Rectangle()
        rect.x = x
        rect.y = y
        rect.width = 1
        rect.height = 1
        menu.set_pointing_to(rect)

        # Show the menu
        menu.popup()

    def _on_clicked(self, gesture, n_press, x, y):
        # Only handle left clicks (button 1)
        if gesture.get_current_button() != 1:
            return

        # Find the main window to access the details panel
        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if window:
            # Store the selected game to maintain state across filtering
            window.current_selected_game = self.game
            window.details_content.set_game(self.game)
            window.details_panel.set_reveal_flap(True)


@Gtk.Template(filename=os.path.join(os.path.dirname(os.path.dirname(__file__)), "layout", "runner_item.ui"))
class RunnerItem(Gtk.Box):
    __gtype_name__ = "RunnerItem"
    image: Gtk.Picture = Gtk.Template.Child()
    label: Gtk.Label = Gtk.Template.Child()

    def __init__(self, runner: Runner, controller):
        super().__init__()
        self.label.set_label(runner.title)

        # Try to load the runner image
        pixbuf = controller.get_runner_pixbuf(runner)
        if pixbuf:
            self.image.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
        else:
            # Set a default icon when no image is available
            icon_name = controller.data_handler.get_runner_icon(runner.id)
            self.image.set_from_icon_name(icon_name)


class GameGridController:
    def __init__(self, main_controller):
        self.main_controller = main_controller
        self.games_model = None

    def bind_gridview(self, grid_view: Gtk.GridView):
        self.games_model = Gio.ListStore(item_type=Gtk.Widget)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_factory_setup)
        factory.connect("bind", self._on_factory_bind)

        # Create selection model that doesn't auto-select the first item
        selection_model = Gtk.SingleSelection(model=self.games_model, autoselect=False)
        grid_view.set_model(selection_model)
        grid_view.set_factory(factory)

        # Set fixed size for grid items
        grid_view.set_enable_rubberband(False)

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

    def populate_games(self, filter_runner: Optional[str] = None, search_text: str = ""):
        self.main_controller.current_filter = filter_runner
        self.games_model.remove_all()
        games = self.main_controller.get_games()

        # Apply runner filter
        if filter_runner is not None:  # Filter is specifically set (including empty string)
            games = [g for g in games if g.runner == filter_runner]

        # Apply search filter if search text is provided
        if search_text:
            games = [g for g in games if search_text in g.title.lower()]

        # Show only hidden or non-hidden games based on self.show_hidden setting
        if hasattr(self.main_controller, 'show_hidden'):
            if self.main_controller.show_hidden:
                # When show_hidden is True, only show hidden games
                games = [g for g in games if g.hidden]
            else:
                # When show_hidden is False, only show non-hidden games
                games = [g for g in games if not g.hidden]

        # Sort the games if sort parameters are set
        if hasattr(self.main_controller, 'sort_field') and hasattr(self.main_controller, 'sort_ascending'):
            games = self.sort_games(games, self.main_controller.sort_field, self.main_controller.sort_ascending)
        else:
            # Default sorting by title ascending
            games = sorted(games, key=lambda g: g.title.lower())

        # Create widgets for the games
        for game in games:
            game_item = self.create_game_widget(game)
            self.games_model.append(game_item)

    def sort_games(self, games: List[Game], sort_field: str, ascending: bool) -> List[Game]:
        """
        Sort a list of games by the specified field and direction

        Args:
            games: List of games to sort
            sort_field: Field to sort by
            ascending: True for ascending, False for descending

        Returns:
            Sorted list of games
        """
        reverse = not ascending

        if sort_field == "title":
            return sorted(games, key=lambda g: g.title.lower(), reverse=reverse)
        elif sort_field == "last_played":
            # Sort by last played time (None values at the end)
            def get_last_played(game):
                time = game.get_last_played_time(self.main_controller.data_handler.data_dir)
                # Use a very old timestamp for games never played
                return time if time is not None else 0
            return sorted(games, key=get_last_played, reverse=reverse)
        elif sort_field == "play_time":
            return sorted(games, key=lambda g: g.play_time, reverse=reverse)
        elif sort_field == "play_count":
            return sorted(games, key=lambda g: g.play_count, reverse=reverse)
        elif sort_field == "date_added":
            # Sort by created timestamp
            def get_created(game):
                return game.created if game.created is not None else 0
            return sorted(games, key=get_created, reverse=reverse)
        elif sort_field == "date_modified":
            # Sort by modified time
            def get_modified(game):
                time = game.get_modified_time(self.main_controller.data_handler.data_dir)
                return time if time is not None else 0
            return sorted(games, key=get_modified, reverse=reverse)
        else:
            # Default to title
            return sorted(games, key=lambda g: g.title.lower(), reverse=reverse)

    def create_game_widget(self, game: Game) -> Gtk.Widget:
        return GameItem(game, self.main_controller)

    def create_runner_widget(self, runner: Runner) -> Gtk.Widget:
        return RunnerItem(runner, self.main_controller)