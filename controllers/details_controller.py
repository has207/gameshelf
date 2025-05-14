from datetime import datetime
from typing import Optional

from gi.repository import Gtk, GLib, Gdk
from data import Game, Runner
from data_mapping import CompletionStatus, Platforms
from process_tracking import ProcessTracker

from controllers.sidebar_controller import get_friendly_time, format_play_time
from controllers.common import show_error_dialog, get_template_path
import re
import html

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
    last_played_label: Gtk.Label = Gtk.Template.Child()
    play_time_label: Gtk.Label = Gtk.Template.Child()
    completion_status_label: Gtk.Label = Gtk.Template.Child()
    description_label: Gtk.Label = Gtk.Template.Child()
    platforms_label: Gtk.Label = Gtk.Template.Child()
    genres_label: Gtk.Label = Gtk.Template.Child()
    features_label: Gtk.Label = Gtk.Template.Child()
    age_ratings_label: Gtk.Label = Gtk.Template.Child()
    regions_label: Gtk.Label = Gtk.Template.Child()
    compatible_runners_box: Gtk.FlowBox = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        self.game = None
        self.controller = None
        self.compatible_runners = []  # List of compatible runners for the current game

    def _get_compatible_runners(self, game: Game) -> list:
        """
        Find runners that are compatible with the game's platforms.

        Args:
            game: The game to find compatible runners for

        Returns:
            List of compatible Runner objects
        """
        if not self.controller or not game.platforms:
            return []

        # Get all runners
        all_runners = self.controller.get_runners()

        # Filter to runners that support at least one of the game's platforms
        compatible = []
        for runner in all_runners:
            if not runner.platforms:
                continue

            # Check if any of the game's platforms are supported by this runner
            for platform in game.platforms:
                if platform in runner.platforms:
                    compatible.append(runner)
                    break

        return compatible

    def _add_runner_to_flowbox(self, runner: Runner):
        """
        Add a runner button to the compatible runners flowbox.

        Args:
            runner: The runner to add
        """
        # Create a button for the runner
        button = Gtk.Button(label=runner.title)
        button.set_tooltip_text(f"Run with {runner.title}")

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

            # Check if we have installation data (files) for this game
            installation_data = self.controller.data_handler.get_installation_data(self.game)
            file_path = None

            # If we have multiple files, show the file selection dialog
            if installation_data and "files" in installation_data and len(installation_data["files"]) > 0:
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

            # Launch the game with this runner and selected file (if any)
            self._launch_with_runner(runner, file_path)

    def _on_file_selected(self, dialog, file_path, runner):
        """
        Handle file selection dialog callback.

        Args:
            dialog: The dialog that was closed
            file_path: The selected file path
            runner: The runner to use
        """
        # Launch the game with this runner and selected file
        self._launch_with_runner(runner, file_path)

    def _launch_with_runner(self, runner: Runner, file_path: Optional[str] = None):
        """
        Launch the game with the given runner and file path.

        Args:
            runner: The runner to use
            file_path: Optional file path to launch
        """
        # Launch the game with this runner
        launch_success = self.controller.process_tracker.launch_game(
            self.game,
            runner.command,
            file_path,
            self._update_playtime_ui  # Callback when game exits
        )

        if launch_success:
            # Update the button state immediately
            self.play_button.set_label("Playing...")
            self.play_button.set_sensitive(False)

            # Update play count in UI (incremented by process tracker)
            self.play_count_label.set_text(f"Play Count: {self.game.play_count}")

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

            # Save state to settings
            window.controller.settings_manager.set_details_visible(False)
            window.controller.settings_manager.set_current_game_id(None)

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

        # Filter to runners with commands
        compatible_runners = [r for r in compatible_runners if r.command]

        if not compatible_runners:
            show_error_dialog(
                self.get_ancestor(Gtk.Window),
                "Invalid Runners",
                "None of the compatible runners have launch commands configured."
            )
            return

        # If we have only one compatible runner, use it directly
        if len(compatible_runners) == 1:
            runner = compatible_runners[0]
            self._on_runner_clicked(None, runner)
        else:
            # Show runner selection dialog
            from controllers.runner_selection_dialog import RunnerSelectionDialog
            window = self.get_ancestor(Gtk.Window)
            dialog = RunnerSelectionDialog(window, compatible_runners)
            dialog.connect("runner-selected", self._on_runner_selected_from_dialog)
            dialog.show()

    def _on_runner_selected_from_dialog(self, dialog, runner):
        """Handle runner selection from the dialog"""
        self._on_runner_clicked(None, runner)

    def _delayed_grid_refresh(self):
        """Refresh the game grid and sidebar after a short delay to ensure data is saved"""
        if self.controller:
            # Force a full reload with sidebar refresh
            self.controller.reload_data(refresh_sidebar=True)

            # This is a cleaner approach than using title_bar_controller.populate_games
            # as it ensures everything is refreshed properly
        return False  # Don't repeat the timeout

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

            # Update the play button state based on whether the game is running
            # (should be false now, but we check the file to be sure)
            if self.game.is_running(self.controller.data_handler.data_dir):
                self.play_button.set_label("Playing...")
                self.play_button.set_sensitive(False)
            else:
                # The game isn't running, enable the play button if there are compatible runners
                compatible_runners = self._get_compatible_runners(self.game)
                can_play = len(compatible_runners) > 0 and any(r.command for r in compatible_runners)

                self.play_button.set_label("Play Game")
                self.play_button.set_sensitive(can_play)

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
        Update the compatible runners flowbox based on the current game's platforms.
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

        # Add each compatible runner
        for runner in self.compatible_runners:
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

            # Set play count
            self.play_count_label.set_text(f"Play Count: {game.play_count}")

            # Set play time
            if game.play_time > 0:
                formatted_time = format_play_time(game.play_time)
                self.play_time_label.set_text(f"Play Time: {formatted_time}")
            else:
                self.play_time_label.set_text("Play Time: Not played")

            # Set completion status - use the enum value
            self.completion_status_label.set_text(f"Status: {game.completion_status.value}")

            last_played = game.get_last_played_time(self.controller.data_handler.data_dir)
            if last_played and game.play_count > 0:
                friendly_time = get_friendly_time(last_played)
                self.last_played_label.set_text(f"Last Played: {friendly_time}")
            else:
                self.last_played_label.set_text("Last Played: Never")

            # Set platforms if available
            if game.platforms and len(game.platforms) > 0:
                platform_names = [platform.value for platform in game.platforms]
                platform_text = ", ".join(platform_names)
                self.platforms_label.set_text(platform_text)
            else:
                self.platforms_label.set_text("No platforms available")

            # Set genres if available
            if game.genres and len(game.genres) > 0:
                genre_names = [genre.value for genre in game.genres]
                genre_text = ", ".join(genre_names)
                self.genres_label.set_text(genre_text)
            else:
                self.genres_label.set_text("No genres available")

            # Set features if available
            if game.features and len(game.features) > 0:
                feature_names = [feature.value for feature in game.features]
                feature_text = ", ".join(feature_names)
                self.features_label.set_text(feature_text)
            else:
                self.features_label.set_text("No features available")

            # Set age ratings if available
            if game.age_ratings and len(game.age_ratings) > 0:
                rating_names = [rating.value for rating in game.age_ratings]
                rating_text = ", ".join(rating_names)
                self.age_ratings_label.set_text(rating_text)
            else:
                self.age_ratings_label.set_text("No age ratings available")

            # Set regions if available
            if game.regions and len(game.regions) > 0:
                region_names = [region.value for region in game.regions]
                region_text = ", ".join(region_names)
                self.regions_label.set_text(region_text)
            else:
                self.regions_label.set_text("No regions available")

            # Set description if available with markup support
            if game.description:
                formatted_description = format_description_markup(game.description)
                self.description_label.set_markup(formatted_description)
            else:
                self.description_label.set_text("No description available")

        # Get compatible runners
        can_play = False
        self.compatible_runners = self._get_compatible_runners(game)
        can_play = len(self.compatible_runners) > 0 and any(r.command for r in self.compatible_runners)

        # Update the play button state based on whether the game is running
        if game.is_running(self.controller.data_handler.data_dir):
            self.play_button.set_label("Playing...")
            self.play_button.set_sensitive(False)
        else:
            self.play_button.set_label("Play Game")
            self.play_button.set_sensitive(can_play)


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

        # Restore details panel state from settings
        should_reveal = self.main_controller.settings_manager.get_details_visible()
        current_game_id = self.main_controller.settings_manager.get_current_game_id()

        # Set the controller for the details content
        if details_content:
            details_content.set_controller(self.main_controller)

        # If we have a current game ID from settings, try to restore it
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
