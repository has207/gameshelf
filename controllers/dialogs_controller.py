from typing import List, Optional, Dict, Any, Tuple
import threading
import tempfile
import requests
from pathlib import Path
from io import BytesIO

from gi.repository import Gtk, Adw, Gio, GObject, GdkPixbuf, Gdk, GLib

from data_handler import Game, Runner, CompletionStatus
from controllers.common import get_template_path, show_image_chooser_dialog
from providers.opencritic_client import OpenCriticClient
from providers.metadata_provider import SearchResultItem, Game as MetadataGame


@Gtk.Template(filename=get_template_path("context_menu.ui"))
class GameContextMenu(Gtk.Popover):
    """Context menu for game items in the grid"""
    __gtype_name__ = "GameContextMenu"

    # Template child widgets
    play_button: Gtk.Button = Gtk.Template.Child()
    edit_button: Gtk.Button = Gtk.Template.Child()
    toggle_hidden_button: Gtk.Button = Gtk.Template.Child()
    remove_button: Gtk.Button = Gtk.Template.Child()

    def __init__(self, game: Game, parent_item):
        super().__init__()
        self.game = game
        self.parent_item = parent_item

        # Connect button signals
        self.play_button.connect("clicked", self._on_play_clicked)
        self.edit_button.connect("clicked", self._on_edit_clicked)
        self.toggle_hidden_button.connect("clicked", self._on_toggle_hidden_clicked)
        self.remove_button.connect("clicked", self._on_remove_clicked)

        # Set appropriate label for toggle hidden button based on current state
        if game.hidden:
            self.toggle_hidden_button.set_label("Unhide Game")
        else:
            self.toggle_hidden_button.set_label("Hide Game")

        # Add CSS classes
        self.play_button.add_css_class("context-menu-item")
        self.edit_button.add_css_class("context-menu-item")
        self.toggle_hidden_button.add_css_class("context-menu-item")
        self.remove_button.add_css_class("context-menu-item")
        self.remove_button.add_css_class("context-menu-item-destructive")

    def _on_play_clicked(self, button):
        self.popdown()
        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if window:
            window.details_content.set_game(self.game)
            window.details_content.on_play_button_clicked(None)

    def _on_edit_clicked(self, button):
        self.popdown()
        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if window:
            window.details_content.set_game(self.game)
            window.details_content.on_edit_button_clicked(None)

    def _on_toggle_hidden_clicked(self, button):
        self.popdown()
        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if window and window.controller:
            # Toggle the hidden state of the game
            window.controller.toggle_game_hidden(self.game)

    def _on_remove_clicked(self, button):
        self.popdown()
        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if window and window.controller and window.controller.game_grid_controller:
            # Use the grid controller's existing delete confirmation functionality
            window.controller.game_grid_controller._show_multi_delete_confirmation([self.game])


@Gtk.Template(filename=get_template_path("game_dialog.ui"))
class GameDialog(Adw.Window):
    """Unified dialog for adding and editing games"""
    __gtype_name__ = "GameDialog"

    # UI elements from template
    dialog_title: Adw.WindowTitle = Gtk.Template.Child()
    title_entry: Adw.EntryRow = Gtk.Template.Child()
    runner_dropdown: Adw.ComboRow = Gtk.Template.Child()
    image_preview: Gtk.Picture = Gtk.Template.Child()
    select_image_button: Gtk.Button = Gtk.Template.Child()
    clear_image_container: Gtk.Box = Gtk.Template.Child()
    clear_image_button: Gtk.Button = Gtk.Template.Child()
    action_button: Gtk.Button = Gtk.Template.Child()
    cancel_button: Gtk.Button = Gtk.Template.Child()
    play_stats_group: Adw.PreferencesGroup = Gtk.Template.Child()
    play_count_entry: Adw.EntryRow = Gtk.Template.Child()
    play_time_entry: Adw.EntryRow = Gtk.Template.Child()
    completion_status_dropdown: Adw.ComboRow = Gtk.Template.Child()
    description_group: Adw.PreferencesGroup = Gtk.Template.Child()
    description_text: Gtk.TextView = Gtk.Template.Child()
    remove_game_container: Adw.PreferencesGroup = Gtk.Template.Child()
    remove_button: Gtk.Button = Gtk.Template.Child()
    download_metadata_button: Gtk.Button = Gtk.Template.Child()

    def __init__(self, parent_window, controller=None, edit_mode=False):
        super().__init__()
        self.parent_window = parent_window
        self.controller = controller or parent_window.controller
        self.edit_mode = edit_mode
        self.selected_runner = None
        self.selected_image_path = None
        self.original_image_path = None
        self.runners_data = []
        self.completion_status_data = []
        self.selected_completion_status = "Not Played"
        self.game = None

        # Adjust dialog height based on parent window height
        parent_height = parent_window.get_height()
        if parent_height > 0:
            # Make the dialog about 80% of parent height, but not smaller than default
            preferred_height = max(650, int(parent_height * 0.8))
            self.set_default_size(500, preferred_height)

        # Set up completion status dropdown
        self._populate_completion_status_dropdown()

        # Configure UI based on mode (add or edit)
        if edit_mode:
            self.dialog_title.set_title("Edit Game")
            self.action_button.set_label("Save Changes")
            self.clear_image_container.set_visible(True)
            self.select_image_button.set_label("Change Image")
            self.play_stats_group.set_visible(True)
            self.remove_game_container.set_visible(True)
        else:
            self.dialog_title.set_title("Add New Game")
            self.action_button.set_label("Add Game")
            self.clear_image_container.set_visible(False)
            self.select_image_button.set_label("Select Image")
            self.play_stats_group.set_visible(False)
            self.remove_game_container.set_visible(False)

        # Ensure action button updates when entry changes
        self.title_entry.connect("notify::text", self.validate_form)

    def set_game(self, game: Game):
        """Set the game to edit (only for edit mode)"""
        if not self.edit_mode:
            return

        self.game = game
        self.title_entry.set_text(game.title)
        self.selected_image_path = None

        # Load the game image
        pixbuf = self.controller.get_game_pixbuf(game, width=200, height=260)
        if pixbuf:
            self.image_preview.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
        else:
            # Set default image if no image is available
            icon_paintable = self.controller.data_handler.get_default_icon_paintable("applications-games-symbolic", 128)
            self.image_preview.set_paintable(icon_paintable)

        # Set play statistics
        self.play_count_entry.set_text(str(game.play_count))
        self.play_time_entry.set_text(str(game.play_time))

        # Set completion status from enum
        # Find the index of the completion status enum in completion_status_data
        for i, status in enumerate(self.completion_status_data):
            if status == game.completion_status:
                self.completion_status_dropdown.set_selected(i)
                self.selected_completion_status = status
                break

        # Populate runners dropdown
        self.populate_runners(self.controller.get_runners())

        # Select current runner in dropdown if game has one
        if self.game:
            if self.game.runner:
                # Find the index of the runner in runners_data
                for i, runner in enumerate(self.runners_data):
                    if runner and runner.id == self.game.runner:
                        self.runner_dropdown.set_selected(i)
                        self.selected_runner = runner
                        break
            else:
                self.runner_dropdown.set_selected(0)
                self.selected_runner = None

        # Enable the action button
        self.validate_form()

    def populate_runners(self, runners: List[Runner]):
        """Populate the runner dropdown with available runners"""
        # Create a list store for the dropdown
        runner_store = Gio.ListStore.new(GObject.Object)

        # Create a string list for displaying runner names
        string_list = Gtk.StringList()

        string_list.append("[none]")

        # Add all runners
        for runner in runners:
            string_list.append(runner.title)

        # Store runners list for reference when selected
        self.runners_data = [None] + runners

        # Set up the dropdown with the string list
        self.runner_dropdown.set_model(string_list)

        # Select "[none]" by default
        self.runner_dropdown.set_selected(0)
        self.selected_runner = None

    def _populate_completion_status_dropdown(self):
        """Populate the completion status dropdown with predefined statuses from the enum"""
        # Create a string list for displaying status names
        string_list = Gtk.StringList()

        # Add all statuses from the enum
        for status in CompletionStatus:
            string_list.append(status.value)

        # Store enum values for reference when selected
        self.completion_status_data = list(CompletionStatus)

        # Set up the dropdown with the string list
        self.completion_status_dropdown.set_model(string_list)

        # Select "Not Played" by default
        self.completion_status_dropdown.set_selected(0)  # CompletionStatus.NOT_PLAYED is first
        self.selected_completion_status = CompletionStatus.NOT_PLAYED

    @Gtk.Template.Callback()
    def on_entry_changed(self, entry, *args):
        self.validate_form()

    @Gtk.Template.Callback()
    def on_runner_selected(self, dropdown, gparam):
        """Handler for runner selection changes"""
        selected_index = dropdown.get_selected()
        if selected_index >= 0 and selected_index < len(self.runners_data):
            # Get the runner from our stored data using the index
            self.selected_runner = self.runners_data[selected_index]
        else:
            self.selected_runner = None
        self.validate_form()

    @Gtk.Template.Callback()
    def on_completion_status_selected(self, dropdown, gparam):
        """Handler for completion status selection changes"""
        selected_index = dropdown.get_selected()
        if selected_index >= 0 and selected_index < len(self.completion_status_data):
            # Get the enum value from our stored data using the index
            self.selected_completion_status = self.completion_status_data[selected_index]
        else:
            self.selected_completion_status = CompletionStatus.NOT_PLAYED
        self.validate_form()

    @Gtk.Template.Callback()
    def on_select_image_clicked(self, button):
        """Handler for select image button click"""
        show_image_chooser_dialog(self, self.on_image_selected)

    def on_image_selected(self, file_path):
        """Handler for image selection"""
        if file_path:
            self.selected_image_path = file_path

            # Load the image directly for preview
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    file_path, 200, 260, True)
                if pixbuf:
                    self.image_preview.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
                else:
                    # Set default icon for invalid image
                    icon_paintable = self.controller.data_handler.get_default_icon_paintable("image-missing", 128)
                    self.image_preview.set_paintable(icon_paintable)
                    self.selected_image_path = None
            except Exception as e:
                print(f"Error loading preview image: {e}")
                # Set default icon for invalid image
                icon_paintable = self.controller.data_handler.get_default_icon_paintable("image-missing", 128)
                self.image_preview.set_paintable(icon_paintable)
                self.selected_image_path = None
        else:
            # Clear the preview if dialog was canceled
            self.selected_image_path = None
            self.image_preview.set_paintable(None)

        self.validate_form()

    @Gtk.Template.Callback()
    def on_clear_image_clicked(self, button):
        """Handler for clear image button click (edit mode only)"""
        if not self.edit_mode:
            return

        # Clear the image
        self.selected_image_path = ""
        icon_paintable = self.controller.data_handler.get_default_icon_paintable("applications-games-symbolic", 128)
        self.image_preview.set_paintable(icon_paintable)
        self.validate_form()

    @Gtk.Template.Callback()
    def on_remove_button_clicked(self, button):
        """Handler for remove game button click (edit mode only)"""
        if not self.edit_mode or not self.game:
            return

        # Create a confirmation dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Remove {self.game.title}?",
            secondary_text="This action cannot be undone. The game will be permanently removed."
        )
        dialog.connect("response", self._on_remove_confirmation_response)
        dialog.show()

    def _on_remove_confirmation_response(self, dialog, response_id):
        """Handle the response from the remove confirmation dialog"""
        if response_id == Gtk.ResponseType.YES:
            # User confirmed removal
            if self.controller.remove_game(self.game):
                # Close edit dialog and details panel if open
                from controllers.window_controller import GameShelfWindow
                window = self.parent_window
                if window and window.details_panel:
                    window.details_panel.set_reveal_flap(False)
                    window.current_selected_game = None

                # Close dialog first
                self.close()

                # Schedule data reload and sidebar refresh async after dialog closes
                GLib.timeout_add(50, lambda: self.controller.reload_data(refresh_sidebar=True) or False)

        # Destroy the dialog in any case
        dialog.destroy()

    def validate_form(self, *args):
        """Validate form fields and update action button sensitivity"""
        # Check if required fields are filled - only title is required
        title = self.title_entry.get_text().strip()
        has_title = len(title) > 0

        if self.edit_mode and self.game:
            # In edit mode, check if any changes were made
            has_changes = False
            # Check title change
            if title != self.game.title:
                has_changes = True

            # Check runner change
            current_runner_id = self.selected_runner.id if self.selected_runner else ""
            if current_runner_id != (self.game.runner or ""):
                has_changes = True

            # Check play stats changes - for EntryRow
            current_play_count = self.play_count_entry.get_text().strip()
            try:
                if current_play_count and int(current_play_count) != self.game.play_count:
                    has_changes = True
            except (ValueError, TypeError):
                pass

            current_play_time = self.play_time_entry.get_text().strip()
            try:
                if current_play_time and int(current_play_time) != self.game.play_time:
                    has_changes = True
            except (ValueError, TypeError):
                pass

            # Check completion status changes
            current_status = self.selected_completion_status
            game_status = self.game.completion_status
            if current_status != game_status:
                has_changes = True

            # Check image change
            if self.selected_image_path is not None:  # Only if image was explicitly changed
                has_changes = True

            # Update button sensitivity - requires title and changes
            self.action_button.set_sensitive(has_title and has_changes)
        else:
            # In add mode, just check for title
            self.action_button.set_sensitive(has_title)

    @Gtk.Template.Callback()
    def on_cancel_clicked(self, button):
        self.close()

    @Gtk.Template.Callback()
    def on_action_clicked(self, button):
        """Handle the primary action (add or save) based on the dialog mode"""
        if self.edit_mode:
            self._save_game_changes()
        else:
            self._add_new_game()

    def _add_new_game(self):
        """Add a new game (add mode)"""
        # Get the input values
        title = self.title_entry.get_text().strip()
        runner_id = self.selected_runner.id if self.selected_runner else ""

        # Create the game using the data handler
        game = self.controller.data_handler.create_game_with_image(
            title=title,
            runner_id=runner_id,
            image_path=self.selected_image_path
        )

        # Save the game through the controller
        if self.controller.add_game(game):
            # Reset form fields
            self.title_entry.set_text("")
            self.runner_dropdown.set_selected(0)  # Select "[none]"
            self.selected_runner = None
            self.selected_image_path = None
            self.image_preview.set_paintable(None)

            # Close the dialog first
            self.close()

            # Schedule sidebar refresh after dialog closes (async)
            GLib.timeout_add(50, lambda: self.controller.reload_data(refresh_sidebar=True) or False)

    def _save_game_changes(self):
        """Save changes to an existing game (edit mode)"""
        if not self.game:
            return

        # Track if the main game.yaml needs updating
        need_to_save_game_yaml = False

        # Get the updated values
        title = self.title_entry.get_text().strip()
        runner_id = self.selected_runner.id if self.selected_runner else ""

        # Check if title or runner ID changed (these are stored in game.yaml)
        if title != self.game.title or runner_id != self.game.runner:
            self.game.title = title
            self.game.runner = runner_id
            need_to_save_game_yaml = True

        # Get play statistics
        try:
            play_count_text = self.play_count_entry.get_text().strip()
            if play_count_text:
                play_count = int(play_count_text)
                if play_count != self.game.play_count:
                    # Update play count with new value
                    self.controller.data_handler.update_play_count(self.game, play_count)
        except (ValueError, TypeError) as e:
            print(f"Error updating play count: {e}")

        try:
            play_time_text = self.play_time_entry.get_text().strip()
            if play_time_text:
                play_time = int(play_time_text)
                if play_time != self.game.play_time:
                    # Update play time with new value
                    self.controller.data_handler.update_play_time(self.game, play_time)
        except (ValueError, TypeError) as e:
            print(f"Error updating play time: {e}")

        # Copy the image if a new one was selected
        if self.selected_image_path is not None:  # Image was changed
            if self.selected_image_path:  # New image selected
                # Save the new image
                self.controller.data_handler.save_game_image(
                    self.selected_image_path,
                    self.game.id
                )
            else:  # Image was cleared
                # Remove the cover image using the data handler
                self.controller.data_handler.remove_game_image(self.game.id)

        # Update completion status if needed
        if self.selected_completion_status != self.game.completion_status:
            # Update the completion status
            self.controller.data_handler.update_completion_status(
                self.game,
                self.selected_completion_status
            )

        # Only save game.yaml if necessary
        success = True
        if need_to_save_game_yaml:
            success = self.controller.data_handler.save_game(self.game)

        if success:
            # Update the details panel if open and showing this game
            if (self.parent_window.current_selected_game and
                self.parent_window.current_selected_game.id == self.game.id):
                self.parent_window.details_content.set_game(self.game)

            # Close the dialog first
            self.close()

            # Schedule sidebar refresh after dialog closes (async)
            GLib.timeout_add(50, lambda: self.controller.reload_data(refresh_sidebar=True) or False)

    @Gtk.Template.Callback()
    def on_download_metadata_clicked(self, button):
        """Handler for download metadata button click"""
        # Use the current title as the initial search term
        search_text = self.title_entry.get_text().strip()

        # Show the search dialog
        metadata_dialog = MetadataSearchDialog(self, self.controller)
        if search_text:
            # Pre-fill the search entry if we have a title
            metadata_dialog.search_entry.set_text(search_text)
            # Trigger the search programmatically
            metadata_dialog.perform_search(search_text)

        # Connect the result handler
        metadata_dialog.connect("metadata-selected", self._on_metadata_selected)
        metadata_dialog.show()

    def _on_metadata_selected(self, dialog, game_metadata, image_path):
        """Handle metadata selection from the search dialog"""
        # Update the title
        if game_metadata.name:
            self.title_entry.set_text(game_metadata.name)

        # Update the description if available
        if game_metadata.description:
            # Show the description group
            self.description_group.set_visible(True)
            # Set the description text in the TextView
            buffer = self.description_text.get_buffer()
            buffer.set_text(game_metadata.description)

        # Update the image if available
        if image_path:
            self.selected_image_path = image_path
            # Load the image directly for preview
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    image_path, 200, 260, True)
                if pixbuf:
                    self.image_preview.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
            except Exception as e:
                print(f"Error loading preview image: {e}")

        # Make sure the action button is enabled
        self.validate_form()


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

        # Initialize OpenCritic client
        self.metadata_client = OpenCriticClient()

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
            print(f"Error searching for '{query}': {e}")
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
            print(f"Selected result: {result_name} (ID: {result_id})")

            # Show the preview dialog
            self._show_game_details(result_id, result_name)

    def _show_game_details(self, game_id, game_name):
        """Show the game details preview dialog"""
        preview_dialog = MetadataPreviewDialog(self, self.controller, game_id, game_name)
        preview_dialog.connect("metadata-accepted", self._on_metadata_accepted)
        preview_dialog.show()

    def _on_metadata_accepted(self, dialog, game_metadata, image_path):
        """Handle metadata acceptance from the preview dialog"""
        # Close this dialog
        self.close()

        # Emit our signal for the parent dialog
        self.emit("metadata-selected", game_metadata, image_path)


@Gtk.Template(filename=get_template_path("metadata_preview_dialog.ui"))
class MetadataPreviewDialog(Adw.Window):
    """Dialog for previewing and confirming game metadata"""
    __gtype_name__ = "MetadataPreviewDialog"

    # Define custom signals
    __gsignals__ = {
        "metadata-accepted": (GObject.SignalFlags.RUN_FIRST, None, (object, str)),
    }

    # UI elements
    dialog_title: Adw.WindowTitle = Gtk.Template.Child()
    accept_button: Gtk.Button = Gtk.Template.Child()
    cancel_button: Gtk.Button = Gtk.Template.Child()
    game_image: Gtk.Picture = Gtk.Template.Child()
    game_title: Gtk.Label = Gtk.Template.Child()
    release_date: Gtk.Label = Gtk.Template.Child()
    publishers: Gtk.Label = Gtk.Template.Child()
    developers: Gtk.Label = Gtk.Template.Child()
    platforms: Gtk.Label = Gtk.Template.Child()
    genres: Gtk.Label = Gtk.Template.Child()
    score: Gtk.Label = Gtk.Template.Child()
    description_text: Gtk.TextView = Gtk.Template.Child()

    def __init__(self, parent_window, controller, game_id, game_name):
        super().__init__()
        self.parent_window = parent_window
        self.controller = controller
        self.set_transient_for(parent_window)
        self.game_id = game_id
        self.game_name = game_name
        self.game_metadata = None
        self.image_path = None

        # Initialize OpenCritic client
        self.metadata_client = OpenCriticClient()

        # Set the window title to include the game name
        self.dialog_title.set_title(f"Preview: {game_name}")

        # Set initial title
        self.game_title.set_text(game_name)

        # Disable the accept button until metadata is loaded
        self.accept_button.set_sensitive(False)

        # Start loading the game details
        self._load_game_details()

    def _load_game_details(self):
        """Load game details in a background thread"""
        # Start a loading spinner in the title bar
        spinner = Gtk.Spinner()
        spinner.set_spinning(True)
        spinner.set_size_request(16, 16)
        self.dialog_title.set_subtitle("Loading...")

        # Start the loading in a separate thread
        thread = threading.Thread(
            target=self._load_game_details_thread
        )
        thread.daemon = True
        thread.start()

    def _load_game_details_thread(self):
        """Background thread for loading game details"""
        try:
            # Fetch the game details
            game = self.metadata_client.get_details(self.game_id)

            # Check if we got valid results
            if game:
                # Store the metadata
                self.game_metadata = game

                # Download the cover image if available
                image_path = None
                if game.images and game.images.box and game.images.box.url:
                    image_path = self._download_image(game.images.box.url)

                # Update the UI in the main thread
                GLib.idle_add(self._update_game_details, game, image_path)
            else:
                GLib.idle_add(self._show_loading_error, "Failed to retrieve game details")
        except Exception as e:
            print(f"Error loading game details for ID {self.game_id}: {e}")
            GLib.idle_add(self._show_loading_error, str(e))

    def _download_image(self, image_url):
        """Download an image from a URL and save it to a temporary file"""
        try:
            response = requests.get(image_url, stream=True)
            if response.status_code == 200:
                # Create a temporary file to save the image
                tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                tmp_file.write(response.content)
                tmp_file.close()
                return tmp_file.name
            return None
        except Exception as e:
            print(f"Error downloading image from {image_url}: {e}")
            return None

    def _update_game_details(self, game, image_path):
        """Update the UI with game details (called in main thread)"""
        # Store the image path
        self.image_path = image_path

        # Update the dialog title
        self.dialog_title.set_subtitle("")

        # Update the game title
        self.game_title.set_text(game.name)

        # Update release date
        if game.first_release_date:
            self.release_date.set_text(game.first_release_date.strftime("%B %d, %Y"))
        else:
            self.release_date.set_text("Unknown")

        # Update publishers
        publishers = [c.name for c in game.companies if c.type.upper() == "PUBLISHER"]
        if publishers:
            self.publishers.set_text(", ".join(publishers))
        else:
            self.publishers.set_text("Unknown")

        # Update developers
        developers = [c.name for c in game.companies if c.type.upper() == "DEVELOPER"]
        if developers:
            self.developers.set_text(", ".join(developers))
        else:
            self.developers.set_text("Unknown")

        # Update platforms
        if game.platforms:
            platform_names = [p.name for p in game.platforms]
            self.platforms.set_text(", ".join(platform_names))
        else:
            self.platforms.set_text("Unknown")

        # Update genres
        if game.genres:
            genre_names = [g.name for g in game.genres]
            self.genres.set_text(", ".join(genre_names))
        else:
            self.genres.set_text("Unknown")

        # Update score
        if game.top_critic_score > 0:
            self.score.set_text(f"{game.top_critic_score:.1f}/100")
        else:
            self.score.set_text("Not rated")

        # Update description
        if game.description:
            buffer = self.description_text.get_buffer()
            buffer.set_text(game.description)
        else:
            buffer = self.description_text.get_buffer()
            buffer.set_text("No description available")

        # Update image if available
        if image_path:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    image_path, 200, 260, True)
                if pixbuf:
                    self.game_image.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
            except Exception as e:
                print(f"Error loading game image: {e}")

        # Enable the accept button
        self.accept_button.set_sensitive(True)

        return False  # Remove from idle queue

    def _show_loading_error(self, error_message):
        """Show an error message in the UI (called in main thread)"""
        self.dialog_title.set_subtitle("Error")

        # Update description to show error
        buffer = self.description_text.get_buffer()
        buffer.set_text(f"Error loading game details: {error_message}")

        # Disable the accept button
        self.accept_button.set_sensitive(False)

        return False  # Remove from idle queue

    @Gtk.Template.Callback()
    def on_cancel_clicked(self, button):
        """Handle cancel button click"""
        self.close()

    @Gtk.Template.Callback()
    def on_accept_clicked(self, button):
        """Handle accept button click"""
        if self.game_metadata:
            # Emit our signal with the metadata and image path
            self.emit("metadata-accepted", self.game_metadata, self.image_path)
            self.close()
