#!/usr/bin/env python3

import logging
import sys
import gi
import os
import signal
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Adw, Gio, Gdk, GLib
from data_handler import DataHandler
from app_state_manager import AppStateManager
# Import controllers
from controllers import GameShelfController, GameShelfWindow, SplashScreen

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class GameShelfApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.example.GameShelf")
        self.win = None
        self.splash = None

        # Load CSS
        css = Gtk.CssProvider()
        css.load_from_path(os.path.join(os.path.dirname(__file__), "layout", "style.css"))
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        # Set up application lifecycle signal handlers
        self.connect("shutdown", self.on_shutdown)

        # This will prevent the app from quitting when all windows are closed
        self.set_flags(Gio.ApplicationFlags.HANDLES_COMMAND_LINE)

        # Debug flag to track if the main window has been shown
        self._window_shown = False

    def do_command_line(self, command_line):
        """Handle command line invocation"""
        self.activate()
        return 0

    def do_activate(self):
        # Show splash screen first
        self._show_splash_screen()

    def _show_splash_screen(self):
        """Show splash screen and start loading the main app in the background"""
        # Path to splash screen image
        splash_image_path = os.path.join(os.path.dirname(__file__), "gameshelf-transparent.png")

        # Create and show splash screen
        self.splash = SplashScreen(
            image_path=splash_image_path,
            timeout_ms=3000,  # Show for 3 seconds minimum
            on_timeout=self._initialize_main_window,
            application=self  # Pass the application to properly parent the window
        )
        self.splash.present()

        # Start loading the main application in the background - 50ms delay to let the splash render first
        GLib.timeout_add(50, self._initialize_app_data)

    def _initialize_app_data(self):
        """Initialize app data in the background while splash screen is showing"""
        try:
            # Initialize data handler and app state manager
            self.data_handler = DataHandler()
            self.settings_manager = AppStateManager()

            # Create main controller with handlers
            self.controller = GameShelfController(self.data_handler, self.settings_manager)

            print("Application data initialization complete")
        except Exception as e:
            # Log any initialization errors but continue with app startup
            print(f"Error during app initialization: {e}")

            # Make sure we have at least minimal required objects
            if not hasattr(self, 'data_handler'):
                self.data_handler = DataHandler()
            if not hasattr(self, 'settings_manager'):
                self.settings_manager = AppStateManager()
            if not hasattr(self, 'controller'):
                self.controller = GameShelfController(self.data_handler, self.settings_manager)

        return False  # Don't repeat this timeout

    def _initialize_main_window(self):
        """Initialize and show the main window after splash screen closes"""
        print("Initializing main window...")

        try:
            # Make sure the controller exists before creating the window
            if not hasattr(self, 'controller') or self.controller is None:
                print("Creating controller first...")
                self.data_handler = DataHandler()
                self.settings_manager = AppStateManager()
                self.controller = GameShelfController(self.data_handler, self.settings_manager)

            # Create the window if not already created
            if not hasattr(self, 'win') or self.win is None:
                print("Creating main window...")
                # Create the window
                self.win = GameShelfWindow(self, self.controller)

                # Apply saved window size and state
                width, height = self.settings_manager.get_window_size()
                self.win.set_default_size(width, height)

                if self.settings_manager.get_window_maximized():
                    self.win.maximize()

            # Present the window
            print("Presenting main window...")
            self.win.present()
            self._window_shown = True
            print("Main window presented successfully")
        except Exception as e:
            print(f"Error initializing main window: {e}")
            # Try again with a fallback approach if there was an error
            try:
                print("Using fallback window initialization...")
                # Create a very basic window as a last resort
                self.win = Adw.ApplicationWindow(application=self, title="GameShelf")
                self.win.set_default_size(800, 600)

                # Add a label with an error message
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
                box.set_margin_top(50)
                box.set_margin_bottom(50)
                box.set_margin_start(50)
                box.set_margin_end(50)

                label = Gtk.Label()
                label.set_markup("<span size='large'>Error loading GameShelf</span>")
                box.append(label)

                error_label = Gtk.Label()
                error_label.set_markup(f"<span color='red'>{str(e)}</span>")
                box.append(error_label)

                self.win.set_content(box)
                self.win.present()
                self._window_shown = True
            except Exception as e2:
                print(f"Fatal error creating window: {e2}")
                # Emergency exit
                sys.exit(1)

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
        if hasattr(self, 'settings_manager'):
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

