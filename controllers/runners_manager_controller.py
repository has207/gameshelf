import os
from pathlib import Path
from typing import Optional

from gi.repository import Gtk, Adw, Gio, GObject, GdkPixbuf, Gdk
from data_handler import Runner

from controllers.sidebar_controller import show_image_chooser_dialog


@Gtk.Template(filename=os.path.join(os.path.dirname(os.path.dirname(__file__)), "layout", "runners_manager.ui"))
class RunnersManagerDialog(Adw.Window):
    """Dialog for managing all runners"""
    __gtype_name__ = "RunnersManagerDialog"

    runners_listbox: Gtk.ListBox = Gtk.Template.Child()
    empty_state: Gtk.Box = Gtk.Template.Child()
    add_runner_button: Gtk.Button = Gtk.Template.Child()
    close_button: Gtk.Button = Gtk.Template.Child()

    def __init__(self, parent_window, controller=None, main_window=None):
        super().__init__()
        self.parent_window = parent_window
        self.controller = controller or parent_window.controller
        self.main_window = main_window

        # Populate the list
        self.refresh_runners_list()

    def refresh_runners_list(self):
        """Refresh the list of runners"""
        # Clear current list
        while child := self.runners_listbox.get_first_child():
            self.runners_listbox.remove(child)

        # Get all runners
        runners = self.controller.get_runners()

        # Show empty state if no runners
        if not runners:
            self.empty_state.set_visible(True)
            self.runners_listbox.set_visible(False)
            return

        # Show runners
        self.empty_state.set_visible(False)
        self.runners_listbox.set_visible(True)

        # Add each runner to the list
        for runner in runners:
            row = RunnerListRow(runner, self.controller, self)
            self.runners_listbox.append(row)

    @Gtk.Template.Callback()
    def on_close_clicked(self, button):
        self.close()

    @Gtk.Template.Callback()
    def on_add_runner_clicked(self, button):
        """Open the dialog to add a new runner"""
        dialog = RunnerDialog(self, self.controller, edit_mode=False, main_window=self.main_window)
        dialog.set_transient_for(self)
        dialog.show()


@Gtk.Template(filename=os.path.join(os.path.dirname(os.path.dirname(__file__)), "layout", "runner_list_row.ui"))
class RunnerListRow(Gtk.ListBoxRow):
    """Row for displaying a runner in the list"""
    __gtype_name__ = "RunnerListRow"

    runner_icon: Gtk.Image = Gtk.Template.Child()
    title_label: Gtk.Label = Gtk.Template.Child()
    command_label: Gtk.Label = Gtk.Template.Child()
    edit_button: Gtk.Button = Gtk.Template.Child()

    def __init__(self, runner: Runner, controller, parent_dialog=None):
        super().__init__()
        self.runner = runner
        self.controller = controller
        self.parent_dialog = parent_dialog

        # Set runner details
        self.title_label.set_text(runner.title)
        if runner.command:
            self.command_label.set_text(runner.command)
        else:
            self.command_label.set_text("No command")

        # Set icon
        icon_name = self.controller.data_handler.get_runner_icon(runner.id)
        self.runner_icon.set_from_icon_name(icon_name)

    @Gtk.Template.Callback()
    def on_edit_clicked(self, button):
        """Open the edit dialog for this runner"""
        if self.parent_dialog:
            # Get the main window from the parent dialog
            from controllers.window_controller import GameShelfWindow
            main_window = getattr(self.parent_dialog, 'main_window', None)

            dialog = RunnerDialog(self.parent_dialog, self.controller, edit_mode=True, main_window=main_window)
            dialog.set_transient_for(self.parent_dialog)
            dialog.set_runner(self.runner)
            dialog.show()


@Gtk.Template(filename=os.path.join(os.path.dirname(os.path.dirname(__file__)), "layout", "runner_dialog.ui"))
class RunnerDialog(Adw.Window):
    """Dialog for adding or editing a runner"""
    __gtype_name__ = "RunnerDialog"

    # UI elements from template
    dialog_title: Adw.WindowTitle = Gtk.Template.Child()
    title_entry: Adw.EntryRow = Gtk.Template.Child()
    command_entry: Adw.EntryRow = Gtk.Template.Child()
    image_preview: Gtk.Picture = Gtk.Template.Child()
    select_image_button: Gtk.Button = Gtk.Template.Child()
    clear_image_container: Gtk.Box = Gtk.Template.Child()
    clear_image_button: Gtk.Button = Gtk.Template.Child()
    action_button: Gtk.Button = Gtk.Template.Child()
    cancel_button: Gtk.Button = Gtk.Template.Child()
    remove_runner_container: Adw.PreferencesGroup = Gtk.Template.Child()
    remove_button: Gtk.Button = Gtk.Template.Child()

    def __init__(self, parent_window, controller=None, edit_mode=False, main_window=None):
        super().__init__()
        self.parent_window = parent_window
        self.controller = controller or parent_window.controller
        self.main_window = main_window  # Reference to the main window for refreshing sidebar
        self.edit_mode = edit_mode
        self.selected_image_path = None
        self.original_image_path = None
        self.runner = None

        # Configure UI based on mode (add or edit)
        if edit_mode:
            self.dialog_title.set_title("Edit Runner")
            self.action_button.set_label("Save Changes")
            self.clear_image_container.set_visible(True)
            self.remove_runner_container.set_visible(True)
        else:
            self.dialog_title.set_title("Add New Runner")
            self.action_button.set_label("Add Runner")
            self.clear_image_container.set_visible(False)
            self.remove_runner_container.set_visible(False)

        # Update titles to indicate required fields
        if hasattr(self.title_entry, 'set_title'):
            self.title_entry.set_title("Title")
        if hasattr(self.command_entry, 'set_title'):
            self.command_entry.set_title("Command")

        # Add required field indicators next to the fields
        self._add_required_field_indicators()

        # (Tooltips are set in _add_required_field_indicators)

        # Connect entry changes to validation
        self.title_entry.connect("notify::text", self.validate_form)
        self.command_entry.connect("notify::text", self.validate_form)

        # Perform initial validation
        self.validate_form()

    def set_runner(self, runner: Runner):
        """Set the runner to edit (only for edit mode)"""
        if not self.edit_mode:
            return

        self.runner = runner
        self.title_entry.set_text(runner.title)
        self.command_entry.set_text(runner.command or "")
        self.selected_image_path = None
        self.original_image_path = runner.image

        # Load the runner image
        pixbuf = self.controller.get_runner_pixbuf(runner, width=128, height=128)
        if pixbuf:
            self.image_preview.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
        else:
            # Set default icon if no image is available
            icon_name = self.controller.data_handler.get_runner_icon(runner.id)
            icon_paintable = self.controller.data_handler.get_default_icon_paintable(icon_name, 96)
            self.image_preview.set_paintable(icon_paintable)

        # Enable the action button
        self.validate_form()

    @Gtk.Template.Callback()
    def on_entry_changed(self, entry, *args):
        self.validate_form()

    @Gtk.Template.Callback()
    def on_select_image_clicked(self, button):
        """Handler for select image button click"""
        show_image_chooser_dialog(self, self.on_image_selected, "Select Runner Icon")

    def on_image_selected(self, file_path):
        """Handler for image selection"""
        if file_path:
            self.selected_image_path = file_path

            # Load the image directly for preview
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    file_path, 128, 128, True)
                if pixbuf:
                    self.image_preview.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
                else:
                    # Set default icon for invalid image
                    icon_paintable = self.controller.data_handler.get_default_icon_paintable("image-missing", 96)
                    self.image_preview.set_paintable(icon_paintable)
                    self.selected_image_path = None
            except Exception as e:
                print(f"Error loading preview image: {e}")
                # Set default icon for invalid image
                icon_paintable = self.controller.data_handler.get_default_icon_paintable("image-missing", 96)
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
        icon_name = "application-x-executable-symbolic"
        if self.runner:
            icon_name = self.controller.data_handler.get_runner_icon(self.runner.id)
        icon_paintable = self.controller.data_handler.get_default_icon_paintable(icon_name, 96)
        self.image_preview.set_paintable(icon_paintable)
        self.validate_form()

    @Gtk.Template.Callback()
    def on_remove_button_clicked(self, button):
        """Handler for remove runner button click (edit mode only)"""
        if not self.edit_mode or not self.runner:
            return

        # Check if the runner is in use
        games_using_runner = [g for g in self.controller.get_games() if g.runner == self.runner.id]

        if games_using_runner:
            # Show warning that this runner is in use
            game_count = len(games_using_runner)
            game_titles = ", ".join([g.title for g in games_using_runner[:3]])
            if game_count > 3:
                game_titles += f" and {game_count - 3} more"

            dialog = Gtk.MessageDialog(
                transient_for=self,
                modal=True,
                message_type=Gtk.MessageType.WARNING,
                buttons=Gtk.ButtonsType.OK,
                text=f"Runner '{self.runner.title}' is in use",
                secondary_text=f"This runner is currently used by {game_count} games: {game_titles}"
            )
            dialog.connect("response", lambda dialog, response: dialog.destroy())
            dialog.show()
            return

        # Create a confirmation dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Remove runner '{self.runner.title}'?",
            secondary_text="This action cannot be undone."
        )
        dialog.connect("response", self._on_remove_confirmation_response)
        dialog.show()

    def _on_remove_confirmation_response(self, dialog, response_id):
        """Handle the response from the remove confirmation dialog"""
        if response_id == Gtk.ResponseType.YES:
            # User confirmed removal
            self._remove_runner()

        # Destroy the dialog in any case
        dialog.destroy()

    def _remove_runner(self):
        """Remove the runner and close the dialog"""
        if not self.runner:
            return

        # Get the runner file path
        runner_file = self.controller.data_handler.runners_dir / f"{self.runner.id}.yaml"

        # Delete the file if it exists
        if runner_file.exists():
            try:
                runner_file.unlink()

                # Reload data
                self.controller.reload_data()

                # Close the dialog
                self.close()

                # If parent is RunnersManagerDialog, refresh it
                if isinstance(self.parent_window, RunnersManagerDialog):
                    self.parent_window.refresh_runners_list()

                # Refresh sidebar in main window
                self.refresh_main_window_sidebar()
            except Exception as e:
                print(f"Error removing runner: {e}")
                # Show error dialog
                dialog = Gtk.MessageDialog(
                    transient_for=self,
                    modal=True,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Failed to remove runner",
                    secondary_text=f"Error: {str(e)}"
                )
                dialog.connect("response", lambda dialog, response: dialog.destroy())
                dialog.show()

    def _add_required_field_indicators(self):
        """Add required field indicators (red asterisks) next to required fields"""
        try:
            # Set normal titles without asterisks
            if hasattr(self.title_entry, 'set_title'):
                self.title_entry.set_title("Title")
            if hasattr(self.command_entry, 'set_title'):
                self.command_entry.set_title("Command")

            # For Adw.EntryRow, we can add a suffix widget with a red asterisk
            if hasattr(self.title_entry, 'add_suffix'):
                # Create a label with the asterisk
                asterisk_label = Gtk.Label(label="*")
                asterisk_label.add_css_class("required-asterisk")
                self.title_entry.add_suffix(asterisk_label)

            if hasattr(self.command_entry, 'add_suffix'):
                # Create a label with the asterisk
                asterisk_label = Gtk.Label(label="*")
                asterisk_label.add_css_class("required-asterisk")
                self.command_entry.add_suffix(asterisk_label)

            # Set tooltips on the entries to indicate they're required
            self.title_entry.set_tooltip_text("Required field")
            self.command_entry.set_tooltip_text("Required field")

        except Exception as e:
            print(f"Error adding required field indicators: {e}")

    def _update_required_field_indicators(self, title_empty=False, command_empty=False):
        """Update tooltips for required fields based on their state

        Args:
            title_empty: Whether the title field is empty
            command_empty: Whether the command field is empty
        """
        # Update tooltips to show more specific messages for empty fields
        if title_empty:
            self.title_entry.set_tooltip_text("Title is required - please enter a value")
        else:
            self.title_entry.set_tooltip_text("Required field")

        if command_empty:
            self.command_entry.set_tooltip_text("Command is required - please enter a value")
        else:
            self.command_entry.set_tooltip_text("Required field")

    def validate_form(self, *args):
        """Validate form fields and update action button sensitivity"""
        # Check if required fields are filled - only title is required
        title = self.title_entry.get_text().strip()
        command = self.command_entry.get_text().strip()
        has_title = len(title) > 0
        has_command = len(command) > 0

        print(f"Runner dialog validate_form: title='{title}', command='{command}'")
        print(f"Edit mode: {self.edit_mode}, Has title: {has_title}, Has command: {has_command}")

        if self.edit_mode and self.runner:
            # In edit mode, check if any changes were made
            has_changes = False

            # Check title change
            if title != self.runner.title:
                has_changes = True
                print(f"Title changed from '{self.runner.title}' to '{title}'")

            # Check command change
            if command != (self.runner.command or ""):
                has_changes = True
                print(f"Command changed from '{self.runner.command}' to '{command}'")

            # Check image change
            if self.selected_image_path is not None:  # Only if image was explicitly changed
                has_changes = True
                print(f"Image changed to '{self.selected_image_path}'")

            # Update button sensitivity - requires title, command, and changes
            self.action_button.set_sensitive(has_title and has_command and has_changes)
            print(f"Edit mode button sensitivity: {has_title and has_command and has_changes}")
        else:
            # In add mode, require both title and command
            self.action_button.set_sensitive(has_title and has_command)
            print(f"Add mode button sensitivity: {has_title and has_command}")

            # Update UI to clearly indicate required fields
            self._update_required_field_indicators(title_empty=not has_title, command_empty=not has_command)

    @Gtk.Template.Callback()
    def on_cancel_clicked(self, button):
        self.close()

    @Gtk.Template.Callback()
    def on_action_clicked(self, button):
        """Handle the primary action (add or save) based on the dialog mode"""
        if self.edit_mode:
            self._save_runner_changes()
        else:
            self._add_new_runner()

    def _add_new_runner(self):
        """Add a new runner (add mode)"""
        # Get the input values
        title = self.title_entry.get_text().strip()
        command = self.command_entry.get_text().strip()

        # Generate an ID based on the title
        runner_id = title.lower().replace(" ", "_")

        # Create the runner
        runner = Runner(
            id=runner_id,
            title=title,
            command=command,
            image=self.selected_image_path
        )

        # Save the runner through the controller
        if self.controller.add_runner(runner):
            # Close the dialog
            self.close()

            # If parent is RunnersManagerDialog, refresh it
            if isinstance(self.parent_window, RunnersManagerDialog):
                self.parent_window.refresh_runners_list()

            # Refresh sidebar in main window
            self.refresh_main_window_sidebar()

    def _save_runner_changes(self):
        """Save changes to an existing runner (edit mode)"""
        if not self.runner:
            return

        # Get the updated values
        title = self.title_entry.get_text().strip()
        command = self.command_entry.get_text().strip()

        # Update the runner object
        self.runner.title = title
        self.runner.command = command

        # Update image
        if self.selected_image_path is not None:  # Image was changed
            if self.selected_image_path:  # New image selected
                self.runner.image = self.selected_image_path
            else:  # Image was cleared
                self.runner.image = None

        # Save the updated runner
        if self.controller.add_runner(self.runner):
            # Close the dialog
            self.close()

            # If parent is RunnersManagerDialog, refresh it
            if isinstance(self.parent_window, RunnersManagerDialog):
                self.parent_window.refresh_runners_list()

            # Refresh sidebar in main window
            self.refresh_main_window_sidebar()

    def refresh_main_window_sidebar(self):
        """Refresh the sidebar in the main window to reflect changes"""
        if self.main_window and hasattr(self.main_window, 'refresh_sidebar_runners'):
            self.main_window.refresh_sidebar_runners()
        elif self.controller and hasattr(self.controller, 'window') and self.controller.window:
            if hasattr(self.controller.window, 'refresh_sidebar_runners'):
                self.controller.window.refresh_sidebar_runners()