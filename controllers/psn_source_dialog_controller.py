import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GObject
import logging

from sources.psn_client import PSNClient
from data import SourceType, Source

# Set up logger
logger = logging.getLogger(__name__)

@Gtk.Template(filename="layout/psn_source_dialog.ui")
class PSNSourceDialog(Gtk.Dialog):
    __gtype_name__ = "PSNSourceDialog"

    name_entry = Gtk.Template.Child()
    token_entry = Gtk.Template.Child()
    verify_button = Gtk.Template.Child()
    status_label = Gtk.Template.Child()
    download_images_switch = Gtk.Template.Child()
    active_switch = Gtk.Template.Child()
    cancel_button = Gtk.Template.Child()
    save_button = Gtk.Template.Child()

    def __init__(self, parent=None, source=None, source_handler=None, **kwargs):
        super().__init__(transient_for=parent, use_header_bar=True, **kwargs)
        self.parent = parent
        self.source = source
        self.source_handler = source_handler
        self.auth_token = None
        self.verified = False
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

            # For PSN sources, we need to check if there are valid tokens in the tokens directory
            if self.source_handler:
                # Get a properly initialized PSN client with token storage set up
                psn = self.source_handler.get_scanner(SourceType.PLAYSTATION, source.id)

                # Try to get the token from the PSN client's token file
                if hasattr(psn, 'npsso_token') and psn.npsso_token:
                    self.token_entry.set_text(psn.npsso_token)
                    self.auth_token = psn.npsso_token

                # Update the auth status
                self._update_auth_status()
            else:
                self.status_label.set_text("Authentication: Not connected")
        else:
            self.set_title("Add PlayStation Source")
            self.name_entry.set_text("PlayStation Games")
            self.status_label.set_text("Authentication: Not connected")
            # Default to True for new sources
            self.download_images_switch.set_active(True)

        # Connect signals
        self.verify_button.connect("clicked", self.on_verify_clicked)

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

    def on_verify_clicked(self, button):
        token = self.token_entry.get_text()
        if not token:
            self.status_label.set_text("Error: Token is required")
            return

        # Update UI to show verification in progress
        self.status_label.set_text("Authentication: Verifying...")
        self.verify_button.set_sensitive(False)

        # Attempt to verify the token
        is_valid = PSNClient.verify_npsso_token(token)

        self.verify_button.set_sensitive(True)

        if is_valid:
            self.auth_token = token
            self.verified = True
            self.status_label.set_text("Authentication: Verified")

            # If we have a source handler and we're editing, save the token
            if self.source_handler and self.editing:
                # Get a properly initialized PSN client with token storage set up
                psn_client = self.source_handler.get_scanner(SourceType.PLAYSTATION, self.source.id)

                # Authenticate with the token (which saves it to the token directory)
                if psn_client.authenticate(token):
                    logger.info("Successfully authenticated with PSN and saved token")
                else:
                    logger.error("Failed to save PSN token")
        else:
            self.verified = False
            self.status_label.set_text("Authentication: Failed - Invalid token")

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

            # No need to store the token in config anymore since we're using token storage
            if "npsso_token" in self.source.config:
                del self.source.config["npsso_token"]
        else:
            # Create new source with ID already assigned
            next_id = self.source_handler.get_next_source_id()
            self.source = Source(
                id=str(next_id),
                name=name,
                path="",  # Not needed for PSN sources
                source_type=SourceType.PLAYSTATION,
                active=self.active_switch.get_active(),
                config={"download_images": self.download_images_switch.get_active()}
            )

        # Save the source first
        if not self.source_handler or not self.source_handler.save_source(self.source):
            self._show_error("Failed to save source")
            return

        # Save the token if one is entered
        token = self.token_entry.get_text()
        if token:
            psn_client = self.source_handler.get_scanner(SourceType.PLAYSTATION, self.source.id)
            psn_client.authenticate(token)

        # Emit signal and close
        self.emit("source-saved", self.source)
        self.close()

    def _check_auth_status(self, quiet=False):
        """
        Check if the PSN authentication is valid

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

        # Get a properly initialized PSN client with token storage set up
        psn = self.source_handler.get_scanner(SourceType.PLAYSTATION, self.source.id)

        # Check if the tokens are valid
        is_authenticated = psn.is_authenticated()

        logger.debug(f"PSN authentication check: {is_authenticated}")

        # Update the UI if not in quiet mode
        if not quiet:
            if is_authenticated:
                self.status_label.set_text("Authentication: Connected")
            else:
                self.status_label.set_text("Authentication: Not connected")

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
        Show the PSN source dialog

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
GObject.type_register(PSNSourceDialog)
GObject.signal_new("source-saved", PSNSourceDialog,
                  GObject.SignalFlags.RUN_LAST, None, (object,))
