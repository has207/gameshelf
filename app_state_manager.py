import os
from pathlib import Path
import yaml
import logging
from typing import Dict, Optional, Any, List, Tuple

# Set up logger
logger = logging.getLogger(__name__)


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
        default_settings = self._get_default_settings()

        if not self.settings_file.exists():
            return default_settings

        try:
            with open(self.settings_file, "r") as f:
                loaded_settings = yaml.safe_load(f)
                if not loaded_settings:
                    return default_settings

                # Deep merge loaded settings with default settings
                # This ensures all default sections and values exist
                merged_settings = self._deep_merge_settings(default_settings, loaded_settings)

                return merged_settings
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            return default_settings

    def _deep_merge_settings(self, defaults: Dict[str, Any], loaded: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively merge loaded settings with default settings

        This ensures that all keys from defaults exist in the result,
        while preserving existing values from loaded.

        Args:
            defaults: Default settings dictionary
            loaded: Loaded settings from file

        Returns:
            Merged settings dictionary
        """
        result = defaults.copy()

        for key, loaded_value in loaded.items():
            # If the key exists in defaults and both are dictionaries, merge them
            if key in defaults and isinstance(defaults[key], dict) and isinstance(loaded_value, dict):
                result[key] = self._deep_merge_settings(defaults[key], loaded_value)
            else:
                # Otherwise use the loaded value
                result[key] = loaded_value

        return result

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
                "selected_index": 0,
                "active_filters": {},
                "expanded_categories": {
                    "runner": True,
                    "completion_status": True
                }
            },
            "details": {
                "visible": False,
                "current_game_id": None
            },
            "import_paths": {
                "json_file": "",
                "cover_dir": ""
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
            logger.error(f"Error saving settings: {e}")
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

    def get_sidebar_active_filters(self) -> Dict[str, str]:
        """
        Get the active filters in the sidebar

        Returns:
            Dictionary mapping category IDs to value IDs
        """
        return self.settings["sidebar"].get("active_filters", {})

    def set_sidebar_active_filters(self, active_filters: Dict[str, str]) -> None:
        """
        Set the active filters in the sidebar

        Args:
            active_filters: Dictionary mapping category IDs to value IDs
        """
        self.settings["sidebar"]["active_filters"] = active_filters

    def get_sidebar_expanded_categories(self) -> Dict[str, bool]:
        """
        Get the expanded state of categories in the sidebar

        Returns:
            Dictionary mapping category IDs to expanded state (True/False)
        """
        return self.settings["sidebar"].get("expanded_categories", {
            "runner": True,
            "completion_status": True
        })

    def set_sidebar_expanded_categories(self, expanded_categories: Dict[str, bool]) -> None:
        """
        Set the expanded state of categories in the sidebar

        Args:
            expanded_categories: Dictionary mapping category IDs to expanded state
        """
        self.settings["sidebar"]["expanded_categories"] = expanded_categories

    def get_import_json_path(self) -> str:
        """
        Get the last used JSON import file path

        Returns:
            Path to the last used JSON file
        """
        return self.settings["import_paths"].get("json_file", "")

    def set_import_json_path(self, path: str) -> None:
        """
        Set the last used JSON import file path

        Args:
            path: Path to the JSON file
        """
        self.settings["import_paths"]["json_file"] = path

    def get_import_cover_dir(self) -> str:
        """
        Get the last used cover images directory path

        Returns:
            Path to the last used cover images directory
        """
        return self.settings["import_paths"].get("cover_dir", "")

    def set_import_cover_dir(self, path: str) -> None:
        """
        Set the last used cover images directory path

        Args:
            path: Path to the cover images directory
        """
        self.settings["import_paths"]["cover_dir"] = path