from typing import List, Optional, Dict, Set
import threading
import time

from gi.repository import Gtk, Gio, Gdk, GObject, GLib
from data_handler import Game, Runner

from controllers.sidebar_controller import SidebarItem
from controllers.common import get_template_path


# Create a GObject-based wrapper for Game objects to use in ListStore
class GameObject(GObject.GObject):
    __gtype_name__ = 'GameObject'

    def __init__(self, game: Game):
        super().__init__()
        self.game = game


@Gtk.Template(filename=get_template_path("game_item.ui"))
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
        from controllers.dialogs_controller import GameContextMenu
        context_menu = GameContextMenu(self.game, self)
        context_menu.set_parent(self)
        # Make sure popover is visible
        context_menu.set_autohide(True)
        return context_menu

    def _on_right_click(self, gesture, n_press, x, y):
        # Find the main window
        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if not window:
            return

        # Get grid controller
        grid_ctrl = window.controller.game_grid_controller

        # Find our position in the model
        position = -1
        for i in range(grid_ctrl.games_model.get_n_items()):
            if grid_ctrl.games_model.get_item(i) == self:
                position = i
                break

        if position < 0:
            return

        # Check if we have multiple items selected
        selected_games = []
        for i in range(grid_ctrl.games_model.get_n_items()):
            if grid_ctrl.selection_model.is_selected(i):
                item = grid_ctrl.games_model.get_item(i)
                if hasattr(item, 'game'):
                    selected_games.append(item.game)

        # If current item is not in selection, select only this item
        if not grid_ctrl.selection_model.is_selected(position):
            # Clear existing selections
            for i in range(grid_ctrl.games_model.get_n_items()):
                if grid_ctrl.selection_model.is_selected(i):
                    grid_ctrl.selection_model.unselect_item(i)

            # Select current item
            grid_ctrl.selection_model.select_item(position, True)
            grid_ctrl.last_selected_position = position
            selected_games = [self.game]

            # Store single game in window state
            window.current_selected_game = self.game

        # Create appropriate menu based on selection count
        if len(selected_games) > 1:
            # Show multi-selection menu
            menu = grid_ctrl.create_multi_context_menu(selected_games, self)
        else:
            # Show standard single-item menu
            menu = self._create_context_menu()

        if not menu:
            return

        # Set the position to be at the mouse pointer
        rect = Gdk.Rectangle()
        rect.x = x
        rect.y = y
        rect.width = 1
        rect.height = 1
        menu.set_pointing_to(rect)

        # Show the menu
        menu.show()


    def _on_clicked(self, gesture, n_press, x, y):
        # Only handle left clicks (button 1)
        if gesture.get_current_button() != 1:
            return

        # Find the main window to access the details panel
        from controllers.window_controller import GameShelfWindow
        window = self.get_ancestor(GameShelfWindow)
        if not window:
            return

        # Get keyboard state to check for shift key
        shift_pressed = (gesture.get_current_event_state() & Gdk.ModifierType.SHIFT_MASK) != 0

        # Find our position in the grid view
        grid_ctrl = window.controller.game_grid_controller
        position = -1

        # Find the index of this game item in the model
        for i in range(grid_ctrl.games_model.get_n_items()):
            if grid_ctrl.games_model.get_item(i) == self:
                position = i
                break

        if position < 0:
            return

        # If shift key is pressed, handle range selection
        if shift_pressed and grid_ctrl.last_selected_position >= 0:
            # Calculate range between last selected position and current position
            start_pos = min(position, grid_ctrl.last_selected_position)
            end_pos = max(position, grid_ctrl.last_selected_position) + 1

            # For Gtk4 MultiSelection, we need to handle selection differently
            # We'll need to toggle each item's selection state individually
            for i in range(start_pos, end_pos):
                # GTK4 doesn't have a direct way to set multiple selections at once in MultiSelection
                # Toggle each item's selection
                grid_ctrl.selection_model.select_item(i, True)

            # Update the last selected position
            grid_ctrl.last_selected_position = position

        # Normal click (no modifier keys)
        else:
            # Clear all selections
            for i in range(grid_ctrl.games_model.get_n_items()):
                if grid_ctrl.selection_model.is_selected(i):
                    grid_ctrl.selection_model.unselect_item(i)

            # Store the selected game to maintain state across filtering
            window.current_selected_game = self.game
            window.details_content.set_game(self.game)
            window.details_panel.set_reveal_flap(True)

            # Save panel visibility and game selection to settings
            window.controller.settings_manager.set_details_visible(True)
            window.controller.settings_manager.set_current_game_id(self.game.id)

            # Update the last selected position
            grid_ctrl.last_selected_position = position


@Gtk.Template(filename=get_template_path("runner_item.ui"))
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


class GameGridController:
    def __init__(self, main_controller):
        self.main_controller = main_controller
        self.games_model = None
        self.last_selected_position = -1  # Track the last selected position for range selection
        self.image_cache = {}  # Cache for game cover images
        self.is_scrolling = False
        self.scroll_timeout_id = None
        self.last_scroll_time = 0
        self.pending_image_loads = []  # Queue of image loads to process when scrolling stops

    def bind_gridview(self, grid_view: Gtk.GridView):
        # Store GameObject wrappers that hold Game objects
        self.games_model = Gio.ListStore(item_type=GameObject)
        self.grid_view = grid_view

        # Create factory for on-demand widget creation
        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self._on_factory_setup)
        factory.connect("bind", self._on_factory_bind)
        factory.connect("unbind", self._on_factory_unbind)  # Release resources when scrolling

        # Create multi-selection model that doesn't auto-select the first item
        self.selection_model = Gtk.MultiSelection(model=self.games_model)
        grid_view.set_model(self.selection_model)
        grid_view.set_factory(factory)

        # Enable rubber band selection
        grid_view.set_enable_rubberband(True)

        # Add keyboard controller for handling key events (like delete)
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self._on_key_pressed)
        grid_view.add_controller(key_controller)

        # Add scroll controller to detect scrolling
        scroll_controller = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll_controller.connect("scroll", self._on_scroll_start)
        grid_view.add_controller(scroll_controller)

        # Setup timer to detect when scrolling stops
        GLib.timeout_add(100, self._check_scrolling_stopped)

        self.populate_games()

    def _on_factory_setup(self, factory, list_item):
        """Set up the container for a grid item - called once per visible item"""
        # Create a simple container box to hold our game item elements
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("game-item-container")

        # Create the game UI elements that will be reused
        image = Gtk.Picture()
        image.set_size_request(180, 240)  # Maintain consistent image size

        label = Gtk.Label()
        label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END = 3
        label.set_max_width_chars(20)
        label.set_lines(2)
        label.set_wrap(True)

        # Store references to the UI elements
        box.image = image
        box.label = label

        # Add the UI elements to the box
        box.append(image)
        box.append(label)

        # Add gestures for interactions
        click_gesture = Gtk.GestureClick.new()
        click_gesture.connect("released", self._on_item_clicked, list_item)
        box.add_controller(click_gesture)

        right_click = Gtk.GestureClick.new()
        right_click.set_button(3)  # Right mouse button
        right_click.connect("pressed", self._on_item_right_click, list_item)
        box.add_controller(right_click)

        list_item.set_child(box)

    def _on_factory_bind(self, factory, list_item):
        """Bind data to an item when it becomes visible"""
        box = list_item.get_child()
        position = list_item.get_position()

        # Get the game object from the model
        if position < self.games_model.get_n_items():
            game_obj = self.games_model.get_item(position)
            game = game_obj.game  # Unwrap the actual Game from GameObject

            # Update the game item with data
            box.label.set_text(game.title)

            # Store reference to the game and position for event handlers
            box.game = game
            box.game_id = game.id
            box.position = position

            # Add selected style based on selection state
            selection = self.selection_model.get_selection()
            if selection.contains(position):
                box.add_css_class("selected-game-item")
            else:
                box.remove_css_class("selected-game-item")

            # First check cache for fast loading
            if game.id in self.image_cache:
                paintable = self.image_cache[game.id]
                box.image.set_paintable(paintable)
            else:
                # Set default icon first for fast rendering
                icon_paintable = self.main_controller.data_handler.get_default_icon_paintable("applications-games-symbolic")
                box.image.set_paintable(icon_paintable)

                # If we're not scrolling, load the image immediately
                # Otherwise, queue it to load when scrolling stops
                if not self.is_scrolling:
                    self._load_game_image(box, game)
                else:
                    # Add to queue for loading when scrolling stops
                    self.pending_image_loads.append((box, game))

    def _on_factory_unbind(self, factory, list_item):
        """Clean up when item scrolls out of view"""
        # Remove from pending loads if it's in the queue
        box = list_item.get_child()
        if box and hasattr(box, 'game'):
            # Remove from pending loads if it exists
            self.pending_image_loads = [(b, g) for b, g in self.pending_image_loads
                                      if b != box]

    def _on_scroll_start(self, controller, dx, dy):
        """Called when scrolling starts or continues"""
        self.is_scrolling = True
        self.last_scroll_time = time.time()
        return False  # Allow event propagation

    def _check_scrolling_stopped(self):
        """Periodically check if scrolling has stopped"""
        current_time = time.time()
        # If no scrolling for 200ms, consider it stopped
        if self.is_scrolling and (current_time - self.last_scroll_time) > 0.2:
            self.is_scrolling = False
            # Process pending image loads
            self._process_pending_image_loads()

        # Keep the timeout active
        return True

    def _process_pending_image_loads(self):
        """Load images for visible items after scrolling stops"""
        # Make a copy of the pending loads and clear the original
        loads = self.pending_image_loads.copy()
        self.pending_image_loads = []

        # Load images for visible items only
        for box, game in loads:
            # Only load if the box is still a child of a visible item
            if box.get_parent() is not None:
                self._load_game_image(box, game)

    def _load_game_image(self, box, game):
        """Load an image for a game with caching"""
        # Check cache first
        if game.id in self.image_cache:
            paintable = self.image_cache[game.id]
            if box and hasattr(box, 'image'):
                box.image.set_paintable(paintable)
            return

        # Load image in background
        thread = threading.Thread(
            target=self._background_load_image,
            args=(box, game)
        )
        thread.daemon = True
        thread.start()

    def _background_load_image(self, box, game):
        """Load image in background thread and update UI in main thread"""
        try:
            # Load the image
            pixbuf = self.main_controller.get_game_pixbuf(game)

            if pixbuf:
                # Create paintable from pixbuf
                paintable = Gdk.Texture.new_for_pixbuf(pixbuf)

                # Limit cache size to 200 images to prevent memory issues
                if len(self.image_cache) > 200:
                    # Remove oldest entries (first 50 keys)
                    keys_to_remove = list(self.image_cache.keys())[:50]
                    for key in keys_to_remove:
                        self.image_cache.pop(key, None)

                # Store in cache
                self.image_cache[game.id] = paintable

                # Update UI in main thread if box is still visible
                GLib.idle_add(self._update_image_ui, box, paintable, game.id)
        except Exception as e:
            print(f"Error loading image for game {game.id}: {e}")

    def _update_image_ui(self, box, paintable, game_id):
        """Update the UI with loaded image (called in main thread)"""
        if box and hasattr(box, 'image') and hasattr(box, 'game_id') and box.game_id == game_id:
            box.image.set_paintable(paintable)
        return False  # Remove from idle queue

    def _on_item_clicked(self, gesture, n_press, x, y, list_item):
        """Handle clicks on game items"""
        # Only handle left clicks (button 1)
        if gesture.get_current_button() != 1:
            return

        position = list_item.get_position()
        if position < 0 or position >= self.games_model.get_n_items():
            return

        game_obj = self.games_model.get_item(position)
        game = game_obj.game  # Unwrap the Game from GameObject
        box = list_item.get_child()

        # Get keyboard state to check for shift key
        shift_pressed = (gesture.get_current_event_state() & Gdk.ModifierType.SHIFT_MASK) != 0

        # Find the main window
        from controllers.window_controller import GameShelfWindow
        window = self.grid_view.get_ancestor(GameShelfWindow)
        if not window:
            return

        # If shift key is pressed, handle range selection
        if shift_pressed and self.last_selected_position >= 0:
            # Calculate range between last selected position and current position
            start_pos = min(position, self.last_selected_position)
            end_pos = max(position, self.last_selected_position) + 1

            # For Gtk4 MultiSelection, we need to toggle each item's selection state
            for i in range(start_pos, end_pos):
                self.selection_model.select_item(i, True)

            # Update the last selected position
            self.last_selected_position = position

        # Normal click (no modifier keys)
        else:
            # Clear all selections
            for i in range(self.games_model.get_n_items()):
                if self.selection_model.is_selected(i):
                    self.selection_model.unselect_item(i)

            # Store the selected game to maintain state across filtering
            window.current_selected_game = game
            window.details_content.set_game(game)
            window.details_panel.set_reveal_flap(True)

            # Save panel visibility and game selection to settings
            window.controller.settings_manager.set_details_visible(True)
            window.controller.settings_manager.set_current_game_id(game.id)

            # Update the last selected position
            self.last_selected_position = position

    def _on_item_right_click(self, gesture, n_press, x, y, list_item):
        """Handle right clicks on game items for context menu"""
        position = list_item.get_position()
        if position < 0 or position >= self.games_model.get_n_items():
            return

        game_obj = self.games_model.get_item(position)
        game = game_obj.game  # Unwrap Game from GameObject
        box = list_item.get_child()

        # Find the main window
        from controllers.window_controller import GameShelfWindow
        window = self.grid_view.get_ancestor(GameShelfWindow)
        if not window:
            return

        # Check if we have multiple items selected
        selected_games = []
        for i in range(self.games_model.get_n_items()):
            if self.selection_model.is_selected(i):
                game_obj = self.games_model.get_item(i)
                selected_games.append(game_obj.game)  # Unwrap Game

        # If current item is not in selection, select only this item
        if not self.selection_model.is_selected(position):
            # Clear existing selections
            for i in range(self.games_model.get_n_items()):
                if self.selection_model.is_selected(i):
                    self.selection_model.unselect_item(i)

            # Select current item
            self.selection_model.select_item(position, True)
            self.last_selected_position = position
            selected_games = [game]

            # Store single game in window state
            window.current_selected_game = game

        # Create appropriate menu based on selection count
        if len(selected_games) > 1:
            # Show multi-selection menu
            menu = self.create_multi_context_menu(selected_games, box)
        else:
            # Show standard single-item menu
            from controllers.dialogs_controller import GameContextMenu
            menu = GameContextMenu(game, box)
            menu.set_parent(box)
            menu.set_autohide(True)

        if not menu:
            return

        # Set the position to be at the mouse pointer
        rect = Gdk.Rectangle()
        rect.x = x
        rect.y = y
        rect.width = 1
        rect.height = 1
        menu.set_pointing_to(rect)

        # Show the menu
        menu.show()

    def populate_games(self, filter_runner: Optional[str] = None,
                    filter_completion_status: Optional[str] = None,
                    filter_runners: Optional[Set[str]] = None,
                    filter_completion_statuses: Optional[Set[str]] = None,
                    search_text: str = ""):
        """
        Populate the games grid with filtered games

        Args:
            filter_runner: (Legacy) Runner ID to filter by, or None for no filter
            filter_completion_status: (Legacy) Completion status enum name to filter by, or None for no filter
            filter_runners: Set of runner IDs to filter by (OR within this category), or None for no filter
            filter_completion_statuses: Set of completion status enum names to filter by (OR within this category), or None for no filter
            search_text: Text to search in game titles
        """
        # For backward compatibility, store single runner filter in main controller
        self.main_controller.current_filter = filter_runner

        # Clear the current games model
        self.games_model.remove_all()

        # Reset selection tracking when repopulating
        self.last_selected_position = -1

        # Get all games
        games = self.main_controller.get_games()
        print(f"Populating games grid with {len(games)} total games...")

        # For backward compatibility, convert legacy filters to sets if provided
        if filter_runners is None and filter_runner is not None:
            # Handle case where filter_runner might already be a set
            if isinstance(filter_runner, set):
                filter_runners = filter_runner
            else:
                filter_runners = {filter_runner}

        if filter_completion_statuses is None and filter_completion_status is not None:
            # Handle case where filter_completion_status might already be a set
            if isinstance(filter_completion_status, set):
                filter_completion_statuses = filter_completion_status
            else:
                filter_completion_statuses = {filter_completion_status}

        # Apply runner filters (OR within category)
        if filter_runners:
            games = [g for g in games if g.runner in filter_runners]
            print(f"After runner filters ({len(filter_runners)} selected): {len(games)} games")

        # Apply completion status filters (OR within category)
        if filter_completion_statuses:
            games = [g for g in games if g.completion_status.name in filter_completion_statuses]
            print(f"After completion status filters ({len(filter_completion_statuses)} selected): {len(games)} games")

        # Apply search filter if search text is provided
        if search_text:
            games = [g for g in games if search_text.lower() in g.title.lower()]
            print(f"After search filter: {len(games)} games")

        # Show only hidden or non-hidden games based on show_hidden setting
        if hasattr(self.main_controller, 'show_hidden'):
            if self.main_controller.show_hidden:
                # When show_hidden is True, only show hidden games
                games = [g for g in games if g.hidden]
            else:
                # When show_hidden is False, only show non-hidden games
                games = [g for g in games if not g.hidden]
            print(f"After hidden filter: {len(games)} games")

        # Sort the games if sort parameters are set
        if hasattr(self.main_controller, 'sort_field') and hasattr(self.main_controller, 'sort_ascending'):
            games = self.sort_games(games, self.main_controller.sort_field, self.main_controller.sort_ascending)
        else:
            # Default sorting by title ascending
            games = sorted(games, key=lambda g: g.title.lower())

        # Wrap each Game in a GameObject before adding to the model
        # Widgets will be created on-demand when the items become visible
        for game in games:
            self.games_model.append(GameObject(game))

        print(f"Grid populated with {self.games_model.get_n_items()} games")

    def sort_games(self, games: List[Game], sort_field: str, ascending: bool) -> List[Game]:
        """
        Sort a list of games by the specified field and direction

        Args:
            games: List of games to sort
            sort_field: Field to sort by
            ascending: True for ascending, False for descending

        Returns:
            Sorted list of games
        """
        reverse = not ascending

        if sort_field == "title":
            return sorted(games, key=lambda g: g.title.lower(), reverse=reverse)
        elif sort_field == "last_played":
            # Sort by last played time (None values at the end)
            def get_last_played(game):
                time = game.get_last_played_time(self.main_controller.data_handler.data_dir)
                # Use a very old timestamp for games never played
                return time if time is not None else 0
            return sorted(games, key=get_last_played, reverse=reverse)
        elif sort_field == "play_time":
            return sorted(games, key=lambda g: g.play_time, reverse=reverse)
        elif sort_field == "play_count":
            return sorted(games, key=lambda g: g.play_count, reverse=reverse)
        elif sort_field == "date_added":
            # Sort by created timestamp
            def get_created(game):
                return game.created if game.created is not None else 0
            return sorted(games, key=get_created, reverse=reverse)
        elif sort_field == "date_modified":
            # Sort by modified time
            def get_modified(game):
                time = game.get_modified_time(self.main_controller.data_handler.data_dir)
                return time if time is not None else 0
            return sorted(games, key=get_modified, reverse=reverse)
        else:
            # Default to title
            return sorted(games, key=lambda g: g.title.lower(), reverse=reverse)

    # We need to keep these methods for compatibility with other parts of the code
    def create_game_widget(self, game: Game) -> Gtk.Widget:
        return GameItem(game, self.main_controller)

    def create_runner_widget(self, runner: Runner) -> Gtk.Widget:
        return RunnerItem(runner, self.main_controller)

    def _on_key_pressed(self, controller, keyval, keycode, state):
        """Handle keyboard events"""
        # Check for Delete key (keyval 65535)
        if keyval == 65535:  # Delete key
            self._handle_delete_key_pressed()
            return True
        return False

    def _handle_delete_key_pressed(self):
        """Handle delete key press by removing selected games"""
        # Get the selected games
        selected_games = []
        # Find all selected items - extract Game objects from GameObject wrappers
        for i in range(self.games_model.get_n_items()):
            if self.selection_model.is_selected(i):
                game_obj = self.games_model.get_item(i)
                selected_games.append(game_obj.game)  # Unwrap Game from GameObject

        if not selected_games:
            return

        # Show confirmation dialog
        self._show_multi_delete_confirmation(selected_games)

    def _show_multi_delete_confirmation(self, games):
        """Show a confirmation dialog for deleting multiple games"""
        from controllers.window_controller import GameShelfWindow
        window = self.grid_view.get_ancestor(GameShelfWindow)
        if not window:
            return

        # Create confirmation dialog
        dialog = Gtk.MessageDialog(
            transient_for=window,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Remove {len(games)} games?",
            secondary_text="This action cannot be undone. The selected games will be permanently removed."
        )
        dialog.connect("response", self._on_multi_delete_response, games)
        dialog.show()

    def _on_multi_delete_response(self, dialog, response_id, games):
        """Handle the response from the remove confirmation dialog"""
        if response_id == Gtk.ResponseType.YES:
            # User confirmed removal
            removed_count = 0
            for game in games:
                if self.main_controller.remove_game(game):
                    removed_count += 1

            # Get the window to update UI if needed
            from controllers.window_controller import GameShelfWindow
            window = self.grid_view.get_ancestor(GameShelfWindow)
            if window and window.details_panel:
                window.details_panel.set_reveal_flap(False)
                window.current_selected_game = None

            # Refresh UI once after all games are removed
            if removed_count > 0:
                # Schedule data reload and sidebar refresh async
                GLib.timeout_add(50, lambda: self.main_controller.reload_data(refresh_sidebar=True) or False)

                # Show feedback message
                self._show_feedback_message(f"{removed_count} games removed")

        # Destroy the dialog
        dialog.destroy()

    def create_multi_context_menu(self, games, parent_item):
        """Create a context menu for multiple selected games"""
        # Create a simple popover with our own widget hierarchy to avoid conflicting handlers
        menu = Gtk.Popover()
        menu.set_parent(parent_item)
        menu.set_autohide(True)

        # Create menu layout
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.add_css_class("context-menu-container")

        # Determine hide/unhide state
        all_hidden = all(game.hidden for game in games)

        # Create toggle hidden button
        if all_hidden:
            toggle_btn = Gtk.Button(label=f"Unhide {len(games)} Games")
        else:
            toggle_btn = Gtk.Button(label=f"Hide {len(games)} Games")

        toggle_btn.add_css_class("context-menu-item")
        vbox.append(toggle_btn)

        # Add separator
        separator = Gtk.Separator()
        separator.add_css_class("context-menu-separator")
        vbox.append(separator)

        # Create remove button
        remove_btn = Gtk.Button(label=f"Remove {len(games)} Games")
        remove_btn.add_css_class("context-menu-item")
        remove_btn.add_css_class("context-menu-item-destructive")
        vbox.append(remove_btn)

        # Set content
        menu.set_child(vbox)

        # Connect signals to completely new buttons
        toggle_btn.connect("clicked",
            lambda b: self._on_multi_toggle_hidden(b, games, all_hidden))
        remove_btn.connect("clicked",
            lambda b: self._on_multi_remove(b, games))

        return menu

    def _on_multi_toggle_hidden(self, button, games, all_hidden):
        """Handle toggling hidden state for multiple games"""
        # Close the menu
        menu = button.get_ancestor(Gtk.Popover)
        if menu:
            menu.popdown()

        # Process all games
        processed_count = 0

        # Choose action based on current state
        new_hidden_state = not all_hidden

        for game in games:
            # Set hidden state
            game.hidden = new_hidden_state

            # Save through the controller's data handler directly (no UI refresh)
            if self.main_controller.data_handler.save_game(game):
                processed_count += 1

        # Reload the UI once after all updates are done
        if processed_count > 0:
            # Schedule data reload and sidebar refresh async
            GLib.timeout_add(50, lambda: self.main_controller.reload_data(refresh_sidebar=True) or False)

            # Show feedback message
            action = "hidden" if new_hidden_state else "unhidden"
            self._show_feedback_message(f"{processed_count} games {action}")

    def _on_multi_remove(self, button, games):
        """Handle removing multiple games"""
        # Close the menu
        menu = button.get_ancestor(Gtk.Popover)
        if menu:
            menu.popdown()

        # Show confirmation dialog
        self._show_multi_delete_confirmation(games)

    def _show_feedback_message(self, message):
        """Show a feedback dialog with the result of a bulk operation"""
        from controllers.window_controller import GameShelfWindow
        window = self.grid_view.get_ancestor(GameShelfWindow)
        if not window:
            return

        # Create a simple message dialog
        dialog = Gtk.MessageDialog(
            transient_for=window,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=message
        )
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.show()
