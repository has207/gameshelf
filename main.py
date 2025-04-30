#!/usr/bin/env python3

import sys
import gi
import os
import signal
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Adw, Gio, Gdk
from data_handler import DataHandler
from app_state_manager import AppStateManager
# Import controllers
from controllers import GameShelfController, GameShelfWindow


class GameShelfApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.example.GameShelf")

        # Load CSS
        css = Gtk.CssProvider()
        css.load_from_path(os.path.join(os.path.dirname(__file__), "layout", "style.css"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Initialize data handler and app state manager
        self.data_handler = DataHandler()
        self.settings_manager = AppStateManager()

        # Create main controller with handlers
        self.controller = GameShelfController(self.data_handler, self.settings_manager)

        # Set up application lifecycle signal handlers
        self.connect("shutdown", self.on_shutdown)

    def do_activate(self):
        # Create and present the window
        self.win = GameShelfWindow(self, self.controller)

        # Apply saved window size and state
        width, height = self.settings_manager.get_window_size()
        self.win.set_default_size(width, height)

        if self.settings_manager.get_window_maximized():
            self.win.maximize()

        self.win.present()

    def on_shutdown(self, app):
        """Save application state when shutting down"""
        # Ensure window size is saved before quitting
        if hasattr(self, 'win') and self.win:
            # Only save size if not maximized (otherwise save the maximized state)
            if not self.win.is_maximized():
                width, height = self.win.get_default_size()  # Get current window size
                self.settings_manager.set_window_size(width, height)

            self.settings_manager.set_window_maximized(self.win.is_maximized())

        # Save all settings to disk
        self.settings_manager.save_settings()


if __name__ == "__main__":
    app = GameShelfApp()

    # Set up signal handler for Ctrl+C (SIGINT)
    def signal_handler(sig, frame):
        """Handle interrupt signals gracefully"""
        print("Kill signal received, exiting...\n")
        if hasattr(app, 'win') and app.win:
            app.on_shutdown(app)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    app.run(sys.argv)

