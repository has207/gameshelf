from typing import Dict, List, Optional
import logging

from gi.repository import Gtk, Adw, Gio, GdkPixbuf, GLib
from data_handler import DataHandler, Game, Runner
from process_tracking import ProcessTracker
from app_state_manager import AppStateManager
from controllers.common import get_template_path

# Set up logger
logger = logging.getLogger(__name__)

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
    def __init__(self, data_handler: DataHandler, app_state_manager: AppStateManager):
        self.data_handler = data_handler
        self.app_state_manager = app_state_manager
        self.games = self.data_handler.load_games()
        self.runners = {runner.id: runner for runner in self.data_handler.load_runners()}
        self.window = None
        self.actions = {}

        # Initialize process tracker
        self.process_tracker = ProcessTracker(data_handler)

        # Load app state
        self.current_filter = self.app_state_manager.get_current_filter()
        self.sort_field, self.sort_ascending = self.app_state_manager.get_sort_state()
        self.show_hidden = self.app_state_manager.get_show_hidden()

        # Sub-controllers will be initialized later when the window is created
        self.title_bar_controller = None
        self.game_grid_controller = None
        self.sidebar_controller = None
        self.details_controller = None

    def get_games(self) -> List[Game]:
        return self.games

    def get_runners(self) -> List[Runner]:
        runners = list(self.runners.values())
        logger.debug(f"get_runners() returning {len(runners)} runners: {[r.id for r in runners]}")
        return runners

    def get_runner(self, runner_id: str) -> Optional[Runner]:
        return self.runners.get(runner_id)

    def get_search_text(self) -> str:
        """
        Get the current search text from the UI or app state

        Returns:
            str: The current search text or empty string if not available
        """
        search_text = ""
        # Try to get from UI
        if self.window and hasattr(self.window, 'search_entry'):
            search_text = self.window.search_entry.get_text().strip().lower()
        # Fall back to app state if UI not available
        elif hasattr(self, 'app_state_manager'):
            search_text = self.app_state_manager.get_search_text()
        return search_text

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

        logger.info(f"Reloaded data: {len(self.games)} games, {len(self.runners)} runners")

        # Get search text
        search_text = self.get_search_text()

        # Refresh the sidebar if requested
        if refresh_sidebar and self.sidebar_controller:
            logger.debug("Refreshing sidebar filters")
            self.sidebar_controller.refresh_filters()

        # Refresh games grid if requested
        if refresh_grid and hasattr(self, 'game_grid_controller') and self.game_grid_controller:
            # Let the grid controller handle the filtering using the sidebar controller
            logger.debug("Refreshing game grid with current filters")
            self.game_grid_controller.populate_games(search_text=search_text)

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
        logger.debug(f"Toggled show_hidden to: {self.show_hidden}")

        # Save state to app state
        self.app_state_manager.set_show_hidden(self.show_hidden)

        # Get search text and save it
        search_text = self.get_search_text()
        self.app_state_manager.set_search_text(search_text)

        # Refresh the sidebar to update filter counts
        if hasattr(self, 'sidebar_controller') and self.sidebar_controller:
            self.sidebar_controller.refresh_filters()

        # Refresh grid with updated filters and visibility setting
        if hasattr(self, 'game_grid_controller') and self.game_grid_controller:
            self.game_grid_controller.populate_games(search_text=search_text)

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
    sync_sources_button: Gtk.Button = Gtk.Template.Child()
    notifications_button: Gtk.Button = Gtk.Template.Child()
    notification_badge: Gtk.Label = Gtk.Template.Child()

    def __init__(self, app, controller):
        super().__init__(application=app)
        self.controller = controller
        self.app = app
        # Set the window reference in the controller
        self.controller.window = self
        # Track the currently selected game to maintain state across filtering
        self.current_selected_game = None
        # Flag to control minimize to tray behavior
        self.minimize_to_tray = True

        # Initialize notification system
        self.notifications = []
        self._setup_notification_system()

        # Debug to see if the UI template is loaded correctly
        logger.debug(f"Sidebar Container: {self.sidebar_container}")
        logger.debug(f"Games Grid: {self.games_grid}")
        logger.debug(f"Details Panel: {self.details_panel}")

        # Connect to the close-request signal
        self.connect("close-request", self._on_close_request)

        # Set the window reference in the process tracker for minimize to tray functionality
        if hasattr(self.controller, 'process_tracker'):
            self.controller.process_tracker.app_window = self
            logger.debug("Set window reference in process tracker for minimize to tray on game launch")

        # Initialize sub-controllers
        self._init_controllers()

    def _init_controllers(self):
        """Initialize all the sub-controllers and connect them to UI elements"""
        logger.info("Initializing controllers...")

        # Initialize controllers in correct dependency order
        self.controller.title_bar_controller = TitleBarController(self.controller)
        self.controller.game_grid_controller = GameGridController(self.controller)
        self.controller.sidebar_controller = SidebarController(self.controller)
        self.controller.details_controller = DetailsController(self.controller)

        # Debug info
        logger.debug(f"Controller initialized: {self.controller}")
        logger.debug(f"Grid controller: {self.controller.game_grid_controller}")
        logger.debug(f"Sidebar controller: {self.controller.sidebar_controller}")

        # Initialize visibility button with saved state
        if hasattr(self, 'visibility_toggle') and self.visibility_toggle is not None:
            show_hidden = self.controller.app_state_manager.get_show_hidden()

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
            logger.debug("Setting up search entry")
            self.controller.title_bar_controller.setup_search(self.search_entry)

        # 2. Then grid view
        if hasattr(self, 'games_grid') and self.games_grid is not None:
            logger.debug("Setting up games grid")
            self.controller.game_grid_controller.bind_gridview(self.games_grid)

            # Clear old sidebar index selection to avoid interference with new filter system
            self.controller.app_state_manager.set_sidebar_selection(0)

        # 3. Then details panel
        if hasattr(self, 'details_content') and hasattr(self, 'details_panel'):
            logger.debug("Setting up details panel")
            self.controller.details_controller.setup_details_panel(self.details_content, self.details_panel)

        # 4. Set up the sidebar (needed before applying filters)
        if hasattr(self, 'sidebar_container') and self.sidebar_container is not None:
            logger.debug("Setting up sidebar")
            self.controller.sidebar_controller.setup_sidebar(self.sidebar_container)

        # 5. Apply saved filters after sidebar is set up
        if hasattr(self, 'games_grid') and self.games_grid is not None:
            # Initialize with active filters from app state
            active_filters = self.controller.app_state_manager.get_sidebar_active_filters()

            # We'll let the sidebar controller apply the filters since it has all the filter categories
            if hasattr(self.controller, 'sidebar_controller') and self.controller.sidebar_controller:
                logger.debug("Applying saved filters from app state")

                # Set active filters in the sidebar controller
                self.controller.sidebar_controller.active_filters = active_filters

                # Update selection state in the UI
                self.controller.sidebar_controller._update_selection_state()

                # Update "All Games" label to reflect if filters are active
                self.controller.sidebar_controller._update_all_games_label()

                # Get search text from app state
                search_text = self.controller.app_state_manager.get_search_text()

                # Populate games with filters from sidebar controller
                self.controller.game_grid_controller.populate_games(search_text=search_text)

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
        source_manager.connect("source-removed", self._on_source_removed)

        dialog.show()

    @Gtk.Template.Callback()
    def on_sync_sources_clicked(self, button):
        """Handle sync sources button click - triggers sync on all enabled sources"""
        from source_handler import SourceHandler

        # Create a source handler
        source_handler = SourceHandler(self.controller.data_handler)

        # Get all enabled sources
        sources = source_handler.load_sources()
        enabled_sources = [source for source in sources if source.active]

        if not enabled_sources:
            self._show_notification("No enabled sources to sync")
            return

        # Replace sync button with progress label
        button.set_visible(False)

        # Get the actual header bar - walk up the widget hierarchy
        widget = button
        header_bar = None
        while widget:
            if isinstance(widget, Adw.HeaderBar):
                header_bar = widget
                break
            widget = widget.get_parent()

        # Create progress label
        progress_label = Gtk.Label()
        progress_label.set_text("Initializing sync...")
        progress_label.add_css_class("sync-progress")

        if header_bar:
            header_bar.pack_end(progress_label)
        else:
            # Fallback: if we can't find header bar, just show notification
            self._show_notification("Starting sync...")
            progress_label = None

        # Start sync for all enabled sources
        def sync_completed(count):
            """Called when sync is complete"""
            # Remove progress label and restore sync button
            if header_bar and progress_label:
                header_bar.remove(progress_label)
            button.set_visible(True)

            # Show notification (UI refresh happens after each source now)
            if count > 0:
                if count == 1:
                    self._show_notification("Sync complete - 1 game updated")
                else:
                    self._show_notification(f"Sync complete - {count} games updated")
            else:
                self._show_notification("Sync complete - no changes")

        def update_progress(source_name, current, total):
            """Update the progress label with current source"""
            progress_text = f"Syncing {source_name} ({current}/{total})"
            if progress_label:
                GLib.idle_add(lambda: progress_label.set_text(progress_text))
            else:
                # Fallback to notification if no progress label
                self._show_notification(progress_text)

        # Trigger sync for all enabled sources
        self._sync_all_sources(enabled_sources, sync_completed, update_progress)

    def _sync_all_sources(self, sources, callback, progress_callback):
        """Sync all provided sources and call callback with total count"""
        from gi.repository import GLib
        import threading

        total_changes = 0
        sources_completed = 0
        total_sources = len(sources)

        def source_completed(count):
            nonlocal total_changes, sources_completed
            total_changes += count
            sources_completed += 1

            if sources_completed == total_sources:
                # All sources complete, call the callback on main thread
                GLib.idle_add(lambda: callback(total_changes))

        # Sync sources sequentially to show proper progress
        def sync_next_source(index):
            if index >= len(sources):
                return

            source = sources[index]

            # Update progress
            progress_callback(source.name, index + 1, total_sources)

            def sync_source():
                try:
                    # Use the same sync logic as the source manager
                    from source_handler import SourceHandler
                    source_handler = SourceHandler(self.controller.data_handler)

                    # Get the scanner for this source type
                    scanner = source_handler.get_scanner(source.source_type, source.id)

                    # Perform the scan with a dummy progress callback
                    def dummy_progress_callback(current, total, message):
                        pass  # We don't need detailed progress, just source-level progress

                    added_count, errors = scanner.scan(source, dummy_progress_callback)

                    # Handle different return formats
                    if isinstance(added_count, tuple):
                        # PSN returns (added_count, updated_count)
                        actual_added, updated_count = added_count
                        changes = actual_added + updated_count
                    else:
                        changes = added_count or 0

                    source_completed(changes)

                    # Refresh UI if there were changes from this source
                    if changes > 0:
                        GLib.idle_add(lambda: self.controller.reload_data(refresh_sidebar=True))

                    # Start next source
                    GLib.idle_add(lambda: sync_next_source(index + 1))

                except Exception as e:
                    logger.error(f"Error syncing source {source.name}: {e}")
                    source_completed(0)

                    # Start next source even if this one failed
                    GLib.idle_add(lambda: sync_next_source(index + 1))

            thread = threading.Thread(target=sync_source)
            thread.daemon = True
            thread.start()

        # Start with the first source
        sync_next_source(0)

    def _setup_notification_system(self):
        """Set up the custom log handler to capture warnings and errors"""
        # Create custom handler that captures log messages
        class NotificationLogHandler(logging.Handler):
            def __init__(self, window):
                super().__init__()
                self.window = window
                self.setLevel(logging.WARNING)  # Capture WARNING and ERROR

            def emit(self, record):
                if record.levelno >= logging.WARNING:
                    # Use GLib.idle_add to ensure UI updates happen on main thread
                    from gi.repository import GLib
                    GLib.idle_add(self.window._add_notification, record)

        # Add our custom handler to the root logger
        self.notification_handler = NotificationLogHandler(self)
        logging.getLogger().addHandler(self.notification_handler)

    def _add_notification(self, record):
        """Add a notification from a log record"""
        import time

        notification = {
            'timestamp': time.time(),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
            'filename': record.filename,
            'lineno': record.lineno
        }

        self.notifications.append(notification)

        # Keep only last 100 notifications to prevent memory issues
        if len(self.notifications) > 100:
            self.notifications = self.notifications[-100:]

        self._update_notification_button()
        return False  # Remove from idle queue

    def _update_notification_button(self):
        """Update the notification button visibility and badge count"""
        count = len(self.notifications)

        if count > 0:
            self.notifications_button.set_visible(True)
            self.notification_badge.set_visible(True)
            self.notification_badge.set_text(str(count))

            # Update tooltip with latest notification
            latest = self.notifications[-1]
            tooltip = f"Latest: {latest['level']} - {latest['message'][:50]}..."
            self.notifications_button.set_tooltip_text(tooltip)
        else:
            self.notifications_button.set_visible(False)
            self.notification_badge.set_visible(False)

    @Gtk.Template.Callback()
    def on_notifications_clicked(self, button):
        """Handle notifications button click - show notifications dialog"""
        self._show_notifications_dialog()

    def _show_notifications_dialog(self):
        """Show dialog with all notifications"""
        dialog = Adw.Window()
        dialog.set_title("Notifications")
        dialog.set_default_size(600, 400)
        dialog.set_transient_for(self)
        dialog.set_modal(True)

        # Create main layout
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Header bar
        header_bar = Adw.HeaderBar()
        header_bar.set_title_widget(Adw.WindowTitle(title="Notifications"))

        # Clear button
        clear_button = Gtk.Button(label="Clear All")
        clear_button.connect("clicked", lambda b: self._clear_notifications(dialog))
        header_bar.pack_end(clear_button)

        # Close button
        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda b: dialog.close())
        header_bar.pack_start(close_button)

        content_box.append(header_bar)

        # Scrolled window for notifications
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        # List box for notifications
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)

        # Add notifications (newest first)
        for notification in reversed(self.notifications):
            self._create_notification_row(listbox, notification)

        if not self.notifications:
            # Show empty state
            empty_label = Gtk.Label(label="No notifications")
            empty_label.add_css_class("dim-label")
            empty_label.set_margin_top(50)
            empty_label.set_margin_bottom(50)
            listbox.append(empty_label)

        scrolled.set_child(listbox)
        content_box.append(scrolled)

        dialog.set_content(content_box)
        dialog.present()

    def _create_notification_row(self, listbox, notification):
        """Create a row for a notification"""
        import datetime

        row = Gtk.ListBoxRow()
        row.set_selectable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)

        # Header with level and timestamp
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        # Level badge
        level_label = Gtk.Label(label=notification['level'])
        level_label.add_css_class("notification-level")
        if notification['level'] == 'ERROR':
            level_label.add_css_class("error")
        elif notification['level'] == 'WARNING':
            level_label.add_css_class("warning")

        # Timestamp
        timestamp = datetime.datetime.fromtimestamp(notification['timestamp'])
        time_label = Gtk.Label(label=timestamp.strftime("%H:%M:%S"))
        time_label.add_css_class("dim-label")
        time_label.set_hexpand(True)
        time_label.set_halign(Gtk.Align.END)

        header_box.append(level_label)
        header_box.append(time_label)

        # Message
        message_label = Gtk.Label(label=notification['message'])
        message_label.set_wrap(True)
        message_label.set_halign(Gtk.Align.START)
        message_label.set_selectable(True)

        # Source info
        source_text = f"{notification['logger']} ({notification['filename']}:{notification['lineno']})"
        source_label = Gtk.Label(label=source_text)
        source_label.add_css_class("dim-label")
        source_label.set_halign(Gtk.Align.START)

        box.append(header_box)
        box.append(message_label)
        box.append(source_label)

        row.set_child(box)
        listbox.append(row)

    def _clear_notifications(self, dialog):
        """Clear all notifications"""
        self.notifications.clear()
        self._update_notification_button()
        dialog.close()

    def _on_games_added_from_source(self, source_manager, count):
        """Handle games being added or updated from a source scan"""
        if count > 0:
            # Reload the game and runner data
            self.controller.games = self.controller.data_handler.load_games()
            self.controller.runners = {runner.id: runner for runner in self.controller.data_handler.load_runners()}

            # Refresh the sidebar to update counts
            if hasattr(self.controller, 'sidebar_controller') and self.controller.sidebar_controller:
                self.controller.sidebar_controller.refresh_filters()

            # Get search text
            search_text = ""
            if hasattr(self, 'search_entry'):
                search_text = self.search_entry.get_text().strip().lower()

            # Refresh the grid with current sidebar filters
            if hasattr(self.controller, 'game_grid_controller') and self.controller.game_grid_controller:
                self.controller.game_grid_controller.populate_games(search_text=search_text)

            # Show a notification - the count here represents the total number of changes
            if count == 1:
                self._show_notification("Library updated with 1 change from source")
            else:
                self._show_notification(f"Library updated with {count} changes from source")

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
                logger.info(f"Notification: {message}")
        except Exception as e:
            # If anything goes wrong, fall back to printing
            logger.info(f"Notification: {message}")
            logger.error(f"Error showing toast: {e}")

    def _on_source_removed(self, source_manager):
        """Handle a source being removed"""
        # Force a full data reload
        self.controller.reload_data(refresh_sidebar=True, refresh_grid=True)

        # Show a notification - games from this source are also removed
        self._show_notification("Source and associated games removed successfully")

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

    def _on_close_request(self, window):
        """
        Handle window close request event

        If minimize_to_tray is True, hide the window instead of closing
        and show a notification to inform the user.

        Returns:
            bool: True to prevent the window from closing, False to allow closing
        """
        logger.debug("Window close request received")

        # Check if we should minimize to tray
        if self.minimize_to_tray and hasattr(self.app, 'tray_icon') and self.app.tray_icon:
            # Hide the window instead of closing it
            logger.info("Minimizing to system tray instead of closing")
            self.hide()

            # Show notification to inform user the app is still running
            try:
                toast = Adw.Toast.new("GameShelf is still running in the system tray")
                toast.set_timeout(3)  # 3 seconds

                # Show the notification
                try:
                    # First try to use overlay from content
                    overlay = None
                    content = self.get_content()

                    if content is not None:
                        if isinstance(content, Adw.ToastOverlay):
                            overlay = content
                        else:
                            # Try to find a toast overlay in the main window
                            for widget in [self.app.win, self]:
                                if hasattr(widget, 'content_area'):
                                    content_area = widget.content_area
                                    for child in content_area:
                                        if isinstance(child, Adw.ToastOverlay):
                                            overlay = child
                                            break

                    if overlay:
                        overlay.add_toast(toast)
                    else:
                        # If we couldn't find a toast overlay, just log the message
                        logger.info("App minimized to system tray, not closed")
                except Exception as inner_e:
                    logger.error(f"Error finding toast overlay: {inner_e}")
                    logger.info("App minimized to system tray, not closed")
            except Exception as e:
                logger.error(f"Error showing toast notification: {e}")
                logger.info("App minimized to system tray, not closed")

            # Return True to prevent the window from closing
            return True

        # Allow the window to close normally
        logger.info("Window will close normally")
        return False
