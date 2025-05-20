import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GObject

from data import SourceType


@Gtk.Template(filename="layout/source_type_dialog.ui")
class SourceTypeDialog(Gtk.Dialog):
    __gtype_name__ = "SourceTypeDialog"

    type_list = Gtk.Template.Child()
    directory_row = Gtk.Template.Child()
    xbox_row = Gtk.Template.Child()
    playstation_row = Gtk.Template.Child()
    epic_row = Gtk.Template.Child()
    steam_row = Gtk.Template.Child()
    cancel_button = Gtk.Template.Child()
    next_button = Gtk.Template.Child()

    def __init__(self, parent=None, **kwargs):
        super().__init__(transient_for=parent, use_header_bar=True, **kwargs)

        # Connect button signals
        self.cancel_button.connect("clicked", self._on_cancel_clicked)
        self.next_button.connect("clicked", self._on_next_clicked)

        # Connect list selection signal
        self.type_list.connect("row-selected", self._on_row_selected)

        # Select first row by default
        self.type_list.select_row(self.directory_row)

        # Initially enable the next button
        self.next_button.set_sensitive(True)

    def _on_cancel_clicked(self, button):
        """Handle cancel button click"""
        self.response(Gtk.ResponseType.CANCEL)
        self.close()

    def _on_next_clicked(self, button):
        """Handle next button click"""
        selected_row = self.type_list.get_selected_row()
        source_type = self._get_source_type_from_row(selected_row)

        # Emit the source-type-selected signal with the selected type
        self.emit("source-type-selected", source_type)
        self.response(Gtk.ResponseType.OK)
        self.close()

    def _on_row_selected(self, list_box, row):
        """Handle row selection in the list"""
        # Enable the next button only if a row is selected
        self.next_button.set_sensitive(row is not None)

    def _get_source_type_from_row(self, row):
        """Convert the selected row to a SourceType"""
        if row == self.directory_row:
            return SourceType.ROM_DIRECTORY
        elif row == self.xbox_row:
            return SourceType.XBOX
        elif row == self.playstation_row:
            return SourceType.PLAYSTATION
        elif row == self.epic_row:
            return SourceType.EPIC
        elif row == self.steam_row:
            return SourceType.STEAM
        else:
            # Default to ROM_DIRECTORY if somehow none selected
            return SourceType.ROM_DIRECTORY

    @classmethod
    def show_dialog(cls, parent, callback):
        """
        Show the source type selection dialog

        Args:
            parent: The parent window
            callback: Function to call with the selected source type

        Returns:
            The dialog instance
        """
        dialog = cls(parent=parent)

        # Connect the source-type-selected signal to the callback
        dialog.connect("source-type-selected", lambda _, source_type: callback(source_type))

        # Show the dialog
        dialog.present()
        return dialog

# Define custom signals
GObject.type_register(SourceTypeDialog)
GObject.signal_new("source-type-selected", SourceTypeDialog,
                  GObject.SignalFlags.RUN_LAST, None, (object,))