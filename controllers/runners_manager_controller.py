from pathlib import Path
from typing import Optional

from gi.repository import Gtk, Adw, Gio, GObject, GdkPixbuf, Gdk
from data import Runner
from data_mapping import Platforms

from controllers.common import get_template_path, show_error_dialog, show_confirmation_dialog, show_image_chooser_dialog


@Gtk.Template(filename=get_template_path("runners_manager.ui"))
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


@Gtk.Template(filename=get_template_path("runner_list_row.ui"))
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


@Gtk.Template(filename=get_template_path("runner_dialog.ui"))
class RunnerDialog(Adw.Window):
    """Dialog for adding or editing a runner"""
    __gtype_name__ = "RunnerDialog"

    # UI elements from template
    dialog_title: Adw.WindowTitle = Gtk.Template.Child()
    title_entry: Adw.EntryRow = Gtk.Template.Child()
    command_entry: Adw.EntryRow = Gtk.Template.Child()
    discord_switch: Adw.SwitchRow = Gtk.Template.Child()
    image_preview: Gtk.Picture = Gtk.Template.Child()
    select_image_button: Gtk.Button = Gtk.Template.Child()
    clear_image_container: Gtk.Box = Gtk.Template.Child()
    clear_image_button: Gtk.Button = Gtk.Template.Child()
    platform_flowbox: Gtk.FlowBox = Gtk.Template.Child()  # Platform selection flowbox
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
        self.selected_platforms = []  # Track selected platforms
        self.discord_enabled = True  # Default value for Discord presence

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

        # Initialize platform selection
        self._init_platform_selection()

        # Connect entry changes to validation
        self.title_entry.connect("notify::text", self.validate_form)
        self.command_entry.connect("notify::text", self.validate_form)

        # Perform initial validation
        self.validate_form()

    def _init_platform_selection(self):
        """Initialize the platform selection flowbox with all available platforms"""
        # Get sorted list of all platforms for better user experience
        platforms = sorted([p for p in Platforms], key=lambda p: p.value)

        # Clear any existing children
        while child := self.platform_flowbox.get_first_child():
            self.platform_flowbox.remove(child)

        # Create a checkbox for each platform
        for platform in platforms:
            # Create a checkbox with platform name
            checkbox = Gtk.CheckButton(label=platform.value)
            checkbox.set_name(platform.name)  # Use enum name as identifier

            # Connect checkbox state change to validate form
            checkbox.connect("toggled", self.validate_form)

            # Wrap in a FlowBoxChild
            flowbox_child = Gtk.FlowBoxChild()
            flowbox_child.set_child(checkbox)

            # Add to flowbox
            self.platform_flowbox.append(flowbox_child)

    def _get_selected_platforms(self):
        """Get list of selected platforms from the flowbox"""
        selected_platforms = []

        # Iterate through all children
        for i, child in enumerate(self.platform_flowbox):
            # Get the checkbox from the flowbox child
            checkbox = child.get_child()
            if checkbox and checkbox.get_active():
                # Get the platform enum from the checkbox name
                platform_name = checkbox.get_name()
                try:
                    platform = getattr(Platforms, platform_name)
                    selected_platforms.append(platform)
                except (AttributeError, TypeError):
                    print(f"Error: Platform {platform_name} not found in Platforms enum")

        return selected_platforms

    def _select_platforms(self, platforms):
        """Select the specified platforms in the flowbox"""
        if not platforms:
            return

        # Iterate through all children to find matching platforms
        for i, child in enumerate(self.platform_flowbox):
            checkbox = child.get_child()
            if checkbox:
                platform_name = checkbox.get_name()

                # Check if this platform is in the list
                for platform in platforms:
                    if platform.name == platform_name:
                        checkbox.set_active(True)
                        break

    def set_runner(self, runner: Runner):
        """Set the runner to edit (only for edit mode)"""
        if not self.edit_mode:
            return

        self.runner = runner
        self.title_entry.set_text(runner.title)
        self.command_entry.set_text(runner.command or "")
        self.discord_switch.set_active(runner.discord_enabled if hasattr(runner, 'discord_enabled') else True)
        self.discord_enabled = runner.discord_enabled if hasattr(runner, 'discord_enabled') else True
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

        # Select platforms if any
        if runner.platforms:
            self._select_platforms(runner.platforms)
            self.selected_platforms = runner.platforms.copy()

        # Enable the action button
        self.validate_form()

    @Gtk.Template.Callback()
    def on_entry_changed(self, entry, *args):
        self.validate_form()

    @Gtk.Template.Callback()
    def on_discord_toggled(self, switch, *args):
        self.discord_enabled = switch.get_active()
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

        # Check if the runner might be needed by any games based on platform compatibility
        games_with_matching_platforms = []

        # Check games that have platforms matching this runner
        for game in self.controller.get_games():
            # Skip games without platforms
            if not game.platforms:
                continue

            # Check if any game platform matches any runner platform
            for game_platform in game.platforms:
                if game_platform in self.runner.platforms:
                    games_with_matching_platforms.append(game)
                    break

        if games_with_matching_platforms:
            # Show warning that this runner has compatible games
            game_count = len(games_with_matching_platforms)
            game_titles = ", ".join([g.title for g in games_with_matching_platforms[:3]])
            if game_count > 3:
                game_titles += f" and {game_count - 3} more"

            # Instead of blocking removal, just inform the user
            show_confirmation_dialog(
                self,
                f"Runner '{self.runner.title}' has {game_count} compatible games",
                f"This runner supports platforms used by {game_count} games: {game_titles}. Do you still want to remove it?",
                self._on_remove_confirmation_response
            )
            return

        # Create a confirmation dialog
        show_confirmation_dialog(
            self,
            f"Remove runner '{self.runner.title}'?",
            "This action cannot be undone.",
            self._on_remove_confirmation_response
        )

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

        try:
            # Use data handler to remove the runner
            if self.controller.data_handler.remove_runner(self.runner):
                # Reload data
                self.controller.reload_data()

                # Close the dialog
                self.close()

                # If parent is RunnersManagerDialog, refresh it
                if isinstance(self.parent_window, RunnersManagerDialog):
                    self.parent_window.refresh_runners_list()

                # Refresh sidebar in main window
                self.refresh_main_window_sidebar()
            else:
                # Show error dialog for failed removal
                show_error_dialog(
                    self,
                    "Failed to remove runner",
                    "The runner file could not be removed."
                )
        except Exception as e:
            print(f"Error removing runner: {e}")
            # Show error dialog
            show_error_dialog(
                self,
                "Failed to remove runner",
                f"Error: {str(e)}"
            )

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
        current_discord_enabled = self.discord_switch.get_active()

        # Get currently selected platforms
        current_platforms = self._get_selected_platforms()

        print(f"Runner dialog validate_form: title='{title}', command='{command}', platforms: {len(current_platforms)}, discord: {current_discord_enabled}")
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

            # Check Discord enabled change
            original_discord_enabled = getattr(self.runner, 'discord_enabled', True)
            if current_discord_enabled != original_discord_enabled:
                has_changes = True
                print(f"Discord enabled changed from {original_discord_enabled} to {current_discord_enabled}")

            # Check image change
            if self.selected_image_path is not None:  # Only if image was explicitly changed
                has_changes = True
                print(f"Image changed to '{self.selected_image_path}'")

            # Check platforms change - get currently selected platforms
            current_platforms = self._get_selected_platforms()

            if len(current_platforms) != len(self.runner.platforms):
                has_changes = True
                print(f"Number of platforms changed from {len(self.runner.platforms)} to {len(current_platforms)}")
            else:
                # Check if the platforms are different
                for platform in current_platforms:
                    if platform not in self.runner.platforms:
                        has_changes = True
                        print(f"Platform {platform.value} added")
                        break

                for platform in self.runner.platforms:
                    if platform not in current_platforms:
                        has_changes = True
                        print(f"Platform {platform.value} removed")
                        break

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
        discord_enabled = self.discord_switch.get_active()

        # Get selected platforms
        platforms = self._get_selected_platforms()

        # Generate an ID based on the title
        runner_id = title.lower().replace(" ", "_")

        # Create the runner
        runner = Runner(
            id=runner_id,
            title=title,
            command=command,
            image=self.selected_image_path,
            platforms=platforms,
            discord_enabled=discord_enabled
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

            # Refresh the details panel if it's currently showing a game
            self.refresh_details_panel()

    def _save_runner_changes(self):
        """Save changes to an existing runner (edit mode)"""
        if not self.runner:
            return

        # Get the updated values
        title = self.title_entry.get_text().strip()
        command = self.command_entry.get_text().strip()
        discord_enabled = self.discord_switch.get_active()

        # Get selected platforms
        platforms = self._get_selected_platforms()

        # Update the runner object
        self.runner.title = title
        self.runner.command = command
        self.runner.platforms = platforms
        self.runner.discord_enabled = discord_enabled

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

            # Refresh the details panel if it's currently showing a game
            self.refresh_details_panel()

    def refresh_main_window_sidebar(self):
        """Refresh the sidebar in the main window to reflect changes"""
        if self.main_window and hasattr(self.main_window, 'refresh_sidebar_runners'):
            self.main_window.refresh_sidebar_runners()
        elif self.controller and hasattr(self.controller, 'window') and self.controller.window:
            if hasattr(self.controller.window, 'refresh_sidebar_runners'):
                self.controller.window.refresh_sidebar_runners()

    def refresh_details_panel(self):
        """Refresh the details panel if it's currently showing a game"""
        # Get window reference
        window = None
        if self.main_window:
            window = self.main_window
        elif self.controller and hasattr(self.controller, 'window') and self.controller.window:
            window = self.controller.window

        # If we found the window and it has a details panel
        if window and hasattr(window, 'details_panel') and window.details_panel:
            # Check if details panel is visible
            if window.details_panel.get_reveal_flap():
                # Get the current game being displayed
                if hasattr(window, 'current_selected_game') and window.current_selected_game:
                    # Get the details content
                    if hasattr(window, 'details_content') and window.details_content:
                        # Update the game details to refresh compatible runners section
                        window.details_content.set_game(window.current_selected_game)
