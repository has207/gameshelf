import gi
import os
import subprocess
import time
import threading
import psutil
from pathlib import Path
from datetime import datetime, timedelta
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GdkPixbuf, Gdk, GObject, GLib
from data_handler import DataHandler, Game, Runner
from typing import Dict, List, Optional, Tuple


def get_friendly_time(timestamp: float) -> str:
    """
    Convert a timestamp to a human-friendly relative time string.

    Args:
        timestamp: The timestamp to convert

    Returns:
        A string like "Just now", "Today", "Yesterday", "X days ago", etc.
    """
    now = datetime.now()
    dt = datetime.fromtimestamp(timestamp)

    # Calculate the difference
    diff = now - dt

    # Just now (within last hour)
    if diff < timedelta(hours=1):
        if diff < timedelta(minutes=1):
            return "Just now"
        elif diff < timedelta(minutes=2):
            return "1 minute ago"
        else:
            return f"{int(diff.total_seconds() / 60)} minutes ago"

    # Today
    if dt.date() == now.date():
        return "Today"

    # Yesterday
    if dt.date() == (now - timedelta(days=1)).date():
        return "Yesterday"

    # Within a week
    if diff < timedelta(days=7):
        return f"{diff.days} days ago"

    # Within a month
    if diff < timedelta(days=30):
        weeks = diff.days // 7
        if weeks == 1:
            return "1 week ago"
        return f"{weeks} weeks ago"

    # Within a year
    if diff < timedelta(days=365):
        months = diff.days // 30
        if months == 1:
            return "1 month ago"
        return f"{months} months ago"

    # More than a year
    years = diff.days // 365
    if years == 1:
        return "1 year ago"
    return f"{years} years ago"


def format_play_time(seconds: int) -> str:
    """
    Format play time in seconds to a human-readable string.

    Args:
        seconds: The number of seconds of play time

    Returns:
        A formatted string like "2h 15m", "45m", "30s", etc.
    """
    if seconds < 60:
        return f"{seconds}s"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"

    hours = minutes // 60
    minutes = minutes % 60

    if minutes == 0:
        return f"{hours}h"
    else:
        return f"{hours}h {minutes}m"


class SidebarItem(GObject.GObject):
    name = GObject.Property(type=str)
    icon_name = GObject.Property(type=str)

    def __init__(self, name, icon_name="applications-games-symbolic"):
        super().__init__()
        self.name = name
        self.icon_name = icon_name


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "sidebar_row.ui"))
class SidebarRow(Gtk.Box):
    __gtype_name__ = "SidebarRow"
    label: Gtk.Label = Gtk.Template.Child()
    icon: Gtk.Image = Gtk.Template.Child()

    def set_icon_name(self, icon_name):
        self.icon.set_from_icon_name(icon_name)


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "details_panel.ui"))
class GameDetailsContent(Gtk.Box):
    __gtype_name__ = "GameDetailsContent"
    title_label: Gtk.Label = Gtk.Template.Child()
    runner_label: Gtk.Label = Gtk.Template.Child()
    runner_icon: Gtk.Image = Gtk.Template.Child()
    play_button: Gtk.Button = Gtk.Template.Child()
    edit_button: Gtk.Button = Gtk.Template.Child()
    remove_button: Gtk.Button = Gtk.Template.Child()
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
        self.get_ancestor(GameShelfWindow).details_panel.set_reveal_flap(False)

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
            try:
                print(f"Launching game: {self.game.title} with command: {runner.command}")
                cmd = runner.command.split()

                # Launch the game
                process = subprocess.Popen(cmd)

                # Save the PID to the PID file
                self.controller.data_handler.save_game_pid(self.game, process.pid)

                # Update the button state immediately
                self.play_button.set_label("Playing...")
                self.play_button.set_sensitive(False)

                # Only increment play count if game launched successfully
                self.controller.data_handler.increment_play_count(self.game)

                # Update play count in UI
                self.play_count_label.set_text(f"Play Count: {self.game.play_count}")

                # Update last played timestamp (get it from the file)
                last_played = self.game.get_last_played_time(self.controller.data_handler.data_dir)
                if last_played:
                    friendly_time = get_friendly_time(last_played)
                    self.last_played_label.set_text(f"Last Played: {friendly_time}")

                # Start tracking the process to monitor play time
                self.monitor_game_process(process.pid, self.game)

            except Exception as e:
                print(f"Error launching game: {e}")
                dialog = Gtk.MessageDialog(
                    transient_for=self.get_ancestor(Gtk.Window),
                    modal=True,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Failed to launch game",
                    secondary_text=f"Error: {str(e)}"
                )
                dialog.connect("response", lambda dialog, response: dialog.destroy())
                dialog.show()

    def monitor_game_process(self, pid: int, game: Game):
        """
        Monitor a game process and update playtime when it exits.

        Args:
            pid: The process ID to monitor
            game: The game being played
        """
        # Start a new thread to monitor the process
        monitor_thread = threading.Thread(
            target=self._process_monitor_thread,
            args=(pid, game),
            daemon=True  # Make it a daemon so it doesn't block program exit
        )
        monitor_thread.start()

    def _process_monitor_thread(self, pid: int, game: Game):
        """
        Thread function to monitor a game process and update playtime.

        Args:
            pid: The process ID to monitor
            game: The game being played
        """
        try:
            # Get the file creation time for the pid.yaml file to use as our start time
            pid_file = Path(game.get_pid_path(self.controller.data_handler.data_dir))
            start_time = pid_file.stat().st_ctime

            # Try to get the process
            try:
                process = psutil.Process(pid)
                # Wait for process to exit
                process.wait()
            except psutil.NoSuchProcess:
                # Process doesn't exist or already exited
                print(f"Process {pid} for game {game.title} no longer exists or has already exited")
                # We'll continue to update the playtime anyway

            # Calculate play time
            end_time = time.time()
            seconds_played = int(end_time - start_time)

            # Don't count very short sessions (less than 1 second)
            if seconds_played < 1:
                seconds_played = 1  # At least record 1 second for very short sessions

            print(f"Game {game.title} played for {seconds_played} seconds")

            # Update the play time in the data handler
            self.controller.data_handler.update_play_time(game, seconds_played)

            # Remove the PID file since the process has exited
            self.controller.data_handler.clear_game_pid(game)

            # Update the UI on the main thread if this game is currently displayed
            GLib.idle_add(self._update_playtime_ui, game)

        except Exception as e:
            print(f"Error monitoring game process: {e}")
            # Make sure to clean up the PID file in case of error
            self.controller.data_handler.clear_game_pid(game)


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

        return False  # Return False to remove this function from the idle queue

    def set_controller(self, controller):
        self.controller = controller

    @Gtk.Template.Callback()
    def on_remove_button_clicked(self, button):
        if not self.game or not self.controller:
            return

        # Create a confirmation dialog
        window = self.get_ancestor(GameShelfWindow)
        if window:
            dialog = Gtk.MessageDialog(
                transient_for=window,
                modal=True,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text=f"Remove {self.game.title}?",
                secondary_text="This action cannot be undone. The game will be permanently removed."
            )
            dialog.connect("response", self._on_remove_confirmation_response)
            dialog.show()

    def _on_remove_confirmation_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.YES:
            # User confirmed removal
            if self.controller.remove_game(self.game):
                # Close the details panel
                window = self.get_ancestor(GameShelfWindow)
                if window:
                    window.details_panel.set_reveal_flap(False)
                    window.current_selected_game = None

        # Destroy the dialog in any case
        dialog.destroy()

    @Gtk.Template.Callback()
    def on_edit_button_clicked(self, button):
        if not self.game or not self.controller:
            return

        # Open the edit dialog
        window = self.get_ancestor(GameShelfWindow)
        if window:
            # Create a new game dialog in edit mode
            dialog = GameDialog(window, self.controller, edit_mode=True)
            dialog.set_transient_for(window)

            # Set the game to edit
            dialog.set_game(self.game)
            dialog.show()

    def set_game(self, game: Game):
        self.game = game
        self.title_label.set_text(game.title)

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


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "window.ui"))
class GameShelfWindow(Adw.ApplicationWindow):
    __gtype_name__ = "GameShelfWindow"

    games_grid: Gtk.GridView = Gtk.Template.Child()
    details_panel: Adw.Flap = Gtk.Template.Child()
    details_content: GameDetailsContent = Gtk.Template.Child()
    sidebar_listview: Gtk.ListView = Gtk.Template.Child()
    add_game_button: Gtk.Button = Gtk.Template.Child()
    search_entry: Gtk.SearchEntry = Gtk.Template.Child()

    def __init__(self, app, controller):
        super().__init__(application=app)
        self.controller = controller
        # Set the window reference in the controller
        self.controller.window = self
        # Track the currently selected game to maintain state across filtering
        self.current_selected_game = None

        # Debug to see if the UI template is loaded correctly
        print("Sidebar ListView:", self.sidebar_listview)
        print("Games Grid:", self.games_grid)
        print("Details Panel:", self.details_panel)

        # Only continue if the template elements exist
        if hasattr(self, 'sidebar_listview') and self.sidebar_listview is not None:
            self.sidebar_store = Gio.ListStore(item_type=SidebarItem)
            self.sidebar_store.append(SidebarItem("Games", "view-grid-symbolic"))

            # Add special entry for games with no runner
            self.sidebar_store.append(SidebarItem("No Runner", "dialog-question-symbolic"))

            # Add runners with appropriate icons
            for runner in self.controller.get_runners():
                icon_name = self.controller.data_handler.get_runner_icon(runner.id)
                self.sidebar_store.append(SidebarItem(runner.id, icon_name))

            factory = Gtk.SignalListItemFactory()
            factory.connect("setup", self._setup_sidebar_item)
            factory.connect("bind", self._bind_sidebar_item)

            selection = Gtk.SingleSelection(model=self.sidebar_store, autoselect=False)
            selection.connect("notify::selected", self._on_sidebar_selection)

            self.sidebar_listview.set_model(selection)
            self.sidebar_listview.set_factory(factory)

            selection.set_selected(0)

        # Only bind grid if it exists
        if hasattr(self, 'games_grid') and self.games_grid is not None:
            self.controller.bind_gridview(self.games_grid)

        # Only setup details panel if it exists
        if hasattr(self, 'details_panel') and self.details_panel is not None:
            self.details_panel.set_reveal_flap(False)

            # Only setup selection model if games_grid exists
            if hasattr(self, 'games_grid') and self.games_grid is not None:
                selection_model = self.games_grid.get_model()
                if isinstance(selection_model, Gtk.SingleSelection):
                    selection_model.connect("notify::selected-item", self._on_game_selected)

    @Gtk.Template.Callback()
    def on_add_game_clicked(self, button):
        # Create a new game dialog in add mode
        dialog = GameDialog(self, self.controller, edit_mode=False)
        dialog.set_transient_for(self)

        # Populate runners list with fresh data
        dialog.populate_runners(self.controller.get_runners())
        dialog.show()


    def _setup_sidebar_item(self, factory, list_item):
        sidebar_row = SidebarRow()
        list_item.set_child(sidebar_row)

    def _bind_sidebar_item(self, factory, list_item):
        row = list_item.get_child()
        item = list_item.get_item()
        row.label.set_label(item.name.capitalize())
        row.set_icon_name(item.icon_name)

    def _on_game_selected(self, selection, param):
        selected_item = selection.get_selected_item()
        if not selected_item or not selected_item.get_first_child():
            return

        game_box = selected_item
        if not game_box or not game_box.get_first_child():
            return

    def _on_sidebar_selection(self, selection, param):
        index = selection.get_selected()
        if index == -1:
            return

        # Save current details panel state
        was_panel_open = self.details_panel.get_reveal_flap()

        selected = self.sidebar_store.get_item(index).name

        # Clear the search entry when changing sidebar selection
        if self.search_entry.get_text():
            self.search_entry.set_text("")

        if selected == "Games":
            self.controller.populate_games()
        elif selected == "No Runner":
            # Special case for games with no runner
            self.controller.populate_games(filter_runner="")
        else:
            self.controller.populate_games(filter_runner=selected)

    @Gtk.Template.Callback()
    def on_search_changed(self, search_entry):
        """Handle search entry text changes"""
        search_text = search_entry.get_text().strip().lower()

        # Populate games with search filter
        self.controller.populate_games(search_text=search_text)


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "game_item.ui"))
class GameItem(Gtk.Box):
    __gtype_name__ = "GameItem"
    image: Gtk.Picture = Gtk.Template.Child()
    label: Gtk.Label = Gtk.Template.Child()

    def __init__(self, game: Game, controller):
        super().__init__()
        self.game = game
        self.controller = controller
        self.label.set_label(game.title)

        # Try to load the game image
        pixbuf = controller.get_game_pixbuf(game)
        if pixbuf:
            self.image.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
        else:
            # Get a default icon paintable from the data handler
            icon_paintable = controller.data_handler.get_default_icon_paintable("applications-games-symbolic")
            self.image.set_paintable(icon_paintable)

        # Add left-click gesture for showing details panel
        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("released", self._on_clicked)
        self.add_controller(click_gesture)

        # Add right-click gesture for context menu
        right_click = Gtk.GestureClick.new()
        right_click.set_button(3)  # Right mouse button
        right_click.connect("pressed", self._on_right_click)
        self.add_controller(right_click)

    def _create_context_menu(self):
        # Create a context menu from the template
        context_menu = GameContextMenu(self.game, self)
        context_menu.set_parent(self)
        return context_menu

    def _on_right_click(self, gesture, n_press, x, y):
        # Show context menu at pointer position
        menu = self._create_context_menu()
        if not menu:
            return

        # Find the main window
        window = self.get_ancestor(GameShelfWindow)
        if window:
            # Store the selected game to maintain state
            window.current_selected_game = self.game

        # Set the position to be at the mouse pointer
        rect = Gdk.Rectangle()
        rect.x = x
        rect.y = y
        rect.width = 1
        rect.height = 1
        menu.set_pointing_to(rect)

        # Show the menu
        menu.popup()


    def _on_clicked(self, gesture, n_press, x, y):
        # Only handle left clicks (button 1)
        if gesture.get_current_button() != 1:
            return

        # Find the main window to access the details panel
        window = self.get_ancestor(GameShelfWindow)
        if window:
            # Store the selected game to maintain state across filtering
            window.current_selected_game = self.game
            window.details_content.set_game(self.game)
            window.details_panel.set_reveal_flap(True)


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "runner_item.ui"))
class RunnerItem(Gtk.Box):
    __gtype_name__ = "RunnerItem"
    image: Gtk.Picture = Gtk.Template.Child()
    label: Gtk.Label = Gtk.Template.Child()

    def __init__(self, runner: Runner, controller):
        super().__init__()
        self.label.set_label(runner.title)

        # Try to load the runner image
        pixbuf = controller.get_runner_pixbuf(runner)
        if pixbuf:
            self.image.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
        else:
            # Set a default icon when no image is available
            icon_name = controller.data_handler.get_runner_icon(runner.id)
            self.image.set_from_icon_name(icon_name)


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "context_menu.ui"))
class GameContextMenu(Gtk.Popover):
    """Context menu for game items in the grid"""
    __gtype_name__ = "GameContextMenu"

    # Template child widgets
    play_button: Gtk.Button = Gtk.Template.Child()
    edit_button: Gtk.Button = Gtk.Template.Child()
    remove_button: Gtk.Button = Gtk.Template.Child()

    def __init__(self, game: Game, parent_item):
        super().__init__()
        self.game = game
        self.parent_item = parent_item

        # Connect button signals
        self.play_button.connect("clicked", self._on_play_clicked)
        self.edit_button.connect("clicked", self._on_edit_clicked)
        self.remove_button.connect("clicked", self._on_remove_clicked)

        # Add CSS classes
        self.play_button.add_css_class("context-menu-item")
        self.edit_button.add_css_class("context-menu-item")
        self.remove_button.add_css_class("context-menu-item")
        self.remove_button.add_css_class("context-menu-item-destructive")

    def _on_play_clicked(self, button):
        self.popdown()
        window = self.get_ancestor(GameShelfWindow)
        if window:
            window.details_content.set_game(self.game)
            window.details_content.on_play_button_clicked(None)

    def _on_edit_clicked(self, button):
        self.popdown()
        window = self.get_ancestor(GameShelfWindow)
        if window:
            window.details_content.set_game(self.game)
            window.details_content.on_edit_button_clicked(None)

    def _on_remove_clicked(self, button):
        self.popdown()
        window = self.get_ancestor(GameShelfWindow)
        if window:
            window.details_content.set_game(self.game)
            window.details_content.on_remove_button_clicked(None)


def show_image_chooser_dialog(parent_window, callback):
    """
    Shows a file chooser dialog for selecting images.

    Args:
        parent_window: The parent window for the dialog
        callback: Function to call with the selected file path or None if canceled
    """
    dialog = Gtk.FileChooserDialog(
        title="Select Game Cover Image",
        action=Gtk.FileChooserAction.OPEN,
        transient_for=parent_window,
        modal=True
    )

    # Add buttons
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.add_button("Select", Gtk.ResponseType.ACCEPT)

    # Add filters
    filter_images = Gtk.FileFilter()
    filter_images.set_name("Images")
    filter_images.add_mime_type("image/jpeg")
    filter_images.add_mime_type("image/png")
    dialog.add_filter(filter_images)

    def on_response(dialog, response):
        path = None
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                path = file.get_path()

        callback(path)
        dialog.destroy()

    dialog.connect("response", on_response)
    dialog.show()




@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "game_dialog.ui"))
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
        else:
            self.dialog_title.set_title("Add New Game")
            self.action_button.set_label("Add Game")
            self.clear_image_container.set_visible(False)
            self.select_image_button.set_label("Select Image")

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
    def on_entry_changed(self, entry):
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


class GameShelfController:
    def __init__(self, data_handler: DataHandler):
        self.data_handler = data_handler
        self.games = self.data_handler.load_games()
        self.runners = {runner.id: runner for runner in self.data_handler.load_runners()}
        self.current_filter = None
        self.window = None
        self.actions = {}

    def get_games(self) -> List[Game]:
        return self.games

    def get_runners(self) -> List[Runner]:
        return list(self.runners.values())

    def get_runner(self, runner_id: str) -> Optional[Runner]:
        return self.runners.get(runner_id)

    def add_game(self, game: Game) -> bool:
        result = self.data_handler.save_game(game)
        if result:
            self.reload_data()
        return result

    def add_runner(self, runner: Runner) -> bool:
        result = self.data_handler.save_runner(runner)
        if result:
            self.reload_data()
        return result

    def remove_game(self, game: Game) -> bool:
        """Remove a game and refresh the UI"""
        result = self.data_handler.remove_game(game)
        if result:
            # Reload data to refresh the UI
            self.reload_data()
        return result

    def reload_data(self):
        """Reload all data from storage and refresh the UI"""
        self.games = self.data_handler.load_games()
        self.runners = {runner.id: runner for runner in self.data_handler.load_runners()}

        # Get search text from the window if available
        search_text = ""
        if self.window and hasattr(self.window, 'search_entry'):
            search_text = self.window.search_entry.get_text().strip().lower()

        self.populate_games(filter_runner=self.current_filter, search_text=search_text)

    def get_game_pixbuf(self, game: Game, width: int = 200, height: int = 260) -> Optional[GdkPixbuf.Pixbuf]:
        """Get a game's image as a pixbuf, using the data handler"""
        return self.data_handler.load_game_image(game, width, height)

    def get_runner_pixbuf(self, runner: Runner, width: int = 64, height: int = 64) -> Optional[GdkPixbuf.Pixbuf]:
        """Get a runner's image as a pixbuf, using the data handler"""
        return self.data_handler.load_runner_image(runner, width, height)

    def bind_gridview(self, grid_view: Gtk.GridView):
        self.games_model = Gio.ListStore(item_type=Gtk.Widget)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_factory_setup)
        factory.connect("bind", self._on_factory_bind)

        # Create selection model that doesn't auto-select the first item
        selection_model = Gtk.SingleSelection(model=self.games_model, autoselect=False)
        grid_view.set_model(selection_model)
        grid_view.set_factory(factory)

        # Set fixed size for grid items
        grid_view.set_enable_rubberband(False)

        self.populate_games()

    def _on_factory_setup(self, factory, list_item):
        # Create a simple container box to hold our game items
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        list_item.set_child(box)

    def _on_factory_bind(self, factory, list_item):
        box = list_item.get_child()
        # Remove any existing children
        child = box.get_first_child()
        while child:
            box.remove(child)
            child = box.get_first_child()

        # Add our game item
        position = list_item.get_position()
        if position < self.games_model.get_n_items():
            game_item = self.games_model.get_item(position)
            box.append(game_item)

    def populate_games(self, filter_runner: Optional[str] = None, search_text: str = ""):
        self.current_filter = filter_runner
        self.games_model.remove_all()
        games = self.get_games()

        # Apply runner filter
        if filter_runner is not None:  # Filter is specifically set (including empty string)
            games = [g for g in games if g.runner == filter_runner]

        # Apply search filter if search text is provided
        if search_text:
            games = [g for g in games if search_text in g.title.lower()]

        # Create widgets for the games
        for game in games:
            game_item = self.create_game_widget(game)
            self.games_model.append(game_item)

    def create_game_widget(self, game: Game) -> Gtk.Widget:
        return GameItem(game, self)

    def create_runner_widget(self, runner: Runner) -> Gtk.Widget:
        return RunnerItem(runner, self)

    def add_action(self, action: Gio.SimpleAction):
        """
        Add an action to the controller's action map.
        This is used for the context menu actions.

        Args:
            action: The action to add
        """
        # Store a reference to the action to prevent it from being garbage collected
        action_name = action.get_name()
        self.actions[action_name] = action

        # Add the action to the window's action map if available
        if self.window:
            self.window.add_action(action)

