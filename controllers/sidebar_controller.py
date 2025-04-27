import gi
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GdkPixbuf, Gdk, GObject, GLib
from data_handler import DataHandler, Game, Runner


def get_friendly_time(timestamp: float) -> str:
    """
    Convert a timestamp to a human-friendly relative time string.

    Args:
        timestamp: The timestamp to convert

    Returns:
        A string like "Just now", "Today", "Yesterday", "X days ago", etc.
    """
    now = datetime.now()
    dt = datetime.fromtimestamp(timestamp)

    # Calculate the difference
    diff = now - dt

    # Just now (within last hour)
    if diff < timedelta(hours=1):
        if diff < timedelta(minutes=1):
            return "Just now"
        elif diff < timedelta(minutes=2):
            return "1 minute ago"
        else:
            return f"{int(diff.total_seconds() / 60)} minutes ago"

    # Today
    if dt.date() == now.date():
        return "Today"

    # Yesterday
    if dt.date() == (now - timedelta(days=1)).date():
        return "Yesterday"

    # Within a week
    if diff < timedelta(days=7):
        return f"{diff.days} days ago"

    # Within a month
    if diff < timedelta(days=30):
        weeks = diff.days // 7
        if weeks == 1:
            return "1 week ago"
        return f"{weeks} weeks ago"

    # Within a year
    if diff < timedelta(days=365):
        months = diff.days // 30
        if months == 1:
            return "1 month ago"
        return f"{months} months ago"

    # More than a year
    years = diff.days // 365
    if years == 1:
        return "1 year ago"
    return f"{years} years ago"


def format_play_time(seconds: int) -> str:
    """
    Format play time in seconds to a human-readable string.

    Args:
        seconds: The number of seconds of play time

    Returns:
        A formatted string like "2h 15m", "45m", "30s", etc.
    """
    if seconds < 60:
        return f"{seconds}s"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"

    hours = minutes // 60
    minutes = minutes % 60

    if minutes == 0:
        return f"{hours}h"
    else:
        return f"{hours}h {minutes}m"


def show_image_chooser_dialog(parent_window, callback, title="Select Image"):
    """
    Shows a file chooser dialog for selecting images.

    Args:
        parent_window: The parent window for the dialog
        callback: Function to call with the selected file path or None if canceled
        title: Optional title for the file chooser
    """
    dialog = Gtk.FileChooserDialog(
        title=title,
        action=Gtk.FileChooserAction.OPEN,
        transient_for=parent_window,
        modal=True
    )

    # Add buttons
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Select", Gtk.ResponseType.ACCEPT)

    # Add filters
    filter_images = Gtk.FileFilter()
    filter_images.set_name("Images")
    filter_images.add_mime_type("image/jpeg")
    filter_images.add_mime_type("image/png")
    dialog.add_filter(filter_images)

    def on_response(dialog, response):
        path = None
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                path = file.get_path()

        callback(path)
        dialog.destroy()

    dialog.connect("response", on_response)
    dialog.show()


class SidebarItem(GObject.GObject):
    name = GObject.Property(type=str)
    icon_name = GObject.Property(type=str)

    def __init__(self, name, icon_name="applications-games-symbolic"):
        super().__init__()
        self.name = name
        self.icon_name = icon_name


@Gtk.Template(filename=os.path.join(os.path.dirname(os.path.dirname(__file__)), "layout", "sidebar_row.ui"))
class SidebarRow(Gtk.Box):
    __gtype_name__ = "SidebarRow"
    label: Gtk.Label = Gtk.Template.Child()
    icon: Gtk.Image = Gtk.Template.Child()

    def set_icon_name(self, icon_name):
        self.icon.set_from_icon_name(icon_name)


class SidebarController:
    def __init__(self, main_controller):
        self.main_controller = main_controller
        self.sidebar_store = None
        self.sidebar_listview = None

    def setup_sidebar(self, sidebar_listview):
        print(f"Setting up sidebar with listview: {sidebar_listview}")
        self.sidebar_listview = sidebar_listview
        self.sidebar_store = Gio.ListStore(item_type=SidebarItem)

        # Add default items to the store
        self.sidebar_store.append(SidebarItem("Games", "view-grid-symbolic"))
        self.sidebar_store.append(SidebarItem("No Runner", "dialog-question-symbolic"))

        # Add runners to the store
        runners = self.main_controller.get_runners()
        if runners:
            for runner in runners:
                icon_name = self.main_controller.data_handler.get_runner_icon(runner.id)
                self.sidebar_store.append(SidebarItem(runner.id, icon_name))

        # Setup factory and selection model
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._setup_sidebar_item)
        factory.connect("bind", self._bind_sidebar_item)

        selection = Gtk.SingleSelection(model=self.sidebar_store)
        selection.set_autoselect(False)
        selection.connect("notify::selected", self._on_sidebar_selection)

        # Set the model and factory on the listview
        self.sidebar_listview.set_factory(factory)
        self.sidebar_listview.set_model(selection)

        # Select the first item
        if self.sidebar_store.get_n_items() > 0:
            selection.set_selected(0)

        print(f"Sidebar initialized with {self.sidebar_store.get_n_items()} items")

    def refresh_sidebar_runners(self):
        """Refresh the sidebar list with current runners"""
        if not self.sidebar_listview or not self.sidebar_store:
            print("Can't refresh sidebar - store or listview not initialized")
            return

        print("Refreshing sidebar runners...")

        # Get current selection model and selected index
        selection_model = self.sidebar_listview.get_model()
        if not selection_model:
            print("Selection model not found")
            return

        current_index = selection_model.get_selected()

        # Clear the store but keep 'Games' and 'No Runner' items
        while self.sidebar_store.get_n_items() > 2:
            self.sidebar_store.remove(2)

        # Add all runners
        runners = self.main_controller.get_runners()
        for runner in runners:
            icon_name = self.main_controller.data_handler.get_runner_icon(runner.id)
            self.sidebar_store.append(SidebarItem(runner.id, icon_name))

        print(f"Sidebar refreshed with {self.sidebar_store.get_n_items()} items")

        # Restore selection if possible
        if current_index >= 0 and current_index < self.sidebar_store.get_n_items():
            selection_model.set_selected(current_index)
        else:
            selection_model.set_selected(0)

    def _setup_sidebar_item(self, factory, list_item):
        try:
            sidebar_row = SidebarRow()
            list_item.set_child(sidebar_row)
        except Exception as e:
            print(f"Error setting up sidebar item: {e}")

    def _bind_sidebar_item(self, factory, list_item):
        try:
            row = list_item.get_child()
            item = list_item.get_item()

            if row and item:
                row.label.set_label(item.name.capitalize())
                row.set_icon_name(item.icon_name)
        except Exception as e:
            print(f"Error binding sidebar item: {e}")

    # Track the last selection to avoid infinite loops
    _last_selection = None

    def _on_sidebar_selection(self, selection, param):
        try:
            index = selection.get_selected()
            if index == -1 or index >= self.sidebar_store.get_n_items():
                return

            item = self.sidebar_store.get_item(index)
            if not item:
                return

            # Skip if we're already processing this selection
            current_selection = (index, item.name)
            if current_selection == self.__class__._last_selection:
                return

            self.__class__._last_selection = current_selection
            print(f"Sidebar selection changed to: {item.name}")

            # Get the window from the controller
            window = self.main_controller.window

            # Clear search text if any
            if window and hasattr(window, 'search_entry'):
                if window.search_entry.get_text():
                    window.search_entry.set_text("")

            # Update filter based on selection
            filter_value = None
            if item.name == "Games":
                filter_value = None
            elif item.name == "No Runner":
                filter_value = ""
            else:
                filter_value = item.name

            # Only update if filter changed
            if self.main_controller.current_filter != filter_value:
                self.main_controller.current_filter = filter_value

                # Update grid without full reload
                if hasattr(self.main_controller, 'game_grid_controller') and self.main_controller.game_grid_controller:
                    print(f"Filtering games by: {filter_value}")
                    self.main_controller.game_grid_controller.populate_games(filter_runner=filter_value)
        except Exception as e:
            print(f"Error in sidebar selection handler: {e}")