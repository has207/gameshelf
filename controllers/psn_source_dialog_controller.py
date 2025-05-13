import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GObject

from sources.psn_client import verify_npsso_token

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

            # If we have existing auth info
            if source.config and "npsso_token" in source.config:
                self.token_entry.set_text(source.config.get("npsso_token", ""))
                self.auth_token = source.config.get("npsso_token")
                self.verified = True
                self.status_label.set_text("Authentication: Connected")
            else:
                self.status_label.set_text("Authentication: Not verified")
        else:
            self.set_title("Add PlayStation Source")
            self.name_entry.set_text("PlayStation Games")
            self.status_label.set_text("Authentication: Not verified")
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
        is_valid = verify_npsso_token(token)

        self.verify_button.set_sensitive(True)

        if is_valid:
            self.auth_token = token
            self.verified = True
            self.status_label.set_text("Authentication: Verified")
        else:
            self.verified = False
            self.status_label.set_text("Authentication: Failed - Invalid token")

    def on_dialog_response(self, dialog, response_id):
        if response_id != Gtk.ResponseType.OK:
            return

        name = self.name_entry.get_text().strip()
        token = self.token_entry.get_text()

        # Validate that we have the necessary information
        if not name:
            self._show_error("Name is required")
            return

        if not token:
            self._show_error("NPSSO token is required")
            return

        if not self.verified:
            # Perform one last verification if the user changed the token without clicking verify
            if token != self.auth_token:
                is_valid = verify_npsso_token(token)
                if is_valid:
                    self.auth_token = token
                    self.verified = True
                else:
                    self._show_error("Invalid token. Please verify before saving.")
                    return
            else:
                self._show_error("Please verify your token")
                return

        # Create or update the source
        if self.editing:
            # Update existing source
            self.source.name = name
            self.source.active = self.active_switch.get_active()
            if not self.source.config:
                self.source.config = {}
            self.source.config["npsso_token"] = self.auth_token
            self.source.config["download_images"] = self.download_images_switch.get_active()
        else:
            # Create new source
            from data import Source, SourceType
            self.source = Source(
                id="",  # Will be auto-generated by the handler
                name=name,
                path="",  # Not needed for PSN sources
                source_type=SourceType.PLAYSTATION,
                active=self.active_switch.get_active(),
                config={
                    "npsso_token": self.auth_token,
                    "download_images": self.download_images_switch.get_active()
                }
            )

        # Save and emit signal
        if self.source_handler and self.source_handler.save_source(self.source):
            self.emit("source-saved", self.source)
            self.close()
        else:
            self._show_error("Failed to save source")

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