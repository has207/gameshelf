import gi
import os
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio, GdkPixbuf, Gdk, GObject, GLib
from data_handler import DataHandler, Game, Runner
from typing import Dict, List, Optional, Tuple


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
    id_label: Gtk.Label = Gtk.Template.Child()
    runner_icon: Gtk.Image = Gtk.Template.Child()
    game_image: Gtk.Picture = Gtk.Template.Child()
    play_button: Gtk.Button = Gtk.Template.Child()
    remove_button: Gtk.Button = Gtk.Template.Child()

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

        # Get the runner for this game
        runner = self.controller.get_runner(self.game.runner)
        if runner and runner.command:
            # In a real app, we'd launch the game here
            print(f"Launching game: {self.game.title} with command: {runner.command}")
            # For a production app, you would use subprocess.Popen here
            # subprocess.Popen(runner.command.split() + [self.game.id], start_new_session=True)

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

    def set_game(self, game: Game):
        self.game = game
        # Set title and ID
        self.title_label.set_text(game.title)
        self.id_label.set_text(game.id)

        # Get window and controller references
        window = self.get_ancestor(GameShelfWindow)
        if window and window.controller:
            self.controller = window.controller

        # Set runner info
        if game.runner:
            runner_name = game.runner.capitalize()
            # Set runner icon if available
            if self.controller:
                icon_name = self.controller.data_handler.get_runner_icon(game.runner)
                self.runner_icon.set_from_icon_name(icon_name)
        else:
            runner_name = "No Runner"
            self.runner_icon.set_from_icon_name("dialog-question-symbolic")

        self.runner_label.set_text(runner_name)

        # Set game image if available
        if self.controller:
            pixbuf = self.controller.get_game_pixbuf(game, width=280, height=380)
            if pixbuf:
                self.game_image.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
            else:
                # Get a default icon paintable from the data handler
                icon_paintable = self.controller.data_handler.get_default_icon_paintable("applications-games-symbolic", 180)
                self.game_image.set_paintable(icon_paintable)

        # Enable/disable play button based on if we have a runner with a command
        can_play = False
        if self.controller and game.runner:  # Ensure there's a runner set
            runner = self.controller.get_runner(game.runner)
            can_play = runner is not None and runner.command is not None

        self.play_button.set_sensitive(can_play)


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "window.ui"))
class GameShelfWindow(Adw.ApplicationWindow):
    __gtype_name__ = "GameShelfWindow"

    games_grid: Gtk.GridView = Gtk.Template.Child()
    details_panel: Adw.Flap = Gtk.Template.Child()
    details_content: GameDetailsContent = Gtk.Template.Child()
    sidebar_listview: Gtk.ListView = Gtk.Template.Child()
    add_game_button: Gtk.Button = Gtk.Template.Child()

    def __init__(self, app, controller):
        super().__init__(application=app)
        self.controller = controller
        # Track the currently selected game to maintain state across filtering
        self.current_selected_game = None

        # Create add game dialog
        self.add_game_dialog = None

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
        # Lazy load the add game dialog only when needed
        if not self.add_game_dialog:
            self.add_game_dialog = AddGameDialog(self)
            self.add_game_dialog.set_transient_for(self)

        # Populate runners list with fresh data
        self.add_game_dialog.populate_runners(self.controller.get_runners())
        self.add_game_dialog.show()


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
        if selected == "Games":
            self.controller.populate_games()
        elif selected == "No Runner":
            # Special case for games with no runner
            self.controller.populate_games(filter_runner="")
        else:
            self.controller.populate_games(filter_runner=selected)


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

        # Add click gesture for showing details panel
        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("released", self._on_clicked)
        self.add_controller(click_gesture)

    def _on_clicked(self, gesture, n_press, x, y):
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


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "add_game_dialog.ui"))
class AddGameDialog(Adw.Window):
    __gtype_name__ = "AddGameDialog"

    # UI elements from template
    title_entry: Adw.EntryRow = Gtk.Template.Child()
    runner_list: Gtk.ListBox = Gtk.Template.Child()
    image_preview: Gtk.Picture = Gtk.Template.Child()
    select_image_button: Gtk.Button = Gtk.Template.Child()
    add_button: Gtk.Button = Gtk.Template.Child()
    cancel_button: Gtk.Button = Gtk.Template.Child()

    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.selected_runner = None
        self.selected_image_path = None
        self.runners_data = []

        # Set up the UI
        self.setup_ui()

    def setup_ui(self):
        # Ensure add button updates when entry changes
        self.title_entry.connect("notify::text", self.validate_form)

    def populate_runners(self, runners: List[Runner]):
        # Remove existing rows
        while True:
            row = self.runner_list.get_first_child()
            if row is None:
                break
            self.runner_list.remove(row)

        # Store runners list for reference when selected
        self.runners_data = runners

        # Add new runner rows
        for i, runner in enumerate(runners):
            row = Gtk.ListBoxRow()
            # Store the index to reference the runner later
            row.runner_index = i

            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(12)
            box.set_margin_end(12)

            # Runner icon
            icon = Gtk.Image()
            icon_name = self.parent_window.controller.data_handler.get_runner_icon(runner.id)
            icon.set_from_icon_name(icon_name)
            box.append(icon)

            # Runner name label
            label = Gtk.Label(label=runner.title)
            label.set_xalign(0)
            label.set_hexpand(True)
            box.append(label)

            row.set_child(box)
            self.runner_list.append(row)

    @Gtk.Template.Callback()
    def on_entry_changed(self, entry):
        self.validate_form()

    @Gtk.Template.Callback()
    def on_runner_selected(self, listbox):
        selected_row = listbox.get_selected_row()
        if selected_row and hasattr(selected_row, 'runner_index'):
            # Get the runner from our stored data using the index
            self.selected_runner = self.runners_data[selected_row.runner_index]
        else:
            self.selected_runner = None
        self.validate_form()

    @Gtk.Template.Callback()
    def on_select_image_clicked(self, button):
        dialog = Gtk.FileChooserDialog(
            title="Select Game Cover Image",
            action=Gtk.FileChooserAction.OPEN,
            transient_for=self,
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

        dialog.connect("response", self.on_file_dialog_response)
        dialog.show()

    def on_file_dialog_response(self, dialog, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = dialog.get_file()
            if file:
                self.selected_image_path = file.get_path()

                # Create a temporary game to use the data handler's image loading
                data_handler = self.parent_window.controller.data_handler
                temp_game = Game(id="preview", title="Preview", image=self.selected_image_path)

                # Load the image using the data handler
                pixbuf = data_handler.load_game_image(temp_game, 200, 260)
                if pixbuf:
                    self.image_preview.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
                else:
                    # Set default icon for invalid image
                    icon_paintable = data_handler.get_default_icon_paintable("image-missing", 128)
                    self.image_preview.set_paintable(icon_paintable)
                    self.selected_image_path = None
            else:
                self.selected_image_path = None
                # Clear the preview if dialog was canceled
                self.image_preview.set_paintable(None)
        else:
            # Clear the preview if dialog was canceled
            self.image_preview.set_paintable(None)

        self.validate_form()
        dialog.destroy()

    def validate_form(self, *args):
        # Check if required fields are filled - only title is required
        title = self.title_entry.get_text().strip()
        has_title = len(title) > 0

        # Update the add button sensitivity - only title is required
        self.add_button.set_sensitive(has_title)

    @Gtk.Template.Callback()
    def on_cancel_clicked(self, button):
        self.close()

    @Gtk.Template.Callback()
    def on_add_clicked(self, button):
        # Get the input values
        title = self.title_entry.get_text().strip()

        # Runner is optional
        runner_id = self.selected_runner.id if self.selected_runner else ""

        # Use the data handler to create and save the game with image
        controller = self.parent_window.controller
        data_handler = controller.data_handler

        # Create the game using the data handler
        game = data_handler.create_game_with_image(
            title=title,
            runner_id=runner_id,
            image_path=self.selected_image_path
        )

        # Save the game through the controller
        if controller.add_game(game):
            # Reset form fields
            self.title_entry.set_text("")
            self.runner_list.unselect_all()
            self.selected_runner = None
            self.selected_image_path = None
            self.image_preview.set_paintable(None)

            # Close the dialog
            self.close()


class GameShelfController:
    def __init__(self, data_handler: DataHandler):
        self.data_handler = data_handler
        self.games = self.data_handler.load_games()
        self.runners = {runner.id: runner for runner in self.data_handler.load_runners()}

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
        # Reload games and runners from disk
        self.games = self.data_handler.load_games()
        self.runners = {runner.id: runner for runner in self.data_handler.load_runners()}

        # Update UI
        self.populate_games()

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

    def populate_games(self, filter_runner: Optional[str] = None):
        self.games_model.remove_all()
        games = self.get_games()

        # Handle filtering
        if filter_runner is not None:  # Filter is specifically set (including empty string)
            games = [g for g in games if g.runner == filter_runner]

        # Create widgets for the games
        for game in games:
            game_item = self.create_game_widget(game)
            self.games_model.append(game_item)

    def create_game_widget(self, game: Game) -> Gtk.Widget:
        return GameItem(game, self)

    def create_runner_widget(self, runner: Runner) -> Gtk.Widget:
        return RunnerItem(runner, self)

