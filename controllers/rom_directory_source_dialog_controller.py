import gi
import os

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GObject

from data import Source, SourceType
from data_mapping import Platforms


@Gtk.Template(filename="layout/rom_directory_source_dialog.ui")
class RomDirectorySourceDialog(Gtk.Dialog):
    __gtype_name__ = "RomDirectorySourceDialog"

    name_entry = Gtk.Template.Child()
    path_entry = Gtk.Template.Child()
    platform_dropdown = Gtk.Template.Child()
    extensions_entry = Gtk.Template.Child()
    active_switch = Gtk.Template.Child()
    browse_button = Gtk.Template.Child()
    cancel_button = Gtk.Template.Child()
    save_button = Gtk.Template.Child()

    def __init__(self, source=None, source_handler=None, parent=None, **kwargs):
        super().__init__(transient_for=parent, use_header_bar=True, **kwargs)

        self.source = source
        self.source_handler = source_handler
        self.editing = source is not None

        # Set up platform dropdown
        self._setup_platform_dropdown()

        # Connect signal handlers
        self.browse_button.connect("clicked", self._on_browse_clicked)
        self.cancel_button.connect("clicked", self._on_cancel_clicked)
        self.save_button.connect("clicked", self._on_save_clicked)

        # If editing an existing source, fill the form with its data
        if self.editing:
            self.set_title("Edit ROM Directory Source")
            self.name_entry.set_text(source.name)
            self.path_entry.set_text(source.path)

            # Set extensions
            if source.file_extensions:
                self.extensions_entry.set_text(", ".join(source.file_extensions))

            # Set active state
            self.active_switch.set_active(source.active)

            # Set platform if it exists in the source config
            if source.config and "platform" in source.config:
                platform_value = source.config["platform"]
                self._select_platform_by_value(platform_value)
        else:
            self.set_title("Add ROM Directory Source")

            # Default values
            self.name_entry.set_text("ROMs")
            
            # Select first platform by default
            self.platform_dropdown.set_selected(0)

    def _setup_platform_dropdown(self):
        """Set up the platform dropdown with all available platforms"""
        # Create a string list to populate the dropdown
        platform_model = Gtk.StringList.new()
        
        # Sort platforms alphabetically by display name
        platforms = sorted([p for p in Platforms], key=lambda p: p.value)
        
        # Add each platform to the model and store enum values in a dict
        self.platform_mapping = {}
        for i, platform in enumerate(platforms):
            platform_model.append(platform.value)
            self.platform_mapping[i] = platform
            
        # Set the model for the dropdown
        self.platform_dropdown.set_model(platform_model)
    
    def _select_platform_by_value(self, platform_value):
        """Find and select a platform in the dropdown by its value"""
        # Try to find the platform in our mapping
        for i, platform in self.platform_mapping.items():
            if platform.value == platform_value:
                self.platform_dropdown.set_selected(i)
                return
            
        # If not found, just select the first one
        self.platform_dropdown.set_selected(0)

    def _on_browse_clicked(self, button):
        """Handle browse button click"""
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Select ROM Folder")

        # Configure for folder selection
        dialog.set_initial_folder(Gio.File.new_for_path(os.path.expanduser("~")))

        # Show the dialog
        dialog.select_folder(self, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        """Handle folder selection"""
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                self.path_entry.set_text(folder.get_path())
        except Exception as e:
            print(f"Error selecting folder: {e}")

    def _on_cancel_clicked(self, button):
        """Handle cancel button click"""
        self.response(Gtk.ResponseType.CANCEL)
        self.close()

    def _on_save_clicked(self, button):
        """Handle save button click"""
        # Validate form
        name = self.name_entry.get_text().strip()
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

        # Get selected platform
        selected_index = self.platform_dropdown.get_selected()
        if selected_index < 0:
            self._show_error("Platform selection is required")
            return
            
        platform = self.platform_mapping[selected_index]

        # Process extensions
        extensions = []
        extensions_text = self.extensions_entry.get_text().strip()
        if extensions_text:
            extensions = [ext.strip() for ext in extensions_text.split(",") if ext.strip()]

        # Get active state
        active = self.active_switch.get_active()

        # Create or update the source
        if self.editing:
            # Update existing source
            self.source.name = name
            self.source.path = path
            self.source.file_extensions = extensions
            self.source.active = active
            
            # Update config with platform
            if not self.source.config:
                self.source.config = {}
            self.source.config["platform"] = platform.value
        else:
            # Create new source with ROM_DIRECTORY type
            self.source = Source(
                id="",  # Will be auto-generated by the handler
                name=name,
                path=path,
                source_type=SourceType.ROM_DIRECTORY,
                active=active,
                file_extensions=extensions,
                config={"platform": platform.value}
            )

        # Save and emit signal
        if self.source_handler and self.source_handler.save_source(self.source):
            self.emit("source-saved", self.source)
            self.response(Gtk.ResponseType.OK)
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
        Show the ROM directory source dialog

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
GObject.type_register(RomDirectorySourceDialog)
GObject.signal_new("source-saved", RomDirectorySourceDialog,
                  GObject.SignalFlags.RUN_LAST, None, (object,))