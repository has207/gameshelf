import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GObject

from data import Source
from source_handler import SourceHandler
from controllers.source_item_controller import SourceItem
from controllers.source_dialog_controller import SourceDialog


class SourceListModel(GObject.Object):
    """Model for storing Source objects in a list view"""

    def __init__(self, source):
        super().__init__()
        self.source = source


@Gtk.Template(filename="layout/source_manager.ui")
class SourceManager(Gtk.Box):
    __gtype_name__ = "SourceManager"

    source_list_view = Gtk.Template.Child()
    source_selection_model = Gtk.Template.Child()
    add_source_button = Gtk.Template.Child()
    cancel_button = Gtk.Template.Child()
    scan_button = Gtk.Template.Child()

    def __init__(self, source_handler: SourceHandler, **kwargs):
        super().__init__(**kwargs)

        self.source_handler = source_handler

        # Set up the model for the list view
        self.list_store = Gio.ListStore.new(SourceListModel)
        self.source_selection_model.set_model(self.list_store)

        # Connect signal handlers
        self.add_source_button.connect("clicked", self._on_add_source_clicked)
        self.cancel_button.connect("clicked", self._on_cancel_clicked)
        self.scan_button.connect("clicked", self._on_scan_clicked)

        # Load sources
        self.load_sources()

    def load_sources(self):
        """Load sources from the source handler and populate the list view"""
        # Clear the list store
        self.list_store.remove_all()

        # Add sources to the list store
        sources = self.source_handler.load_sources()
        for source in sources:
            self.list_store.append(SourceListModel(source))

    @Gtk.Template.Callback()
    def setup_source_item(self, factory, list_item):
        """Set up a new item in the list view"""
        source_item = SourceItem(None, self.source_handler)
        list_item.set_child(source_item)

        # Connect signals
        source_item.connect("edit-source", self._on_edit_source)
        source_item.connect("delete-source", self._on_delete_source)

    @Gtk.Template.Callback()
    def bind_source_item(self, factory, list_item):
        """Bind a source to an item in the list view"""
        source_item = list_item.get_child()
        model_item = list_item.get_item()

        if model_item is not None and source_item is not None:
            source = model_item.source

            # Update the source in the item
            source_item.source = source

            # Update UI with source data
            source_item.name_label.set_text(source.name)
            source_item.path_label.set_text(source.path)
            source_item.active_switch.set_active(source.active)

    def _on_add_source_clicked(self, button):
        """Show the dialog to add a new source"""
        dialog = SourceDialog(source_handler=self.source_handler, parent=self.get_root())
        dialog.connect("source-saved", self._on_source_saved)
        dialog.show()

    def _on_edit_source(self, source_item, source):
        """Show the dialog to edit a source"""
        dialog = SourceDialog(source=source, source_handler=self.source_handler, parent=self.get_root())
        dialog.connect("source-saved", self._on_source_saved)
        dialog.show()

    def _on_delete_source(self, source_item, source):
        """Show a confirmation dialog to delete a source"""
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root(),
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete source '{source.name}'?"
        )
        dialog.format_secondary_text("This will not delete any games in your library but will remove the source configuration.")

        dialog.connect("response", self._on_delete_response, source)
        dialog.show()

    def _on_delete_response(self, dialog, response, source):
        """Handle the response from the delete confirmation dialog"""
        if response == Gtk.ResponseType.YES:
            if self.source_handler.remove_source(source):
                self.load_sources()  # Reload the list

        dialog.destroy()

    def _on_source_saved(self, dialog, source):
        """Handle a source being saved in the dialog"""
        self.load_sources()  # Reload the list

    def _on_cancel_clicked(self, button):
        """Close the dialog"""
        self.emit("closed")

    def _on_scan_clicked(self, button):
        """Scan the selected source for games"""
        selected = self.source_selection_model.get_selected()
        if selected == Gtk.INVALID_LIST_POSITION:
            self._show_error("Please select a source to scan")
            return

        # Get the selected source
        source_model = self.source_selection_model.get_selected_item()
        source = source_model.source

        # Start scanning with a progress dialog
        self._scan_source_with_progress(source)

    def _scan_source_with_progress(self, source):
        """Scan a source with a progress dialog"""
        # Create progress dialog
        dialog = Gtk.Dialog(
            title=f"Scanning {source.name}",
            transient_for=self.get_root(),
            modal=True,
            use_header_bar=True
        )

        # Add content
        content_area = dialog.get_content_area()
        content_area.set_spacing(12)
        content_area.set_margin_start(12)
        content_area.set_margin_end(12)
        content_area.set_margin_top(12)
        content_area.set_margin_bottom(12)

        label = Gtk.Label(label=f"Scanning {source.name}...")
        content_area.append(label)

        progress_bar = Gtk.ProgressBar()
        progress_bar.set_fraction(0)
        progress_bar.set_show_text(True)
        content_area.append(progress_bar)

        status_label = Gtk.Label(label="")
        content_area.append(status_label)

        dialog.show()

        # Function to update progress
        def update_progress(current, total, item_name):
            if total > 0:
                fraction = min(current / total, 1.0)
                progress_bar.set_fraction(fraction)
                progress_bar.set_text(f"{current} of {total}")

            if item_name:
                status_label.set_text(f"Processing: {item_name}")

            # If the scan is complete, close the dialog after a delay
            if current >= total and total > 0:
                # Show number of games added in status label
                status_label.set_text(f"Scan complete: {current} files processed")

                # Schedule a timeout to close the dialog
                GObject.timeout_add(1500, lambda: dialog.close() or False)

            return True

        # Create a source for progress updates
        self.cancel_scan = False

        # Use GLib.timeout_add for scanning in smaller chunks
        def start_scan():
            # Start the scan process
            self._do_scan(source, update_progress)
            return False  # Do not repeat

        # Start scanning after a short delay to let the UI update
        GObject.timeout_add(100, start_scan)

    def _do_scan(self, source, progress_callback):
        """Perform the actual scan"""
        # Scan the source
        added, errors = self.source_handler.scan_source(source, progress_callback)

        if errors:
            # Show errors in a dialog after scan completes
            GObject.timeout_add(1500, lambda: self._show_scan_errors(errors) or False)

        # Emit a signal that games were added
        self.emit("games-added", added)

        return False  # Don't call again

    def _show_scan_errors(self, errors):
        """Show errors from scanning in a dialog"""
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root(),
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK,
            text=f"Completed with {len(errors)} errors"
        )

        # Add a scrolled window for the errors
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(200)
        scrolled.set_vexpand(True)

        # Add a text view for the errors
        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        text_buffer = text_view.get_buffer()

        # Add the errors to the text buffer
        error_text = "\n".join(errors)
        text_buffer.set_text(error_text)

        scrolled.set_child(text_view)

        # Add the scrolled window to the dialog
        message_area = dialog.get_message_area()
        message_area.append(scrolled)

        dialog.show()

    def _show_error(self, message):
        """Show an error dialog"""
        dialog = Gtk.MessageDialog(
            transient_for=self.get_root(),
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message
        )
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.show()

    # Define custom signals
    __gsignals__ = {
        "closed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "games-added": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }