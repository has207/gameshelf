import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GObject, GLib
import os
import logging
import threading
from pathlib import Path
from typing import Optional

from sources.gog_library import GogLibraryClient
from data import Source, SourceType

# Set up logger
logger = logging.getLogger(__name__)

@Gtk.Template(filename="layout/gog_source_dialog.ui")
class GogSourceDialog(Gtk.Dialog):
    __gtype_name__ = "GogSourceDialog"

    name_entry = Gtk.Template.Child()
    download_images_switch = Gtk.Template.Child()
    auth_button = Gtk.Template.Child()
    auth_status_label = Gtk.Template.Child()
    cancel_button = Gtk.Template.Child()
    save_button = Gtk.Template.Child()

    def __init__(self, parent=None, source=None, source_handler=None, **kwargs):
        super().__init__(transient_for=parent, use_header_bar=True, **kwargs)
        self.parent = parent
        self.source_handler = source_handler
        self.auth_token = None
        self.editing = source is not None and hasattr(source, 'id') and source.id

        # For new source, generate ID upfront so tokens can be stored properly
        if not self.editing and self.source_handler:
            source_id = str(self.source_handler.get_next_source_id())
            self.source = Source(
                id=source_id,
                name="GOG Games",
                source_type=SourceType.GOG,
                active=True,
                config={}
            )
        else:
            self.source = source

        # If editing an existing source, populate the fields
        if self.editing:
            self.name_entry.set_text(self.source.name)

            # Set download_images_switch based on source config
            if self.source.config and "download_images" in self.source.config:
                self.download_images_switch.set_active(self.source.config.get("download_images", True))
            else:
                # Default to True if not specified
                self.download_images_switch.set_active(True)

            # For GOG sources, check if there are valid tokens
            if self.source_handler:
                # Update the auth status immediately
                self._update_auth_status()
            else:
                self.auth_status_label.set_text("Authentication: Not connected")
        else:
            self.set_title("Add GOG Source")
            self.name_entry.set_text("GOG Games")
            self.auth_status_label.set_text("Authentication: Not connected")
            # Default to True for new sources
            self.download_images_switch.set_active(True)

        # Connect signals
        self.auth_button.connect("clicked", self.on_auth_clicked)

        # Check if these buttons exist before trying to connect them
        if hasattr(self, 'cancel_button') and self.cancel_button is not None:
            self.cancel_button.connect("clicked", self._on_cancel_clicked)

        if hasattr(self, 'save_button') and self.save_button is not None:
            self.save_button.connect("clicked", self._on_save_clicked)

        self.connect("response", self.on_dialog_response)

    def _on_cancel_clicked(self, button):
        """Handle cancel button click"""
        # If we're creating a new source and already generated an ID,
        # clean up the token directory to avoid orphaned auth files
        if not self.editing and self.source and self.source_handler:
            try:
                # Get the token directory for this source
                tokens_dir = self.source_handler.ensure_secure_token_storage(self.source.id)
                if tokens_dir.exists():
                    import shutil
                    # Remove the tokens directory and its contents
                    shutil.rmtree(tokens_dir)
                    logger.debug(f"Cleaned up token directory for canceled GOG source: {tokens_dir}")
            except Exception as e:
                logger.error(f"Error cleaning up token directory: {e}")

        self.response(Gtk.ResponseType.CANCEL)
        self.close()

    def _on_save_clicked(self, button):
        """Handle save button click"""
        self.response(Gtk.ResponseType.OK)

    def on_auth_clicked(self, button):
        """Handle OAuth authentication with GOG"""
        self.auth_status_label.set_text("Authentication: In progress...")

        # Get the token directory for this source (source ID is always set now)
        tokens_dir = None
        if self.source_handler and self.source:
            tokens_dir = self.source_handler.ensure_secure_token_storage(self.source.id)

        # Launch authentication
        gog_client = GogLibraryClient(token_dir=tokens_dir)
        if gog_client.authenticate():
            self.auth_status_label.set_text("Authentication: Connected")
            self.auth_token = "gog_authenticated"  # Just a marker value
        else:
            self.auth_status_label.set_text("Authentication: Failed")

    def on_dialog_response(self, dialog, response_id):
        if response_id != Gtk.ResponseType.OK:
            # Handle cleanup on cancel in _on_cancel_clicked
            return

        name = self.name_entry.get_text().strip()

        # Validate that we have the necessary information
        if not name:
            self._show_error("Name is required")
            return

        # Create or update the source
        if self.editing:
            # Update existing source
            self.source.name = name

            # Update the config settings
            if not self.source.config:
                self.source.config = {}
            self.source.config["download_images"] = self.download_images_switch.get_active()

            # No need to store any authentication state in the config
            # as we're dynamically checking the token files
        else:
            # Update the source that was created in __init__
            self.source.name = name
            self.source.config = {
                "download_images": self.download_images_switch.get_active()
            }

        # Save and emit signal
        if self.source_handler and self.source_handler.save_source(self.source):
            self.emit("source-saved", self.source)
            self.close()
        else:
            self._show_error("Failed to save source")

    def _check_auth_status(self, quiet=False):
        """
        Check if the GOG authentication is valid

        Args:
            quiet: If True, don't update the UI

        Returns:
            bool: True if authenticated, False otherwise
        """
        if not self.source_handler or not self.source:
            return False

        # Get the token directory for this source
        tokens_dir = self.source_handler.ensure_secure_token_storage(self.source.id)

        # Create a GOG Library instance with this token directory
        gog_client = GogLibraryClient(token_dir=tokens_dir)

        # Check if the tokens are valid
        is_authenticated = gog_client.is_authenticated()

        logger.debug(f"GOG authentication check: {is_authenticated}")

        # Update the UI if not in quiet mode
        if not quiet:
            if is_authenticated:
                self.auth_status_label.set_text("Authentication: Connected")
            else:
                self.auth_status_label.set_text("Authentication: Not connected")

        return is_authenticated

    def _update_auth_status(self):
        """Update the authentication status label based on current token state"""
        self._check_auth_status(quiet=False)

    def _show_error(self, message):
        """Show an error message dialog"""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Error"
        )
        dialog.format_secondary_text(message)
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()

    @classmethod
    def show_dialog(cls, source=None, source_handler=None, parent=None, callback=None):
        """
        Show the GOG source dialog

        Args:
            source: The source to edit, or None for a new source
            source_handler: The source handler
            parent: The parent window
            callback: Function to call with the saved source

        Returns:
            The dialog instance
        """
        dialog = cls(source=source, source_handler=source_handler, parent=parent)

        # Connect the source-saved signal to the callback
        if callback:
            dialog.connect("source-saved", lambda _, source: callback(source))

        # Show the dialog
        dialog.present()
        return dialog

# Define custom signals
GObject.type_register(GogSourceDialog)
GObject.signal_new("source-saved", GogSourceDialog,
                  GObject.SignalFlags.RUN_LAST, None, (object,))