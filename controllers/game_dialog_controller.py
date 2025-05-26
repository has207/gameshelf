from typing import List, Optional, Dict, Type, Set
import logging
import html
from datetime import datetime

from gi.repository import Gtk, Adw, Gio, GObject, GdkPixbuf, Gdk, GLib

# Set up logger
logger = logging.getLogger(__name__)

from data import Game, Runner
from data_mapping import (
    CompletionStatus,
    Platforms, AgeRatings, Features, Genres, Regions,
    InvalidPlatformError, InvalidAgeRatingError, InvalidFeatureError, InvalidGenreError, InvalidRegionError
)
from controllers.common import get_template_path, show_image_chooser_dialog
from controllers.metadata_search_dialog_controller import MetadataSearchDialog
from controllers.metadata_selection_dialog import MetadataSelectionDialog


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
    first_played_button: Gtk.Button = Gtk.Template.Child()
    last_played_button: Gtk.Button = Gtk.Template.Child()
    completion_status_dropdown: Adw.ComboRow = Gtk.Template.Child()
    description_group: Adw.PreferencesGroup = Gtk.Template.Child()
    description_text: Gtk.TextView = Gtk.Template.Child()
    remove_game_container: Adw.PreferencesGroup = Gtk.Template.Child()
    remove_button: Gtk.Button = Gtk.Template.Child()
    download_metadata_button: Gtk.Button = Gtk.Template.Child()

    # Metadata UI elements
    metadata_group: Adw.PreferencesGroup = Gtk.Template.Child()
    platforms_summary_label: Gtk.Label = Gtk.Template.Child()
    genres_summary_label: Gtk.Label = Gtk.Template.Child()
    features_summary_label: Gtk.Label = Gtk.Template.Child()
    age_ratings_summary_label: Gtk.Label = Gtk.Template.Child()
    regions_summary_label: Gtk.Label = Gtk.Template.Child()

    @Gtk.Template.Callback()
    def on_first_played_clicked(self, button):
        """Handle first played date button click"""
        self._show_calendar_dialog("first_played")

    @Gtk.Template.Callback()
    def on_last_played_clicked(self, button):
        """Handle last played date button click"""
        self._show_calendar_dialog("last_played")

    def _show_calendar_dialog(self, field_type):
        """Show a calendar dialog for date selection"""
        dialog = Adw.Window()
        dialog.set_title("Select Date")
        dialog.set_modal(True)
        dialog.set_transient_for(self)
        dialog.set_default_size(320, 400)

        # Create main box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        dialog.set_content(main_box)

        # Header bar
        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        main_box.append(header)

        # Cancel button
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda b: dialog.close())
        header.pack_start(cancel_btn)

        # Select button
        select_btn = Gtk.Button(label="Select")
        select_btn.add_css_class("suggested-action")
        header.pack_end(select_btn)

        # Calendar widget
        calendar = Gtk.Calendar()
        calendar.set_margin_top(12)
        calendar.set_margin_bottom(12)
        calendar.set_margin_start(12)
        calendar.set_margin_end(12)

        # Set current date if available
        if field_type == "first_played" and self.first_played_date:
            # Convert Python date to GLib.DateTime
            glib_date = GLib.DateTime.new_local(
                self.first_played_date.year,
                self.first_played_date.month,
                self.first_played_date.day,
                0, 0, 0
            )
            calendar.select_day(glib_date)
        elif field_type == "last_played" and self.last_played_date:
            # Convert Python date to GLib.DateTime
            glib_date = GLib.DateTime.new_local(
                self.last_played_date.year,
                self.last_played_date.month,
                self.last_played_date.day,
                0, 0, 0
            )
            calendar.select_day(glib_date)

        main_box.append(calendar)

        # Clear button at bottom
        clear_btn = Gtk.Button(label="Clear Date")
        clear_btn.add_css_class("destructive-action")
        clear_btn.set_margin_top(12)
        clear_btn.set_margin_bottom(12)
        clear_btn.set_margin_start(12)
        clear_btn.set_margin_end(12)
        main_box.append(clear_btn)

        # Connect signals
        def on_select_clicked(btn):
            selected_date = calendar.get_date()
            # Convert GLib.DateTime to Python datetime.date
            python_date = selected_date.to_local().format("%Y-%m-%d")
            date_obj = datetime.strptime(python_date, "%Y-%m-%d").date()

            if field_type == "first_played":
                self.first_played_date = date_obj
                self.first_played_button.set_label(python_date)
            elif field_type == "last_played":
                self.last_played_date = date_obj
                self.last_played_button.set_label(python_date)
            self.validate_form()
            dialog.close()

        def on_clear_clicked(btn):
            if field_type == "first_played":
                self.first_played_date = None
                self.first_played_button.set_label("Select Date")
            elif field_type == "last_played":
                self.last_played_date = None
                self.last_played_button.set_label("Select Date")
            self.validate_form()
            dialog.close()

        select_btn.connect("clicked", on_select_clicked)
        clear_btn.connect("clicked", on_clear_clicked)

        dialog.present()

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

        # Initialize metadata lists
        self.selected_platforms = []
        self.selected_genres = []
        self.selected_features = []
        self.selected_age_ratings = []
        self.selected_regions = []


        # Date state for calendar dialogs
        self.first_played_date = None  # datetime.date object
        self.last_played_date = None   # datetime.date object

        # Adjust dialog height based on mode and parent window height
        parent_height = parent_window.get_height()
        if parent_height > 0:
            if edit_mode:
                # Edit mode needs more space for additional sections
                preferred_height = max(650, int(parent_height * 0.8))
            else:
                # Add mode can be more compact
                preferred_height = max(500, int(parent_height * 0.6))
            self.set_default_size(500, preferred_height)

        # Configure UI based on mode (add or edit)
        if edit_mode:
            self.dialog_title.set_title("Edit Game")
            self.action_button.set_label("Save Changes")
            self.clear_image_container.set_visible(True)
            self.select_image_button.set_label("Change Image")
            self.play_stats_group.set_visible(True)
            self.metadata_group.set_visible(True)
            self.remove_game_container.set_visible(True)
        else:
            self.dialog_title.set_title("Add New Game")
            self.action_button.set_label("Add Game")
            self.clear_image_container.set_visible(False)
            self.select_image_button.set_label("Select Image")
            self.play_stats_group.set_visible(False)
            self.metadata_group.set_visible(False)
            self.remove_game_container.set_visible(False)

        # Set up completion status dropdown
        self._populate_completion_status_dropdown()

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

        # Set timestamps if available
        if hasattr(game, 'first_played') and game.first_played:
            dt = datetime.fromtimestamp(game.first_played)
            self.first_played_date = dt.date()
            self.first_played_button.set_label(dt.strftime("%Y-%m-%d"))
        else:
            self.first_played_date = None
            self.first_played_button.set_label("Select Date")

        if hasattr(game, 'last_played') and game.last_played:
            dt = datetime.fromtimestamp(game.last_played)
            self.last_played_date = dt.date()
            self.last_played_button.set_label(dt.strftime("%Y-%m-%d"))
        else:
            self.last_played_date = None
            self.last_played_button.set_label("Select Date")

        # Set completion status from enum
        # Find the index of the completion status enum in completion_status_data
        for i, status in enumerate(self.completion_status_data):
            if status == game.completion_status:
                self.completion_status_dropdown.set_selected(i)
                self.selected_completion_status = status
                break

        # Load metadata values if available
        self.selected_platforms = game.platforms.copy() if game.platforms else []
        self.selected_genres = game.genres.copy() if game.genres else []
        self.selected_features = game.features.copy() if game.features else []
        self.selected_age_ratings = game.age_ratings.copy() if game.age_ratings else []
        self.selected_regions = game.regions.copy() if game.regions else []

        # Update metadata summary labels
        self._update_metadata_summary_labels()

        # Populate runners dropdown - for informational purposes only
        self.populate_runners(self.controller.get_runners())

        # Enable the action button
        self.validate_form()

    def populate_runners(self, runners: List[Runner]):
        """
        Store the list of runners but don't show the dropdown
        as runners are now associated via platforms
        """
        # Store runners list for reference
        self.runners_data = [None] + runners
        # Ensure the runner dropdown is hidden
        self.runner_dropdown.set_visible(False)

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
        """Handler for runner selection changes - no longer used but kept for compatibility"""
        # This handler is no longer used as runners are linked via platforms
        # We keep it for compatibility with the UI template
        pass

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
                logger.error(f"Error loading preview image: {e}")
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

            # Note: Runners are now associated via platforms instead of direct assignment

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

            # Check timestamp changes
            game_first_played = getattr(self.game, 'first_played', None)
            game_last_played = getattr(self.game, 'last_played', None)

            # Check first played changes
            current_first_timestamp = None
            if self.first_played_date:
                dt = datetime.combine(self.first_played_date, datetime.min.time())
                current_first_timestamp = dt.timestamp()

            if current_first_timestamp != game_first_played:
                has_changes = True

            # Check last played changes
            current_last_timestamp = None
            if self.last_played_date:
                dt = datetime.combine(self.last_played_date, datetime.min.time())
                current_last_timestamp = dt.timestamp()

            if current_last_timestamp != game_last_played:
                has_changes = True

            # Check completion status changes
            current_status = self.selected_completion_status
            game_status = self.game.completion_status
            if current_status != game_status:
                has_changes = True

            # Check metadata changes
            # For platforms
            game_platforms = self.game.platforms or []
            if set(self.selected_platforms) != set(game_platforms):
                has_changes = True

            # For genres
            game_genres = self.game.genres or []
            if set(self.selected_genres) != set(game_genres):
                has_changes = True

            # For features
            game_features = self.game.features or []
            if set(self.selected_features) != set(game_features):
                has_changes = True

            # For age ratings
            game_age_ratings = self.game.age_ratings or []
            if set(self.selected_age_ratings) != set(game_age_ratings):
                has_changes = True

            # For regions
            game_regions = self.game.regions or []
            if set(self.selected_regions) != set(game_regions):
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

        # Create the game using the data handler
        game = self.controller.data_handler.create_game_with_image(
            title=title,
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

        # Save metadata fields if any were selected (for new games)
        if success:
            # For platforms
            if self.selected_platforms:
                self.controller.data_handler.update_platforms(
                    game,
                    self.selected_platforms
                )

            # For genres
            if self.selected_genres:
                self.controller.data_handler.update_genres(
                    game,
                    self.selected_genres
                )

            # For features
            if self.selected_features:
                self.controller.data_handler.update_features(
                    game,
                    self.selected_features
                )

            # For age ratings
            if self.selected_age_ratings:
                self.controller.data_handler.update_age_ratings(
                    game,
                    self.selected_age_ratings
                )

            # For regions
            if self.selected_regions:
                self.controller.data_handler.update_regions(
                    game,
                    self.selected_regions
                )

        if success:
            # Reset form fields
            self.title_entry.set_text("")
            self.runner_dropdown.set_selected(0)  # Select "[none]"
            self.selected_runner = None
            self.selected_image_path = None
            self.metadata_description = None
            self.image_preview.set_paintable(None)

            # Reset metadata fields
            self.selected_platforms = []
            self.selected_genres = []
            self.selected_features = []
            self.selected_age_ratings = []
            self.selected_regions = []
            self._update_metadata_summary_labels()

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

        # Check if title changed (stored in game.yaml)
        if title != self.game.title:
            self.game.title = title
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
            logger.error(f"Error updating play count: {e}")

        try:
            play_time_text = self.play_time_entry.get_text().strip()
            if play_time_text:
                play_time = int(play_time_text)
                if play_time != self.game.play_time:
                    # Update play time with new value
                    self.controller.data_handler.update_play_time(self.game, play_time)
        except (ValueError, TypeError) as e:
            logger.error(f"Error updating play time: {e}")

        # Update timestamps
        try:
            # Update first played time
            if self.first_played_date:
                dt = datetime.combine(self.first_played_date, datetime.min.time())
                first_played_timestamp = dt.timestamp()
                current_first_played = getattr(self.game, 'first_played', None)
                if first_played_timestamp != current_first_played:
                    self.controller.data_handler.set_first_played_time(self.game, first_played_timestamp)
            else:
                # Clear first played time if no date selected
                if hasattr(self.game, 'first_played') and self.game.first_played:
                    self.controller.data_handler.set_first_played_time(self.game, None)

            # Update last played time
            if self.last_played_date:
                dt = datetime.combine(self.last_played_date, datetime.min.time())
                last_played_timestamp = dt.timestamp()
                current_last_played = getattr(self.game, 'last_played', None)
                if last_played_timestamp != current_last_played:
                    self.controller.data_handler.set_last_played_time(self.game, last_played_timestamp)
            else:
                # Clear last played time if no date selected
                if hasattr(self.game, 'last_played') and self.game.last_played:
                    self.controller.data_handler.set_last_played_time(self.game, None)

        except Exception as e:
            logger.error(f"Error updating timestamps: {e}")

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

        # Update metadata fields if they've changed

        # For platforms
        game_platforms = self.game.platforms or []
        if set(self.selected_platforms) != set(game_platforms):
            self.controller.data_handler.update_platforms(
                self.game,
                self.selected_platforms
            )

        # For genres
        game_genres = self.game.genres or []
        if set(self.selected_genres) != set(game_genres):
            self.controller.data_handler.update_genres(
                self.game,
                self.selected_genres
            )

        # For features
        game_features = self.game.features or []
        if set(self.selected_features) != set(game_features):
            self.controller.data_handler.update_features(
                self.game,
                self.selected_features
            )

        # For age ratings
        game_age_ratings = self.game.age_ratings or []
        if set(self.selected_age_ratings) != set(game_age_ratings):
            self.controller.data_handler.update_age_ratings(
                self.game,
                self.selected_age_ratings
            )

        # For regions
        game_regions = self.game.regions or []
        if set(self.selected_regions) != set(game_regions):
            self.controller.data_handler.update_regions(
                self.game,
                self.selected_regions
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
            # Close the dialog first
            self.close()

            # Schedule full refresh after dialog closes (async)
            def refresh_after_edit():
                self.controller.reload_data(refresh_sidebar=True)
                # Also refresh the details panel if it's showing this game
                if (hasattr(self.parent_window, 'current_selected_game') and
                    self.parent_window.current_selected_game and
                    self.parent_window.current_selected_game.id == self.game.id):
                    # Find the updated game in the reloaded data
                    for game in self.controller.games:
                        if game.id == self.game.id:
                            self.parent_window.current_selected_game = game
                            if hasattr(self.parent_window, 'details_content'):
                                self.parent_window.details_content.set_game(game)
                            break
                return False

            GLib.timeout_add(50, refresh_after_edit)

    @Gtk.Template.Callback()
    def on_select_platforms_clicked(self, row):
        """Handler for platforms selection"""
        dialog = MetadataSelectionDialog(
            self,
            "Select Platforms",
            Platforms,
            self.selected_platforms
        )
        dialog.connect("metadata-selected", self._on_platforms_selected)
        dialog.present()

    def _on_platforms_selected(self, dialog, platforms):
        """Handle platforms selection results"""
        self.selected_platforms = platforms
        self._update_metadata_summary_labels()
        self.validate_form()

    @Gtk.Template.Callback()
    def on_select_genres_clicked(self, row):
        """Handler for genres selection"""
        dialog = MetadataSelectionDialog(
            self,
            "Select Genres",
            Genres,
            self.selected_genres
        )
        dialog.connect("metadata-selected", self._on_genres_selected)
        dialog.present()

    def _on_genres_selected(self, dialog, genres):
        """Handle genres selection results"""
        self.selected_genres = genres
        self._update_metadata_summary_labels()
        self.validate_form()

    @Gtk.Template.Callback()
    def on_select_features_clicked(self, row):
        """Handler for features selection"""
        dialog = MetadataSelectionDialog(
            self,
            "Select Features",
            Features,
            self.selected_features
        )
        dialog.connect("metadata-selected", self._on_features_selected)
        dialog.present()

    def _on_features_selected(self, dialog, features):
        """Handle features selection results"""
        self.selected_features = features
        self._update_metadata_summary_labels()
        self.validate_form()

    @Gtk.Template.Callback()
    def on_select_age_ratings_clicked(self, row):
        """Handler for age ratings selection"""
        dialog = MetadataSelectionDialog(
            self,
            "Select Age Ratings",
            AgeRatings,
            self.selected_age_ratings
        )
        dialog.connect("metadata-selected", self._on_age_ratings_selected)
        dialog.present()

    def _on_age_ratings_selected(self, dialog, age_ratings):
        """Handle age ratings selection results"""
        self.selected_age_ratings = age_ratings
        self._update_metadata_summary_labels()
        self.validate_form()

    @Gtk.Template.Callback()
    def on_select_regions_clicked(self, row):
        """Handler for regions selection"""
        dialog = MetadataSelectionDialog(
            self,
            "Select Regions",
            Regions,
            self.selected_regions
        )
        dialog.connect("metadata-selected", self._on_regions_selected)
        dialog.present()

    def _on_regions_selected(self, dialog, regions):
        """Handle regions selection results"""
        self.selected_regions = regions
        self._update_metadata_summary_labels()
        self.validate_form()

    def _update_metadata_summary_labels(self):
        """Update the summary labels for all metadata fields"""
        # Update platforms label
        if self.selected_platforms:
            platforms_text = ", ".join([p.value for p in self.selected_platforms])
            if len(platforms_text) > 30:
                platforms_text = f"{len(self.selected_platforms)} selected"
            self.platforms_summary_label.set_text(platforms_text)
        else:
            self.platforms_summary_label.set_text("None selected")

        # Update genres label
        if self.selected_genres:
            genres_text = ", ".join([g.value for g in self.selected_genres])
            if len(genres_text) > 30:
                genres_text = f"{len(self.selected_genres)} selected"
            self.genres_summary_label.set_text(genres_text)
        else:
            self.genres_summary_label.set_text("None selected")

        # Update features label
        if self.selected_features:
            features_text = ", ".join([f.value for f in self.selected_features])
            if len(features_text) > 30:
                features_text = f"{len(self.selected_features)} selected"
            self.features_summary_label.set_text(features_text)
        else:
            self.features_summary_label.set_text("None selected")

        # Update age ratings label
        if self.selected_age_ratings:
            ratings_text = ", ".join([r.value for r in self.selected_age_ratings])
            if len(ratings_text) > 30:
                ratings_text = f"{len(self.selected_age_ratings)} selected"
            self.age_ratings_summary_label.set_text(ratings_text)
        else:
            self.age_ratings_summary_label.set_text("None selected")

        # Update regions label
        if self.selected_regions:
            regions_text = ", ".join([r.value for r in self.selected_regions])
            if len(regions_text) > 30:
                regions_text = f"{len(self.selected_regions)} selected"
            self.regions_summary_label.set_text(regions_text)
        else:
            self.regions_summary_label.set_text("None selected")

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
                logger.error(f"Error loading preview image: {e}")

        # Make sure the action button is enabled
        self.validate_form()

