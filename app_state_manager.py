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
        Initialize the app state manager

        Args:
            data_dir: The data directory path
        """
        self.data_dir = Path(data_dir)
        self.app_state_file = self.data_dir / "app_state.yaml"
        self.app_state = self._load_app_state()

    def _load_app_state(self) -> Dict[str, Any]:
        """
        Load app state from the app state file

        Returns:
            Dictionary containing app state
        """
        default_app_state = self._get_default_app_state()

        if not self.app_state_file.exists():
            return default_app_state

        try:
            with open(self.app_state_file, "r") as f:
                loaded_app_state = yaml.safe_load(f)
                if not loaded_app_state:
                    return default_app_state

                # Deep merge loaded app state with default app state
                # This ensures all default sections and values exist
                merged_app_state = self._deep_merge_app_state(default_app_state, loaded_app_state)

                return merged_app_state
        except Exception as e:
            logger.error(f"Error loading app state: {e}")
            return default_app_state

    def _deep_merge_app_state(self, defaults: Dict[str, Any], loaded: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively merge loaded app state

        This ensures that all keys from defaults exist in the result,
        while preserving existing values from loaded.

        Args:
            defaults: Default app state dictionary
            loaded: Loaded app state from file

        Returns:
            Merged app state dictionary
        """
        result = defaults.copy()

        for key, loaded_value in loaded.items():
            # If the key exists in defaults and both are dictionaries, merge them
            if key in defaults and isinstance(defaults[key], dict) and isinstance(loaded_value, dict):
                result[key] = self._deep_merge_app_state(defaults[key], loaded_value)
            else:
                # Otherwise use the loaded value
                result[key] = loaded_value

        return result

    def _get_default_app_state(self) -> Dict[str, Any]:
        """
        Get default state

        Returns:
            Dictionary with default state
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

    def save_app_state(self) -> bool:
        """
        Save app state to the app state file

        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure the data directory exists
            self.data_dir.mkdir(parents=True, exist_ok=True)

            # Write app state to file
            with open(self.app_state_file, "w") as f:
                yaml.dump(self.app_state, f)
            return True
        except Exception as e:
            logger.error(f"Error saving app state: {e}")
            return False

    def get_window_size(self) -> Tuple[int, int]:
        """
        Get the window size

        Returns:
            Tuple of (width, height)
        """
        return (
            self.app_state["window"]["width"],
            self.app_state["window"]["height"]
        )

    def set_window_size(self, width: int, height: int) -> None:
        """
        Set the window size

        Args:
            width: Window width
            height: Window height
        """
        self.app_state["window"]["width"] = width
        self.app_state["window"]["height"] = height

    def get_window_maximized(self) -> bool:
        """
        Get whether the window is maximized

        Returns:
            True if the window is maximized, False otherwise
        """
        return self.app_state["window"]["maximized"]

    def set_window_maximized(self, maximized: bool) -> None:
        """
        Set whether the window is maximized

        Args:
            maximized: True if maximized, False otherwise
        """
        self.app_state["window"]["maximized"] = maximized

    def get_current_filter(self) -> Optional[str]:
        """
        Get the current filter for games

        Returns:
            Current filter, or None for no filter
        """
        return self.app_state["filters"]["current_filter"]

    def set_current_filter(self, filter_value: Optional[str]) -> None:
        """
        Set the current filter for games

        Args:
            filter_value: Filter value or None for no filter
        """
        self.app_state["filters"]["current_filter"] = filter_value

    def get_show_hidden(self) -> bool:
        """
        Get whether to show hidden games

        Returns:
            True if showing hidden games, False otherwise
        """
        return self.app_state["filters"]["show_hidden"]

    def set_show_hidden(self, show_hidden: bool) -> None:
        """
        Set whether to show hidden games

        Args:
            show_hidden: True to show hidden games, False otherwise
        """
        self.app_state["filters"]["show_hidden"] = show_hidden

    def get_search_text(self) -> str:
        """
        Get the current search text

        Returns:
            Current search text
        """
        return self.app_state["filters"]["search_text"]

    def set_search_text(self, search_text: str) -> None:
        """
        Set the current search text

        Args:
            search_text: Search text
        """
        self.app_state["filters"]["search_text"] = search_text

    def get_sort_state(self) -> Tuple[str, bool]:
        """
        Get the current sort state

        Returns:
            Tuple of (sort_field, ascending)
        """
        return (
            self.app_state["sort"]["field"],
            self.app_state["sort"]["ascending"]
        )

    def set_sort_state(self, sort_field: str, ascending: bool) -> None:
        """
        Set the sort state

        Args:
            sort_field: Field to sort by
            ascending: True for ascending, False for descending
        """
        self.app_state["sort"]["field"] = sort_field
        self.app_state["sort"]["ascending"] = ascending

    def get_sidebar_selection(self) -> int:
        """
        Get the selected index in the sidebar

        Returns:
            Selected index
        """
        return self.app_state["sidebar"]["selected_index"]

    def set_sidebar_selection(self, index: int) -> None:
        """
        Set the selected index in the sidebar

        Args:
            index: Selected index
        """
        self.app_state["sidebar"]["selected_index"] = index

    def get_details_visible(self) -> bool:
        """
        Get whether the details panel is visible

        Returns:
            True if visible, False otherwise
        """
        return self.app_state["details"]["visible"]

    def set_details_visible(self, visible: bool) -> None:
        """
        Set whether the details panel is visible

        Args:
            visible: True if visible, False otherwise
        """
        self.app_state["details"]["visible"] = visible

    def get_current_game_id(self) -> Optional[str]:
        """
        Get the ID of the currently loaded game

        Returns:
            Current game ID or None
        """
        return self.app_state["details"]["current_game_id"]

    def set_current_game_id(self, game_id: Optional[str]) -> None:
        """
        Set the ID of the currently loaded game

        Args:
            game_id: Game ID or None
        """
        self.app_state["details"]["current_game_id"] = game_id

    def get_sidebar_active_filters(self) -> Dict[str, str]:
        """
        Get the active filters in the sidebar

        Returns:
            Dictionary mapping category IDs to value IDs
        """
        return self.app_state["sidebar"].get("active_filters", {})

    def set_sidebar_active_filters(self, active_filters: Dict[str, str]) -> None:
        """
        Set the active filters in the sidebar

        Args:
            active_filters: Dictionary mapping category IDs to value IDs
        """
        self.app_state["sidebar"]["active_filters"] = active_filters

    def get_sidebar_expanded_categories(self) -> Dict[str, bool]:
        """
        Get the expanded state of categories in the sidebar

        Returns:
            Dictionary mapping category IDs to expanded state (True/False)
        """
        return self.app_state["sidebar"].get("expanded_categories", {
            "runner": True,
            "completion_status": True
        })

    def set_sidebar_expanded_categories(self, expanded_categories: Dict[str, bool]) -> None:
        """
        Set the expanded state of categories in the sidebar

        Args:
            expanded_categories: Dictionary mapping category IDs to expanded state
        """
        self.app_state["sidebar"]["expanded_categories"] = expanded_categories

    def get_import_json_path(self) -> str:
        """
        Get the last used JSON import file path

        Returns:
            Path to the last used JSON file
        """
        return self.app_state["import_paths"].get("json_file", "")

    def set_import_json_path(self, path: str) -> None:
        """
        Set the last used JSON import file path

        Args:
            path: Path to the JSON file
        """
        self.app_state["import_paths"]["json_file"] = path

    def get_import_cover_dir(self) -> str:
        """
        Get the last used cover images directory path

        Returns:
            Path to the last used cover images directory
        """
        return self.app_state["import_paths"].get("cover_dir", "")

    def set_import_cover_dir(self, path: str) -> None:
        """
        Set the last used cover images directory path

        Args:
            path: Path to the cover images directory
        """
        self.app_state["import_paths"]["cover_dir"] = path
