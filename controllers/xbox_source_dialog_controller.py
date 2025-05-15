import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GObject

import os
import json
import sys
import subprocess
from pathlib import Path
from datetime import datetime
import requests

from sources.xbox_client import XboxLibrary
from sources.xbox_auth_code_wrapper import XboxAuthCodeWrapper
from data import Source, SourceType

@Gtk.Template(filename="layout/xbox_source_dialog.ui")
class XboxSourceDialog(Gtk.Dialog):
    __gtype_name__ = "XboxSourceDialog"

    name_entry = Gtk.Template.Child()
    active_switch = Gtk.Template.Child()
    download_images_switch = Gtk.Template.Child()
    auth_button = Gtk.Template.Child()
    auth_status_label = Gtk.Template.Child()
    cancel_button = Gtk.Template.Child()
    save_button = Gtk.Template.Child()

    # Xbox API constants - copied from xbox_client.py
    CLIENT_ID = "85736097-7c70-4eba-ae9a-0cf0de4391e1"
    REDIRECT_URI = "https://login.live.com/oauth20_desktop.srf"
    SCOPE = "Xboxlive.signin Xboxlive.offline_access"

    def __init__(self, parent=None, source=None, source_handler=None, **kwargs):
        super().__init__(transient_for=parent, use_header_bar=True, **kwargs)
        self.parent = parent
        self.source = source
        self.source_handler = source_handler
        self.auth_token = None
        self.editing = source is not None

        # If editing an existing source, populate the fields
        if self.editing:
            self.name_entry.set_text(source.name)
            self.active_switch.set_active(source.active)

            # Set download_images_switch based on source config
            if source.config and "download_images" in source.config:
                self.download_images_switch.set_active(source.config.get("download_images", True))
            else:
                # Default to True if not specified
                self.download_images_switch.set_active(True)

            # For Xbox sources, we need to check if there are valid tokens in the tokens directory
            # We'll check this dynamically each time the dialog is shown
            if self.source_handler:
                # Update the auth status immediately
                self._update_auth_status()
            else:
                self.auth_status_label.set_text("Authentication: Not connected")
        else:
            self.set_title("Add Xbox Source")
            self.name_entry.set_text("Xbox Games")
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
        self.response(Gtk.ResponseType.CANCEL)
        self.close()

    def _on_save_clicked(self, button):
        """Handle save button click"""
        self.response(Gtk.ResponseType.OK)

    def on_auth_clicked(self, button):
        """Handle OAuth authentication with Xbox - launches a separate process"""
        self.auth_status_label.set_text("Authentication: In progress...")
        auth_token = self.authenticate_xbox()

        if auth_token:
            # After successful authentication, we'll save the token using the Xbox library
            if self.source_handler and self.editing:
                # Get the token directory for this source
                tokens_dir = self.source_handler.ensure_secure_token_storage(self.source.id)

                # Now we have the auth code, let's complete the authentication with our wrapper
                try:
                    # Use our auth code wrapper to complete the authentication flow
                    auth_wrapper = XboxAuthCodeWrapper(tokens_dir)

                    if auth_wrapper.complete_auth_with_code(auth_token):
                        print("Successfully authenticated with Xbox")
                        # Update the authentication status
                        self._update_auth_status()
                        return

                    else:
                        self.auth_status_label.set_text("Authentication: Failed to exchange code for tokens")
                except Exception as e:
                    print(f"Error processing Xbox authentication: {e}")
                    self.auth_status_label.set_text(f"Authentication: Error - {str(e)}")
            else:
                self.auth_token = "xbox_authenticated"  # Just a marker value
                self.auth_status_label.set_text("Authentication: Connected")
        else:
            self.auth_status_label.set_text("Authentication: Failed")

    def authenticate_xbox(self):
        """
        Initiate Xbox authentication flow using a separate process
        to avoid GTK version conflicts

        Returns:
            str: Authentication token if successful, None otherwise
        """
        # Get the path to the auth helper script
        auth_helper_path = Path(__file__).parent.parent / "sources" / "xbox_auth_helper.py"

        # Check if the helper script exists
        if not auth_helper_path.exists():
            print(f"Error: Authentication helper script not found at {auth_helper_path}")
            return None

        try:
            # Make sure the helper script is executable
            os.chmod(auth_helper_path, 0o755)

            # Run the authentication helper as a completely separate process
            # This ensures no GTK version conflicts
            cmd = [
                sys.executable,
                str(auth_helper_path),
                self.CLIENT_ID,
                self.REDIRECT_URI,
                self.SCOPE
            ]

            print("Starting authentication process in separate process...")

            # Run the process and wait for completion
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True
            )

            # Show a spinner or some UI indication that we're waiting
            self.auth_status_label.set_text("Waiting for authentication...")
            self.auth_button.set_sensitive(False)

            # Wait for the process to complete, but update the UI periodically
            while process.poll() is None:
                # Update UI and process events
                while Gtk.events_pending():
                    Gtk.main_iteration()

            # Process is done
            self.auth_button.set_sensitive(True)

            stdout, stderr = process.communicate()
            exit_code = process.returncode

            if exit_code != 0:
                print(f"Authentication process failed with exit code {exit_code}")
                print(f"Error: {stderr}")
                return None

            # Parse the JSON output from the helper script
            try:
                # Remove any extra text before the JSON
                json_start = stdout.find('{')
                if json_start >= 0:
                    json_str = stdout[json_start:]
                    auth_result = json.loads(json_str)
                    if 'error' in auth_result:
                        print(f"Authentication error: {auth_result['error']}")
                        return None
                    elif 'code' in auth_result:
                        return auth_result['code']
                    else:
                        print("Unexpected authentication result")
                        return None
                else:
                    print("No JSON found in authentication output")
                    print(f"Output: {stdout}")
                    return None
            except json.JSONDecodeError as e:
                print(f"Failed to parse authentication result: {e}")
                print(f"Output: {stdout}")
                print(f"Error: {stderr}")
                return None

        except Exception as e:
            print(f"Error running authentication: {e}")
            return None

    def on_dialog_response(self, dialog, response_id):
        if response_id != Gtk.ResponseType.OK:
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
            self.source.active = self.active_switch.get_active()

            # Update the download_images setting in config
            if not self.source.config:
                self.source.config = {}
            self.source.config["download_images"] = self.download_images_switch.get_active()

            # No need to store any authentication state in the config
            # as we're dynamically checking the token files
        else:
            # Create new source with ID already assigned
            next_id = self.source_handler.get_next_source_id()
            self.source = Source(
                id=str(next_id),
                name=name,
                path="",  # Not needed for Xbox sources
                source_type=SourceType.XBOX,
                active=self.active_switch.get_active(),
                config={"download_images": self.download_images_switch.get_active()}
            )

        # Save and emit signal
        if self.source_handler and self.source_handler.save_source(self.source):
            self.emit("source-saved", self.source)
            self.close()
        else:
            self._show_error("Failed to save source")

    def _check_auth_status(self, quiet=False):
        """
        Check if the Xbox authentication is valid

        Args:
            quiet: If True, don't update the UI

        Returns:
            bool: True if authenticated, False otherwise
        """
        if not self.source_handler:
            return False

        # For authentication check, we should have a valid source with ID
        if not self.editing:
            return False

        # Get the token directory for this source
        tokens_dir = self.source_handler.ensure_secure_token_storage(self.source.id)

        # Create an Xbox Library instance with this token directory
        xbox = XboxLibrary(token_dir=tokens_dir)

        # Check if the tokens are valid
        is_authenticated = xbox.is_authenticated(try_refresh=True)

        print(f"DEBUG: Xbox authentication check: {is_authenticated}")

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
        Show the Xbox source dialog

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
GObject.type_register(XboxSourceDialog)
GObject.signal_new("source-saved", XboxSourceDialog,
                  GObject.SignalFlags.RUN_LAST, None, (object,))