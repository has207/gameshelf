import gi
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set

# Set up logger
logger = logging.getLogger(__name__)

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GdkPixbuf, Gdk, GObject, GLib
from data_handler import DataHandler, Game, Runner
from data_mapping import CompletionStatus, Platforms, AgeRatings, Features, Genres, Regions
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
        # Structure will be {category_id: Set[value_id]} to support multiple selections per category
        self.active_filters = self.main_controller.settings_manager.get_sidebar_active_filters()

        # Convert old format (if needed)
        if self.active_filters and not all(isinstance(values, set) for values in self.active_filters.values()):
            converted_filters = {}
            for category, value in self.active_filters.items():
                if value is not None:
                    converted_filters[category] = {value}
            self.active_filters = converted_filters

    def setup_sidebar(self, sidebar_container):
        logger.debug(f"Setting up sidebar with container: {sidebar_container}")
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

        logger.debug("Sidebar initialization complete")

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

        # Store reference to the label for updating later
        all_games_box.label = label

        # Add click gesture
        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("released", self._on_all_games_clicked)
        all_games_box.add_controller(click_gesture)

        # Store reference to the all_games_row
        self.all_games_row = all_games_box

        # Update the label and styling based on active filters
        self._update_all_games_label()

        # Return the created box (which is already stored in self.all_games_row)
        return self.all_games_row

    def _update_all_games_label(self):
        """Update the All Games row label based on whether filters are active"""
        if not self.all_games_row:
            return

        # Check if any filters are active
        has_active_filters = bool(self.active_filters) and any(values for values in self.active_filters.values())

        # Change label to "Clear Filters" if any filters are active, otherwise "All Games"
        if has_active_filters:
            # Has active filters - show "Clear Filters"
            self.all_games_row.label.set_text("Clear Filters")
            # Change icon to match the clear action
            first_child = self.all_games_row.get_first_child()
            if first_child and isinstance(first_child, Gtk.Image):
                first_child.set_from_icon_name("edit-clear-all-symbolic")
            # Apply error styling
            self.all_games_row.remove_css_class("selected-sidebar-item")
            self.all_games_row.add_css_class("clear-filters-row")
        else:
            # No active filters - show "All Games"
            self.all_games_row.label.set_text("All Games")
            # Restore original icon
            first_child = self.all_games_row.get_first_child()
            if first_child and isinstance(first_child, Gtk.Image):
                first_child.set_from_icon_name("view-grid-symbolic")
            # Apply normal selected styling
            self.all_games_row.add_css_class("selected-sidebar-item")
            self.all_games_row.remove_css_class("clear-filters-row")

    def _on_all_games_clicked(self, gesture, n_press, x, y):
        """Handle clicks on the All Games row"""
        # Check if any filters are active
        has_active_filters = bool(self.active_filters) and any(values for values in self.active_filters.values())

        # If we already have no active filters, don't do anything
        if not has_active_filters:
            return

        logger.debug("Clearing all active filters")

        # Clear active filters
        self.active_filters = {}

        # Save to settings
        self.main_controller.settings_manager.set_sidebar_active_filters(self.active_filters)
        self.main_controller.settings_manager.save_settings()

        # Update UI to show this as selected
        self._update_selection_state()

        # Update "All Games" row text
        self._update_all_games_label()

        # When clicking the "All Games/Clear Filters" row, we also clear search text
        if hasattr(self.main_controller, 'game_grid_controller') and self.main_controller.game_grid_controller:
            logger.debug("Showing all games - filters cleared")

            # Clear search text in UI and settings
            window = self.main_controller.window
            if window and hasattr(window, 'search_entry'):
                if window.search_entry.get_text():
                    window.search_entry.set_text("")
                    self.main_controller.settings_manager.set_search_text("")

            # Refresh grid with no filters
            self.main_controller.game_grid_controller.populate_games(search_text="")

    def add_filter_categories(self):
        """Add filter category sections to the sidebar"""
        # Get expanded states from settings
        expanded_categories = self.main_controller.settings_manager.get_sidebar_expanded_categories()
        logger.debug(f"Loaded expanded categories from settings: {expanded_categories}")

        # Create all categories - define them in alphabetical order

        # Age Rating category
        age_rating_category = CategoryItem(
            name="Age Ratings",
            icon_name="security-high-symbolic",
            category_id="age_ratings",
            expanded=expanded_categories.get("age_ratings", False)
        )
        self.filter_categories["age_ratings"] = age_rating_category

        # Completion status category
        status_category = CategoryItem(
            name="Completion Status",
            icon_name="task-due-symbolic",
            category_id="completion_status",
            expanded=expanded_categories.get("completion_status", True)
        )
        self.filter_categories["completion_status"] = status_category

        # Feature category
        feature_category = CategoryItem(
            name="Features",
            icon_name="preferences-system-symbolic",
            category_id="features",
            expanded=expanded_categories.get("features", False)
        )
        self.filter_categories["features"] = feature_category

        # Genre category
        genre_category = CategoryItem(
            name="Genres",
            icon_name="view-grid-symbolic",
            category_id="genres",
            expanded=expanded_categories.get("genres", False)
        )
        self.filter_categories["genres"] = genre_category

        # Platform category
        platform_category = CategoryItem(
            name="Platforms",
            icon_name="computer-symbolic",
            category_id="platforms",
            expanded=expanded_categories.get("platforms", False)
        )
        self.filter_categories["platforms"] = platform_category

        # Region category
        region_category = CategoryItem(
            name="Regions",
            icon_name="globe-symbolic",
            category_id="regions",
            expanded=expanded_categories.get("regions", False)
        )
        self.filter_categories["regions"] = region_category

        # Source category
        source_category = CategoryItem(
            name="Sources",
            icon_name="drive-harddisk-symbolic",
            category_id="sources",
            expanded=expanded_categories.get("sources", False)
        )
        self.filter_categories["sources"] = source_category

        # Create an ordered list of categories based on display name
        sorted_categories = sorted(
            [(category_id, category) for category_id, category in self.filter_categories.items()],
            key=lambda x: x[1].name.lower()
        )

        # Create UI for categories in alphabetical order
        for category_id, category_item in sorted_categories:
            category_row = FilterCategoryRow(category_item, self._on_category_toggled)
            category_row.category_id = category_id  # Store reference for click handling

            # Explicitly set expanded state to match category_item.expanded
            category_row.set_expanded(category_item.expanded)

            self.sidebar_box.append(category_row)

    def _on_category_toggled(self, category_item):
        """Handle category expansion toggling and save to settings"""
        category_id = category_item.category_id
        logger.debug(f"Category {category_item.name} ({category_id}) toggled to {category_item.expanded}")

        # Check if this category has active filters
        has_active_filters = (category_id in self.active_filters and
                             self.active_filters.get(category_id))

        # If trying to collapse a category with active filters, prevent it
        if has_active_filters and not category_item.expanded:
            logger.debug(f"Preventing collapse of category {category_id} because it has active filters")

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
        logger.debug(f"Current expanded categories before update: {expanded_categories}")

        # Update the expanded state for this category
        expanded_categories[category_id] = category_item.expanded

        # Save to settings
        self.main_controller.settings_manager.set_sidebar_expanded_categories(expanded_categories)
        self.main_controller.settings_manager.save_settings()

        logger.debug(f"Updated expanded categories: {expanded_categories}")

    def refresh_filters(self):
        """Refresh all filter categories with current data"""
        logger.debug("Refreshing all filter categories")

        # Get all games for analysis
        games = self.main_controller.get_games()

        # Runner filters are no longer used - we now use platforms instead

        # Update completion status filter
        self._refresh_completion_status_filters(games)

        # Update platform filter
        self._refresh_platforms_filters(games)

        # Update genre filter
        self._refresh_genres_filters(games)

        # Update age rating filter
        self._refresh_age_ratings_filters(games)

        # Update feature filter
        self._refresh_features_filters(games)

        # Update region filter
        self._refresh_regions_filters(games)

        # Update source filter
        self._refresh_sources_filters(games)

        # After creating filter rows, restore selections from active_filters
        self._restore_filter_selections()

    def _refresh_runner_filters(self, games: List[Game]):
        """Refresh the runner filter category with current data - now deprecated"""
        # This method is intentionally empty since runners have been replaced by platform-based filtering
        return

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
            logger.warning("Completion status category row not found")
            return

        # Clear existing value rows
        category_row.clear_values()

        # Count games by completion status
        status_counts = {}
        for game in games:
            status = game.completion_status
            status_key = status.name
            status_counts[status_key] = status_counts.get(status_key, 0) + 1

        # Create a list to hold rows for sorting
        status_rows = []

        # Add status options with games or if they're already selected
        for status in CompletionStatus:
            status_key = status.name
            status_count = status_counts.get(status_key, 0)

            # Check if this status is currently selected
            is_selected = (
                "completion_status" in self.active_filters and
                status_key in self.active_filters.get("completion_status", set())
            )

            # Skip statuses with no games unless they're already selected
            if status_count == 0 and not is_selected:
                continue

            icon_name = get_completion_status_icon(status)

            status_item = ValueItem(
                name=status.value,
                icon_name=icon_name,
                count=status_count,
                value_id=status_key,
                parent_category="completion_status"
            )

            status_row = FilterValueRow(status_item)
            status_row.value_id = status_key
            status_row.parent_category_id = "completion_status"
            status_row.sort_key = status.value.lower()  # For alphabetical sorting

            # Add left-click handler
            left_click = Gtk.GestureClick.new()
            left_click.set_button(1)  # Left button
            left_click.connect("released", self._on_filter_value_clicked, status_row, False)
            status_row.add_controller(left_click)

            # Add right-click handler for multi-select
            right_click = Gtk.GestureClick.new()
            right_click.set_button(3)  # Right button
            right_click.connect("released", self._on_filter_value_clicked, status_row, True)
            status_row.add_controller(right_click)

            status_rows.append(status_row)

        # Sort rows alphabetically and add them to the UI
        sorted_rows = sorted(status_rows, key=lambda row: row.sort_key)
        for row in sorted_rows:
            category_row.add_value_row(row)

    def _on_filter_value_clicked(self, gesture, n_press, x, y, value_row, multi_select=False):
        """Handle clicks on filter value rows with toggle behavior

        Args:
            gesture: The gesture that triggered this callback
            n_press: Number of presses (clicks)
            x: X coordinate of click
            y: Y coordinate of click
            value_row: The filter value row that was clicked
            multi_select: If True, preserves other selections (right-click behavior)
        """
        if not hasattr(value_row, 'value_id') or not hasattr(value_row, 'parent_category_id'):
            return

        value_id = value_row.value_id
        category_id = value_row.parent_category_id

        # Initialize the category's filter set if it doesn't exist
        if category_id not in self.active_filters:
            self.active_filters[category_id] = set()

        # Toggle behavior: If this value is already selected, deselect it
        if value_id in self.active_filters.get(category_id, set()):
            logger.debug(f"Toggling off filter {category_id}={value_id}")
            # Remove this value from the filter set
            self.active_filters[category_id].remove(value_id)

            # If the category has no more filters, remove it from active_filters
            if not self.active_filters[category_id]:
                self.active_filters.pop(category_id)
        else:
            # If not multi-select (left click), clear existing filters for this category
            if not multi_select and category_id in self.active_filters:
                self.active_filters[category_id].clear()

            # Add the new filter value
            logger.debug(f"Adding filter {category_id}={value_id}")
            if category_id not in self.active_filters:
                self.active_filters[category_id] = set()
            self.active_filters[category_id].add(value_id)

            # Ensure the category is expanded when a filter is selected
            category_row = self._find_category_row(category_id)
            if category_row and not category_row.is_expanded():
                logger.debug(f"Auto-expanding category {category_id} because a filter was selected")
                category_row.set_expanded(True)

                # Also update the stored expanded states
                expanded_categories = self.main_controller.settings_manager.get_sidebar_expanded_categories()
                expanded_categories[category_id] = True
                self.main_controller.settings_manager.set_sidebar_expanded_categories(expanded_categories)

        # Save to settings
        self.main_controller.settings_manager.set_sidebar_active_filters(self.active_filters)
        self.main_controller.settings_manager.save_settings()

        # Update UI to show the correct items as selected
        self._update_selection_state()

        # Update "All Games" row text based on whether filters are active
        self._update_all_games_label()

        # Get current search text if any
        search_text = ""
        if hasattr(self.main_controller, 'get_search_text'):
            search_text = self.main_controller.get_search_text()
        else:
            # Fallback if get_search_text not implemented
            window = self.main_controller.window
            if window and hasattr(window, 'search_entry'):
                search_text = window.search_entry.get_text()

        # Update grid with filters from sidebar controller
        if hasattr(self.main_controller, 'game_grid_controller') and self.main_controller.game_grid_controller:
            logger.debug(f"Applying filters: {self.active_filters}")
            # Just pass the search text - the grid controller will get filters from this controller
            self.main_controller.game_grid_controller.populate_games(search_text=search_text)

    def _update_selection_state(self):
        """Update the UI to show all selected filter values"""
        # Check if any filters are active
        has_active_filters = bool(self.active_filters) and any(values for values in self.active_filters.values())

        # Handle All Games row selection state
        if self.all_games_row:
            if not has_active_filters:
                self.all_games_row.add_css_class("selected-sidebar-item")
            else:
                self.all_games_row.remove_css_class("selected-sidebar-item")

        # Update selection state for all filter values
        for category_id, category_item in self.filter_categories.items():
            # Find category row
            category_row = self._find_category_row(category_id)
            if not category_row:
                continue

            # Get selected values for this category
            selected_values = self.active_filters.get(category_id, set())

            # Update each value row in this category
            value_container = category_row.values_container
            child = value_container.get_first_child()
            while child:
                if hasattr(child, 'value_id'):
                    # Clear selection first
                    child.remove_css_class("selected-sidebar-item")

                    # Add selection class if this value is selected
                    if child.value_id in selected_values:
                        child.add_css_class("selected-sidebar-item")

                child = child.get_next_sibling()

    def _restore_filter_selections(self):
        """Restore selected filter values from active_filters"""
        # Check if any filters are active
        has_active_filters = bool(self.active_filters) and any(values for values in self.active_filters.values())

        # Update selection state
        self._update_selection_state()

        if not has_active_filters:
            # If no active filters, nothing more to do
            return

        # All selection state is handled by _update_selection_state

    def _find_category_row(self, category_id: str) -> Optional[FilterCategoryRow]:
        """Find a category row by its ID"""
        child = self.sidebar_box.get_first_child()
        while child:
            if isinstance(child, FilterCategoryRow) and hasattr(child, 'category_id') and child.category_id == category_id:
                return child
            child = child.get_next_sibling()
        return None

    def _refresh_platforms_filters(self, games: List[Game]):
        """Refresh the platforms filter category with current data"""
        platform_category = self.filter_categories.get("platforms")
        if not platform_category:
            return

        # Find the category row in the sidebar
        category_row = self._find_category_row("platforms")
        if not category_row:
            logger.warning("Platforms category row not found")
            return

        # Clear existing value rows
        category_row.clear_values()

        # Count games by platform
        platform_counts = {}
        for game in games:
            for platform in game.platforms:
                platform_key = platform.name
                platform_counts[platform_key] = platform_counts.get(platform_key, 0) + 1

        # Create a list to hold rows for sorting
        platform_rows = []

        # Add rows for each platform that has games
        for platform in Platforms:
            platform_key = platform.name
            platform_count = platform_counts.get(platform_key, 0)

            # Check if this platform is currently selected
            is_selected = (
                "platforms" in self.active_filters and
                platform_key in self.active_filters.get("platforms", set())
            )

            # Skip platforms with no games unless they're already selected
            if platform_count == 0 and not is_selected:
                continue

            platform_item = ValueItem(
                name=platform.value,
                icon_name="computer-symbolic",
                count=platform_count,
                value_id=platform_key,
                parent_category="platforms"
            )

            platform_row = FilterValueRow(platform_item)
            platform_row.value_id = platform_key
            platform_row.parent_category_id = "platforms"
            platform_row.sort_key = platform.value.lower()  # For alphabetical sorting

            # Add left-click handler
            left_click = Gtk.GestureClick.new()
            left_click.set_button(1)  # Left button
            left_click.connect("released", self._on_filter_value_clicked, platform_row, False)
            platform_row.add_controller(left_click)

            # Add right-click handler for multi-select
            right_click = Gtk.GestureClick.new()
            right_click.set_button(3)  # Right button
            right_click.connect("released", self._on_filter_value_clicked, platform_row, True)
            platform_row.add_controller(right_click)

            platform_rows.append(platform_row)

        # Sort rows alphabetically and add them to the UI
        sorted_rows = sorted(platform_rows, key=lambda row: row.sort_key)
        for row in sorted_rows:
            category_row.add_value_row(row)

    def _refresh_genres_filters(self, games: List[Game]):
        """Refresh the genres filter category with current data"""
        genre_category = self.filter_categories.get("genres")
        if not genre_category:
            return

        # Find the category row in the sidebar
        category_row = self._find_category_row("genres")
        if not category_row:
            logger.warning("Genres category row not found")
            return

        # Clear existing value rows
        category_row.clear_values()

        # Count games by genre
        genre_counts = {}
        for game in games:
            for genre in game.genres:
                genre_key = genre.name
                genre_counts[genre_key] = genre_counts.get(genre_key, 0) + 1

        # Create a list to hold rows for sorting
        genre_rows = []

        # Add rows for each genre that has games
        for genre in Genres:
            genre_key = genre.name
            genre_count = genre_counts.get(genre_key, 0)

            # Check if this genre is currently selected
            is_selected = (
                "genres" in self.active_filters and
                genre_key in self.active_filters.get("genres", set())
            )

            # Skip genres with no games unless they're already selected
            if genre_count == 0 and not is_selected:
                continue

            genre_item = ValueItem(
                name=genre.value,
                icon_name="view-grid-symbolic",
                count=genre_count,
                value_id=genre_key,
                parent_category="genres"
            )

            genre_row = FilterValueRow(genre_item)
            genre_row.value_id = genre_key
            genre_row.parent_category_id = "genres"
            genre_row.sort_key = genre.value.lower()  # For alphabetical sorting

            # Add left-click handler
            left_click = Gtk.GestureClick.new()
            left_click.set_button(1)  # Left button
            left_click.connect("released", self._on_filter_value_clicked, genre_row, False)
            genre_row.add_controller(left_click)

            # Add right-click handler for multi-select
            right_click = Gtk.GestureClick.new()
            right_click.set_button(3)  # Right button
            right_click.connect("released", self._on_filter_value_clicked, genre_row, True)
            genre_row.add_controller(right_click)

            genre_rows.append(genre_row)

        # Sort rows alphabetically and add them to the UI
        sorted_rows = sorted(genre_rows, key=lambda row: row.sort_key)
        for row in sorted_rows:
            category_row.add_value_row(row)

    def _refresh_age_ratings_filters(self, games: List[Game]):
        """Refresh the age ratings filter category with current data"""
        age_rating_category = self.filter_categories.get("age_ratings")
        if not age_rating_category:
            return

        # Find the category row in the sidebar
        category_row = self._find_category_row("age_ratings")
        if not category_row:
            logger.warning("Age ratings category row not found")
            return

        # Clear existing value rows
        category_row.clear_values()

        # Count games by age rating
        age_rating_counts = {}
        for game in games:
            for rating in game.age_ratings:
                rating_key = rating.name
                age_rating_counts[rating_key] = age_rating_counts.get(rating_key, 0) + 1

        # Create a list to hold rows for sorting
        rating_rows = []

        # Add rows for each age rating that has games
        for rating in AgeRatings:
            rating_key = rating.name
            rating_count = age_rating_counts.get(rating_key, 0)

            # Check if this rating is currently selected
            is_selected = (
                "age_ratings" in self.active_filters and
                rating_key in self.active_filters.get("age_ratings", set())
            )

            # Skip ratings with no games unless they're already selected
            if rating_count == 0 and not is_selected:
                continue

            rating_item = ValueItem(
                name=rating.value,
                icon_name="security-high-symbolic",
                count=rating_count,
                value_id=rating_key,
                parent_category="age_ratings"
            )

            rating_row = FilterValueRow(rating_item)
            rating_row.value_id = rating_key
            rating_row.parent_category_id = "age_ratings"
            rating_row.sort_key = rating.value.lower()  # For alphabetical sorting

            # Add left-click handler
            left_click = Gtk.GestureClick.new()
            left_click.set_button(1)  # Left button
            left_click.connect("released", self._on_filter_value_clicked, rating_row, False)
            rating_row.add_controller(left_click)

            # Add right-click handler for multi-select
            right_click = Gtk.GestureClick.new()
            right_click.set_button(3)  # Right button
            right_click.connect("released", self._on_filter_value_clicked, rating_row, True)
            rating_row.add_controller(right_click)

            rating_rows.append(rating_row)

        # Sort rows alphabetically and add them to the UI
        sorted_rows = sorted(rating_rows, key=lambda row: row.sort_key)
        for row in sorted_rows:
            category_row.add_value_row(row)

    def _refresh_features_filters(self, games: List[Game]):
        """Refresh the features filter category with current data"""
        feature_category = self.filter_categories.get("features")
        if not feature_category:
            return

        # Find the category row in the sidebar
        category_row = self._find_category_row("features")
        if not category_row:
            logger.warning("Features category row not found")
            return

        # Clear existing value rows
        category_row.clear_values()

        # Count games by feature
        feature_counts = {}
        for game in games:
            for feature in game.features:
                feature_key = feature.name
                feature_counts[feature_key] = feature_counts.get(feature_key, 0) + 1

        # Create a list to hold rows for sorting
        feature_rows = []

        # Add rows for each feature that has games
        for feature in Features:
            feature_key = feature.name
            feature_count = feature_counts.get(feature_key, 0)

            # Check if this feature is currently selected
            is_selected = (
                "features" in self.active_filters and
                feature_key in self.active_filters.get("features", set())
            )

            # Skip features with no games unless they're already selected
            if feature_count == 0 and not is_selected:
                continue

            feature_item = ValueItem(
                name=feature.value,
                icon_name="preferences-system-symbolic",
                count=feature_count,
                value_id=feature_key,
                parent_category="features"
            )

            feature_row = FilterValueRow(feature_item)
            feature_row.value_id = feature_key
            feature_row.parent_category_id = "features"
            feature_row.sort_key = feature.value.lower()  # For alphabetical sorting

            # Add left-click handler
            left_click = Gtk.GestureClick.new()
            left_click.set_button(1)  # Left button
            left_click.connect("released", self._on_filter_value_clicked, feature_row, False)
            feature_row.add_controller(left_click)

            # Add right-click handler for multi-select
            right_click = Gtk.GestureClick.new()
            right_click.set_button(3)  # Right button
            right_click.connect("released", self._on_filter_value_clicked, feature_row, True)
            feature_row.add_controller(right_click)

            feature_rows.append(feature_row)

        # Sort rows alphabetically and add them to the UI
        sorted_rows = sorted(feature_rows, key=lambda row: row.sort_key)
        for row in sorted_rows:
            category_row.add_value_row(row)

    def _refresh_regions_filters(self, games: List[Game]):
        """Refresh the regions filter category with current data"""
        region_category = self.filter_categories.get("regions")
        if not region_category:
            return

        # Find the category row in the sidebar
        category_row = self._find_category_row("regions")
        if not category_row:
            logger.warning("Regions category row not found")
            return

        # Clear existing value rows
        category_row.clear_values()

        # Count games by region
        region_counts = {}
        for game in games:
            for region in game.regions:
                region_key = region.name
                region_counts[region_key] = region_counts.get(region_key, 0) + 1

        # Create a list to hold rows for sorting
        region_rows = []

        # Add rows for each region that has games
        for region in Regions:
            region_key = region.name
            region_count = region_counts.get(region_key, 0)

            # Check if this region is currently selected
            is_selected = (
                "regions" in self.active_filters and
                region_key in self.active_filters.get("regions", set())
            )

            # Skip regions with no games unless they're already selected
            if region_count == 0 and not is_selected:
                continue

            region_item = ValueItem(
                name=region.value,
                icon_name="globe-symbolic",
                count=region_count,
                value_id=region_key,
                parent_category="regions"
            )

            region_row = FilterValueRow(region_item)
            region_row.value_id = region_key
            region_row.parent_category_id = "regions"
            region_row.sort_key = region.value.lower()  # For alphabetical sorting

            # Add left-click handler
            left_click = Gtk.GestureClick.new()
            left_click.set_button(1)  # Left button
            left_click.connect("released", self._on_filter_value_clicked, region_row, False)
            region_row.add_controller(left_click)

            # Add right-click handler for multi-select
            right_click = Gtk.GestureClick.new()
            right_click.set_button(3)  # Right button
            right_click.connect("released", self._on_filter_value_clicked, region_row, True)
            region_row.add_controller(right_click)

            region_rows.append(region_row)

        # Sort rows alphabetically and add them to the UI
        sorted_rows = sorted(region_rows, key=lambda row: row.sort_key)
        for row in sorted_rows:
            category_row.add_value_row(row)

    def _refresh_sources_filters(self, games: List[Game]):
        """Refresh the sources filter category with current data"""
        source_category = self.filter_categories.get("sources")
        if not source_category:
            return

        # Find the category row in the sidebar
        category_row = self._find_category_row("sources")
        if not category_row:
            logger.warning("Sources category row not found")
            return

        # Clear existing value rows
        category_row.clear_values()

        # Create a list to hold all rows so we can sort them before adding
        all_source_rows = []

        # Get the current show_hidden setting
        show_hidden = hasattr(self.main_controller, 'show_hidden') and self.main_controller.show_hidden

        # Simple count by source (will only include sources with matching games)
        source_counts = {}

        # Count games by source, respecting the hidden/visible setting
        for game in games:
            # Skip games that don't match the hidden filter
            if show_hidden and not game.hidden:
                continue
            if not show_hidden and game.hidden:
                continue

            source = game.source or ""
            source_counts[source] = source_counts.get(source, 0) + 1

        # Debug output
        logger.debug(f"Source counts (show_hidden={show_hidden}): {source_counts}")

        # Add "No Source" option if there are games with no source or if it's already selected
        no_source_count = source_counts.get("", 0)
        is_selected = (
            "sources" in self.active_filters and
            "" in self.active_filters.get("sources", set())
        )

        # The counts are now pre-filtered based on the hidden/visible setting
        logger.debug(f"No Source count: {no_source_count}")

        if no_source_count > 0 or is_selected:
            no_source_item = ValueItem(
                name="No Source",
                icon_name="dialog-question-symbolic",
                count=no_source_count,
                value_id="",
                parent_category="sources"
            )
            no_source_row = FilterValueRow(no_source_item)
            no_source_row.value_id = ""
            no_source_row.parent_category_id = "sources"

            # Add left-click handler
            left_click = Gtk.GestureClick.new()
            left_click.set_button(1)  # Left button
            left_click.connect("released", self._on_filter_value_clicked, no_source_row, False)
            no_source_row.add_controller(left_click)

            # Add right-click handler for multi-select
            right_click = Gtk.GestureClick.new()
            right_click.set_button(3)  # Right button
            right_click.connect("released", self._on_filter_value_clicked, no_source_row, True)
            no_source_row.add_controller(right_click)

            # Add to our list of rows - "No Source" gets a special sort key to always be first
            no_source_row.sort_key = "0"  # This will sort before any alphabetical key
            all_source_rows.append(no_source_row)

        # Get all sources
        sources = self.main_controller.get_sources() if hasattr(self.main_controller, 'get_sources') else []

        # If we don't have a get_sources method, extract unique sources from games
        if not sources:
            # Get source IDs directly from games
            source_ids = set(game.source for game in games if game.source)

            # Sort the source IDs alphabetically
            sorted_source_ids = sorted(source_ids)

            # Create simple Source-like objects
            for source_id in sorted_source_ids:
                # Add rows for each source that has games
                # Check if this source is currently selected
                is_selected = (
                    "sources" in self.active_filters and
                    source_id in self.active_filters.get("sources", set())
                )

                # Debug output
                logger.debug(f"Processing source ID: '{source_id}', count: {source_counts.get(source_id, 0)}, selected: {is_selected}")

                # Get actual game count considering hidden games
                source_count = source_counts.get(source_id, 0)

                # The counts are already filtered by the hidden/visible setting
                logger.debug(f"Source '{source_id}' count: {source_count}")

                # Skip sources with no games unless they're already selected
                if source_count == 0 and not is_selected:
                    logger.debug(f"Skipping source ID '{source_id}' with no games and not selected")
                    continue

                # Get a more friendly name for the source if it's a numeric ID
                source_name = source_id
                if source_id.isdigit():
                    # Try to get source name from the main controller's data handler
                    if hasattr(self.main_controller, 'data_handler'):
                        source_obj = self.main_controller.data_handler.get_source_by_id(source_id)
                        if source_obj and hasattr(source_obj, 'name'):
                            source_name = source_obj.name
                        else:
                            # Use a default if we couldn't find the name
                            source_name = f"Source {source_id}"
                else:
                    # Just capitalize the source ID if it's not numeric
                    source_name = source_id.capitalize()

                # Use the count that already respects the hidden/visible mode
                source_item = ValueItem(
                    name=source_name,
                    icon_name="drive-harddisk-symbolic",
                    count=source_count,
                    value_id=source_id,
                    parent_category="sources"
                )

                source_row = FilterValueRow(source_item)
                source_row.value_id = source_id
                source_row.parent_category_id = "sources"

                # Add left-click handler
                left_click = Gtk.GestureClick.new()
                left_click.set_button(1)  # Left button
                left_click.connect("released", self._on_filter_value_clicked, source_row, False)
                source_row.add_controller(left_click)

                # Add right-click handler for multi-select
                right_click = Gtk.GestureClick.new()
                right_click.set_button(3)  # Right button
                right_click.connect("released", self._on_filter_value_clicked, source_row, True)
                source_row.add_controller(right_click)

                # Set a sort key based on the source name (for text-based sources)
                source_row.sort_key = source_name.lower()  # Use lowercase for case-insensitive sorting
                all_source_rows.append(source_row)
        else:
            # Sort sources by name
            sorted_sources = sorted(sources, key=lambda src: src.name)

            # Add rows for each source
            for source in sorted_sources:
                # Check if this source is currently selected
                is_selected = (
                    "sources" in self.active_filters and
                    source.id in self.active_filters.get("sources", set())
                )

                # Skip sources with no games unless they're already selected
                source_count = source_counts.get(source.id, 0)
                if source_count == 0 and not is_selected:
                    continue

                source_item = ValueItem(
                    name=source.name,
                    icon_name="drive-harddisk-symbolic",
                    count=source_count,
                    value_id=source.id,
                    parent_category="sources"
                )

                source_row = FilterValueRow(source_item)
                source_row.value_id = source.id
                source_row.parent_category_id = "sources"

                # Add left-click handler
                left_click = Gtk.GestureClick.new()
                left_click.set_button(1)  # Left button
                left_click.connect("released", self._on_filter_value_clicked, source_row, False)
                source_row.add_controller(left_click)

                # Add right-click handler for multi-select
                right_click = Gtk.GestureClick.new()
                right_click.set_button(3)  # Right button
                right_click.connect("released", self._on_filter_value_clicked, source_row, True)
                source_row.add_controller(right_click)

                # Set a sort key based on the source name (for text-based sources)
                source_row.sort_key = source_name.lower()  # Use lowercase for case-insensitive sorting
                all_source_rows.append(source_row)

        # Sort all source rows by their sort_key and add them to the UI
        sorted_source_rows = sorted(all_source_rows, key=lambda row: row.sort_key)
        for row in sorted_source_rows:
            category_row.add_value_row(row)

    def refresh_sidebar_runners(self):
        """
        Refresh platform filters since runners are now linked to platforms
        This method is kept with its original name for backward compatibility.
        """
        if not self.sidebar_container:
            logger.warning("Can't refresh sidebar - not initialized")
            return

        logger.debug("Refreshing platform filters for runners...")

        # Get current games
        games = self.main_controller.get_games()

        # Refresh platform filters since runners are now linked to platforms
        self._refresh_platforms_filters(games)

        # Restore selected values
        self._restore_filter_selections()

        # If we have "runner" in active filters, clear it since we no longer use runner filtering
        if "runner" in self.active_filters:
            logger.debug("Clearing obsolete runner filters")
            self.active_filters.pop("runner")
            self.main_controller.settings_manager.set_sidebar_active_filters(self.active_filters)
            self.main_controller.settings_manager.save_settings()

    def get_active_filters(self):
        """
        Get all active filters as a dictionary of filter categories and their values.

        Returns:
            dict: A dictionary with filter category IDs as keys and sets of filter values as values
        """
        # Return a copy of active filters to prevent unexpected modifications
        return self.active_filters.copy()

    def apply_filters_to_games(self, games):
        """
        Apply all active filters to a list of games.

        Args:
            games: List of games to filter

        Returns:
            List[Game]: Filtered list of games
        """
        filtered_games = games

        # If no active filters, return all games
        if not self.active_filters:
            return filtered_games

        # Apply each filter category
        for category, values in self.active_filters.items():
            if not values:  # Skip empty filter sets
                continue

            # Apply filter based on category
            if category == "runner":
                # Runner filtering is no longer supported as we now use platforms instead
                # Remove these filters since they're obsolete
                self.active_filters.pop(category, None)
                continue

            elif category == "completion_status":
                filtered_games = [g for g in filtered_games if g.completion_status.name in values]
                logger.debug(f"After completion status filters ({len(values)} selected): {len(filtered_games)} games")

            elif category == "platforms":
                filtered_games = [g for g in filtered_games if g.platforms and any(platform.name in values for platform in g.platforms)]
                logger.debug(f"After platform filters ({len(values)} selected): {len(filtered_games)} games")

            elif category == "genres":
                filtered_games = [g for g in filtered_games if g.genres and any(genre.name in values for genre in g.genres)]
                logger.debug(f"After genre filters ({len(values)} selected): {len(filtered_games)} games")

            elif category == "age_ratings":
                filtered_games = [g for g in filtered_games if g.age_ratings and any(rating.name in values for rating in g.age_ratings)]
                logger.debug(f"After age rating filters ({len(values)} selected): {len(filtered_games)} games")

            elif category == "features":
                filtered_games = [g for g in filtered_games if g.features and any(feature.name in values for feature in g.features)]
                logger.debug(f"After feature filters ({len(values)} selected): {len(filtered_games)} games")

            elif category == "regions":
                filtered_games = [g for g in filtered_games if g.regions and any(region.name in values for region in g.regions)]
                logger.debug(f"After region filters ({len(values)} selected): {len(filtered_games)} games")

            elif category == "sources":
                # Special case for empty source filter (matches games with no source)
                if "" in values:
                    if len(values) == 1:
                        # Only filtering for "No Source" - get all games with no source or empty source
                        filtered_games = [g for g in filtered_games if g.source is None or g.source == ""]
                    else:
                        # Mixed filter including "No Source" and other sources
                        filtered_games = [g for g in filtered_games if g.source is None or g.source == "" or g.source in values]
                else:
                    # Normal source filtering
                    filtered_games = [g for g in filtered_games if g.source in values]
                logger.debug(f"After source filters ({len(values)} selected): {len(filtered_games)} games")

        return filtered_games
