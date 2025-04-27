import os
from typing import Optional

from gi.repository import Gtk


@Gtk.Template(filename=os.path.join(os.path.dirname(os.path.dirname(__file__)), "layout", "sort_menu.ui"))
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
        # Sort order and field will be set by handlers
        self.ascending = True
        self.sort_field = "title"

    @Gtk.Template.Callback()
    def on_sort_order_toggled(self, button):
        """Called when sort order buttons are toggled"""
        if button == self.sort_ascending_button and button.get_active():
            self.ascending = True
        elif button == self.sort_descending_button and button.get_active():
            self.ascending = False

        # Update sort
        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if window and window.controller:
            window.controller.title_bar_controller.update_sort(self.sort_field, self.ascending)

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

    def on_search_changed(self, search_entry):
        """Handle search entry text changes"""
        search_text = search_entry.get_text().strip().lower()
        print(f"Search text changed to: {search_text}")

        # Update games grid directly without a full reload
        if hasattr(self.main_controller, 'game_grid_controller') and self.main_controller.game_grid_controller:
            self.main_controller.game_grid_controller.populate_games(
                filter_runner=self.main_controller.current_filter,
                search_text=search_text
            )

    def update_sort(self, sort_field: str, ascending: bool):
        """
        Update the sort parameters and refresh the game grid

        Args:
            sort_field: Field to sort by (title, last_played, etc.)
            ascending: True for ascending order, False for descending
        """
        self.main_controller.sort_field = sort_field
        self.main_controller.sort_ascending = ascending

        # Reload games with current filters and new sort
        search_text = ""
        if self.search_entry:
            search_text = self.search_entry.get_text().strip().lower()

        self.populate_games(filter_runner=self.main_controller.current_filter, search_text=search_text)

    def populate_games(self, filter_runner: Optional[str] = None, search_text: str = ""):
        # Delegate to the grid controller to actually populate games
        if hasattr(self.main_controller, 'game_grid_controller') and self.main_controller.game_grid_controller:
            self.main_controller.game_grid_controller.populate_games(filter_runner=filter_runner, search_text=search_text)

    def on_visibility_toggle_clicked(self, button):
        """Handle visibility toggle button click"""
        # Update the icon based on toggle state
        if button.get_active():
            # When toggled on, we're showing hidden games
            button.set_icon_name("view-reveal-symbolic")
            button.set_tooltip_text("Showing Hidden Games")
            button.add_css_class("destructive-action")  # Make the button red when showing hidden games
        else:
            # When toggled off, we're showing normal games
            button.set_icon_name("view-conceal-symbolic")
            button.set_tooltip_text("Showing Normal Games")
            button.remove_css_class("destructive-action")  # Remove the red styling

        # Tell the controller to toggle visibility mode
        self.main_controller.toggle_show_hidden()