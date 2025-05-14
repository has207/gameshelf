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
        print("DEBUG: load_sources called")

        # Clear the list store
        self.list_store.remove_all()
        print("DEBUG: list store cleared")

        # Add sources to the list store
        sources = self.source_handler.load_sources()
        print(f"DEBUG: Loaded {len(sources)} sources from disk")

        for source in sources:
            print(f"DEBUG: Adding source to list: {source.name} (ID: {source.id})")
            self.list_store.append(SourceListModel(source))

        print(f"DEBUG: List store now has {self.list_store.get_n_items()} items")

        # Refresh the UI
        self.source_list_view.queue_draw()
        print("DEBUG: Queued source list view for redraw")

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
        desc_label = Gtk.Label(label="This will remove the source configuration.\nGames imported from this source will remain in your library.")
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
            self._show_error("Please select a source to scan")
            return

        # Get the selected source
        source_model = self.source_selection_model.get_selected_item()
        source = source_model.source

        # Start scanning with a progress dialog
        self._scan_source_with_progress(source)

    def _scan_source_with_progress(self, source):
        """Scan a source with a progress dialog"""
        # Use a specialized approach for Xbox sources
        if source.source_type == SourceType.XBOX:
            # For Xbox sources, we'll use a simpler non-modal dialog with a close button
            dialog = Gtk.Dialog(
                title=f"Xbox Library Sync: {source.name}",
                transient_for=self.get_root(),
                modal=False
            )

            # Add a close button
            dialog.add_button("Close", Gtk.ResponseType.CLOSE)

            # Add content
            content_area = dialog.get_content_area()
            content_area.set_spacing(12)
            content_area.set_margin_start(12)
            content_area.set_margin_end(12)
            content_area.set_margin_top(12)
            content_area.set_margin_bottom(12)

            # Add explanatory label
            label = Gtk.Label()
            label.set_markup(f"<b>Syncing games from Xbox Library</b>")
            label.set_margin_bottom(10)
            content_area.append(label)

            status_label = Gtk.Label(label="Connecting to Xbox API...")
            status_label.set_wrap(True)
            status_label.set_width_chars(40)
            status_label.set_justify(Gtk.Justification.LEFT)
            status_label.set_halign(Gtk.Align.START)
            content_area.append(status_label)

            # Activity indicator
            spinner = Gtk.Spinner()
            spinner.set_size_request(32, 32)
            spinner.start()
            content_area.append(spinner)

            # Connect close response
            dialog.connect("response", lambda d, r: d.destroy())

            # Show the dialog
            dialog.set_default_size(400, -1)
            dialog.present()

            # Define a progress callback for Xbox
            def xbox_progress_callback(current, total, item_name):
                # Use GLib.idle_add to ensure UI updates happen in the main thread
                def update_ui():
                    progress_text = ""
                    if total > 0:
                        progress_text = f" ({current} of {total})"

                    if item_name:
                        status_label.set_text(f"{item_name}{progress_text}")
                    elif progress_text:
                        status_label.set_text(f"Processing games{progress_text}")

                    # If we're done, update the status and stop the spinner
                    if current >= total and total > 0:
                        spinner.stop()
                        status_label.set_text(f"Sync complete: Added {current} games")
                        GObject.timeout_add(3000, lambda: dialog.close() or False)
                    return False  # Don't repeat

                GObject.idle_add(update_ui)
                return True

            # Start the scan in a separate thread

            # Flag to track if the dialog has been closed
            dialog_active = [True]

            # Handle dialog close properly
            def on_dialog_response(dialog, response):
                dialog_active[0] = False
                dialog.destroy()

            # Connect dialog response handler
            dialog.connect("response", on_dialog_response)

            def run_scan():
                try:
                    # Get the scanner for this source type
                    scanner = self.source_handler.get_scanner(source.source_type, source.id)
                    counts, errors = scanner.scan(source, xbox_progress_callback)

                    # Unpack the counts tuple
                    if isinstance(counts, tuple) and len(counts) == 2:
                        added_count, updated_count = counts
                    else:
                        # For backward compatibility with other scanners
                        added_count, updated_count = counts, 0

                    # Update UI on completion if dialog is still active
                    def on_complete():
                        if not dialog_active[0]:
                            # Dialog already closed, just emit the signal that games were added
                            total_changes = added_count + updated_count
                            if total_changes > 0:
                                self.emit("games-added", total_changes)
                            return False

                        # Stop the spinner
                        spinner.stop()

                        # Use the counts from the scanner to report all changes
                        changes_message = []
                        if added_count > 0:
                            changes_message.append(f"Added {added_count} games")
                        if updated_count > 0:
                            changes_message.append(f"Updated {updated_count} games")

                        if changes_message:
                            status_label.set_text(f"Sync complete: {', '.join(changes_message)}")
                        else:
                            status_label.set_text("Sync complete: No changes")

                        # Handle errors if any
                        if errors:
                            # Show errors after a delay so user can see completion message
                            GObject.timeout_add(2000, lambda: self._show_scan_errors(errors) if dialog_active[0] else False)

                        # Tell the app we updated games data
                        # Only emit a positive count if we actually had changes
                        total_changes = added_count + updated_count
                        if total_changes > 0:
                            self.emit("games-added", total_changes)

                        # Close the dialog after a delay if it's still active
                        GObject.timeout_add(3000, lambda: dialog.close() if dialog_active[0] else False)

                        return False

                    # Schedule UI update on the main thread
                    GObject.idle_add(on_complete)
                except Exception as e:
                    # Handle thread exceptions
                    def on_error():
                        if not dialog_active[0]:
                            return False

                        # Stop the spinner
                        spinner.stop()

                        # Show error in dialog
                        status_label.set_text(f"Error: {str(e)}")
                        logger.error(f"Error in Xbox sync thread: {e}")

                        return False

                    GObject.idle_add(on_error)

            # Start scan thread
            scan_thread = threading.Thread(target=run_scan)
            scan_thread.daemon = True
            scan_thread.start()

            return

        # PlayStation Network sources should also use the special background processing
        if source.source_type == SourceType.PLAYSTATION:
            dialog = Gtk.Dialog(
                title=f"PlayStation Network Sync: {source.name}",
                transient_for=self.get_root(),
                modal=False
            )

            # Add a close button
            dialog.add_button("Close", Gtk.ResponseType.CLOSE)

            # Add content
            content_area = dialog.get_content_area()
            content_area.set_spacing(12)
            content_area.set_margin_start(12)
            content_area.set_margin_end(12)
            content_area.set_margin_top(12)
            content_area.set_margin_bottom(12)

            # Add explanatory label
            label = Gtk.Label()
            label.set_markup(f"<b>Syncing games from PlayStation Network</b>")
            label.set_margin_bottom(10)
            content_area.append(label)

            status_label = Gtk.Label(label="Connecting to PlayStation Network...")
            status_label.set_wrap(True)
            status_label.set_width_chars(40)
            status_label.set_justify(Gtk.Justification.LEFT)
            status_label.set_halign(Gtk.Align.START)
            content_area.append(status_label)

            # No progress bar, just using the spinner and status text

            # Activity indicator
            spinner = Gtk.Spinner()
            spinner.set_size_request(32, 32)
            spinner.start()
            content_area.append(spinner)

            # Connect close response
            dialog.connect("response", lambda d, r: d.destroy())

            # Show the dialog
            dialog.set_default_size(400, -1)
            dialog.present()

            # Define a progress callback for PSN
            def psn_progress_callback(current, total, item_name):
                # Use GLib.idle_add to ensure UI updates happen in the main thread
                def update_ui():
                    progress_text = ""
                    if total > 0:
                        progress_text = f" ({current} of {total})"

                    if item_name:
                        status_label.set_text(f"{item_name}{progress_text}")
                    elif progress_text:
                        status_label.set_text(f"Processing games{progress_text}")

                    # If we're done, update the status and stop the spinner
                    if current >= total and total > 0:
                        spinner.stop()
                        status_label.set_text(f"Sync complete: Added {current} games")
                        GObject.timeout_add(3000, lambda: dialog.close() or False)
                    return False  # Don't repeat

                GObject.idle_add(update_ui)
                return True

            # Start the scan in a separate thread

            # Flag to track if the dialog has been closed
            dialog_active = [True]

            # Handle dialog close properly
            def on_dialog_response(dialog, response):
                dialog_active[0] = False
                dialog.destroy()

            # Connect dialog response handler
            dialog.connect("response", on_dialog_response)

            def run_scan():
                try:
                    # Get the scanner for this source type
                    scanner = self.source_handler.get_scanner(source.source_type, source.id)
                    counts, errors = scanner.scan(source, psn_progress_callback)

                    # Unpack the counts tuple - PSN now returns (added_count, updated_count)
                    if isinstance(counts, tuple) and len(counts) == 2:
                        added_count, updated_count = counts
                    else:
                        # For backward compatibility with other scanners
                        added_count, updated_count = counts, 0

                    # Update UI on completion if dialog is still active
                    def on_complete():
                        if not dialog_active[0]:
                            # Dialog already closed, just emit the signal that games were added
                            total_changes = added_count + updated_count
                            if total_changes > 0:
                                self.emit("games-added", total_changes)
                            return False

                        # Stop the spinner
                        spinner.stop()

                        # Use the counts from the scanner to report all changes
                        changes_message = []
                        if added_count > 0:
                            changes_message.append(f"Added {added_count} games")
                        if updated_count > 0:
                            changes_message.append(f"Updated {updated_count} games")

                        if changes_message:
                            status_label.set_text(f"Sync complete: {', '.join(changes_message)}")
                        else:
                            status_label.set_text("Sync complete: No changes")

                        # Handle errors if any
                        if errors:
                            # Show errors after a delay so user can see completion message
                            GObject.timeout_add(2000, lambda: self._show_scan_errors(errors) if dialog_active[0] else False)

                        # Tell the app we updated games data
                        # Only emit a positive count if we actually had changes
                        total_changes = added_count + updated_count
                        if total_changes > 0:
                            self.emit("games-added", total_changes)

                        # Close the dialog after a delay if it's still active
                        GObject.timeout_add(3000, lambda: dialog.close() if dialog_active[0] else False)

                        return False

                    # Schedule UI update on the main thread
                    GObject.idle_add(on_complete)
                except Exception as e:
                    # Handle thread exceptions
                    def on_error():
                        if not dialog_active[0]:
                            return False

                        # Stop the spinner
                        spinner.stop()

                        # Show error in dialog
                        status_label.set_text(f"Error: {str(e)}")
                        logger.error(f"Error in PSN sync thread: {e}")

                        return False

                    GObject.idle_add(on_error)

            # Start scan thread
            scan_thread = threading.Thread(target=run_scan)
            scan_thread.daemon = True
            scan_thread.start()

            return

        # For other source types, use a similar thread-based approach as Xbox/PSN
        dialog = Gtk.Dialog(
            title=f"Scanning {source.name}",
            transient_for=self.get_root(),
            modal=False  # Non-modal to prevent UI freezing
        )

        # Add content
        content_area = dialog.get_content_area()
        content_area.set_spacing(12)
        content_area.set_margin_start(12)
        content_area.set_margin_end(12)
        content_area.set_margin_top(12)
        content_area.set_margin_bottom(12)

        # Add explanatory label
        label = Gtk.Label()
        label.set_markup(f"<b>Scanning directory: {source.name}</b>")
        label.set_margin_bottom(10)
        content_area.append(label)

        # Status label to show current progress
        status_label = Gtk.Label(label="Preparing scan...")
        status_label.set_wrap(True)
        status_label.set_width_chars(40)
        status_label.set_justify(Gtk.Justification.LEFT)
        status_label.set_halign(Gtk.Align.START)
        content_area.append(status_label)

        # No progress bar, just using text status updates

        # Activity indicator
        spinner = Gtk.Spinner()
        spinner.set_size_request(32, 32)
        spinner.start()
        content_area.append(spinner)

        # Add a close button
        dialog.add_button("Close", Gtk.ResponseType.CLOSE)

        # Show dialog
        dialog.set_default_size(400, -1)
        dialog.present()

        # Flag to track if the dialog has been closed
        dialog_active = [True]

        # Handle dialog close properly
        def on_dialog_response(dialog, response):
            dialog_active[0] = False
            dialog.destroy()

        # Connect dialog response handler
        dialog.connect("response", on_dialog_response)

        # Function to update progress - thread-safe
        def directory_progress_callback(current, total, item_name):
            # Use GObject.idle_add to ensure UI updates happen in the main thread
            def update_ui():
                if not dialog_active[0]:
                    return False

                progress_text = ""
                if total > 0:
                    progress_text = f" ({current} of {total})"

                if item_name:
                    status_label.set_text(f"{item_name}{progress_text}")
                elif progress_text:
                    status_label.set_text(f"Scanning files{progress_text}")

                # If the scan is complete, close the dialog after a delay
                if current >= total and total > 0:
                    spinner.stop()
                    status_label.set_text(f"Scan complete: {current} files processed")
                    # Close the dialog after a delay if still active
                    GObject.timeout_add(3000, lambda: dialog.close() if dialog_active[0] else False)
                return False  # Don't repeat

            GObject.idle_add(update_ui)
            return True

        # Start the scan in a separate thread

        def run_scan():
            try:
                # Get the scanner for this source type
                scanner = self.source_handler.get_scanner(source.source_type, source.id)
                counts, errors = scanner.scan(source, directory_progress_callback)

                # Unpack the counts tuple
                if isinstance(counts, tuple) and len(counts) == 2:
                    added_count, updated_count = counts
                else:
                    # For backward compatibility with other scanners
                    added_count, updated_count = counts, 0

                # Update UI on completion
                def on_complete():
                    if not dialog_active[0]:
                        # Dialog already closed, just emit the signal that games were added
                        total_changes = added_count + updated_count
                        if total_changes > 0:
                            self.emit("games-added", total_changes)
                        return False

                    # Stop the spinner
                    spinner.stop()

                    # Use the counts from the scanner to report all changes
                    changes_message = []
                    if added_count > 0:
                        changes_message.append(f"Added {added_count} games")
                    if updated_count > 0:
                        changes_message.append(f"Updated {updated_count} games")

                    if changes_message:
                        status_label.set_text(f"Scan complete: {', '.join(changes_message)}")
                    else:
                        status_label.set_text("Scan complete: No changes")

                    # Handle errors if any
                    if errors:
                        # Show errors after a delay so user can see completion message
                        GObject.timeout_add(2000, lambda: self._show_scan_errors(errors) if dialog_active[0] else False)

                    # Tell the app we updated games data
                    # Pass 1 as minimum to ensure UI refresh even if only existing games were updated
                    added_or_updated = max(1, added)
                    self.emit("games-added", added_or_updated)

                    # Close the dialog after a delay if it's still active
                    GObject.timeout_add(3000, lambda: dialog.close() if dialog_active[0] else False)

                    return False

                # Schedule UI update on the main thread
                GObject.idle_add(on_complete)
            except Exception as e:
                # Handle thread exceptions
                error = e
                def on_error():
                    if not dialog_active[0]:
                        return False

                    # Stop the spinner
                    spinner.stop()

                    # Show error in dialog
                    status_label.set_text(f"Error: {str(error)}")
                    logger.error(f"Error in directory scan thread: {error}")

                    return False

                GObject.idle_add(on_error)

        # Start scan thread
        scan_thread = threading.Thread(target=run_scan)
        scan_thread.daemon = True
        scan_thread.start()

    # _do_scan method removed as we now perform scanning directly in the thread

    def _show_scan_errors(self, errors):
        """Show errors from scanning in a dialog"""
        # Create a custom dialog to avoid issues with MessageDialog
        dialog = Gtk.Dialog(
            title=f"Completed with {len(errors)} errors",
            transient_for=self.get_root(),
            modal=True
        )

        # Add OK button manually
        dialog.add_button("OK", Gtk.ResponseType.OK)

        # Create content area
        content_area = dialog.get_content_area()
        content_area.set_spacing(10)
        content_area.set_margin_start(20)
        content_area.set_margin_end(20)
        content_area.set_margin_top(20)
        content_area.set_margin_bottom(20)

        # Add a label for the title
        title_label = Gtk.Label()
        title_label.set_markup(f"<b>Completed with {len(errors)} errors</b>")
        title_label.set_halign(Gtk.Align.START)
        content_area.append(title_label)

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
        content_area.append(scrolled)

        # Connect response to close the dialog
        dialog.connect("response", lambda d, r: d.destroy())

        # Show the dialog
        dialog.set_default_size(400, 300)
        dialog.present()

    def _show_error(self, message):
        """Show an error dialog"""
        # Create a custom dialog instead of MessageDialog
        dialog = Gtk.Dialog(
            title="Error",
            transient_for=self.get_root(),
            modal=True
        )

        # Add OK button
        dialog.add_button("OK", Gtk.ResponseType.OK)

        # Create content area
        content_area = dialog.get_content_area()
        content_area.set_spacing(10)
        content_area.set_margin_start(20)
        content_area.set_margin_end(20)
        content_area.set_margin_top(20)
        content_area.set_margin_bottom(20)

        # Create a box with icon and message
        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        # Add error icon
        icon = Gtk.Image.new_from_icon_name("dialog-error")
        icon.set_pixel_size(32)
        hbox.append(icon)

        # Add message
        msg_label = Gtk.Label(label=message)
        msg_label.set_wrap(True)
        msg_label.set_halign(Gtk.Align.START)
        msg_label.set_valign(Gtk.Align.CENTER)
        msg_label.set_hexpand(True)
        hbox.append(msg_label)

        content_area.append(hbox)

        # Connect response to close dialog
        dialog.connect("response", lambda d, r: d.destroy())

        # Show dialog
        dialog.set_default_size(300, -1)
        dialog.present()

    # Define custom signals
    __gsignals__ = {
        "closed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "games-added": (GObject.SignalFlags.RUN_FIRST, None, (int,)),
    }
