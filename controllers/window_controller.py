from typing import Dict, List, Optional

from gi.repository import Gtk, Adw, Gio, GdkPixbuf
from data_handler import DataHandler, Game, Runner
from process_tracking import ProcessTracker
from app_state_manager import AppStateManager
from controllers.common import get_template_path

from controllers.details_controller import GameDetailsContent, DetailsController
from controllers.dialogs_controller import GameDialog
from controllers.runners_manager_controller import RunnersManagerDialog
from controllers.game_grid_controller import GameGridController
from controllers.sidebar_controller import SidebarController
from controllers.title_bar_controller import TitleBarController


class GameShelfController:
    """
    Main controller class for the GameShelf application.
    Handles data management, game/runner operations, and UI coordination.
    """
    def __init__(self, data_handler: DataHandler, settings_manager: AppStateManager):
        self.data_handler = data_handler
        self.settings_manager = settings_manager
        self.games = self.data_handler.load_games()
        self.runners = {runner.id: runner for runner in self.data_handler.load_runners()}
        self.window = None
        self.actions = {}

        # Initialize process tracker
        self.process_tracker = ProcessTracker(data_handler)

        # Load settings
        self.current_filter = self.settings_manager.get_current_filter()
        self.sort_field, self.sort_ascending = self.settings_manager.get_sort_settings()
        self.show_hidden = self.settings_manager.get_show_hidden()

        # Sub-controllers will be initialized later when the window is created
        self.title_bar_controller = None
        self.game_grid_controller = None
        self.sidebar_controller = None
        self.details_controller = None

    def get_games(self) -> List[Game]:
        return self.games

    def get_runners(self) -> List[Runner]:
        runners = list(self.runners.values())
        print(f"get_runners() returning {len(runners)} runners: {[r.id for r in runners]}")
        return runners

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

    def remove_game(self, game: Game) -> bool:
        """Remove a game and refresh the UI"""
        result = self.data_handler.remove_game(game)
        if result:
            # Reload data to refresh the UI
            self.reload_data()
        return result

    def reload_data(self, refresh_sidebar=True, refresh_grid=True):
        """Reload all data from storage and refresh the UI

        Args:
            refresh_sidebar: Whether to refresh the sidebar runners
            refresh_grid: Whether to refresh the games grid
        """
        self.games = self.data_handler.load_games()
        self.runners = {runner.id: runner for runner in self.data_handler.load_runners()}

        print(f"Reloaded data: {len(self.games)} games, {len(self.runners)} runners")

        # Get search text from the window if available
        search_text = ""
        if self.window and hasattr(self.window, 'search_entry'):
            search_text = self.window.search_entry.get_text().strip().lower()

        # Refresh the sidebar if requested
        if refresh_sidebar and self.window and hasattr(self.window, 'refresh_sidebar_runners'):
            print("Refreshing sidebar runners from controller")
            self.window.refresh_sidebar_runners()

        # Refresh games grid if requested
        if refresh_grid:
            if hasattr(self, 'title_bar_controller') and self.title_bar_controller:
                print("Populating games through title bar controller")
                self.title_bar_controller.populate_games(filter_runner=self.current_filter, search_text=search_text)
            elif hasattr(self, 'game_grid_controller') and self.game_grid_controller:
                print("Populating games through game grid controller")
                self.game_grid_controller.populate_games(filter_runner=self.current_filter, search_text=search_text)

    def get_game_pixbuf(self, game: Game, width: int = 200, height: int = 260) -> Optional[GdkPixbuf.Pixbuf]:
        """Get a game's image as a pixbuf, using the data handler"""
        return self.data_handler.load_game_image(game, width, height)

    def get_runner_pixbuf(self, runner: Runner, width: int = 64, height: int = 64) -> Optional[GdkPixbuf.Pixbuf]:
        """Get a runner's image as a pixbuf, using the data handler"""
        return self.data_handler.load_runner_image(runner, width, height)

    def toggle_game_hidden(self, game: Game) -> bool:
        """
        Toggle the hidden state of a game

        Args:
            game: The game to toggle hidden state for

        Returns:
            True if successful, False otherwise
        """
        game.hidden = not game.hidden

        # Save the updated game
        result = self.data_handler.save_game(game)
        if result:
            # Refresh the game list
            self.reload_data()

        return result

    def toggle_show_hidden(self) -> None:
        """Toggle between showing hidden or non-hidden games"""
        self.show_hidden = not self.show_hidden
        print(f"Toggled show_hidden to: {self.show_hidden}")

        # Save state to settings
        self.settings_manager.set_show_hidden(self.show_hidden)

        # Get search text from the window if available
        search_text = ""
        if self.window and hasattr(self.window, 'search_entry'):
            search_text = self.window.search_entry.get_text().strip().lower()
            # Save search text
            self.settings_manager.set_search_text(search_text)

        # Only refresh the grid, sidebar doesn't need to change when toggling visibility
        if hasattr(self, 'game_grid_controller') and self.game_grid_controller:
            self.game_grid_controller.populate_games(filter_runner=self.current_filter, search_text=search_text)

    def add_action(self, action: Gio.SimpleAction):
        """
        Add an action to the controller's action map.
        This is used for the context menu actions.

        Args:
            action: The action to add
        """
        # Store a reference to the action to prevent it from being garbage collected
        action_name = action.get_name()
        self.actions[action_name] = action

        # Add the action to the window's action map if available
        if self.window:
            self.window.add_action(action)


@Gtk.Template(filename=get_template_path("window.ui"))
class GameShelfWindow(Adw.ApplicationWindow):
    __gtype_name__ = "GameShelfWindow"

    games_grid: Gtk.GridView = Gtk.Template.Child()
    details_panel: Adw.Flap = Gtk.Template.Child()
    details_content: GameDetailsContent = Gtk.Template.Child()
    sidebar_listview: Gtk.ListView = Gtk.Template.Child()
    add_game_button: Gtk.Button = Gtk.Template.Child()
    search_entry: Gtk.SearchEntry = Gtk.Template.Child()
    visibility_toggle: Gtk.ToggleButton = Gtk.Template.Child()

    def __init__(self, app, controller):
        super().__init__(application=app)
        self.controller = controller
        # Set the window reference in the controller
        self.controller.window = self
        # Track the currently selected game to maintain state across filtering
        self.current_selected_game = None

        # Debug to see if the UI template is loaded correctly
        print("Sidebar ListView:", self.sidebar_listview)
        print("Games Grid:", self.games_grid)
        print("Details Panel:", self.details_panel)

        # Initialize sub-controllers
        self._init_controllers()

    def _init_controllers(self):
        """Initialize all the sub-controllers and connect them to UI elements"""
        print("Initializing controllers...")

        # Initialize controllers in correct dependency order
        self.controller.title_bar_controller = TitleBarController(self.controller)
        self.controller.game_grid_controller = GameGridController(self.controller)
        self.controller.sidebar_controller = SidebarController(self.controller)
        self.controller.details_controller = DetailsController(self.controller)

        # Debug info
        print(f"Controller initialized: {self.controller}")
        print(f"Grid controller: {self.controller.game_grid_controller}")
        print(f"Sidebar controller: {self.controller.sidebar_controller}")

        # Initialize visibility toggle with saved state
        if hasattr(self, 'visibility_toggle') and self.visibility_toggle is not None:
            show_hidden = self.controller.settings_manager.get_show_hidden()
            self.visibility_toggle.set_active(show_hidden)

            # Update the icon based on state
            if show_hidden:
                self.visibility_toggle.set_icon_name("view-reveal-symbolic")
                self.visibility_toggle.set_tooltip_text("Showing Hidden Games")
                self.visibility_toggle.add_css_class("destructive-action")
            else:
                self.visibility_toggle.set_icon_name("view-conceal-symbolic")
                self.visibility_toggle.set_tooltip_text("Showing Normal Games")
                self.visibility_toggle.remove_css_class("destructive-action")

        # Setup components in correct order
        # 1. First title bar (needed for search)
        if hasattr(self, 'search_entry') and self.search_entry is not None:
            print("Setting up search entry")
            self.controller.title_bar_controller.setup_search(self.search_entry)

        # 2. Then grid view
        if hasattr(self, 'games_grid') and self.games_grid is not None:
            print("Setting up games grid")
            self.controller.game_grid_controller.bind_gridview(self.games_grid)

        # 3. Then details panel
        if hasattr(self, 'details_content') and hasattr(self, 'details_panel'):
            print("Setting up details panel")
            self.controller.details_controller.setup_details_panel(self.details_content, self.details_panel)

        # 4. Finally sidebar (which needs the others for filtering/selection)
        if hasattr(self, 'sidebar_listview') and self.sidebar_listview is not None:
            print("Setting up sidebar")
            self.controller.sidebar_controller.setup_sidebar(self.sidebar_listview)

    def refresh_sidebar_runners(self):
        """Delegate to sidebar controller"""
        if hasattr(self.controller, 'sidebar_controller') and self.controller.sidebar_controller:
            self.controller.sidebar_controller.refresh_sidebar_runners()

    @Gtk.Template.Callback()
    def on_add_game_clicked(self, button):
        # Create a new game dialog in add mode
        dialog = GameDialog(self, self.controller, edit_mode=False)
        dialog.set_transient_for(self)

        # Populate runners list with fresh data
        dialog.populate_runners(self.controller.get_runners())
        dialog.show()

    @Gtk.Template.Callback()
    def on_manage_runners_clicked(self, button):
        # Open the runners manager dialog
        dialog = RunnersManagerDialog(self, self.controller, self)
        dialog.set_transient_for(self)
        dialog.show()

    @Gtk.Template.Callback()
    def on_search_changed(self, search_entry):
        """Handle search entry text changes"""
        if self.controller.title_bar_controller:
            self.controller.title_bar_controller.on_search_changed(search_entry)

    @Gtk.Template.Callback()
    def on_visibility_toggle_clicked(self, button):
        """Handle visibility toggle button click"""
        if self.controller.title_bar_controller:
            self.controller.title_bar_controller.on_visibility_toggle_clicked(button)