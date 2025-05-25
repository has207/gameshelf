import threading
import logging

from gi.repository import Gtk, Adw, Gio, GObject, GLib

# Set up logger
logger = logging.getLogger(__name__)

from controllers.common import get_template_path
from providers.opencritic_client import OpenCriticClient
from providers.launchbox_client import LaunchBoxMetadata


@Gtk.Template(filename=get_template_path("metadata_search_dialog.ui"))
class MetadataSearchDialog(Adw.Window):
    """Dialog for searching and selecting game metadata from online sources"""
    __gtype_name__ = "MetadataSearchDialog"

    # Define custom signals
    __gsignals__ = {
        "metadata-selected": (GObject.SignalFlags.RUN_FIRST, None, (object, str)),
    }

    # UI elements
    dialog_title: Adw.WindowTitle = Gtk.Template.Child()
    search_entry: Gtk.SearchEntry = Gtk.Template.Child()
    search_button: Gtk.Button = Gtk.Template.Child()
    cancel_button: Gtk.Button = Gtk.Template.Child()
    results_list: Gtk.ListBox = Gtk.Template.Child()
    results_scroll: Gtk.ScrolledWindow = Gtk.Template.Child()
    status_container: Gtk.Box = Gtk.Template.Child()
    status_label: Gtk.Label = Gtk.Template.Child()
    loading_spinner: Gtk.Spinner = Gtk.Template.Child()

    def __init__(self, parent_window, controller=None):
        super().__init__()
        self.parent_window = parent_window
        self.controller = controller or parent_window.controller
        self.set_transient_for(parent_window)

        # Initialize provider selection dropdown
        self.provider_dropdown = Gtk.DropDown.new_from_strings(["LaunchBox", "OpenCritic"])
        self.provider_dropdown.set_margin_start(10)
        self.provider_dropdown.set_margin_end(10)
        self.provider_dropdown.set_margin_top(10)
        self.provider_dropdown.set_margin_bottom(10)
        self.provider_dropdown.connect("notify::selected", self.on_provider_changed)

        # Find the box container that has the search entry
        parent_box = self.search_entry.get_parent()
        if parent_box:
            parent_box.prepend(self.provider_dropdown)

        # Initialize the selected metadata client (default to LaunchBox)
        self.selected_provider = "LaunchBox"
        self.metadata_client = LaunchBoxMetadata()

        # Check if LaunchBox database needs initialization
        self.launchbox_metadata = None

        # State tracking
        self.search_results = []
        self.selected_result = None
        self.current_search_thread = None

        # Set up the ListBox for results
        self.results_list.set_header_func(self._add_separator_between_rows)

        # Update button state
        self.search_button.set_sensitive(False)

    def _add_separator_between_rows(self, row, before):
        """Add separators between rows in the results list"""
        if before is not None:
            separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            separator.set_margin_start(8)
            separator.set_margin_end(8)
            row.set_header(separator)

    @Gtk.Template.Callback()
    def on_cancel_clicked(self, button):
        """Handle cancel button click"""
        self.close()

    @Gtk.Template.Callback()
    def on_search_changed(self, entry):
        """Handler for search entry text changes"""
        query = entry.get_text().strip()
        self.search_button.set_sensitive(len(query) > 0)

    @Gtk.Template.Callback()
    def on_search_entry_activated(self, entry):
        """Handler for Enter key in search entry"""
        if self.search_button.get_sensitive():
            self.on_search_clicked(self.search_button)

    @Gtk.Template.Callback()
    def on_search_clicked(self, button):
        """Handler for search button click"""
        query = self.search_entry.get_text().strip()
        if query:
            self.perform_search(query)

    def perform_search(self, query):
        """Perform the search operation in a background thread"""
        # Cancel any previous search
        if self.current_search_thread and self.current_search_thread.is_alive():
            # Cannot actually cancel threads in Python, but we'll ignore results
            pass

        # Clear previous results
        self._clear_results()

        # Show loading indicators
        self.loading_spinner.set_spinning(True)
        self.status_label.set_text("Searching...")
        self.status_container.set_visible(True)
        self.results_scroll.set_visible(False)

        # Start the search in a separate thread
        self.current_search_thread = threading.Thread(
            target=self._perform_search_thread,
            args=(query,)
        )
        self.current_search_thread.daemon = True
        self.current_search_thread.start()

    def _perform_search_thread(self, query):
        """Background thread for search operation"""
        try:
            # Perform the search
            results = self.metadata_client.search(query)

            # Update the UI in the main thread
            GLib.idle_add(self._update_search_results, results)
        except Exception as e:
            logger.error(f"Error searching for '{query}': {e}")
            GLib.idle_add(self._show_search_error, str(e))

    def _update_search_results(self, results):
        """Update the UI with search results (called in main thread)"""
        # Store the results
        self.search_results = results

        # Hide loading indicators
        self.loading_spinner.set_spinning(False)

        # Update the UI based on the results
        if not results:
            self.status_label.set_text("No results found. Try a different search term.")
            self.status_container.set_visible(True)
            self.results_scroll.set_visible(False)
        else:
            self.status_container.set_visible(False)
            self.results_scroll.set_visible(True)

            # Populate the results list
            for result in results:
                row = Gtk.ListBoxRow()
                row.set_margin_top(8)
                row.set_margin_bottom(8)

                # Create a box for the result item
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                box.set_margin_start(12)
                box.set_margin_end(12)
                box.set_margin_top(4)
                box.set_margin_bottom(4)

                # Add game name
                label = Gtk.Label(label=result.name)
                label.set_halign(Gtk.Align.START)
                label.set_hexpand(True)

                # Store the result ID for retrieval when selected
                row.result_id = result.id
                row.result_name = result.name

                box.append(label)
                row.set_child(box)
                self.results_list.append(row)

            # Show the populated list
            self.results_list.show()

        return False  # Remove from idle queue

    def _show_search_error(self, error_message):
        """Show an error message in the UI (called in main thread)"""
        self.loading_spinner.set_spinning(False)
        self.status_label.set_text(f"Error: {error_message}")
        self.status_container.set_visible(True)
        self.results_scroll.set_visible(False)
        return False  # Remove from idle queue

    def _clear_results(self):
        """Clear the results list"""
        while True:
            row = self.results_list.get_first_child()
            if row:
                self.results_list.remove(row)
            else:
                break

        self.search_results = []
        self.selected_result = None

    @Gtk.Template.Callback()
    def on_result_selected(self, list_box, row):
        """Handler for result selection in the list"""
        if row is None:
            return

        # Store the selected result
        result_id = getattr(row, 'result_id', None)
        result_name = getattr(row, 'result_name', "")

        if result_id is not None:
            logger.info(f"Selected result: {result_name} (ID: {result_id})")

            # Show the preview dialog
            self._show_game_details(result_id, result_name)

    def on_provider_changed(self, dropdown, param):
        """Handle metadata provider selection change"""
        selected_item = dropdown.get_selected_item()
        if selected_item:
            provider_name = selected_item.get_string()
            self.selected_provider = provider_name

            if provider_name == "LaunchBox":
                if not self.launchbox_metadata:
                    # Data directory from the controller
                    data_dir = self.controller.data_handler.data_dir
                    self.launchbox_metadata = LaunchBoxMetadata(str(data_dir))
                self.metadata_client = self.launchbox_metadata

                # Check if database initialization is required
                if not self.launchbox_metadata.database.database_exists():
                    self._show_launchbox_init_dialog()
                    # Return early - we'll handle the search after initialization
                    return
            elif provider_name == "OpenCritic":
                self.metadata_client = OpenCriticClient()

        # Clear existing results when changing provider
        self._clear_results()

        # Automatically perform search if there's text in the search field
        query = self.search_entry.get_text().strip()
        if query:
            self.perform_search(query)
        else:
            self.search_entry.grab_focus()

    def _select_provider(self, provider_name):
        """Helper method to select a provider by name"""
        model = self.provider_dropdown.get_model()
        for i in range(model.get_n_items()):
            item = model.get_item(i)
            if item.get_string() == provider_name:
                self.provider_dropdown.set_selected(i)
                break

    def _show_launchbox_init_dialog(self):
        """Show dialog for initializing LaunchBox database"""
        dialog = Adw.MessageDialog.new(
            self,
            "LaunchBox Database Required",
            "The LaunchBox database needs to be downloaded and initialized before searching. This might take several minutes. Do you want to initialize it now?"
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("download", "Download & Initialize")
        dialog.set_response_appearance("download", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", self._on_launchbox_init_response)
        dialog.present()

    def _on_launchbox_init_response(self, dialog, response):
        """Handle response from the LaunchBox initialization dialog"""
        if response == "download":
            # Start the initialization in a background thread
            self.status_container.set_visible(True)
            self.results_scroll.set_visible(False)
            self.loading_spinner.set_spinning(True)
            self.status_label.set_text("Downloading and initializing LaunchBox database...\nThis may take several minutes.")

            thread = threading.Thread(
                target=self._initialize_launchbox_thread
            )
            thread.daemon = True
            thread.start()
        else:
            # Switch back to OpenCritic
            self._select_provider("OpenCritic")

    def _initialize_launchbox_thread(self):
        """Background thread for LaunchBox database initialization"""
        try:
            success = self.launchbox_metadata.initialize_database()
            GLib.idle_add(self._on_launchbox_init_complete, success)
        except Exception as e:
            logger.error(f"Error initializing LaunchBox database: {e}")
            GLib.idle_add(self._on_launchbox_init_complete, False, str(e))

    def _on_launchbox_init_complete(self, success, error_message=None):
        """Handle completion of LaunchBox database initialization"""
        self.loading_spinner.set_spinning(False)

        if success:
            self.status_label.set_text("LaunchBox database initialized successfully.")

            # Automatically perform search if there's text in the search field
            query = self.search_entry.get_text().strip()
            if query:
                # Give UI a chance to update first
                GLib.timeout_add(500, lambda: self.perform_search(query))
            else:
                self.status_container.set_visible(True)
                self.results_scroll.set_visible(False)
                self.search_entry.grab_focus()
        else:
            error_msg = error_message or "Unknown error"
            self.status_label.set_text(f"Failed to initialize LaunchBox database: {error_msg}")
            # Switch back to OpenCritic
            self._select_provider("OpenCritic")

        return False  # Remove from idle queue

    def _show_game_details(self, game_id, game_name):
        """Show the game details preview dialog"""
        from controllers.metadata_preview_dialog_controller import MetadataPreviewDialog
        preview_dialog = MetadataPreviewDialog(
            self,
            self.controller,
            game_id,
            game_name,
            self.metadata_client,
            self.selected_provider
        )
        preview_dialog.connect("metadata-accepted", self._on_metadata_accepted)
        preview_dialog.show()

    def _on_metadata_accepted(self, dialog, game_metadata, image_path):
        """Handle metadata acceptance from the preview dialog"""
        # Close this dialog
        self.close()

        # Emit our signal for the parent dialog
        self.emit("metadata-selected", game_metadata, image_path)