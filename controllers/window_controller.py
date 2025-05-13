from typing import Dict, List, Optional

from gi.repository import Gtk, Adw, Gio, GdkPixbuf, GLib
from data_handler import DataHandler, Game, Runner
from process_tracking import ProcessTracker
from app_state_manager import AppStateManager
from controllers.common import get_template_path

from controllers.details_controller import GameDetailsContent, DetailsController
from controllers.game_dialog_controller import GameDialog
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
            # Force sidebar refresh when a game is added
            self.reload_data(refresh_sidebar=True)
        return result

    def add_runner(self, runner: Runner) -> bool:
        result = self.data_handler.save_runner(runner)
        if result:
            # Force sidebar refresh when a runner is added
            self.reload_data(refresh_sidebar=True)
        return result

    def remove_game(self, game: Game) -> bool:
        """Remove a game"""
        return self.data_handler.remove_game(game)

    def reload_data(self, refresh_sidebar=True, refresh_grid=True):
        """Reload all data from storage and refresh the UI

        Args:
            refresh_sidebar: Whether to refresh the sidebar filters
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
        if refresh_sidebar and self.sidebar_controller:
            print("Refreshing sidebar filters")
            self.sidebar_controller.refresh_filters()

        # Refresh games grid if requested
        if refresh_grid:
            # Get active filters from sidebar controller if available
            filter_runners = None
            filter_completion_statuses = None
            filter_platforms = None
            filter_genres = None
            filter_age_ratings = None
            filter_features = None
            filter_regions = None

            if self.sidebar_controller:
                sidebar = self.sidebar_controller
                filter_runners = sidebar.active_filters.get("runner", set())
                filter_completion_statuses = sidebar.active_filters.get("completion_status", set())
                filter_platforms = sidebar.active_filters.get("platforms", set())
                filter_genres = sidebar.active_filters.get("genres", set())
                filter_age_ratings = sidebar.active_filters.get("age_ratings", set())
                filter_features = sidebar.active_filters.get("features", set())
                filter_regions = sidebar.active_filters.get("regions", set())
            else:
                # Fall back to legacy filter if sidebar controller not available
                if self.current_filter is not None:
                    filter_runners = {self.current_filter}

            if hasattr(self, 'game_grid_controller') and self.game_grid_controller:
                print(f"Populating games with filters: runners={filter_runners}, completion_statuses={filter_completion_statuses}, "
                      f"platforms={filter_platforms}, genres={filter_genres}, age_ratings={filter_age_ratings}, "
                      f"features={filter_features}, regions={filter_regions}, search={search_text}")
                self.game_grid_controller.populate_games(
                    filter_runners=filter_runners,
                    filter_completion_statuses=filter_completion_statuses,
                    filter_platforms=filter_platforms,
                    filter_genres=filter_genres,
                    filter_age_ratings=filter_age_ratings,
                    filter_features=filter_features,
                    filter_regions=filter_regions,
                    search_text=search_text
                )

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
        # Update the hidden state
        game.hidden = not game.hidden

        # Save the updated game - hidden flag is stored in game.yaml
        result = self.data_handler.save_game(game)
        if result:
            # Schedule refresh async after the operation completes
            GLib.timeout_add(50, lambda: self.reload_data(refresh_sidebar=True) or False)

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

        # Refresh the sidebar to update filter counts
        if hasattr(self, 'sidebar_controller') and self.sidebar_controller:
            self.sidebar_controller.refresh_filters()

        # Only refresh the grid, sidebar doesn't need to change when toggling visibility
        if hasattr(self, 'game_grid_controller') and self.game_grid_controller:
            # Get active filters from sidebar controller if available
            filter_runners = None
            filter_completion_statuses = None
            filter_platforms = None
            filter_genres = None
            filter_age_ratings = None
            filter_features = None
            filter_regions = None

            if hasattr(self, 'sidebar_controller') and self.sidebar_controller:
                sidebar = self.sidebar_controller
                filter_runners = sidebar.active_filters.get("runner", set())
                filter_completion_statuses = sidebar.active_filters.get("completion_status", set())
                filter_platforms = sidebar.active_filters.get("platforms", set())
                filter_genres = sidebar.active_filters.get("genres", set())
                filter_age_ratings = sidebar.active_filters.get("age_ratings", set())
                filter_features = sidebar.active_filters.get("features", set())
                filter_regions = sidebar.active_filters.get("regions", set())
                filter_sources = sidebar.active_filters.get("sources", set())

            self.game_grid_controller.populate_games(
                filter_runners=filter_runners,
                filter_completion_statuses=filter_completion_statuses,
                filter_platforms=filter_platforms,
                filter_genres=filter_genres,
                filter_age_ratings=filter_age_ratings,
                filter_features=filter_features,
                filter_regions=filter_regions,
                filter_sources=filter_sources,
                search_text=search_text
            )

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
    sidebar_container: Gtk.ScrolledWindow = Gtk.Template.Child()
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
        print("Sidebar Container:", self.sidebar_container)
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

        # Initialize visibility button with saved state
        if hasattr(self, 'visibility_toggle') and self.visibility_toggle is not None:
            show_hidden = self.controller.settings_manager.get_show_hidden()

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

            # Clear old sidebar index selection to avoid interference with new filter system
            self.controller.settings_manager.set_sidebar_selection(0)

        # 3. Then details panel
        if hasattr(self, 'details_content') and hasattr(self, 'details_panel'):
            print("Setting up details panel")
            self.controller.details_controller.setup_details_panel(self.details_content, self.details_panel)

        # 4. Set up the sidebar (needed before applying filters)
        if hasattr(self, 'sidebar_container') and self.sidebar_container is not None:
            print("Setting up sidebar")
            self.controller.sidebar_controller.setup_sidebar(self.sidebar_container)

        # 5. Apply saved filters after sidebar is set up
        if hasattr(self, 'games_grid') and self.games_grid is not None:
            # Initialize with active filters from settings
            active_filters = self.controller.settings_manager.get_sidebar_active_filters()

            # We'll let the sidebar controller apply the filters since it has all the filter categories
            if hasattr(self.controller, 'sidebar_controller') and self.controller.sidebar_controller:
                print("Applying saved filters from settings")

                # Set active filters in the sidebar controller
                self.controller.sidebar_controller.active_filters = active_filters

                # Update selection state in the UI
                self.controller.sidebar_controller._update_selection_state()

                # Update "All Games" label to reflect if filters are active
                self.controller.sidebar_controller._update_all_games_label()

                # Apply filters to the grid
                runner_filters = active_filters.get("runner", set())
                completion_status_filters = active_filters.get("completion_status", set())
                platform_filters = active_filters.get("platforms", set())
                genre_filters = active_filters.get("genres", set())
                age_rating_filters = active_filters.get("age_ratings", set())
                feature_filters = active_filters.get("features", set())
                region_filters = active_filters.get("regions", set())
                source_filters = active_filters.get("sources", set())

                # Get search text from settings
                search_text = self.controller.settings_manager.get_search_text()

                # Populate games with stored filters
                self.controller.game_grid_controller.populate_games(
                    filter_runners=runner_filters,
                    filter_completion_statuses=completion_status_filters,
                    filter_platforms=platform_filters,
                    filter_genres=genre_filters,
                    filter_age_ratings=age_rating_filters,
                    filter_features=feature_filters,
                    filter_regions=region_filters,
                    filter_sources=source_filters,
                    search_text=search_text
                )

    def refresh_sidebar_runners(self):
        """Delegate to sidebar controller - refresh filters"""
        if hasattr(self.controller, 'sidebar_controller') and self.controller.sidebar_controller:
            self.controller.sidebar_controller.refresh_filters()

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
    def on_import_games_clicked(self, button):
        # Open the import dialog
        from controllers.import_dialog import ImportDialog
        dialog = ImportDialog(self, self.controller)
        dialog.set_transient_for(self)
        dialog.show()

    @Gtk.Template.Callback()
    def on_manage_sources_clicked(self, button):
        # Open the source manager dialog
        from controllers.source_manager_controller import SourceManager
        from source_handler import SourceHandler

        # Create a source handler
        source_handler = SourceHandler(self.controller.data_handler)

        # Create a new dialog window for the source manager
        dialog = Gtk.Dialog(
            title="Manage Sources",
            transient_for=self,
            modal=True,
            use_header_bar=True
        )

        # Set dialog properties
        dialog.set_default_size(600, 400)

        # Create and add the source manager to the dialog
        source_manager = SourceManager(source_handler)
        dialog.get_content_area().append(source_manager)

        # Connect signals
        source_manager.connect("closed", lambda sm: dialog.close())
        source_manager.connect("games-added", self._on_games_added_from_source)

        dialog.show()

    def _on_games_added_from_source(self, source_manager, count):
        """Handle games being added from a source scan"""
        if count > 0:
            # Reload data after games are added
            self.controller.reload_data(refresh_sidebar=True)

            # Show a notification
            self._show_notification(f"Added {count} games from source")

    def _show_notification(self, message):
        """Show a toast notification or just print if toast overlay not available"""
        try:
            # Create a toast with the message
            toast = Adw.Toast.new(message)
            toast.set_timeout(3)  # 3 seconds

            # Try to add the toast to a toast overlay
            added = False

            # Get the content and check for a toast overlay
            content = self.get_content()
            if content is not None:
                # Check if the content itself is a toast overlay
                if isinstance(content, Adw.ToastOverlay):
                    content.add_toast(toast)
                    added = True
                # Otherwise try to find one in the children
                elif hasattr(content, "get_first_child") and content.get_first_child() is not None:
                    for child in content.get_first_child().observe_children():
                        if isinstance(child, Adw.ToastOverlay):
                            child.add_toast(toast)
                            added = True
                            break

            if not added:
                # If we couldn't add the toast, print the message
                print(f"Notification: {message}")
        except Exception as e:
            # If anything goes wrong, fall back to printing
            print(f"Notification: {message}")
            print(f"Error showing toast: {e}")

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
