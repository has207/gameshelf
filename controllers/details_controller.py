import os
from datetime import datetime
from typing import Optional

from gi.repository import Gtk, GLib, Gdk
from data_handler import Game
from process_tracking import ProcessTracker

from controllers.sidebar_controller import get_friendly_time, format_play_time


@Gtk.Template(filename=os.path.join(os.path.dirname(os.path.dirname(__file__)), "layout", "details_panel.ui"))
class GameDetailsContent(Gtk.Box):
    __gtype_name__ = "GameDetailsContent"
    title_label: Gtk.Label = Gtk.Template.Child()
    runner_label: Gtk.Label = Gtk.Template.Child()
    runner_icon: Gtk.Image = Gtk.Template.Child()
    play_button: Gtk.Button = Gtk.Template.Child()
    edit_button: Gtk.Button = Gtk.Template.Child()
    toggle_hidden_button: Gtk.Button = Gtk.Template.Child()
    created_label: Gtk.Label = Gtk.Template.Child()
    modified_label: Gtk.Label = Gtk.Template.Child()
    play_count_label: Gtk.Label = Gtk.Template.Child()
    last_played_label: Gtk.Label = Gtk.Template.Child()
    play_time_label: Gtk.Label = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        self.game = None
        self.controller = None

    @Gtk.Template.Callback()
    def on_close_details_clicked(self, button):
        from controllers.window_controller import GameShelfWindow
        self.get_ancestor(GameShelfWindow).details_panel.set_reveal_flap(False)

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

        runner = self.controller.get_runner(self.game.runner)
        if runner and runner.command:
            # Launch the game
            launch_success = self.controller.process_tracker.launch_game(
                self.game,
                runner.command,
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
                dialog = Gtk.MessageDialog(
                    transient_for=self.get_ancestor(Gtk.Window),
                    modal=True,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Failed to launch game",
                    secondary_text="Could not start the game process"
                )
                dialog.connect("response", lambda dialog, response: dialog.destroy())
                dialog.show()

    def _delayed_grid_refresh(self):
        """Refresh the game grid after a short delay to ensure data is saved"""
        if self.controller:
            from controllers.window_controller import GameShelfWindow
            window = self.get_ancestor(GameShelfWindow)
            if window:
                search_text = window.search_entry.get_text().strip().lower() if window.search_entry else ""
                self.controller.title_bar_controller.populate_games(
                    filter_runner=self.controller.current_filter,
                    search_text=search_text
                )
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
                # The game isn't running, enable the play button if there's a valid runner
                can_play = False
                if self.controller and self.game.runner:
                    runner = self.controller.get_runner(self.game.runner)
                    can_play = runner is not None and runner.command is not None

                self.play_button.set_label("Play Game")
                self.play_button.set_sensitive(can_play)

            # Refresh the game grid to reflect updated sorting if we're sorting by play-related criteria
            if self.controller:
                # Check if current sort field is affected by playing a game
                sort_field = getattr(self.controller, 'sort_field', None)
                play_related_fields = ['last_played', 'play_time', 'play_count']

                if sort_field in play_related_fields:
                    # Refresh the game grid with current sorting and filtering settings
                    from controllers.window_controller import GameShelfWindow
                    window = self.get_ancestor(GameShelfWindow)
                    if window:
                        # Trigger a refresh by calling populate_games with existing parameters
                        self.controller.title_bar_controller.populate_games(
                            filter_runner=self.controller.current_filter,
                            search_text=window.search_entry.get_text().strip().lower() if window.search_entry else ""
                        )

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
            from controllers.dialogs_controller import GameDialog
            dialog = GameDialog(window, self.controller, edit_mode=True)
            dialog.set_transient_for(window)

            # Set the game to edit
            dialog.set_game(self.game)
            dialog.show()

    def set_game(self, game: Game):
        self.game = game
        self.title_label.set_text(game.title)

        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if window and window.controller:
            self.controller = window.controller

        if game.runner:
            runner_name = game.runner.capitalize()
            if self.controller:
                icon_name = self.controller.data_handler.get_runner_icon(game.runner)
                self.runner_icon.set_from_icon_name(icon_name)
        else:
            runner_name = "[none]"
            self.runner_icon.set_from_icon_name("dialog-question-symbolic")

        self.runner_label.set_text(runner_name)

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

            last_played = game.get_last_played_time(self.controller.data_handler.data_dir)
            if last_played and game.play_count > 0:
                friendly_time = get_friendly_time(last_played)
                self.last_played_label.set_text(f"Last Played: {friendly_time}")
            else:
                self.last_played_label.set_text("Last Played: Never")

        can_play = False
        if self.controller and game.runner:
            runner = self.controller.get_runner(game.runner)
            can_play = runner is not None and runner.command is not None

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

    def setup_details_panel(self, details_content, details_panel):
        self.details_content = details_content
        self.details_panel = details_panel

        # Initialize details panel
        if details_panel:
            details_panel.set_reveal_flap(False)

        # Set the controller for the details content
        if details_content:
            details_content.set_controller(self.main_controller)