import gi
import os

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GObject

from data import Source, SourceType, RomPath
from data_mapping import Platforms
from controllers.rom_path_item_controller import RomPathItem


@Gtk.Template(filename="layout/rom_directory_source_dialog.ui")
class RomDirectorySourceDialog(Gtk.Dialog):
    __gtype_name__ = "RomDirectorySourceDialog"

    name_entry = Gtk.Template.Child()
    platform_dropdown = Gtk.Template.Child()
    active_switch = Gtk.Template.Child()
    paths_container = Gtk.Template.Child()
    add_path_button = Gtk.Template.Child()
    cancel_button = Gtk.Template.Child()
    save_button = Gtk.Template.Child()

    def __init__(self, source=None, source_handler=None, parent=None, **kwargs):
        super().__init__(transient_for=parent, use_header_bar=True, **kwargs)

        self.source = source
        self.source_handler = source_handler
        self.editing = source is not None

        # Track whether we need to disable extensions for Wii U games
        self.is_wiiu = False

        # Set up platform dropdown
        self._setup_platform_dropdown()

        # Connect signal handlers
        self.add_path_button.connect("clicked", self._on_add_path_clicked)
        self.cancel_button.connect("clicked", self._on_cancel_clicked)
        self.save_button.connect("clicked", self._on_save_clicked)

        # Connect platform selection handler to enable/disable extensions for Wii U
        self.platform_dropdown.connect("notify::selected", self._on_platform_changed)

        # If editing an existing source, fill the form with its data
        if self.editing:
            self.set_title("Edit ROM Directory Source")
            self.name_entry.set_text(source.name)

            # Set active state
            self.active_switch.set_active(source.active)

            # Set platform if it exists in the source config
            if source.config and "platform" in source.config:
                platform_value = source.config["platform"]
                self._select_platform_by_value(platform_value)
                # Update extensions field state based on platform
                self._update_extensions_field_state()

            # Add existing paths
            if hasattr(source, "rom_paths") and source.rom_paths:
                for rom_path in source.rom_paths:
                    self._add_path_item(rom_path)
            else:
                # Add a default path row
                self._add_path_item()
        else:
            self.set_title("Add ROM Directory Source")

            # Default values
            self.name_entry.set_text("ROMs")

            # Select first platform by default
            self.platform_dropdown.set_selected(0)

            # Update extensions field state based on initial platform
            self._update_extensions_field_state()

            # Add a default path row
            self._add_path_item()

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

    def _on_platform_changed(self, dropdown, param):
        """Handle platform selection change"""
        self._update_extensions_field_state()

    def _update_extensions_field_state(self):
        """Update the state of extension fields for all path items based on the selected platform"""
        selected_index = self.platform_dropdown.get_selected()
        if selected_index < 0:
            return

        platform = self.platform_mapping[selected_index]

        # For Wii U, disable extensions field since we'll detect games based on folder structure
        self.is_wiiu = (platform == Platforms.NINTENDO_WIIU)

        # Update all path items in the container
        for child in self.paths_container:
            if isinstance(child, RomPathItem):
                child.set_extensions_sensitive(not self.is_wiiu)

    def _add_path_item(self, rom_path=None):
        """Add a new path item to the container"""
        path_item = RomPathItem(rom_path, not self.is_wiiu)
        path_item.connect("remove-requested", self._on_path_remove_requested)
        self.paths_container.append(path_item)
        return path_item

    def _on_add_path_clicked(self, button):
        """Handle add path button click"""
        self._add_path_item()

    def _on_path_remove_requested(self, path_item, sender):
        """Handle path item removal request"""
        # Don't remove the last path
        if len(list(self.paths_container)) > 1:
            self.paths_container.remove(path_item)

    def _on_cancel_clicked(self, button):
        """Handle cancel button click"""
        self.response(Gtk.ResponseType.CANCEL)
        self.close()

    def _on_save_clicked(self, button):
        """Handle save button click"""
        # Validate form
        name = self.name_entry.get_text().strip()

        if not name:
            self._show_error("Name is required")
            return

        # Get selected platform
        selected_index = self.platform_dropdown.get_selected()
        if selected_index < 0:
            self._show_error("Platform selection is required")
            return

        platform = self.platform_mapping[selected_index]

        # Collect all path data and validate
        rom_paths = []
        path_errors = []

        for child in self.paths_container:
            if isinstance(child, RomPathItem):
                path_data = child.get_path_data()

                # Validate path
                if not path_data.path:
                    path_errors.append("Path is required")
                    continue

                if not os.path.isdir(path_data.path):
                    path_errors.append(f"Path '{path_data.path}' must be a valid directory")
                    continue

                rom_paths.append(path_data)

        if path_errors:
            self._show_error("\n".join(path_errors))
            return

        if not rom_paths:
            self._show_error("At least one valid path is required")
            return

        # Get active state
        active = self.active_switch.get_active()

        # Create or update the source
        if self.editing:
            # Update existing source
            self.source.name = name
            self.source.active = active
            self.source.rom_paths = rom_paths

            # Update config with platform
            if not self.source.config:
                self.source.config = {}
            self.source.config["platform"] = platform.value
        else:
            # Create new source with ROM_DIRECTORY type
            self.source = Source(
                id="",  # Will be auto-generated by the handler
                name=name,
                source_type=SourceType.ROM_DIRECTORY,
                active=active,
                rom_paths=rom_paths,
                config={
                    "platform": platform.value
                }
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
            text="Error",
            secondary_text=message
        )
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