import os
from pathlib import Path
import yaml
from typing import Dict, Optional, Any, List, Tuple


class AppStateManager:
    def __init__(self, data_dir: str = "data"):
        """
        Initialize the settings manager

        Args:
            data_dir: The data directory path
        """
        self.data_dir = Path(data_dir)
        self.settings_file = self.data_dir / "app_state.yaml"
        self.settings = self._load_settings()

    def _load_settings(self) -> Dict[str, Any]:
        """
        Load settings from the settings file

        Returns:
            Dictionary containing settings
        """
        if not self.settings_file.exists():
            return self._get_default_settings()

        try:
            with open(self.settings_file, "r") as f:
                settings = yaml.safe_load(f)
                return settings if settings else self._get_default_settings()
        except Exception as e:
            print(f"Error loading settings: {e}")
            return self._get_default_settings()

    def _get_default_settings(self) -> Dict[str, Any]:
        """
        Get default settings

        Returns:
            Dictionary with default settings
        """
        return {
            "window": {
                "width": 1200,
                "height": 800,
                "maximized": False
            },
            "filters": {
                "current_filter": None,
                "show_hidden": False,
                "search_text": ""
            },
            "sort": {
                "field": "title",
                "ascending": True
            },
            "sidebar": {
                "selected_index": 0
            },
            "details": {
                "visible": False,
                "current_game_id": None
            }
        }

    def save_settings(self) -> bool:
        """
        Save settings to the settings file

        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure the data directory exists
            self.data_dir.mkdir(parents=True, exist_ok=True)

            # Write settings to file
            with open(self.settings_file, "w") as f:
                yaml.dump(self.settings, f)
            return True
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False

    def get_window_size(self) -> Tuple[int, int]:
        """
        Get the window size from settings

        Returns:
            Tuple of (width, height)
        """
        return (
            self.settings["window"]["width"],
            self.settings["window"]["height"]
        )

    def set_window_size(self, width: int, height: int) -> None:
        """
        Set the window size in settings

        Args:
            width: Window width
            height: Window height
        """
        self.settings["window"]["width"] = width
        self.settings["window"]["height"] = height

    def get_window_maximized(self) -> bool:
        """
        Get whether the window is maximized

        Returns:
            True if the window is maximized, False otherwise
        """
        return self.settings["window"]["maximized"]

    def set_window_maximized(self, maximized: bool) -> None:
        """
        Set whether the window is maximized

        Args:
            maximized: True if maximized, False otherwise
        """
        self.settings["window"]["maximized"] = maximized

    def get_current_filter(self) -> Optional[str]:
        """
        Get the current filter for games

        Returns:
            Current filter, or None for no filter
        """
        return self.settings["filters"]["current_filter"]

    def set_current_filter(self, filter_value: Optional[str]) -> None:
        """
        Set the current filter for games

        Args:
            filter_value: Filter value or None for no filter
        """
        self.settings["filters"]["current_filter"] = filter_value

    def get_show_hidden(self) -> bool:
        """
        Get whether to show hidden games

        Returns:
            True if showing hidden games, False otherwise
        """
        return self.settings["filters"]["show_hidden"]

    def set_show_hidden(self, show_hidden: bool) -> None:
        """
        Set whether to show hidden games

        Args:
            show_hidden: True to show hidden games, False otherwise
        """
        self.settings["filters"]["show_hidden"] = show_hidden

    def get_search_text(self) -> str:
        """
        Get the current search text

        Returns:
            Current search text
        """
        return self.settings["filters"]["search_text"]

    def set_search_text(self, search_text: str) -> None:
        """
        Set the current search text

        Args:
            search_text: Search text
        """
        self.settings["filters"]["search_text"] = search_text

    def get_sort_settings(self) -> Tuple[str, bool]:
        """
        Get the current sort settings

        Returns:
            Tuple of (sort_field, ascending)
        """
        return (
            self.settings["sort"]["field"],
            self.settings["sort"]["ascending"]
        )

    def set_sort_settings(self, sort_field: str, ascending: bool) -> None:
        """
        Set the sort settings

        Args:
            sort_field: Field to sort by
            ascending: True for ascending, False for descending
        """
        self.settings["sort"]["field"] = sort_field
        self.settings["sort"]["ascending"] = ascending

    def get_sidebar_selection(self) -> int:
        """
        Get the selected index in the sidebar

        Returns:
            Selected index
        """
        return self.settings["sidebar"]["selected_index"]

    def set_sidebar_selection(self, index: int) -> None:
        """
        Set the selected index in the sidebar

        Args:
            index: Selected index
        """
        self.settings["sidebar"]["selected_index"] = index

    def get_details_visible(self) -> bool:
        """
        Get whether the details panel is visible

        Returns:
            True if visible, False otherwise
        """
        return self.settings["details"]["visible"]

    def set_details_visible(self, visible: bool) -> None:
        """
        Set whether the details panel is visible

        Args:
            visible: True if visible, False otherwise
        """
        self.settings["details"]["visible"] = visible

    def get_current_game_id(self) -> Optional[str]:
        """
        Get the ID of the currently loaded game

        Returns:
            Current game ID or None
        """
        return self.settings["details"]["current_game_id"]

    def set_current_game_id(self, game_id: Optional[str]) -> None:
        """
        Set the ID of the currently loaded game

        Args:
            game_id: Game ID or None
        """
        self.settings["details"]["current_game_id"] = game_id