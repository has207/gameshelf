import gi
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GdkPixbuf, Gdk, GObject, GLib
from data_handler import DataHandler, Game, Runner, CompletionStatus
from controllers.common import get_template_path
from controllers.filter_controller import (
    FilterCategoryRow, FilterValueRow,
    CategoryItem, ValueItem,
    get_completion_status_icon
)


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


class SidebarItem(GObject.GObject):
    name = GObject.Property(type=str)
    icon_name = GObject.Property(type=str)

    def __init__(self, name, icon_name="applications-games-symbolic"):
        super().__init__()
        self.name = name
        self.icon_name = icon_name


@Gtk.Template(filename=get_template_path("sidebar_row.ui"))
class SidebarRow(Gtk.Box):
    __gtype_name__ = "SidebarRow"
    label: Gtk.Label = Gtk.Template.Child()
    icon: Gtk.Image = Gtk.Template.Child()

    def set_icon_name(self, icon_name):
        self.icon.set_from_icon_name(icon_name)


class SidebarController:
    def __init__(self, main_controller):
        self.main_controller = main_controller
        self.sidebar_container = None
        self.sidebar_box = None
        self.all_games_row = None
        self.filter_categories = {}  # Maps category_id to CategoryItem

        # Load active filters from settings
        self.active_filters = self.main_controller.settings_manager.get_sidebar_active_filters()

    def setup_sidebar(self, sidebar_container):
        print(f"Setting up sidebar with container: {sidebar_container}")
        self.sidebar_container = sidebar_container

        # Create a box container for all sidebar content
        self.sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.sidebar_box.set_margin_top(8)
        self.sidebar_box.set_margin_start(4)
        self.sidebar_box.set_margin_end(4)
        sidebar_container.set_child(self.sidebar_box)

        # Create the "All Games" row at the top
        self.all_games_row = self._create_all_games_row()
        self.sidebar_box.append(self.all_games_row)

        # Add filter sections
        self.add_filter_categories()

        # Populate the filter sections
        self.refresh_filters()

        print("Sidebar initialization complete")

    def _create_all_games_row(self):
        """Create the 'All Games' row that shows all games"""
        all_games_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        all_games_box.add_css_class("sidebar-row")

        # Add icon
        icon = Gtk.Image.new_from_icon_name("view-grid-symbolic")
        icon.set_icon_size(1)
        all_games_box.append(icon)

        # Add label
        label = Gtk.Label(label="All Games")
        label.set_xalign(0)
        label.set_hexpand(True)
        label.set_halign(Gtk.Align.START)
        label.add_css_class("sidebar-label")
        all_games_box.append(label)

        # Add click gesture
        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("released", self._on_all_games_clicked)
        all_games_box.add_controller(click_gesture)

        # Style the row as selected initially only if no active filters
        if not self.active_filters:
            all_games_box.add_css_class("selected-sidebar-item")

        return all_games_box

    def _on_all_games_clicked(self, gesture, n_press, x, y):
        """Handle clicks on the All Games row"""
        # If we already have no active filters, don't do anything
        if not self.active_filters:
            return

        print("Clearing all active filters")

        # Clear active filters
        self.active_filters = {}

        # Save to settings
        self.main_controller.settings_manager.set_sidebar_active_filters(self.active_filters)
        self.main_controller.settings_manager.save_settings()

        # Update UI to show this as selected
        self._update_selection_state(None)

        # Clear search text if any
        window = self.main_controller.window
        if window and hasattr(window, 'search_entry'):
            if window.search_entry.get_text():
                window.search_entry.set_text("")
                self.main_controller.settings_manager.set_search_text("")

        # Update grid without filter
        self.main_controller.current_filter = None
        self.main_controller.settings_manager.set_current_filter(None)

        if hasattr(self.main_controller, 'game_grid_controller') and self.main_controller.game_grid_controller:
            print("Showing all games")
            self.main_controller.game_grid_controller.populate_games(
                filter_runner=None,
                filter_completion_status=None
            )

    def add_filter_categories(self):
        """Add filter category sections to the sidebar"""
        # Get expanded states from settings
        expanded_categories = self.main_controller.settings_manager.get_sidebar_expanded_categories()
        print(f"Loaded expanded categories from settings: {expanded_categories}")

        # Runner category
        runner_category = CategoryItem(
            name="Runner",
            icon_name="applications-games-symbolic",
            category_id="runner",
            expanded=expanded_categories.get("runner", True)
        )
        self.filter_categories["runner"] = runner_category

        # Completion status category
        status_category = CategoryItem(
            name="Completion Status",
            icon_name="task-due-symbolic",
            category_id="completion_status",
            expanded=expanded_categories.get("completion_status", True)
        )
        self.filter_categories["completion_status"] = status_category

        # Create UI for categories
        for category_id, category_item in self.filter_categories.items():
            category_row = FilterCategoryRow(category_item, self._on_category_toggled)
            category_row.category_id = category_id  # Store reference for click handling

            # Explicitly set expanded state to match category_item.expanded
            category_row.set_expanded(category_item.expanded)

            self.sidebar_box.append(category_row)

    def _on_category_toggled(self, category_item):
        """Handle category expansion toggling and save to settings"""
        category_id = category_item.category_id
        print(f"Category {category_item.name} ({category_id}) toggled to {category_item.expanded}")

        # Check if this category has an active filter
        has_active_filter = category_id in self.active_filters and self.active_filters[category_id] is not None

        # If trying to collapse a category with an active filter, prevent it
        if has_active_filter and not category_item.expanded:
            print(f"Preventing collapse of category {category_id} because it has an active filter")

            # Find the category row and force it to stay expanded
            category_row = self._find_category_row(category_id)
            if category_row:
                category_row.set_expanded(True)

                # Flash the category header to indicate it can't be collapsed
                header_box = category_row.header_box

                # Add warning class
                header_box.add_css_class("filter-category-locked")

                # Remove the class after a short delay
                def remove_warning_class():
                    header_box.remove_css_class("filter-category-locked")
                    return False  # Don't repeat

                GLib.timeout_add(300, remove_warning_class)
                return

        # Get current expanded states
        expanded_categories = self.main_controller.settings_manager.get_sidebar_expanded_categories()
        print(f"Current expanded categories before update: {expanded_categories}")

        # Update the expanded state for this category
        expanded_categories[category_id] = category_item.expanded

        # Save to settings
        self.main_controller.settings_manager.set_sidebar_expanded_categories(expanded_categories)
        self.main_controller.settings_manager.save_settings()

        print(f"Updated expanded categories: {expanded_categories}")

    def refresh_filters(self):
        """Refresh all filter categories with current data"""
        print("Refreshing all filter categories")

        # Get all games for analysis
        games = self.main_controller.get_games()

        # Update runners filter
        self._refresh_runner_filters(games)

        # Update completion status filter
        self._refresh_completion_status_filters(games)

        # After creating filter rows, restore selections from active_filters
        self._restore_filter_selections()

    def _refresh_runner_filters(self, games: List[Game]):
        """Refresh the runner filter category with current data"""
        runner_category = self.filter_categories.get("runner")
        if not runner_category:
            return

        # Find the category row in the sidebar
        category_row = None
        child = self.sidebar_box.get_first_child()
        while child:
            if isinstance(child, FilterCategoryRow) and hasattr(child, 'category_id') and child.category_id == "runner":
                category_row = child
                break
            child = child.get_next_sibling()

        if not category_row:
            print("Runner category row not found")
            return

        # Clear existing value rows
        category_row.clear_values()

        # Count games by runner
        runner_counts = {}
        for game in games:
            runner_id = game.runner or ""
            runner_counts[runner_id] = runner_counts.get(runner_id, 0) + 1

        # Add "No Runner" option
        no_runner_item = ValueItem(
            name="No Runner",
            icon_name="dialog-question-symbolic",
            count=runner_counts.get("", 0),
            value_id="",
            parent_category="runner"
        )
        no_runner_row = FilterValueRow(no_runner_item)
        no_runner_row.value_id = ""
        no_runner_row.parent_category_id = "runner"

        # Add click handler
        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("released", self._on_filter_value_clicked, no_runner_row)
        no_runner_row.add_controller(click_gesture)

        category_row.add_value_row(no_runner_row)

        # Add rows for each runner
        runners = self.main_controller.get_runners()
        for runner in runners:
            # Skip if no games use this runner
            if runner.id not in runner_counts or runner_counts[runner.id] == 0:
                continue

            icon_name = self.main_controller.data_handler.get_runner_icon(runner.id)
            runner_item = ValueItem(
                name=runner.id.capitalize(),
                icon_name=icon_name,
                count=runner_counts.get(runner.id, 0),
                value_id=runner.id,
                parent_category="runner"
            )

            runner_row = FilterValueRow(runner_item)
            runner_row.value_id = runner.id
            runner_row.parent_category_id = "runner"

            # Add click handler
            click_gesture = Gtk.GestureClick.new()
            click_gesture.connect("released", self._on_filter_value_clicked, runner_row)
            runner_row.add_controller(click_gesture)

            category_row.add_value_row(runner_row)

    def _refresh_completion_status_filters(self, games: List[Game]):
        """Refresh the completion status filter category with current data"""
        status_category = self.filter_categories.get("completion_status")
        if not status_category:
            return

        # Find the category row in the sidebar
        category_row = None
        child = self.sidebar_box.get_first_child()
        while child:
            if isinstance(child, FilterCategoryRow) and hasattr(child, 'category_id') and child.category_id == "completion_status":
                category_row = child
                break
            child = child.get_next_sibling()

        if not category_row:
            print("Completion status category row not found")
            return

        # Clear existing value rows
        category_row.clear_values()

        # Count games by completion status
        status_counts = {}
        for game in games:
            status = game.completion_status
            status_key = status.name
            status_counts[status_key] = status_counts.get(status_key, 0) + 1

        # Add all status options
        for status in CompletionStatus:
            status_key = status.name
            icon_name = get_completion_status_icon(status)

            status_item = ValueItem(
                name=status.value,
                icon_name=icon_name,
                count=status_counts.get(status_key, 0),
                value_id=status_key,
                parent_category="completion_status"
            )

            status_row = FilterValueRow(status_item)
            status_row.value_id = status_key
            status_row.parent_category_id = "completion_status"

            # Add click handler
            click_gesture = Gtk.GestureClick.new()
            click_gesture.connect("released", self._on_filter_value_clicked, status_row)
            status_row.add_controller(click_gesture)

            category_row.add_value_row(status_row)

    def _on_filter_value_clicked(self, gesture, n_press, x, y, value_row):
        """Handle clicks on filter value rows"""
        if not hasattr(value_row, 'value_id') or not hasattr(value_row, 'parent_category_id'):
            return

        value_id = value_row.value_id
        category_id = value_row.parent_category_id

        # Store the filter selection
        self.active_filters[category_id] = value_id

        # Ensure the category is expanded when a filter is selected
        category_row = self._find_category_row(category_id)
        if category_row and not category_row.is_expanded():
            print(f"Auto-expanding category {category_id} because a filter was selected")
            category_row.set_expanded(True)

            # Also update the stored expanded states
            expanded_categories = self.main_controller.settings_manager.get_sidebar_expanded_categories()
            expanded_categories[category_id] = True
            self.main_controller.settings_manager.set_sidebar_expanded_categories(expanded_categories)

        # Save to settings
        self.main_controller.settings_manager.set_sidebar_active_filters(self.active_filters)
        self.main_controller.settings_manager.save_settings()

        # Update UI to show this item as selected
        self._update_selection_state(value_row)

        # Apply filters to the grid
        runner_filter = self.active_filters.get("runner")
        completion_status_filter = self.active_filters.get("completion_status")

        # Clear search text if any
        window = self.main_controller.window
        if window and hasattr(window, 'search_entry'):
            if window.search_entry.get_text():
                window.search_entry.set_text("")
                self.main_controller.settings_manager.set_search_text("")

        # Update grid with selected filters
        if hasattr(self.main_controller, 'game_grid_controller') and self.main_controller.game_grid_controller:
            print(f"Filtering by: runner={runner_filter}, completion_status={completion_status_filter}")
            self.main_controller.game_grid_controller.populate_games(
                filter_runner=runner_filter,
                filter_completion_status=completion_status_filter
            )

    def _update_selection_state(self, selected_row):
        """Update the UI to show the selected filter value"""
        # Clear selection from All Games row
        if self.all_games_row:
            if selected_row is None:
                self.all_games_row.add_css_class("selected-sidebar-item")
            else:
                self.all_games_row.remove_css_class("selected-sidebar-item")

        # Clear selection from all values
        for category_id, category_item in self.filter_categories.items():
            # Find category row
            category_row = None
            child = self.sidebar_box.get_first_child()
            while child:
                if isinstance(child, FilterCategoryRow) and hasattr(child, 'category_id') and child.category_id == category_id:
                    category_row = child
                    break
                child = child.get_next_sibling()

            if not category_row:
                continue

            # Check all filter value rows
            value_container = category_row.values_container
            child = value_container.get_first_child()
            while child:
                if hasattr(child, 'value_id'):
                    # Clear selection
                    child.remove_css_class("selected-sidebar-item")

                    # Set selected if this is the selected row
                    if child == selected_row:
                        child.add_css_class("selected-sidebar-item")
                child = child.get_next_sibling()

    def _restore_filter_selections(self):
        """Restore selected filter values from active_filters"""
        if not self.active_filters:
            # If no active filters, select "All Games"
            self._update_selection_state(None)
            return

        # For each category, find the selected value and update the UI
        for category_id, value_id in self.active_filters.items():
            category_row = self._find_category_row(category_id)
            if not category_row:
                continue

            # Find the value row in this category
            found_value_row = None
            child = category_row.values_container.get_first_child()
            while child:
                if hasattr(child, 'value_id') and hasattr(child, 'parent_category_id') and \
                   child.parent_category_id == category_id and child.value_id == value_id:
                    found_value_row = child
                    break
                child = child.get_next_sibling()

            if found_value_row:
                # Update UI to show this value as selected
                self._update_selection_state(found_value_row)

    def _find_category_row(self, category_id: str) -> Optional[FilterCategoryRow]:
        """Find a category row by its ID"""
        child = self.sidebar_box.get_first_child()
        while child:
            if isinstance(child, FilterCategoryRow) and hasattr(child, 'category_id') and child.category_id == category_id:
                return child
            child = child.get_next_sibling()
        return None

    def refresh_sidebar_runners(self):
        """Refresh runner filters with current data"""
        if not self.sidebar_container:
            print("Can't refresh sidebar - not initialized")
            return

        print("Refreshing sidebar runners...")

        # Get current games
        games = self.main_controller.get_games()

        # Update runner filters
        self._refresh_runner_filters(games)

        # Restore selected values
        self._restore_filter_selections()
