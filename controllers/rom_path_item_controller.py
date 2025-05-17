import gi
import os

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GObject

from data import RomPath


@Gtk.Template(filename="layout/rom_path_item.ui")
class RomPathItem(Gtk.Box):
    __gtype_name__ = "RomPathItem"

    path_entry = Gtk.Template.Child()
    extensions_entry = Gtk.Template.Child()
    name_regex_entry = Gtk.Template.Child()
    browse_button = Gtk.Template.Child()
    remove_button = Gtk.Template.Child()

    def __init__(self, rom_path=None, extensions_sensitive=True, **kwargs):
        super().__init__(**kwargs)

        self.rom_path = rom_path

        # Connect handlers
        self.browse_button.connect("clicked", self._on_browse_clicked)
        self.remove_button.connect("clicked", self._on_remove_clicked)

        # Set initial values if path is provided
        if rom_path:
            self.path_entry.set_text(rom_path.path)

            if rom_path.file_extensions:
                self.extensions_entry.set_text(", ".join(rom_path.file_extensions))

            if rom_path.name_regex:
                self.name_regex_entry.set_text(rom_path.name_regex)
            else:
                # Default regex that strips file extension
                self.name_regex_entry.set_text("^(.+?)(\.[^.]+)?$")
        else:
            # Default regex that strips file extension
            self.name_regex_entry.set_text("^(.+?)(\.[^.]+)?$")

        # Set extensions field sensitivity
        self.set_extensions_sensitive(extensions_sensitive)

    def set_extensions_sensitive(self, sensitive):
        """Enable or disable the extensions field"""
        self.extensions_entry.set_sensitive(sensitive)
        if not sensitive:
            self.extensions_entry.set_text("")
            self.extensions_entry.set_tooltip_text(
                "File extensions not needed for Wii U games. " +
                "Games are detected by folders containing 'content', 'meta', and 'code' subdirectories."
            )
        else:
            self.extensions_entry.set_tooltip_text("")

    def get_path_data(self):
        """Get the current path data from the form"""
        path = self.path_entry.get_text().strip()

        # Process extensions
        extensions = []
        extensions_text = self.extensions_entry.get_text().strip()
        if extensions_text:
            extensions = [ext.strip() for ext in extensions_text.split(",") if ext.strip()]

        # Get name regex
        name_regex = self.name_regex_entry.get_text().strip()
        if not name_regex:
            # Default regex that strips file extension
            name_regex = "^(.+?)(\.[^.]+)?$"

        return RomPath(
            path=path,
            file_extensions=extensions,
            name_regex=name_regex
        )

    def _on_browse_clicked(self, button):
        """Handle browse button click"""
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Select ROM Folder")

        # Configure for folder selection
        dialog.set_initial_folder(Gio.File.new_for_path(os.path.expanduser("~")))

        # Show the dialog
        dialog.select_folder(self.get_root(), None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        """Handle folder selection"""
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                self.path_entry.set_text(folder.get_path())
        except Exception as e:
            print(f"Error selecting folder: {e}")

    def _on_remove_clicked(self, button):
        """Handle remove button click"""
        self.emit("remove-requested", self)


# Define custom signals
GObject.type_register(RomPathItem)
GObject.signal_new("remove-requested", RomPathItem,
                  GObject.SignalFlags.RUN_LAST, None, (object,))