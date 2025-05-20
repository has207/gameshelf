import os
import re
import logging
import threading
import requests
from pathlib import Path
from typing import Optional, Callable, Dict, Any

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio, GObject

from data import Source, SourceType
from sources.steam_client import DEFAULT_STEAMAPPS_PATH, SteamCLI

# Set up logger
logger = logging.getLogger(__name__)

@Gtk.Template(filename="layout/steam_source_dialog.ui")
class SteamSourceDialog(Gtk.Dialog):
    __gtype_name__ = "SteamSourceDialog"

    # UI Elements
    source_name_entry = Gtk.Template.Child()
    steam_path_entry = Gtk.Template.Child()
    browse_button = Gtk.Template.Child()
    path_status_label = Gtk.Template.Child()
    api_key_entry = Gtk.Template.Child()
    steam_id_entry = Gtk.Template.Child()
    verify_api_button = Gtk.Template.Child()
    api_status_label = Gtk.Template.Child()
    include_online_games_check = Gtk.Template.Child()
    save_button = Gtk.Template.Child()

    def __init__(self, parent: Gtk.Window, source: Optional[Source] = None):
        """Initialize the Steam source dialog

        Args:
            parent: Parent window
            source: Optional existing source to edit
        """
        super().__init__(transient_for=parent)
        self.is_editing = source is not None
        self.source = source or Source(
            id="",
            name="",
            source_type=SourceType.STEAM,
            config={}
        )

        self.api_verification_in_progress = False

        # Initialize UI
        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        """Initialize UI elements with current source data"""
        if self.is_editing:
            # Set dialog title for edit mode
            self.set_title("Edit Steam Source")

            # Fill source name
            self.source_name_entry.set_text(self.source.name)

            # Fill Steam path
            if self.source.config and "steam_path" in self.source.config:
                self.steam_path_entry.set_text(self.source.config["steam_path"])
            else:
                self.steam_path_entry.set_text(str(DEFAULT_STEAMAPPS_PATH))

            # Fill API key if exists
            if self.source.config and "api_key" in self.source.config:
                self.api_key_entry.set_text(self.source.config["api_key"])

            # Fill Steam ID if exists
            if self.source.config and "steam_id" in self.source.config:
                self.steam_id_entry.set_text(self.source.config["steam_id"])

            # Set include online games checkbox
            if self.source.config and "include_online_games" in self.source.config:
                self.include_online_games_check.set_active(self.source.config["include_online_games"])
        else:
            # Set default values for new source
            self.source_name_entry.set_text("Steam Library")
            self.steam_path_entry.set_text(str(DEFAULT_STEAMAPPS_PATH))
            self.include_online_games_check.set_active(True)

        # Validate path
        self._validate_path()

    def _connect_signals(self):
        """Connect signals for UI elements"""
        self.browse_button.connect("clicked", self._on_browse_clicked)
        self.steam_path_entry.connect("changed", self._on_path_changed)
        self.source_name_entry.connect("changed", self._on_name_changed)
        self.verify_api_button.connect("clicked", self._on_verify_api_clicked)
        self.api_key_entry.connect("changed", self._on_api_key_changed)
        self.steam_id_entry.connect("changed", self._on_steam_id_changed)
        self.include_online_games_check.connect("toggled", self._on_include_online_toggled)

    def _on_browse_clicked(self, button):
        """Handle browse button click"""
        dialog = Gtk.FileDialog()
        dialog.set_title("Select Steam Directory")
        dialog.set_modal(True)

        # Get current path
        current_path = self.steam_path_entry.get_text()
        if current_path:
            initial_folder = None
            try:
                if os.path.isdir(current_path):
                    initial_folder = Gio.File.new_for_path(current_path)
                elif os.path.isdir(os.path.dirname(current_path)):
                    initial_folder = Gio.File.new_for_path(os.path.dirname(current_path))
                else:
                    initial_folder = Gio.File.new_for_path(str(Path.home()))
            except Exception as e:
                logger.error(f"Error setting initial folder: {e}")
                initial_folder = Gio.File.new_for_path(str(Path.home()))

            dialog.set_initial_folder(initial_folder)

        # Select folder
        dialog.select_folder(self, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        """Handle folder selection result"""
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                self.steam_path_entry.set_text(folder.get_path())
                self._validate_path()
        except Exception as e:
            logger.error(f"Error selecting folder: {e}")

    def _on_path_changed(self, entry):
        """Handle path changes"""
        self._validate_path()

    def _on_name_changed(self, entry):
        """Handle name changes"""
        self._update_save_button()

    def _on_api_key_changed(self, entry):
        """Handle API key changes"""
        # Clear API status label when key changes
        self.api_status_label.set_text("")
        self._update_save_button()

    def _on_steam_id_changed(self, entry):
        """Handle Steam ID changes"""
        # Clear API status label when ID changes
        self.api_status_label.set_text("")
        self._update_save_button()

    def _on_include_online_toggled(self, check_button):
        """Handle include online games checkbox toggle"""
        self._update_save_button()

    def _on_verify_api_clicked(self, button):
        """Handle verify API button click"""
        api_key = self.api_key_entry.get_text()
        steam_id = self.steam_id_entry.get_text()

        # Check if inputs are empty
        if not api_key:
            self.api_status_label.set_markup('<span foreground="red">API key is required</span>')
            return

        if not steam_id:
            self.api_status_label.set_markup('<span foreground="red">Steam ID is required</span>')
            return

        # Process URL if provided
        if "steamcommunity.com" in steam_id:
            # Extract vanity name or ID from URL
            match = re.search(r'steamcommunity\.com/(?:id|profiles)/([^/]+)', steam_id)
            if match:
                steam_id = match.group(1)
            else:
                self.api_status_label.set_markup('<span foreground="red">Invalid Steam profile URL</span>')
                return

        # Disable verify button during verification
        self.verify_api_button.set_sensitive(False)
        self.api_status_label.set_markup('<span foreground="blue">Verifying...</span>')

        # Set verification in progress flag
        self.api_verification_in_progress = True

        # Start verification in a separate thread
        thread = threading.Thread(
            target=self._verify_api_credentials,
            args=(api_key, steam_id)
        )
        thread.daemon = True
        thread.start()

    def _verify_api_credentials(self, api_key: str, steam_id: str):
        """
        Verify Steam API credentials in a background thread

        Args:
            api_key: Steam Web API key
            steam_id: Steam ID or vanity URL
        """
        # If numeric, use directly; otherwise, try to resolve vanity URL
        if steam_id.isdigit():
            resolved_steam_id = steam_id
        else:
            # Try to resolve vanity URL using the API
            try:
                url = "https://api.steampowered.com/ISteamUser/ResolveVanityURL/v1/"
                params = {
                    "key": api_key,
                    "vanityurl": steam_id
                }
                response = requests.get(url, params=params)
                data = response.json()

                if data.get("response", {}).get("success") == 1:
                    resolved_steam_id = data["response"]["steamid"]
                else:
                    # Update UI in main thread
                    GLib.idle_add(
                        self._handle_api_verification_result,
                        False,
                        f"Could not resolve vanity URL: {steam_id}"
                    )
                    return
            except Exception as e:
                # Update UI in main thread
                GLib.idle_add(
                    self._handle_api_verification_result,
                    False,
                    f"Error resolving vanity URL: {e}"
                )
                return

        # Now verify the API key and resolved Steam ID
        try:
            url = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
            params = {
                "key": api_key,
                "steamids": resolved_steam_id
            }

            response = requests.get(url, params=params)
            data = response.json()

            # Check if we got valid player data
            if (data.get("response", {}).get("players") and
                len(data["response"]["players"]) > 0):

                player = data["response"]["players"][0]
                username = player.get("personaname", "Unknown")

                # Update UI in main thread with success message
                GLib.idle_add(
                    self._handle_api_verification_result,
                    True,
                    f"Success! Connected to account: {username}",
                    resolved_steam_id  # Pass resolved ID
                )
            else:
                # Update UI in main thread with error message
                GLib.idle_add(
                    self._handle_api_verification_result,
                    False,
                    "No player data found. Check your Steam ID."
                )
        except Exception as e:
            # Update UI in main thread with error message
            GLib.idle_add(
                self._handle_api_verification_result,
                False,
                f"Error verifying API credentials: {e}"
            )

    def _handle_api_verification_result(self, success: bool, message: str, resolved_id: str = None):
        """
        Update UI with API verification result

        Args:
            success: Whether verification succeeded
            message: Message to display
            resolved_id: Resolved Steam ID (for vanity URLs)
        """
        # Reset verification flag
        self.api_verification_in_progress = False

        # Re-enable verify button
        self.verify_api_button.set_sensitive(True)

        # Update status label
        if success:
            self.api_status_label.set_markup(f'<span foreground="green">{message}</span>')

            # If we resolved a vanity URL, update the field with the actual Steam ID
            if resolved_id and not self.steam_id_entry.get_text().isdigit():
                self.steam_id_entry.set_text(resolved_id)
        else:
            self.api_status_label.set_markup(f'<span foreground="red">{message}</span>')

        # Update save button state
        self._update_save_button()

        # Return False to remove this function from the idle queue
        return False

    def _validate_path(self):
        """Validate Steam path"""
        path = self.steam_path_entry.get_text()

        if not path:
            self.path_status_label.set_markup('<span foreground="red">Please enter a path</span>')
            return False

        # Check if path exists
        if not os.path.isdir(path):
            self.path_status_label.set_markup('<span foreground="red">Directory does not exist</span>')
            return False

        # Check for libraryfolders.vdf
        libraries_file = os.path.join(path, "libraryfolders.vdf")
        if not os.path.isfile(libraries_file):
            self.path_status_label.set_markup('<span foreground="orange">Warning: libraries file not found</span>')
            return True

        # Path is valid
        self.path_status_label.set_markup('<span foreground="green">Path is valid</span>')
        return True

    def _update_save_button(self):
        """Update save button sensitivity based on input validity"""
        name = self.source_name_entry.get_text()
        path_valid = self._validate_path()

        # Check if API credentials are required (if include_online_games is checked)
        api_credentials_valid = True
        if self.include_online_games_check.get_active():
            api_key = self.api_key_entry.get_text()
            steam_id = self.steam_id_entry.get_text()
            api_credentials_valid = bool(api_key) and bool(steam_id)

        # Enable save button if name and path are valid, and API credentials if required
        self.save_button.set_sensitive(bool(name) and path_valid and api_credentials_valid)

    def get_source(self) -> Source:
        """Get the configured source

        Returns:
            The source object with updated configuration
        """
        # Update source properties
        self.source.name = self.source_name_entry.get_text()

        # Update source config
        if not self.source.config:
            self.source.config = {}

        # Save Steam path
        self.source.config["steam_path"] = self.steam_path_entry.get_text()

        # Save API settings if needed
        include_online_games = self.include_online_games_check.get_active()
        self.source.config["include_online_games"] = include_online_games

        if include_online_games:
            self.source.config["api_key"] = self.api_key_entry.get_text()
            self.source.config["steam_id"] = self.steam_id_entry.get_text()
        else:
            # Remove API settings if not including online games
            if "api_key" in self.source.config:
                del self.source.config["api_key"]
            if "steam_id" in self.source.config:
                del self.source.config["steam_id"]

        return self.source