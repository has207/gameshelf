import os
from typing import List, Optional
from pathlib import Path

from gi.repository import Gtk, Adw, Gio, GObject, GdkPixbuf, Gdk

from data_handler import Game, Runner
from controllers.sidebar_controller import show_image_chooser_dialog


@Gtk.Template(filename=os.path.join(os.path.dirname(os.path.dirname(__file__)), "layout", "context_menu.ui"))
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
        if window:
            window.details_content.set_game(self.game)
            window.details_content.on_remove_button_clicked(None)


@Gtk.Template(filename=os.path.join(os.path.dirname(os.path.dirname(__file__)), "layout", "game_dialog.ui"))
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
    remove_game_container: Adw.PreferencesGroup = Gtk.Template.Child()
    remove_button: Gtk.Button = Gtk.Template.Child()

    def __init__(self, parent_window, controller=None, edit_mode=False):
        super().__init__()
        self.parent_window = parent_window
        self.controller = controller or parent_window.controller
        self.edit_mode = edit_mode
        self.selected_runner = None
        self.selected_image_path = None
        self.original_image_path = None
        self.runners_data = []
        self.game = None

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
                self.close()

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

            # Close the dialog
            self.close()

    def _save_game_changes(self):
        """Save changes to an existing game (edit mode)"""
        if not self.game:
            return

        # Get the updated values
        title = self.title_entry.get_text().strip()
        runner_id = self.selected_runner.id if self.selected_runner else ""

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
                # Delete the cover.jpg file if it exists
                game_dir = self.controller.data_handler.games_dir / self.game.id
                cover_path = game_dir / "cover.jpg"
                if cover_path.exists():
                    try:
                        cover_path.unlink()
                    except Exception as e:
                        print(f"Error removing cover image: {e}")

        # Update the game object
        self.game.title = title
        self.game.runner = runner_id

        # Save the updated game
        if self.controller.add_game(self.game):
            # Update the details panel if open and showing this game
            if (self.parent_window.current_selected_game and
                self.parent_window.current_selected_game.id == self.game.id):
                self.parent_window.details_content.set_game(self.game)

            # Close the dialog
            self.close()