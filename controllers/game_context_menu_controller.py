from typing import Optional

from gi.repository import Gtk, GLib

from data import Game

from controllers.common import get_template_path


@Gtk.Template(filename=get_template_path("context_menu.ui"))
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
        if window and window.controller and window.controller.game_grid_controller:
            # Use the grid controller's existing delete confirmation functionality
            window.controller.game_grid_controller._show_multi_delete_confirmation([self.game])