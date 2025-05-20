import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GObject

from data import SourceType
from controllers.source_type_dialog_controller import SourceTypeDialog
from controllers.rom_directory_source_dialog_controller import RomDirectorySourceDialog
from controllers.xbox_source_dialog_controller import XboxSourceDialog
from controllers.psn_source_dialog_controller import PSNSourceDialog
from controllers.epic_source_dialog_controller import EpicSourceDialog
from controllers.steam_source_dialog_controller import SteamSourceDialog

class SourceWizard:
    """
    A wizard for adding or editing sources.

    This class coordinates the flow between different source dialogs:
    1. First showing the source type selection dialog
    2. Then showing the appropriate type-specific dialog
    """

    def __init__(self, source_handler, parent, source=None):
        """
        Initialize the source wizard.

        Args:
            source_handler: The source handler
            parent: The parent window
            source: The source to edit, or None for a new source
        """
        self.source_handler = source_handler
        self.parent = parent
        self.source = source
        self.source_saved_callback = None

    def start(self, callback=None):
        """
        Start the wizard.

        Args:
            callback: Function to call with the saved source
        """
        self.source_saved_callback = callback

        if self.source:
            # For editing, skip the type selection and go directly to the appropriate dialog
            self._show_source_dialog_for_type(self.source.source_type)
        else:
            # For adding, show the type selection dialog first
            self._show_type_selection_dialog()

    def _show_type_selection_dialog(self):
        """Show the source type selection dialog"""
        dialog = SourceTypeDialog(parent=self.parent)
        dialog.connect("source-type-selected", lambda _, source_type: self._on_type_selected(source_type))
        dialog.present()

    def _on_type_selected(self, source_type):
        """
        Handle source type selection.

        Args:
            source_type: The selected SourceType
        """
        # After type is selected, show the appropriate source dialog
        self._show_source_dialog_for_type(source_type)

    def _show_source_dialog_for_type(self, source_type):
        """
        Show the appropriate source dialog for the given type.

        Args:
            source_type: The SourceType to show a dialog for
        """
        if source_type == SourceType.ROM_DIRECTORY:
            RomDirectorySourceDialog.show_dialog(
                source=self.source,
                source_handler=self.source_handler,
                parent=self.parent,
                callback=self._on_source_saved
            )
        elif source_type == SourceType.XBOX:
            XboxSourceDialog.show_dialog(
                source=self.source,
                source_handler=self.source_handler,
                parent=self.parent,
                callback=self._on_source_saved
            )
        elif source_type == SourceType.PLAYSTATION:
            PSNSourceDialog.show_dialog(
                source=self.source,
                source_handler=self.source_handler,
                parent=self.parent,
                callback=self._on_source_saved
            )
        elif source_type == SourceType.EPIC:
            EpicSourceDialog.show_dialog(
                source=self.source,
                source_handler=self.source_handler,
                parent=self.parent,
                callback=self._on_source_saved
            )
        elif source_type == SourceType.STEAM:
            dialog = SteamSourceDialog(parent=self.parent, source=self.source)
            dialog.connect("response", lambda dialog, response_id: self._on_steam_dialog_response(dialog, response_id))
            dialog.present()

    def _on_source_saved(self, source):
        """
        Handle source being saved.

        Args:
            source: The saved Source
        """
        # Call the callback if provided
        if self.source_saved_callback:
            self.source_saved_callback(source)

    def _on_steam_dialog_response(self, dialog, response_id):
        """
        Handle the response from the Steam source dialog.

        Args:
            dialog: The dialog that received the response
            response_id: The response ID
        """
        if response_id == Gtk.ResponseType.ACCEPT:
            # Get the source from the dialog
            source = dialog.get_source()

            # Save the source
            if self.source_handler.save_source(source):
                # Call the callback if provided
                if self.source_saved_callback:
                    self.source_saved_callback(source)

        # Close the dialog
        dialog.destroy()