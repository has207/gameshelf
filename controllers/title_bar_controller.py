from typing import Optional

from gi.repository import Gtk
from controllers.common import get_template_path


@Gtk.Template(filename=get_template_path("sort_menu.ui"))
class GameSortMenu(Gtk.Popover):
    """Sort menu for games grid"""
    __gtype_name__ = "GameSortMenu"

    # Template child widgets
    sort_ascending_button: Gtk.ToggleButton = Gtk.Template.Child()
    sort_descending_button: Gtk.ToggleButton = Gtk.Template.Child()
    sort_by_title: Gtk.CheckButton = Gtk.Template.Child()
    sort_by_last_played: Gtk.CheckButton = Gtk.Template.Child()
    sort_by_play_time: Gtk.CheckButton = Gtk.Template.Child()
    sort_by_play_count: Gtk.CheckButton = Gtk.Template.Child()
    sort_by_date_added: Gtk.CheckButton = Gtk.Template.Child()
    sort_by_date_modified: Gtk.CheckButton = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        # Sort order and field will be initialized from main controller
        # when shown for the first time
        self.ascending = True
        self.sort_field = "title"

        # We'll initialize the correct buttons when the menu is first shown
        self.connected = False

        # Connect to the visibility signal to initialize values when first shown
        self.connect("notify::visible", self.on_visible_notify)

    @Gtk.Template.Callback()
    def on_sort_order_toggled(self, button):
        """Called when sort order buttons are toggled"""
        # Only react when a button is toggled ON, not when it's toggled OFF
        if not button.get_active():
            return

        # Set the new sort order
        if button == self.sort_ascending_button:
            self.ascending = True
        elif button == self.sort_descending_button:
            self.ascending = False

        # Update sort
        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if window and window.controller:
            window.controller.title_bar_controller.update_sort(self.sort_field, self.ascending)

    def on_visible_notify(self, popover, param):
        """Called when the popover visibility changes"""
        if popover.get_visible() and not self.connected:
            # Only load settings the first time the menu is shown
            self.connected = True

            # Get window
            from controllers.window_controller import GameShelfWindow
            window = self.get_ancestor(GameShelfWindow)
            if window and window.controller:
                # Get sort settings
                self.sort_field, self.ascending = window.controller.settings_manager.get_sort_settings()

                # Set the correct sort field button without triggering callbacks
                # This part just sets up the UI to match current settings
                button_to_activate = None
                if self.sort_field == "title":
                    button_to_activate = self.sort_by_title
                elif self.sort_field == "last_played":
                    button_to_activate = self.sort_by_last_played
                elif self.sort_field == "play_time":
                    button_to_activate = self.sort_by_play_time
                elif self.sort_field == "play_count":
                    button_to_activate = self.sort_by_play_count
                elif self.sort_field == "date_added":
                    button_to_activate = self.sort_by_date_added
                elif self.sort_field == "date_modified":
                    button_to_activate = self.sort_by_date_modified

                # Temporarily block signal connections to prevent grid reloading
                if button_to_activate:
                    button_to_activate.set_active(True)

                # Set the correct sort order button
                if self.ascending:
                    self.sort_ascending_button.set_active(True)
                else:
                    self.sort_descending_button.set_active(True)

    @Gtk.Template.Callback()
    def on_sort_by_toggled(self, button):
        """Called when sort field options are toggled"""
        if not button.get_active():
            # Skip when buttons are untoggled (we only care about active selections)
            return

        # Map buttons to sort fields
        if button == self.sort_by_title:
            self.sort_field = "title"
        elif button == self.sort_by_last_played:
            self.sort_field = "last_played"
        elif button == self.sort_by_play_time:
            self.sort_field = "play_time"
        elif button == self.sort_by_play_count:
            self.sort_field = "play_count"
        elif button == self.sort_by_date_added:
            self.sort_field = "date_added"
        elif button == self.sort_by_date_modified:
            self.sort_field = "date_modified"

        # Update sort
        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if window and window.controller:
            window.controller.title_bar_controller.update_sort(self.sort_field, self.ascending)


class TitleBarController:
    def __init__(self, main_controller):
        self.main_controller = main_controller
        self.search_entry = None

    def setup_search(self, search_entry):
        self.search_entry = search_entry

        # Set initial search text from settings
        saved_search = self.main_controller.settings_manager.get_search_text()
        if saved_search:
            search_entry.set_text(saved_search)

    def on_search_changed(self, search_entry):
        """Handle search entry text changes"""
        search_text = search_entry.get_text().strip().lower()
        print(f"Search text changed to: {search_text}")

        # Save search text to settings
        self.main_controller.settings_manager.set_search_text(search_text)

        # Get all active filters from sidebar controller if available
        filter_runners = None
        filter_completion_statuses = None
        filter_platforms = None
        filter_genres = None
        filter_age_ratings = None
        filter_features = None
        filter_regions = None

        if hasattr(self.main_controller, 'sidebar_controller') and self.main_controller.sidebar_controller:
            sidebar = self.main_controller.sidebar_controller
            filter_runners = sidebar.active_filters.get("runner")
            filter_completion_statuses = sidebar.active_filters.get("completion_status")
            filter_platforms = sidebar.active_filters.get("platforms")
            filter_genres = sidebar.active_filters.get("genres")
            filter_age_ratings = sidebar.active_filters.get("age_ratings")
            filter_features = sidebar.active_filters.get("features")
            filter_regions = sidebar.active_filters.get("regions")
        else:
            # Fall back to legacy filter if sidebar controller not available
            filter_runners = self.main_controller.current_filter

        # Update games grid directly without a full reload
        if hasattr(self.main_controller, 'game_grid_controller') and self.main_controller.game_grid_controller:
            self.main_controller.game_grid_controller.populate_games(
                filter_runners=filter_runners,
                filter_completion_statuses=filter_completion_statuses,
                filter_platforms=filter_platforms,
                filter_genres=filter_genres,
                filter_age_ratings=filter_age_ratings,
                filter_features=filter_features,
                filter_regions=filter_regions,
                search_text=search_text
            )

    def update_sort(self, sort_field: str, ascending: bool):
        """
        Update the sort parameters and refresh the game grid

        Args:
            sort_field: Field to sort by (title, last_played, etc.)
            ascending: True for ascending order, False for descending
        """
        # Only update and refresh if the sort parameters actually changed
        if sort_field != self.main_controller.sort_field or ascending != self.main_controller.sort_ascending:
            self.main_controller.sort_field = sort_field
            self.main_controller.sort_ascending = ascending

            # Save sort settings to persist across sessions
            self.main_controller.settings_manager.set_sort_settings(sort_field, ascending)

            # Get current search text
            search_text = ""
            if self.search_entry:
                search_text = self.search_entry.get_text().strip().lower()

            # Get all current filter settings directly from sidebar
            if hasattr(self.main_controller, 'game_grid_controller') and self.main_controller.game_grid_controller:
                self.main_controller.game_grid_controller.populate_games(search_text=search_text)
        # If sort parameters didn't change, do nothing to avoid unnecessary reloading

    # The populate_games method has been removed as it was redundant and unnecessary.
    # The game_grid_controller.populate_games method should be used directly instead.

    def on_visibility_toggle_clicked(self, button):
        """Handle visibility toggle button click"""
        # Toggle the show_hidden state
        show_hidden = not self.main_controller.show_hidden

        # Update the icon based on the new state
        if show_hidden:
            # When showing hidden games
            button.set_icon_name("view-reveal-symbolic")
            button.set_tooltip_text("Showing Hidden Games")
            button.add_css_class("destructive-action")  # Make the button red when showing hidden games
        else:
            # When showing normal games
            button.set_icon_name("view-conceal-symbolic")
            button.set_tooltip_text("Showing Normal Games")
            button.remove_css_class("destructive-action")  # Remove the red styling

        # Tell the controller to toggle visibility mode
        self.main_controller.toggle_show_hidden()
