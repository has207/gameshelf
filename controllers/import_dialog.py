from gi.repository import Gtk, Gio, GLib
import os
import threading
import logging
from pathlib import Path

# Set up logger
logger = logging.getLogger(__name__)

from importers.json_importer import JsonImporter


class ImportDialog(Gtk.Dialog):
    """Dialog for importing games from external sources"""

    def __init__(self, parent, controller):
        super().__init__(
            title="Import Games",
            transient_for=parent,
            modal=True,
            destroy_with_parent=True
        )

        self.controller = controller
        self.data_handler = controller.data_handler
        self.settings_manager = controller.settings_manager
        self.json_path = None
        self.cover_dir = None

        # Set dialog size
        self.set_default_size(500, 400)

        # Add buttons
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.import_button = self.add_button("Import", Gtk.ResponseType.APPLY)
        self.import_button.set_sensitive(False)

        # Create main content area
        content_area = self.get_content_area()
        content_area.add_css_class("import-dialog-content")

        # Create main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        main_box.set_spacing(12)
        main_box.add_css_class("import-dialog-main-box")
        content_area.append(main_box)

        # Source selection section
        source_frame = Gtk.Frame(label="Import Source")
        source_frame.add_css_class("import-dialog-frame")
        main_box.append(source_frame)

        source_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        source_box.set_spacing(12)
        source_box.add_css_class("import-dialog-source-box")
        source_frame.set_child(source_box)

        # JSON file selection
        json_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        json_box.set_spacing(6)
        json_box.add_css_class("import-dialog-field-box")
        source_box.append(json_box)

        json_label = Gtk.Label(label="JSON File:")
        json_label.set_xalign(0)
        json_label.add_css_class("import-dialog-label")
        json_box.append(json_label)

        self.json_entry = Gtk.Entry()
        self.json_entry.set_hexpand(True)
        self.json_entry.set_placeholder_text("Select JSON file...")
        json_box.append(self.json_entry)

        json_button = Gtk.Button(label="Browse...")
        json_button.add_css_class("import-dialog-browse-button")
        json_button.connect("clicked", self.on_json_browse_clicked)
        json_box.append(json_button)

        # Cover directory selection
        cover_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        cover_box.set_spacing(6)
        cover_box.add_css_class("import-dialog-field-box")
        source_box.append(cover_box)

        cover_label = Gtk.Label(label="Cover Images Directory:")
        cover_label.set_xalign(0)
        cover_label.add_css_class("import-dialog-label")
        cover_box.append(cover_label)

        self.cover_entry = Gtk.Entry()
        self.cover_entry.set_hexpand(True)
        self.cover_entry.set_placeholder_text("Select cover images directory...")
        cover_box.append(self.cover_entry)

        cover_button = Gtk.Button(label="Browse...")
        cover_button.add_css_class("import-dialog-browse-button")
        cover_button.connect("clicked", self.on_cover_browse_clicked)
        cover_box.append(cover_button)

        # Progress area
        self.progress_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.progress_area.set_spacing(6)
        self.progress_area.add_css_class("import-dialog-progress-area")
        self.progress_area.set_visible(False)
        main_box.append(self.progress_area)

        self.progress_label = Gtk.Label(label="Importing...")
        self.progress_label.set_xalign(0)
        self.progress_label.add_css_class("import-dialog-progress-label")
        self.progress_area.append(self.progress_label)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.add_css_class("import-dialog-progress-bar")
        self.progress_area.append(self.progress_bar)

        # Results area
        self.results_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.results_area.set_spacing(6)
        self.results_area.add_css_class("import-dialog-results-area")
        self.results_area.set_visible(False)
        main_box.append(self.results_area)

        self.results_label = Gtk.Label(label="")
        self.results_label.set_xalign(0)
        self.results_label.add_css_class("import-dialog-results-label")
        self.results_area.append(self.results_label)

        # Create a scroll window for the errors
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add_css_class("import-dialog-error-scroll")
        self.results_area.append(scroll)

        # Create a text view for the errors
        self.error_view = Gtk.TextView()
        self.error_view.set_editable(False)
        self.error_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.error_view.add_css_class("import-dialog-error-view")
        self.error_buffer = self.error_view.get_buffer()
        scroll.set_child(self.error_view)

        # Connect dialog signals
        self.connect("response", self.on_response)

        # Connect entry signals to validate
        self.json_entry.connect("changed", self.validate_inputs)
        self.cover_entry.connect("changed", self.validate_inputs)

        # Initialize with saved paths
        saved_json_path = self.settings_manager.get_import_json_path()
        saved_cover_dir = self.settings_manager.get_import_cover_dir()

        if saved_json_path:
            self.json_entry.set_text(saved_json_path)

        if saved_cover_dir:
            self.cover_entry.set_text(saved_cover_dir)

    def validate_inputs(self, widget=None):
        """Validate form inputs and enable/disable the import button"""
        json_path = self.json_entry.get_text()
        cover_dir = self.cover_entry.get_text()

        self.json_path = json_path if os.path.isfile(json_path) else None
        self.cover_dir = cover_dir if os.path.isdir(cover_dir) else None

        # Save valid paths to app state
        if self.json_path:
            self.settings_manager.set_import_json_path(self.json_path)
            self.settings_manager.save_settings()

        if self.cover_dir:
            self.settings_manager.set_import_cover_dir(self.cover_dir)
            self.settings_manager.save_settings()

        # Enable import button only if both paths are valid
        self.import_button.set_sensitive(self.json_path is not None and self.cover_dir is not None)

    def on_json_browse_clicked(self, button):
        """Handle JSON file browse button click"""
        file_dialog = Gtk.FileDialog.new()
        file_dialog.set_title("Select JSON File")

        # Create a filter for JSON files
        json_filter = Gtk.FileFilter()
        json_filter.set_name("JSON files")
        json_filter.add_pattern("*.json")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(json_filter)
        file_dialog.set_filters(filters)

        # Set initial folder if we have a saved path
        saved_json_path = self.settings_manager.get_import_json_path()
        if saved_json_path:
            initial_folder = os.path.dirname(saved_json_path)
            if os.path.isdir(initial_folder):
                file_dialog.set_initial_folder(Gio.File.new_for_path(initial_folder))

        # Open the dialog
        file_dialog.open(self, None, self._on_json_file_selected)

    def _on_json_file_selected(self, dialog, result):
        """Handle JSON file selection"""
        try:
            file = dialog.open_finish(result)
            if file:
                path = file.get_path()
                self.json_entry.set_text(path)

                # Auto-set cover directory to JSON file's directory if not already set
                if not self.cover_entry.get_text():
                    self.cover_entry.set_text(os.path.dirname(path))
        except Exception as e:
            logger.error(f"Error selecting JSON file: {e}")

    def on_cover_browse_clicked(self, button):
        """Handle cover directory browse button click"""
        file_dialog = Gtk.FileDialog.new()
        file_dialog.set_title("Select Cover Images Directory")

        # Set initial folder if we have a saved path
        saved_cover_dir = self.settings_manager.get_import_cover_dir()
        if saved_cover_dir and os.path.isdir(saved_cover_dir):
            file_dialog.set_initial_folder(Gio.File.new_for_path(saved_cover_dir))

        # Open the dialog for folder selection
        file_dialog.select_folder(self, None, self._on_cover_dir_selected)

    def _on_cover_dir_selected(self, dialog, result):
        """Handle cover directory selection"""
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                path = folder.get_path()
                self.cover_entry.set_text(path)
        except Exception as e:
            logger.error(f"Error selecting cover directory: {e}")

    def on_response(self, dialog, response_id):
        """Handle dialog response"""
        if response_id == Gtk.ResponseType.APPLY:
            # Start import process
            self._start_import()
            return

        # Otherwise close the dialog
        self.close()

    def _start_import(self):
        """Start the import process in a separate thread"""
        # Hide normal dialog parts
        self.import_button.set_sensitive(False)

        # Show progress parts
        self.progress_area.set_visible(True)
        self.progress_bar.set_fraction(0.0)

        # Create the importer with the existing games from the controller
        existing_games = self.controller.get_games()
        importer = JsonImporter(self.data_handler, existing_games)

        # Start a thread to do the import
        thread = threading.Thread(
            target=self._import_thread,
            args=(importer, self.json_path, self.cover_dir)
        )
        thread.daemon = True
        thread.start()

    def _import_thread(self, importer, json_path, cover_dir):
        """Run the import in a separate thread"""
        try:
            # Get game count from the importer
            total_count = importer.get_game_count(json_path)

            # Update UI to show total game count
            if total_count > 0:
                GLib.idle_add(self._update_progress_label, f"Preparing to import {total_count} games...")

            # Do the import with progress reporting
            imported_count, skipped_count, errors = importer.import_from_file(
                json_path,
                cover_dir,
                progress_callback=self._update_progress
            )

            # Update UI from main thread
            GLib.idle_add(self._import_complete, imported_count, skipped_count, errors)
        except Exception as e:
            GLib.idle_add(self._import_failed, str(e))

    def _update_progress(self, current, total, game_title):
        """Update progress UI from the callback"""
        if total > 0:
            fraction = current / total
            # Update UI in main thread
            GLib.idle_add(self._update_progress_ui, fraction, current, total, game_title)

    def _update_progress_ui(self, fraction, current, total, game_title):
        """Update progress UI in the main thread"""
        self.progress_bar.set_fraction(fraction)
        self.progress_label.set_text(f"Importing {current+1} of {total}: {game_title}")
        return False  # Remove from idle

    def _update_progress_label(self, text):
        """Update just the progress label"""
        self.progress_label.set_text(text)
        return False  # Remove from idle

    def _import_complete(self, imported_count, skipped_count, errors):
        """Handle import completion"""
        # Hide progress, show results
        self.progress_area.set_visible(False)
        self.results_area.set_visible(True)

        # Update results with import and skipped counts
        if skipped_count > 0:
            self.results_label.set_text(f"Import complete: {imported_count} games imported, {skipped_count} games skipped.")
        else:
            self.results_label.set_text(f"Import complete: {imported_count} games imported.")

        if errors:
            # Show errors in text view
            error_text = "\n".join([f"• {error}" for error in errors])
            self.error_buffer.set_text(error_text)
        else:
            self.error_buffer.set_text("No errors.")

        # Remove existing buttons
        cancel_button = self.get_widget_for_response(Gtk.ResponseType.CANCEL)
        if cancel_button:
            cancel_button.set_visible(False)

        # Remove import button and add a close button
        self.import_button.set_visible(False)
        close_button = self.add_button("Close", Gtk.ResponseType.OK)
        close_button.set_sensitive(True)

        # Refresh game list
        self.controller.reload_data()

        return False  # Remove from idle

    def _import_failed(self, error_message):
        """Handle import failure"""
        # Hide progress, show results
        self.progress_area.set_visible(False)
        self.results_area.set_visible(True)

        # Update results
        self.results_label.set_text("Import failed!")
        self.error_buffer.set_text(f"Error: {error_message}")

        # Remove existing buttons
        cancel_button = self.get_widget_for_response(Gtk.ResponseType.CANCEL)
        if cancel_button:
            cancel_button.set_visible(False)

        # Remove import button and add a close button
        self.import_button.set_visible(False)
        close_button = self.add_button("Close", Gtk.ResponseType.OK)
        close_button.set_sensitive(True)

        return False  # Remove from idle