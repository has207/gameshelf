import re
import html

from datetime import datetime
from typing import Optional

from gi.repository import Gtk, GLib, Gdk
from data import Game, Runner
from data_mapping import CompletionStatus, Platforms, LauncherType
from process_tracking import ProcessTracker

from controllers.sidebar_controller import get_friendly_time, format_play_time
from controllers.common import show_error_dialog, get_template_path

def format_description_markup(description: str) -> str:
    """
    Convert text description to Pango markup, preserving line breaks and basic HTML formatting.

    Args:
        description: The raw text description, may contain HTML tags

    Returns:
        Formatted description with Pango markup
    """
    if not description:
        return "No description available"

    # First, let's determine if this description seems to contain HTML
    has_html = bool(re.search(r'<[a-z]+[^>]*>', description.lower()))

    if has_html:
        # Process HTML-like description
        # Escape any special characters that would interfere with Pango markup
        escaped_desc = description.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        # Convert common HTML tags to Pango markup
        # Bold
        escaped_desc = re.sub(r'&lt;b&gt;(.*?)&lt;/b&gt;', r'<b>\1</b>', escaped_desc, flags=re.DOTALL)
        escaped_desc = re.sub(r'&lt;strong&gt;(.*?)&lt;/strong&gt;', r'<b>\1</b>', escaped_desc, flags=re.DOTALL)

        # Italic
        escaped_desc = re.sub(r'&lt;i&gt;(.*?)&lt;/i&gt;', r'<i>\1</i>', escaped_desc, flags=re.DOTALL)
        escaped_desc = re.sub(r'&lt;em&gt;(.*?)&lt;/em&gt;', r'<i>\1</i>', escaped_desc, flags=re.DOTALL)

        # Underline
        escaped_desc = re.sub(r'&lt;u&gt;(.*?)&lt;/u&gt;', r'<u>\1</u>', escaped_desc, flags=re.DOTALL)

        # Paragraph breaks
        escaped_desc = re.sub(r'&lt;p&gt;(.*?)&lt;/p&gt;', r'\1\n\n', escaped_desc, flags=re.DOTALL)

        # Convert HTML breaks to newlines
        escaped_desc = re.sub(r'&lt;br\s*/?&gt;', '\n', escaped_desc)

        # Handle lists
        escaped_desc = re.sub(r'&lt;li&gt;(.*?)&lt;/li&gt;', r'• \1\n', escaped_desc, flags=re.DOTALL)

        # Strip any remaining HTML tags
        escaped_desc = re.sub(r'&lt;[^&]*?&gt;', '', escaped_desc)

    else:
        # Plain text - just escape for Pango markup but preserve newlines
        escaped_desc = html.escape(description)
        # Make sure newlines are preserved
        escaped_desc = escaped_desc.replace('\n', '\n')

    # Replace multiple consecutive newlines with just two
    escaped_desc = re.sub(r'\n{3,}', '\n\n', escaped_desc)

    # For Pango markup, we need to explicitly represent newlines
    escaped_desc = escaped_desc.replace('\n', '&#10;')

    return escaped_desc

@Gtk.Template(filename=get_template_path("details_panel.ui"))
class GameDetailsContent(Gtk.Box):
    __gtype_name__ = "GameDetailsContent"
    title_label: Gtk.Label = Gtk.Template.Child()
    play_button: Gtk.Button = Gtk.Template.Child()
    edit_button: Gtk.Button = Gtk.Template.Child()
    toggle_hidden_button: Gtk.Button = Gtk.Template.Child()
    info_button: Gtk.Button = Gtk.Template.Child()
    created_label: Gtk.Label = Gtk.Template.Child()
    modified_label: Gtk.Label = Gtk.Template.Child()
    play_count_label: Gtk.Label = Gtk.Template.Child()
    first_played_label: Gtk.Label = Gtk.Template.Child()
    last_played_label: Gtk.Label = Gtk.Template.Child()
    play_time_label: Gtk.Label = Gtk.Template.Child()
    completion_status_label: Gtk.Label = Gtk.Template.Child()
    play_stats_box: Gtk.Box = Gtk.Template.Child()
    description_label: Gtk.Label = Gtk.Template.Child()
    platforms_label: Gtk.Label = Gtk.Template.Child()
    platforms_title_label: Gtk.Label = Gtk.Template.Child()
    genres_label: Gtk.Label = Gtk.Template.Child()
    genres_title_label: Gtk.Label = Gtk.Template.Child()
    features_label: Gtk.Label = Gtk.Template.Child()
    features_title_label: Gtk.Label = Gtk.Template.Child()
    age_ratings_label: Gtk.Label = Gtk.Template.Child()
    age_ratings_title_label: Gtk.Label = Gtk.Template.Child()
    regions_label: Gtk.Label = Gtk.Template.Child()
    regions_title_label: Gtk.Label = Gtk.Template.Child()
    source_label: Gtk.Label = Gtk.Template.Child()
    source_title_label: Gtk.Label = Gtk.Template.Child()
    developer_label: Gtk.Label = Gtk.Template.Child()
    developer_title_label: Gtk.Label = Gtk.Template.Child()
    publisher_label: Gtk.Label = Gtk.Template.Child()
    publisher_title_label: Gtk.Label = Gtk.Template.Child()
    compatible_runners_box: Gtk.FlowBox = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        self.game = None
        self.controller = None
        self.compatible_runners = []  # List of compatible runners for the current game

    def _get_compatible_runners(self, game: Game) -> list:
        """
        Find runners that are compatible with the game's platforms and launcher type.

        Args:
            game: The game to find compatible runners for

        Returns:
            List of compatible Runner objects
        """
        if not self.controller or not game.platforms:
            return []

        # Get all runners
        all_runners = self.controller.get_runners()

        # Get launcher type from the game object
        game_launcher_type = None
        if hasattr(game, 'launcher_type') and game.launcher_type:
            game_launcher_type = game.launcher_type

        # Filter to runners that support at least one of the game's platforms
        compatible = []
        generic_runners = []  # Runners with matching platforms but no launcher type

        for runner in all_runners:
            if not runner.platforms:
                continue

            # Track if this runner is platform-compatible
            platform_compatible = False

            # Check if any of the game's platforms are supported by this runner
            for platform in game.platforms:
                if platform in runner.platforms:
                    platform_compatible = True
                    break

            # If not platform compatible, skip this runner
            if not platform_compatible:
                continue

            # For games with launcher type, check for matching runners
            if game_launcher_type:
                # Check if runner has launcher type that matches the game
                if hasattr(runner, 'launcher_type') and runner.launcher_type:
                    # If runner launcher type matches game launcher type, add to compatible list
                    if runner.launcher_type == game_launcher_type:
                        compatible.append(runner)
                    else:
                        # Runner has launcher type but doesn't match the game's launcher type
                        # Skip this runner entirely for launcher-specific games
                        continue
                else:
                    # Runner with matching platform but no launcher type
                    generic_runners.append(runner)
            else:
                # For games without launcher type, only add runners that also don't have launcher type
                if not hasattr(runner, 'launcher_type') or not runner.launcher_type:
                    compatible.append(runner)
                # Skip runners with launcher_type for non-launcher games

        # If we have matched launcher-type runners, return only those
        if game_launcher_type and compatible:
            return compatible

        # Otherwise, return generic runners
        return compatible + generic_runners

    def _add_runner_to_flowbox(self, runner: Runner, launcher_type: Optional[str] = None):
        """
        Add a runner button to the compatible runners flowbox.

        Args:
            runner: The runner to add
            launcher_type: Optional launcher type to display with the runner
        """
        label_text = runner.title
        tooltip_text = f"Run with {runner.title}"

        # If launcher type is provided, add it to the button label
        if launcher_type:
            # Get the display name for the launcher type
            launcher_display = launcher_type
            try:
                # Try to convert to a nicer display name if it's a LauncherType enum value
                launcher_enum = getattr(LauncherType, launcher_type)
                launcher_display = launcher_enum.value
            except (AttributeError, ValueError):
                # If not a valid enum value, use the raw string
                pass

            # Update label and tooltip
            label_text = f"{runner.title} ({launcher_display})"
            tooltip_text = f"Run with {runner.title} - configured for {launcher_display}"

        # Create a button for the runner
        button = Gtk.Button(label=label_text)
        button.set_tooltip_text(tooltip_text)

        # Set up click handler
        button.connect("clicked", self._on_runner_clicked, runner)

        # Create flowbox child
        flowbox_child = Gtk.FlowBoxChild()
        flowbox_child.set_child(button)

        # Add to flowbox
        self.compatible_runners_box.append(flowbox_child)

    def _on_runner_clicked(self, button, runner: Runner):
        """
        Handle click on a runner button - launches the game with the selected runner.

        Args:
            button: The button that was clicked
            runner: The runner that was clicked
        """
        if not self.game or not self.controller:
            return

        # Directly launch the game with this runner
        if runner and runner.command:
            # Don't launch if the game is already running
            if self.game.is_running(self.controller.data_handler.data_dir):
                self.play_button.set_label("Playing...")
                self.play_button.set_sensitive(False)
                return

            # Check if we have launcher data or installation data for this game
            installation_data = self.controller.data_handler.get_installation_data(self.game)
            file_path = None
            launcher_id = None

            # Check if this is a game with launcher data
            if hasattr(self.game, 'launcher_id') and self.game.launcher_id:
                # Use launcher_id instead of file_path
                launcher_id = self.game.launcher_id
            else:
                # Check if this is a Wii U game
                is_wiiu_game = installation_data and "is_wiiu" in installation_data and installation_data["is_wiiu"]

                # For Wii U games, we don't need file selection - just pass directory to the runner
                if is_wiiu_game:
                    # We'll pass None for file_path, process_tracking will handle the directory
                    file_path = None
                # For regular games, we handle file selection
                elif installation_data and "files" in installation_data and len(installation_data["files"]) > 0:
                    files = installation_data["files"]

                    # If there's only one file, use it directly
                    if len(files) == 1:
                        file_path = files[0]
                    else:
                        # Show file selection dialog
                        from controllers.file_selection_dialog import FileSelectionDialog
                        dialog = FileSelectionDialog(
                            self.get_ancestor(Gtk.Window),
                            installation_data.get("directory", ""),
                            files
                        )
                        dialog.connect("file-selected", self._on_file_selected, runner)
                        dialog.show()
                        # Return and wait for the file selection callback
                        return

            # Launch the game with this runner and selected file or launcher ID
            self._launch_with_runner(runner, file_path, launcher_id)

    def _on_file_selected(self, dialog, file_path, runner):
        """
        Handle file selection dialog callback.

        Args:
            dialog: The dialog that was closed
            file_path: The selected file path
            runner: The runner to use
        """
        # Launch the game with this runner and selected file (no launcher ID in this path)
        self._launch_with_runner(runner, file_path, None)

    def _launch_with_runner(self, runner: Runner, file_path: Optional[str] = None, launcher_id: Optional[str] = None):
        """
        Launch the game with the given runner and file path or launcher ID.

        Args:
            runner: The runner to use
            file_path: Optional file path to launch
            launcher_id: Optional launcher-specific ID for the game
        """
        # Get the discord_enabled setting from the runner (default to True if not present)
        discord_enabled = getattr(runner, 'discord_enabled', True)

        # Launch the game with this runner, passing the discord_enabled setting
        # If launcher_id is provided, use that instead of file_path
        launch_success = self.controller.process_tracker.launch_game(
            self.game,
            runner.command,
            file_path,
            self._update_playtime_ui,  # Callback when game exits
            discord_enabled,  # Pass the Discord setting from the runner
            launcher_id  # Pass launcher ID if available
        )

        if launch_success:
            # Update the button state immediately
            self.play_button.set_label("Playing...")
            self.play_button.set_sensitive(False)

            # Update play count in UI (incremented by process tracker)
            if self.game.play_count is not None:
                self.play_count_label.set_text(f"Play Count: {self.game.play_count}")
                self.play_count_label.set_visible(True)
            else:
                self.play_count_label.set_visible(False)

            # Update completion status in UI (might have changed due to play count)
            self.completion_status_label.set_text(f"Status: {self.game.completion_status.value}")

            # Update last played timestamp (get it from the file)
            last_played = self.game.get_last_played_time(self.controller.data_handler.data_dir)
            if last_played:
                friendly_time = get_friendly_time(last_played)
                self.last_played_label.set_text(f"Last Played: {friendly_time}")

            # Refresh the game grid immediately if we're sorting by play count or last played
            # (play time will be updated when the process exits)
            sort_field = getattr(self.controller, 'sort_field', None)
            immediate_update_fields = ['last_played', 'play_count']

            if sort_field in immediate_update_fields:
                from controllers.window_controller import GameShelfWindow
                window = self.get_ancestor(GameShelfWindow)
                if window:
                    # Create a short delay to ensure changes are saved before refreshing
                    GLib.timeout_add(100, self._delayed_grid_refresh)
        else:
            # Show error dialog if launch failed
            show_error_dialog(
                self.get_ancestor(Gtk.Window),
                "Failed to launch game",
                "Could not start the game process"
            )

    @Gtk.Template.Callback()
    def on_close_details_clicked(self, button):
        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if window and window.controller:
            # Hide the panel
            window.details_panel.set_reveal_flap(False)

            # Save state to file
            window.controller.app_state_manager.set_details_visible(False)
            window.controller.app_state_manager.set_current_game_id(None)

    @Gtk.Template.Callback()
    def on_toggle_hidden_clicked(self, button):
        if not self.game or not self.controller:
            return

        # Toggle the hidden state using the controller
        self.controller.toggle_game_hidden(self.game)

        # Update the button icon based on the new state
        if self.game.hidden:
            self.toggle_hidden_button.set_icon_name("view-reveal-symbolic")
            self.toggle_hidden_button.set_tooltip_text("Unhide Game")
        else:
            self.toggle_hidden_button.set_icon_name("view-conceal-symbolic")
            self.toggle_hidden_button.set_tooltip_text("Hide Game")

    @Gtk.Template.Callback()
    def on_play_button_clicked(self, button):
        if not self.game or not self.controller:
            return

        # Don't launch if the game is already running
        if self.game.is_running(self.controller.data_handler.data_dir):
            self.play_button.set_label("Playing...")
            self.play_button.set_sensitive(False)
            return

        # Check if this is an install operation
        is_install_operation = self.play_button.get_label() == "Install Game"

        # Get compatible runners
        compatible_runners = self._get_compatible_runners(self.game)

        # Check if we have any compatible runners
        if not compatible_runners:
            show_error_dialog(
                self.get_ancestor(Gtk.Window),
                "No Compatible Runners",
                "No runners are compatible with this game's platform. Please add a runner for this platform."
            )
            return

        if is_install_operation:
            # Filter to runners with install commands and matching launcher type
            game_launcher_type = getattr(self.game, 'launcher_type', None)
            install_runners = []
            for runner in compatible_runners:
                if (hasattr(runner, 'launcher_type') and runner.launcher_type == game_launcher_type and
                    hasattr(runner, 'install_command') and runner.install_command):
                    install_runners.append(runner)

            if not install_runners:
                show_error_dialog(
                    self.get_ancestor(Gtk.Window),
                    "No Install Commands",
                    "None of the compatible runners have install commands configured."
                )
                return

            # Use install runners
            target_runners = install_runners
        else:
            # Filter to runners with launch commands
            play_runners = [r for r in compatible_runners if r.command]

            if not play_runners:
                show_error_dialog(
                    self.get_ancestor(Gtk.Window),
                    "Invalid Runners",
                    "None of the compatible runners have launch commands configured."
                )
                return

            # Use play runners
            target_runners = play_runners

        # If we have only one target runner, use it directly
        if len(target_runners) == 1:
            runner = target_runners[0]
            if is_install_operation:
                self._on_install_runner_clicked(runner)
            else:
                self._on_runner_clicked(None, runner)
        else:
            # Show runner selection dialog
            from controllers.runner_selection_dialog import RunnerSelectionDialog
            window = self.get_ancestor(Gtk.Window)
            dialog_title = "Select Install Runner" if is_install_operation else "Select Runner"
            dialog = RunnerSelectionDialog(window, target_runners, title=dialog_title)
            if is_install_operation:
                dialog.connect("runner-selected", self._on_install_runner_selected_from_dialog)
            else:
                dialog.connect("runner-selected", self._on_runner_selected_from_dialog)
            dialog.show()

    def _on_runner_selected_from_dialog(self, dialog, runner):
        """Handle runner selection from the dialog"""
        self._on_runner_clicked(None, runner)

    def _on_install_runner_selected_from_dialog(self, dialog, runner):
        """Handle install runner selection from the dialog"""
        self._on_install_runner_clicked(runner)

    def _on_install_runner_clicked(self, runner):
        """
        Handle click on an install runner - installs the game with the selected runner.

        Args:
            runner: The runner that was clicked for installation
        """
        if not self.game or not self.controller or not runner:
            return

        if not hasattr(runner, 'install_command') or not runner.install_command:
            show_error_dialog(
                self.get_ancestor(Gtk.Window),
                "No Install Command",
                f"Runner '{runner.title}' does not have an install command configured."
            )
            return

        # Use the install command instead of the regular command
        install_command = runner.install_command

        # Get launcher ID for the command
        launcher_id = None
        if hasattr(self.game, 'launcher_id') and self.game.launcher_id:
            launcher_id = self.game.launcher_id

        # Launch through process tracker using install command
        launch_success = self.controller.process_tracker.launch_game(
            self.game,
            install_command,
            None,  # No file path for install
            self._update_playtime_ui,  # Callback when install completes
            True,  # Discord enabled (can be configurable later)
            launcher_id  # Pass launcher ID
        )

        if launch_success:
            # Update the button state immediately
            self.play_button.set_label("Installing...")
            self.play_button.set_sensitive(False)
        else:
            show_error_dialog(
                self.get_ancestor(Gtk.Window),
                "Install Failed",
                "Failed to start the installation process."
            )

    def _delayed_grid_refresh(self):
        """Refresh the game grid and sidebar after a short delay to ensure data is saved"""
        if self.controller:
            # Force a full reload with sidebar refresh
            self.controller.reload_data(refresh_sidebar=True)

            # This is a cleaner approach than using title_bar_controller.populate_games
            # as it ensures everything is refreshed properly
        return False  # Don't repeat the timeout

    def _update_play_button_state(self, game: Game):
        """
        Update the play button state based on game's state and eligibility to be played.

        Args:
            game: The game to update the play button for
        """
        if not self.controller:
            return

        # Check if the game is running
        if game.is_running(self.controller.data_handler.data_dir):
            self.play_button.set_label("Playing...")
            self.play_button.set_sensitive(False)
            return

        # Check for compatible runners
        compatible_runners = self._get_compatible_runners(game)
        has_compatible_runners = len(compatible_runners) > 0 and any(r.command for r in compatible_runners)

        # Check for installation data
        installation_data = self.controller.data_handler.get_installation_data(game)

        # Check if this game has launcher data
        has_launcher_data = hasattr(game, 'launcher_id') and game.launcher_id

        # Check if this is a Wii U game (which doesn't use the files array)
        is_wiiu_game = installation_data and "is_wiiu" in installation_data and installation_data["is_wiiu"]

        # For Wii U games, we check if the directory exists
        if is_wiiu_game:
            has_installation_files = installation_data and "directory" in installation_data
        # For launcher games, check if they have installation data (meaning they're installed)
        elif has_launcher_data:
            has_installation_files = installation_data and "directory" in installation_data
        else:
            # For regular games, check for files list
            has_installation_files = installation_data and "files" in installation_data and len(installation_data["files"]) > 0

        # Update button state based on conditions
        if not has_installation_files:
            # Check if this is a launcher game that can be installed
            if has_launcher_data and has_compatible_runners:
                # Get the game's launcher type
                game_launcher_type = getattr(game, 'launcher_type', None)

                # Check if any compatible runner has an install command
                install_runners = []
                for runner in compatible_runners:
                    if (hasattr(runner, 'launcher_type') and runner.launcher_type == game_launcher_type and
                        hasattr(runner, 'install_command') and runner.install_command):
                        install_runners.append(runner)

                if install_runners:
                    self.play_button.set_label("Install Game")
                    self.play_button.set_sensitive(True)
                else:
                    self.play_button.set_label("No Game Files")
                    self.play_button.set_sensitive(False)
            else:
                self.play_button.set_label("No Game Files")
                self.play_button.set_sensitive(False)
        elif not has_compatible_runners:
            self.play_button.set_label("No Compatible Runners")
            self.play_button.set_sensitive(False)
        else:
            self.play_button.set_label("Play Game")
            self.play_button.set_sensitive(True)

    def _update_playtime_ui(self, game: Game):
        """
        Update the play time in the UI. This is called from the monitor thread via GLib.idle_add.

        Args:
            game: The game to update playtime for
        """
        if self.game and self.game.id == game.id:
            # Format the play time
            formatted_time = format_play_time(game.play_time)
            self.play_time_label.set_text(f"Play Time: {formatted_time}")

            # Update the play button state
            self._update_play_button_state(self.game)

            # Always refresh data including sidebar after game has stopped running
            if self.controller:
                # Force a full data reload to ensure all UI elements are up to date
                GLib.timeout_add(100, lambda: self.controller.reload_data(refresh_sidebar=True) or False)

        return False  # Return False to remove this function from the idle queue

    def set_controller(self, controller):
        self.controller = controller

    @Gtk.Template.Callback()
    def on_edit_button_clicked(self, button):
        if not self.game or not self.controller:
            return

        # Open the edit dialog
        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if window:
            # Create a new game dialog in edit mode
            from controllers.game_dialog_controller import GameDialog
            dialog = GameDialog(window, self.controller, edit_mode=True)
            dialog.set_transient_for(window)

            # Set the game to edit
            dialog.set_game(self.game)
            dialog.show()

    @Gtk.Template.Callback()
    def on_info_button_clicked(self, button):
        if not self.game or not self.controller:
            return

        # Get the game directory
        game_dir = self.game._get_game_dir_path(self.controller.data_handler.data_dir)

        # Open the directory in the default file manager
        import subprocess
        try:
            # Use xdg-open to open the directory in the default file manager
            subprocess.Popen(['xdg-open', str(game_dir)])
        except Exception as e:
            show_error_dialog(
                self.get_ancestor(Gtk.Window),
                "Failed to open directory",
                f"Could not open the game directory: {e}"
            )

    def _update_compatible_runners(self):
        """
        Update the compatible runners flowbox based on the current game's platforms and launcher type.
        """
        if not self.game or not self.controller:
            return

        # Clear existing items
        while child := self.compatible_runners_box.get_first_child():
            self.compatible_runners_box.remove(child)

        # Get compatible runners
        self.compatible_runners = self._get_compatible_runners(self.game)

        # If there are no compatible runners, add a message
        if not self.compatible_runners:
            label = Gtk.Label(label="No compatible runners found")
            label.add_css_class("dim-label")

            flowbox_child = Gtk.FlowBoxChild()
            flowbox_child.set_child(label)

            self.compatible_runners_box.append(flowbox_child)
            return

        # Add each compatible runner with additional info if it has launcher_type
        game_launcher_type = None
        if hasattr(self.game, 'launcher_type') and self.game.launcher_type:
            game_launcher_type = self.game.launcher_type

        for runner in self.compatible_runners:
            # Add launcher type indicator to the button if present
            if hasattr(runner, 'launcher_type') and runner.launcher_type:
                # Add runner with launcher type indicator
                self._add_runner_to_flowbox(runner, launcher_type=runner.launcher_type)
            else:
                # Add regular runner
                self._add_runner_to_flowbox(runner)

    def set_game(self, game: Game):
        self.game = game
        self.title_label.set_text(game.title)

        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if window and window.controller:
            self.controller = window.controller


        # Update the compatible runners section
        self._update_compatible_runners()

        # Update the toggle hidden button icon based on the game's hidden state
        if game.hidden:
            self.toggle_hidden_button.set_icon_name("view-reveal-symbolic")
            self.toggle_hidden_button.set_tooltip_text("Unhide Game")
        else:
            self.toggle_hidden_button.set_icon_name("view-conceal-symbolic")
            self.toggle_hidden_button.set_tooltip_text("Hide Game")

        if self.controller:
            if game.created:
                created_time = datetime.fromtimestamp(game.created).strftime("%Y-%m-%d %H:%M:%S")
                self.created_label.set_text(f"Added: {created_time}")
            else:
                self.created_label.set_text("Added: Unknown")

            modified_time = game.get_modified_time(self.controller.data_handler.data_dir)
            if modified_time:
                modified_str = datetime.fromtimestamp(modified_time).strftime("%Y-%m-%d %H:%M:%S")
                self.modified_label.set_text(f"Modified: {modified_str}")
            else:
                self.modified_label.set_text("Modified: Unknown")

            # Set play count - only show if > 0
            if game.play_count is not None and game.play_count > 0:
                self.play_count_label.set_text(f"Play Count: {game.play_count}")
                self.play_count_label.set_visible(True)
            else:
                self.play_count_label.set_visible(False)

            # Set play time - only show if > 0
            if game.play_time is not None and game.play_time > 0:
                formatted_time = format_play_time(game.play_time)
                self.play_time_label.set_text(f"Play Time: {formatted_time}")
                self.play_time_label.set_visible(True)
            else:
                self.play_time_label.set_visible(False)

            # Set completion status - always show
            self.completion_status_label.set_text(f"Status: {game.completion_status.value}")
            self.completion_status_label.set_visible(True)

            # Set first played - show if available
            first_played = game.get_first_played_time(self.controller.data_handler.data_dir)
            if first_played:
                friendly_time = get_friendly_time(first_played)
                self.first_played_label.set_text(f"First Played: {friendly_time}")
                self.first_played_label.set_visible(True)
            else:
                self.first_played_label.set_visible(False)

            # Set last played - show if available
            last_played = game.get_last_played_time(self.controller.data_handler.data_dir)
            if last_played:
                friendly_time = get_friendly_time(last_played)
                self.last_played_label.set_text(f"Last Played: {friendly_time}")
                self.last_played_label.set_visible(True)
            else:
                self.last_played_label.set_visible(False)

            # Set platforms if available
            if game.platforms and len(game.platforms) > 0:
                platform_names = [platform.value for platform in game.platforms]
                platform_text = ", ".join(platform_names)
                self.platforms_label.set_text(platform_text)
                self.platforms_label.set_visible(True)
                self.platforms_title_label.set_visible(True)
            else:
                self.platforms_label.set_visible(False)
                self.platforms_title_label.set_visible(False)

            # Set genres if available
            if game.genres and len(game.genres) > 0:
                # Decode HTML entities in genre names before displaying
                genre_names = [html.unescape(genre.value) for genre in game.genres]
                genre_text = ", ".join(genre_names)
                self.genres_label.set_text(genre_text)
                self.genres_label.set_visible(True)
                self.genres_title_label.set_visible(True)
            else:
                self.genres_label.set_visible(False)
                self.genres_title_label.set_visible(False)

            # Set features if available
            if game.features and len(game.features) > 0:
                feature_names = [feature.value for feature in game.features]
                feature_text = ", ".join(feature_names)
                self.features_label.set_text(feature_text)
                self.features_label.set_visible(True)
                self.features_title_label.set_visible(True)
            else:
                self.features_label.set_visible(False)
                self.features_title_label.set_visible(False)

            # Set age ratings if available
            if game.age_ratings and len(game.age_ratings) > 0:
                rating_names = [rating.value for rating in game.age_ratings]
                rating_text = ", ".join(rating_names)
                self.age_ratings_label.set_text(rating_text)
                self.age_ratings_label.set_visible(True)
                self.age_ratings_title_label.set_visible(True)
            else:
                self.age_ratings_label.set_visible(False)
                self.age_ratings_title_label.set_visible(False)

            # Set regions if available
            if game.regions and len(game.regions) > 0:
                region_names = [region.value for region in game.regions]
                region_text = ", ".join(region_names)
                self.regions_label.set_text(region_text)
                self.regions_label.set_visible(True)
                self.regions_title_label.set_visible(True)
            else:
                self.regions_label.set_visible(False)
                self.regions_title_label.set_visible(False)

            # Set source if available
            if hasattr(game, 'source') and game.source:
                # Get friendly source name
                source_name = game.source
                if game.source.isdigit():
                    # Try to get source name from the data handler
                    if self.controller and hasattr(self.controller, 'data_handler'):
                        source_obj = self.controller.data_handler.get_source_by_id(game.source)
                        if source_obj and hasattr(source_obj, 'name'):
                            source_name = source_obj.name
                        else:
                            # Use a default if we couldn't find the name
                            source_name = f"Source {game.source}"
                else:
                    # Just capitalize the source ID if it's not numeric
                    source_name = game.source.capitalize()

                self.source_label.set_text(source_name)
                self.source_label.set_visible(True)
                self.source_title_label.set_visible(True)
            else:
                self.source_label.set_visible(False)
                self.source_title_label.set_visible(False)

            # Set developer if available
            if hasattr(game, 'developer') and game.developer:
                self.developer_label.set_text(game.developer)
                self.developer_label.set_visible(True)
                self.developer_title_label.set_visible(True)
            else:
                self.developer_label.set_visible(False)
                self.developer_title_label.set_visible(False)

            # Set publisher if available
            if hasattr(game, 'publisher') and game.publisher:
                self.publisher_label.set_text(game.publisher)
                self.publisher_label.set_visible(True)
                self.publisher_title_label.set_visible(True)
            else:
                self.publisher_label.set_visible(False)
                self.publisher_title_label.set_visible(False)

            # Launcher data is already loaded in the game object from game.yaml

            # Set description if available with markup support
            if game.description:
                formatted_description = format_description_markup(game.description)
                self.description_label.set_markup(formatted_description)
            else:
                self.description_label.set_text("No description available")

        # Update the play button state
        self._update_play_button_state(game)


class DetailsController:
    def __init__(self, main_controller):
        self.main_controller = main_controller
        self.details_content = None

        # Create process tracker
        if not hasattr(main_controller, 'process_tracker'):
            main_controller.process_tracker = ProcessTracker(main_controller.data_handler)

    def update_game(self, game: Game) -> bool:
        """
        Update an existing game.

        Args:
            game: The game to update

        Returns:
            True if successful, False otherwise
        """
        return self.main_controller.data_handler.save_game(game, preserve_created_time=True)

    def setup_details_panel(self, details_content, details_panel):
        self.details_content = details_content
        self.details_panel = details_panel

        # Restore details panel state
        should_reveal = self.main_controller.app_state_manager.get_details_visible()
        current_game_id = self.main_controller.app_state_manager.get_current_game_id()

        # Set the controller for the details content
        if details_content:
            details_content.set_controller(self.main_controller)

        # If we have a current game ID from app state, try to restore it
        if current_game_id and should_reveal:
            # Find the game with the saved ID
            for game in self.main_controller.games:
                if game.id == current_game_id:
                    # Set the game in the details content
                    if details_content:
                        details_content.set_game(game)

                    # Reveal the details panel
                    if details_panel:
                        details_panel.set_reveal_flap(True)

                    # Store the current game in the window for state tracking
                    if self.main_controller.window:
                        self.main_controller.window.current_selected_game = game

                    # Game found and loaded
                    break
        else:
            # No game to restore, hide panel
            if details_panel:
                details_panel.set_reveal_flap(False)
