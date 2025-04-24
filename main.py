import sys
import gi
import os
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gdk, Gtk, Adw, Gio
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

        # Load custom CSS
        css = Gtk.CssProvider()
        css.load_from_path(os.path.join(os.path.dirname(__file__), "layout", "style.css"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Set up model/controller
        self.data_handler = DataHandler()
        self.controller = GameShelfController(self.data_handler)

    def do_activate(self):
        self.win = GameShelfWindow(self, self.controller)
        self.win.present()


if __name__ == "__main__":
    app = GameShelfApp()
    app.run(sys.argv)

