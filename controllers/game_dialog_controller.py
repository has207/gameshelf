from typing import List, Optional

from gi.repository import Gtk, Adw, Gio, GObject, GdkPixbuf, Gdk, GLib

from data import Game, Runner
from data_mapping import CompletionStatus
from controllers.common import get_template_path, show_image_chooser_dialog
from controllers.metadata_search_dialog_controller import MetadataSearchDialog


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
        self.metadata_description = None

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
        self.metadata_description = None  # Reset metadata description

        # Load the game image
        pixbuf = self.controller.get_game_pixbuf(game, width=200, height=260)
        if pixbuf:
            self.image_preview.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
        else:
            # Set default image if no image is available
            icon_paintable = self.controller.data_handler.get_default_icon_paintable("applications-games-symbolic", 128)
            self.image_preview.set_paintable(icon_paintable)

        # Load the description if available
        if game.description:
            self.description_group.set_visible(True)
            buffer = self.description_text.get_buffer()
            buffer.set_text(game.description)

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
        success = self.controller.add_game(game)

        # If we have a description from metadata, save it
        if success and self.metadata_description:
            self.controller.data_handler.update_game_description(
                game,
                self.metadata_description
            )

        if success:
            # Reset form fields
            self.title_entry.set_text("")
            self.runner_dropdown.set_selected(0)  # Select "[none]"
            self.selected_runner = None
            self.selected_image_path = None
            self.metadata_description = None
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

        # Update description if we have one from metadata
        if self.metadata_description:
            self.controller.data_handler.update_game_description(
                self.game,
                self.metadata_description
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

            # Store the description to save it when the game is created/updated
            self.metadata_description = game_metadata.description
        else:
            self.metadata_description = None

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