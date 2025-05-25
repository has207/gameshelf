import gi
import logging
import threading

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gio, GObject

from data import Source, SourceType
from source_handler import SourceHandler
from sources.scanner_base import SourceScanner
from controllers.source_item_controller import SourceItem
from controllers.source_wizard_controller import SourceWizard
from controllers.progress_dialog_controller import ProgressDialog, ErrorDialog, ScanErrorsDialog
from progress_manager import get_progress_manager, ProgressType

# Set up logger
logger = logging.getLogger(__name__)


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
        self.progress_manager = get_progress_manager()

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
        logger.debug("load_sources called")

        # Clear the list store
        self.list_store.remove_all()
        logger.debug("list store cleared")

        # Add sources to the list store
        sources = self.source_handler.load_sources()
        logger.debug(f"Loaded {len(sources)} sources from disk")

        for source in sources:
            logger.debug(f"Adding source to list: {source.name} (ID: {source.id})")
            self.list_store.append(SourceListModel(source))

        logger.debug(f"List store now has {self.list_store.get_n_items()} items")

        # Refresh the UI
        self.source_list_view.queue_draw()
        logger.debug("Queued source list view for redraw")

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

            # Show platform information in the path label
            if source.config and "platform" in source.config:
                platform_value = source.config["platform"]
                source_item.path_label.set_text(f"Platform: {platform_value}")
            else:
                source_item.path_label.set_text("")

            source_item.active_switch.set_active(source.active)

    def _on_add_source_clicked(self, button):
        """Show the wizard to add a new source"""
        wizard = SourceWizard(source_handler=self.source_handler, parent=self.get_root())
        wizard.start(callback=self._on_source_saved)

    def _on_edit_source(self, source_item, source):
        """Show the wizard to edit a source"""
        wizard = SourceWizard(source_handler=self.source_handler, parent=self.get_root(), source=source)
        wizard.start(callback=self._on_source_saved)

    def _on_delete_source(self, source_item, source):
        """Show a confirmation dialog before deleting a source"""
        # Create a simple dialog for deletion confirmation
        dialog = Gtk.Dialog(
            title="Confirm Deletion",
            transient_for=self.get_root(),
            modal=True
        )

        # Add Cancel and Delete buttons
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        delete_button = dialog.add_button("Delete", Gtk.ResponseType.YES)
        delete_button.add_css_class("destructive-action")

        # Set up the content area
        content_area = dialog.get_content_area()
        content_area.set_spacing(10)
        content_area.set_margin_start(20)
        content_area.set_margin_end(20)
        content_area.set_margin_top(20)
        content_area.set_margin_bottom(20)

        # Create the confirmation message layout
        message_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        # Add warning icon
        icon = Gtk.Image.new_from_icon_name("dialog-warning")
        icon.set_pixel_size(32)
        message_box.append(icon)

        # Add text container
        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # Primary text
        title_label = Gtk.Label()
        title_label.set_markup(f"<b>Delete source '{source.name}'?</b>")
        title_label.set_halign(Gtk.Align.START)
        title_label.set_wrap(True)
        text_box.append(title_label)

        # Secondary text
        desc_label = Gtk.Label(label="WARNING: This will remove all games associated with this source from your library!")
        desc_label.set_halign(Gtk.Align.START)
        desc_label.set_wrap(True)
        text_box.append(desc_label)

        message_box.append(text_box)
        content_area.append(message_box)

        # Connect response handler
        def on_response(dialog, response):
            if response == Gtk.ResponseType.YES:
                # Delete the source
                result = self.source_handler.remove_source(source)

                # Reload the sources list if successful
                if result:
                    self.load_sources()
                    # Emit signal to notify that a source was removed, so sidebar can be refreshed
                    self.emit("source-removed")

            # Always close the dialog
            dialog.destroy()

        # Connect the response signal
        dialog.connect("response", on_response)

        # Show the dialog
        dialog.present()

    def _on_source_saved(self, source):
        """Handle a source being saved in the wizard"""
        self.load_sources()  # Reload the list

    def _on_cancel_clicked(self, button):
        """Close the dialog"""
        self.emit("closed")

    def _on_scan_clicked(self, button):
        """Scan the selected source for games"""
        selected = self.source_selection_model.get_selected()
        if selected == Gtk.INVALID_LIST_POSITION:
            error_dialog = ErrorDialog("Please select a source to scan", transient_for=self.get_root())
            error_dialog.present()
            return

        # Get the selected source
        source_model = self.source_selection_model.get_selected_item()
        source = source_model.source

        # Start scanning with a progress dialog
        self._scan_source_with_progress(source)

    def _scan_source_with_progress(self, source):
        """Scan a source with unified progress dialog"""
        # Generate unique operation ID
        operation_id = f"scan_{source.source_type.value}_{source.id}"

        # Determine progress type
        progress_type = ProgressType.DETERMINATE if source.source_type in [SourceType.STEAM, SourceType.ROM_DIRECTORY] else ProgressType.INDETERMINATE

        # Create simple progress dialog with proper centering
        dialog = Gtk.Dialog(
            transient_for=self.get_root(),
            modal=True  # Keep modal to maintain centering
        )
        dialog.set_decorated(False)  # Remove title bar
        dialog.set_default_size(450, -1)

        # Add content
        content_area = dialog.get_content_area()
        content_area.add_css_class("dialog-content")

        # Start progress operation
        progress_callback = self.progress_manager.start_operation(
            operation_id=operation_id,
            operation_name=f"Scanning {source.name}",
            progress_type=progress_type,
            cancellable=True
        )

        # Create and add progress widget
        progress_widget = self.progress_manager.create_progress_widget(operation_id)
        content_area.append(progress_widget)

        # Track dialog state
        dialog_active = [True]

        # Connect to progress manager signals to handle completion/cancellation
        def on_operation_completed(manager, op_id):
            if op_id == operation_id and dialog_active[0]:
                # Auto-close after delay
                GObject.timeout_add(2000, lambda: dialog.destroy() if dialog_active[0] else False)

        def on_operation_cancelled(manager, op_id):
            if op_id == operation_id and dialog_active[0]:
                dialog_active[0] = False
                dialog.destroy()

        def on_operation_error(manager, op_id, error_msg):
            if op_id == operation_id and dialog_active[0]:
                # Keep dialog open briefly to show error, then auto-close
                GObject.timeout_add(3000, lambda: dialog.destroy() if dialog_active[0] else False)

        self.progress_manager.connect("operation-completed", on_operation_completed)
        self.progress_manager.connect("operation-cancelled", on_operation_cancelled)
        self.progress_manager.connect("operation-error", on_operation_error)

        # Show dialog (keep modal for proper centering)
        dialog.present()

        # Start scanning in background thread
        def scan_thread_func():
            try:
                scanner = self.source_handler.get_scanner(source.source_type, source.id)

                # Create adapter callback that converts to unified format
                def unified_progress_callback(current, total, message):
                    if not dialog_active[0] or self.progress_manager.is_operation_cancelled(operation_id):
                        return
                    progress_callback(current, total, message)

                # Perform the scan
                added_count, errors = scanner.scan(source, unified_progress_callback)

                if self.progress_manager.is_operation_cancelled(operation_id):
                    progress_callback.complete("Cancelled")
                    return

                # Handle different return formats
                if isinstance(added_count, tuple):
                    # PSN returns (added_count, updated_count)
                    actual_added, updated_count = added_count
                    total_changes = actual_added + updated_count
                    changes_message = []
                    if actual_added > 0:
                        changes_message.append(f"Added {actual_added} games")
                    if updated_count > 0:
                        changes_message.append(f"Updated {updated_count} games")

                    message = ", ".join(changes_message) if changes_message else "No changes"
                    progress_callback.complete(f"Complete: {message}")

                    if total_changes > 0:
                        GObject.idle_add(lambda: self.emit("games-added", total_changes))
                else:
                    # Standard return format
                    progress_callback.complete(f"Complete: Added {added_count} games")

                    if added_count > 0:
                        GObject.idle_add(lambda: self.emit("games-added", added_count))

                # Show errors dialog if any
                if errors:
                    def show_errors():
                        if dialog_active[0]:
                            error_dialog = ScanErrorsDialog(errors, transient_for=self.get_root())
                            error_dialog.present()
                        return False

                    error_summary = f"{len(errors)} errors occurred"
                    logger.warning(f"Scan completed with errors: {errors}")
                    progress_callback.update_message(error_summary)
                    GObject.timeout_add(2000, show_errors)

                # Dialog will auto-close via signal handler

            except Exception as e:
                logger.error(f"Error in scan thread: {e}")
                progress_callback.error(str(e))

        scan_thread = threading.Thread(target=scan_thread_func)
        scan_thread.daemon = True
        scan_thread.start()

        return

    # Define custom signals
    __gsignals__ = {
        "closed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "games-added": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
        "source-removed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

