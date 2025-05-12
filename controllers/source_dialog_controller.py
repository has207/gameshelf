import gi
import os

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GObject

from data import Source, SourceType
from sources.xbox_client import XboxLibrary


@Gtk.Template(filename="layout/source_dialog.ui")
class SourceDialog(Gtk.Dialog):
    __gtype_name__ = "SourceDialog"

    name_entry = Gtk.Template.Child()
    path_entry = Gtk.Template.Child()
    extensions_entry = Gtk.Template.Child()
    type_dropdown = Gtk.Template.Child()
    active_switch = Gtk.Template.Child()

    auth_label = Gtk.Template.Child()
    auth_button = Gtk.Template.Child()

    browse_button = Gtk.Template.Child()
    cancel_button = Gtk.Template.Child()
    save_button = Gtk.Template.Child()

    def __init__(self, source=None, source_handler=None, parent=None, **kwargs):
        super().__init__(transient_for=parent, use_header_bar=True, **kwargs)

        self.source = source
        self.source_handler = source_handler
        self.editing = source is not None

        # Set up the type dropdown with available source types
        string_list = Gtk.StringList()
        for source_type in SourceType:
            string_list.append(source_type.name.capitalize())
        self.type_dropdown.set_model(string_list)

        # Connect signal handlers
        self.browse_button.connect("clicked", self._on_browse_clicked)
        self.cancel_button.connect("clicked", self._on_cancel_clicked)
        self.save_button.connect("clicked", self._on_save_clicked)
        self.auth_button.connect("clicked", self._on_auth_clicked)

        # Setup type dropdown callback to show/hide auth button
        self.type_dropdown.connect("notify::selected", self._on_type_changed)

        # Initially update UI based on selected type
        self._on_type_changed(self.type_dropdown, None)

        # If editing an existing source, fill the form with its data
        if self.editing:
            self.set_title("Edit Source")
            self.name_entry.set_text(source.name)
            self.path_entry.set_text(source.path)

            # Set the active type in the dropdown
            for i, source_type in enumerate(SourceType):
                if source_type == source.source_type:
                    self.type_dropdown.set_selected(i)
                    break

            # Set extensions
            if source.file_extensions:
                self.extensions_entry.set_text(", ".join(source.file_extensions))

            # Set active state
            self.active_switch.set_active(source.active)
        else:
            self.set_title("Add Source")

    def _on_browse_clicked(self, button):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Select Folder")

        # Configure for folder selection
        dialog.set_initial_folder(Gio.File.new_for_path(os.path.expanduser("~")))

        # Show the dialog
        dialog.select_folder(self, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                self.path_entry.set_text(folder.get_path())
        except Exception as e:
            print(f"Error selecting folder: {e}")

    def _on_cancel_clicked(self, button):
        self.close()

    def _on_type_changed(self, dropdown, param):
        """Show/hide authentication button based on selected source type"""
        selected_type_index = dropdown.get_selected()
        if selected_type_index >= 0:
            source_type = list(SourceType)[selected_type_index]

            # Show authentication button for Xbox source type
            if source_type == SourceType.XBOX:
                # Show authentication controls
                self.auth_label.set_visible(True)
                self.auth_button.set_visible(True)

                # Path entry is not used for Xbox, so auto-fill and disable it
                self.path_entry.set_sensitive(False)
                self.path_entry.set_text("xbox://")  # Pre-fill with placeholder
                self.path_entry.set_placeholder_text("Not needed for Xbox source")
                self.browse_button.set_sensitive(False)

                # Extensions not used for Xbox, auto-fill and disable
                self.extensions_entry.set_sensitive(False)
                self.extensions_entry.set_text("")  # Clear any existing text
                self.extensions_entry.set_placeholder_text("Not needed for Xbox source")

                # Suggest a default name if field is empty
                if not self.name_entry.get_text():
                    self.name_entry.set_text("Xbox Game Library")

                # Update the auth button state based on the current authentication
                self._update_auth_button_state()
            else:
                # Hide authentication controls
                self.auth_label.set_visible(False)
                self.auth_button.set_visible(False)

                # Enable path selection for directory sources
                self.path_entry.set_sensitive(True)
                self.path_entry.set_text("")  # Clear any Xbox placeholder
                self.path_entry.set_placeholder_text("")
                self.browse_button.set_sensitive(True)

                # Enable extensions field for directory sources
                self.extensions_entry.set_sensitive(True)
                self.extensions_entry.set_placeholder_text("exe,lnk,url,desktop (comma separated)")

    def _update_auth_button_state(self):
        """Update the authentication button state and label based on auth status"""
        # Use existing source ID if editing, otherwise we can't check auth until source is created
        source_id = self.source.id if self.editing else None

        if not source_id:
            # If not editing, we'll need to create the source first before authenticating
            self.auth_button.set_label("Authenticate with Xbox")
            self.auth_button.set_tooltip_text("Save the source first, then authenticate")
            return

        # Create XboxLibrary instance with token dir from source handler
        try:
            if self.source_handler:
                tokens_dir = self.source_handler.ensure_secure_token_storage(source_id)
                xbox = XboxLibrary(token_dir=tokens_dir)

                # Check if authenticated
                auth_status = xbox.is_authenticated()

                if auth_status:
                    self.auth_button.set_label("✓ Authenticated with Xbox")
                    self.auth_button.set_tooltip_text("Already authenticated, click to re-authenticate")
                else:
                    self.auth_button.set_label("Authenticate with Xbox")
                    self.auth_button.set_tooltip_text("Click to start Xbox authentication")
            else:
                self.auth_button.set_label("Authenticate with Xbox")
                self.auth_button.set_tooltip_text("Source handler not available")
        except Exception as e:
            print(f"Error checking authentication: {e}")
            self.auth_button.set_label("Authenticate with Xbox")
            self.auth_button.set_tooltip_text("Error checking authentication status")

    def _on_auth_clicked(self, button):
        """Handle Xbox authentication button click"""
        # For authentication, we need a valid source ID

        if not self.editing:
            # If creating a new source, we need to save it first to get an ID
            name = self.name_entry.get_text().strip()
            if not name:
                self._show_error("Please enter a name before authenticating")
                return

            # Create and save a temporary source to get an ID
            selected_type_index = self.type_dropdown.get_selected()
            source_type = list(SourceType)[selected_type_index]

            # Create a temporary source
            temp_source = Source(
                id="",  # Will be assigned by source handler
                name=name,
                path="xbox://",  # Placeholder
                source_type=source_type
            )

            # Save the source to get an ID
            if not self.source_handler.save_source(temp_source):
                self._show_error("Failed to create temporary source")
                return

            # Use the new ID
            self.source = temp_source
            source_id = temp_source.id
            self.editing = True  # Now we're editing the new source

            # Update dialog title to reflect we're now editing
            self.set_title("Edit Source")
        else:
            # We already have a source ID
            source_id = self.source.id

        # Initialize Xbox client with token directory
        if self.source_handler:
            try:
                tokens_dir = self.source_handler.ensure_secure_token_storage(source_id)
                xbox = XboxLibrary(token_dir=tokens_dir)
            except Exception as e:
                self._show_error(f"Error setting up token directory: {e}")
                return
        else:
            self._show_error("Source handler not available")
            return

        from gi.repository import GLib

        # Start authentication process
        self.auth_button.set_sensitive(False)
        self.auth_button.set_label("Authenticating...")

        # Start a timeout to check for authentication completion
        # This allows the UI to remain responsive without threading
        def auth_timeout_handler():
            try:
                # Try to authenticate
                success = xbox.authenticate()

                # Update UI based on result
                self.auth_button.set_sensitive(True)

                if success:
                    self.auth_button.set_label("✓ Authenticated")
                    self._simple_message_dialog(
                        "Authentication Successful",
                        "You have successfully authenticated with Xbox."
                    )
                    self._update_auth_button_state()
                else:
                    self.auth_button.set_label("Authenticate with Xbox")
                    self._simple_message_dialog(
                        "Authentication Failed",
                        "Authentication failed or was cancelled.",
                        Gtk.MessageType.ERROR
                    )
            except Exception as e:
                # Handle errors
                self.auth_button.set_sensitive(True)
                self.auth_button.set_label("Authenticate with Xbox")
                self._simple_message_dialog(
                    "Authentication Error",
                    f"Error during authentication: {e}",
                    Gtk.MessageType.ERROR
                )

            # Don't repeat the timeout
            return False

        # Use a timeout to run authentication after a brief delay
        # This allows the UI to update first
        GLib.timeout_add(100, auth_timeout_handler)

    def _on_save_clicked(self, button):
        # Validate form
        name = self.name_entry.get_text().strip()

        # Extract source type
        selected_type_index = self.type_dropdown.get_selected()
        source_type = list(SourceType)[selected_type_index]

        # Different validation based on source type
        if source_type == SourceType.DIRECTORY:
            # For directory sources, we need both name and path
            path = self.path_entry.get_text().strip()

            if not name:
                self._show_error("Name is required")
                return

            if not path:
                self._show_error("Path is required")
                return

            if not os.path.isdir(path):
                self._show_error("Path must be a valid directory")
                return

        elif source_type == SourceType.XBOX:
            # For Xbox sources, we only need name (can be auto-generated) and authentication
            if not name:
                # Auto-generate a name if not provided
                name = "Xbox Game Library"

            # For Xbox source, we need an ID to access token storage
            # This ID is assigned when source is first saved, or existing if editing
            source_id = self.source.id if self.editing else None

            # Check if authentication is needed
            # Only require authentication if:
            # 1. This is a new source (not editing), or
            # 2. We're changing a different source type to Xbox
            auth_needed = False

            if not self.editing:
                # New source needs authentication
                auth_needed = True
            elif self.source.source_type != SourceType.XBOX:
                # Changed source type to Xbox
                auth_needed = True

            if auth_needed and self.source_handler:
                if source_id:  # We already have a source ID
                    tokens_dir = self.source_handler.ensure_secure_token_storage(source_id)
                    xbox = XboxLibrary(token_dir=tokens_dir)

                    if not xbox.is_authenticated():
                        self._show_error("Please authenticate with Xbox before saving")
                        return
                else:
                    # Cannot authenticate without a source ID
                    self._show_error("Please create and authenticate the source first")
                    return

            # Set a placeholder path for Xbox sources (not actually used)
            path = "xbox://"

        # Extract extensions
        extensions_text = self.extensions_entry.get_text().strip()
        extensions = []
        if extensions_text:
            extensions = [ext.strip() for ext in extensions_text.split(",") if ext.strip()]

        # Get active state
        active = self.active_switch.get_active()

        # Create or update the source
        if self.editing:
            # Update existing source
            self.source.name = name
            self.source.path = path
            self.source.source_type = source_type
            self.source.file_extensions = extensions
            self.source.active = active
        else:
            # Create new source
            self.source = Source(
                id="",  # Will be auto-generated by the handler
                name=name,
                path=path,
                source_type=source_type,
                active=active,
                file_extensions=extensions
            )

        # Save and emit signal
        if self.source_handler.save_source(self.source):
            self.emit("source-saved", self.source)
            self.close()
        else:
            self._show_error("Failed to save source")

    def _show_error(self, message):
        """Show an error message dialog with GTK 4.0 style dialog"""
        self._simple_message_dialog("Error", message, Gtk.MessageType.ERROR)

    def _show_message(self, title, message):
        """Show an info message dialog with GTK 4.0 style dialog"""
        self._simple_message_dialog(title, message, Gtk.MessageType.INFO)

    def _simple_message_dialog(self, title, message, message_type=Gtk.MessageType.INFO):
        """Create a simple message dialog compatible with GTK 4.0"""
        # Create a custom dialog
        dialog = Gtk.Dialog()
        dialog.set_title(title)
        dialog.set_transient_for(self)
        dialog.set_modal(True)

        # Add OK button manually
        dialog.add_button("OK", Gtk.ResponseType.OK)

        # Create content
        content_area = dialog.get_content_area()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        # Create appropriate icon based on message type
        icon_name = "dialog-information"
        if message_type == Gtk.MessageType.ERROR:
            icon_name = "dialog-error"
        elif message_type == Gtk.MessageType.WARNING:
            icon_name = "dialog-warning"
        elif message_type == Gtk.MessageType.QUESTION:
            icon_name = "dialog-question"

        # Create horizontal box for icon and text
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        # Add icon
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(48)
        hbox.append(icon)

        # Add message text
        msg_label = Gtk.Label(label=message)
        msg_label.set_wrap(True)
        msg_label.set_selectable(True)
        msg_label.set_max_width_chars(60)
        msg_label.set_halign(Gtk.Align.START)
        msg_label.set_valign(Gtk.Align.CENTER)
        msg_label.set_hexpand(True)
        hbox.append(msg_label)

        box.append(hbox)
        content_area.append(box)

        # Show the dialog and wait for response
        dialog.set_default_size(400, -1)
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()

    # Define custom signals
    __gsignals__ = {
        "source-saved": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }