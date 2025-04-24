import sys
import gi
import os
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, Gio
from data_handler import DataHandler
from controller import GameShelfController


@Gtk.Template(filename=os.path.join(os.path.dirname(__file__), "layout", "window.ui"))
class GameShelfWindow(Adw.ApplicationWindow):
    __gtype_name__ = "GameShelfWindow"

    games_grid: Gtk.GridView = Gtk.Template.Child()

    def __init__(self, app, controller: GameShelfController):
        super().__init__(application=app)
        controller.bind_gridview(self.games_grid)


class GameShelfApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.example.GameShelf")
        self.data_handler = DataHandler()
        self.controller = GameShelfController(self.data_handler)
        self.connect('activate', self.on_activate)

    def on_activate(self, app):
        self.win = GameShelfWindow(app, self.controller)
        self.win.present()


if __name__ == "__main__":
    app = GameShelfApp()
    app.run(sys.argv)

