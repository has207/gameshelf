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
# Import tray icon implementation
from tray_icon import GameShelfTrayIcon

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class GameShelfApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.example.GameShelf")
        self.win = None
        self.splash = None
        self.tray_icon = None

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
        # Flag to track if initialization was successful
        self._initialization_complete = False

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

            logging.info("Application data initialization complete")
        except Exception as e:
            # Log any initialization errors but continue with app startup
            logging.error(f"Error during app initialization: {e}")

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
        logging.info("Initializing main window...")

        try:
            # Make sure the controller exists before creating the window
            if not hasattr(self, 'controller') or self.controller is None:
                logging.info("Creating controller first...")
                self.data_handler = DataHandler()
                self.settings_manager = AppStateManager()
                self.controller = GameShelfController(self.data_handler, self.settings_manager)

            # Create the window if not already created
            if not hasattr(self, 'win') or self.win is None:
                logging.info("Creating main window...")
                # Create the window
                self.win = GameShelfWindow(self, self.controller)

                # Apply saved window size and state
                width, height = self.settings_manager.get_window_size()
                self.win.set_default_size(width, height)

                if self.settings_manager.get_window_maximized():
                    self.win.maximize()

            # Present the window
            logging.info("Presenting main window...")
            self.win.present()
            self._window_shown = True
            logging.info("Main window presented successfully")

            # Mark initialization as complete
            self._initialization_complete = True

            # Initialize system tray icon
            logging.info("Initializing system tray icon...")
            self.tray_icon = GameShelfTrayIcon(self)

            # Connect window hide/show signals to update tray icon menu
            if hasattr(self.win, "connect"):
                self.win.connect("hide", self._on_window_hide)
                self.win.connect("show", self._on_window_show)
        except Exception as e:
            logging.error(f"Error initializing main window: {e}")
            # Try again with a fallback approach if there was an error
            try:
                logging.warning("Using fallback window initialization...")
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

                # Initialize system tray icon even in fallback mode
                logging.info("Initializing system tray icon (fallback mode)...")
                self.tray_icon = GameShelfTrayIcon(self)

                # Connect window hide/show signals
                if hasattr(self.win, "connect"):
                    self.win.connect("hide", self._on_window_hide)
                    self.win.connect("show", self._on_window_show)
            except Exception as e2:
                logging.critical(f"Fatal error creating window: {e2}")
                # Emergency exit
                sys.exit(1)


    def _on_window_hide(self, window):
        """Handle window hide event to update tray icon menu"""
        logging.debug("Window hidden")
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.update_show_hide_label(False)

    def _on_window_show(self, window):
        """Handle window show event to update tray icon menu"""
        logging.debug("Window shown")
        if hasattr(self, 'tray_icon') and self.tray_icon:
            self.tray_icon.update_show_hide_label(True)

    def on_shutdown(self, app):
        """Save application state when shutting down"""
        # Only save window state if initialization was completed successfully
        if self._initialization_complete and hasattr(self, 'win') and self.win:
            logging.info("Saving window state on shutdown...")
            # Only save size if not maximized (otherwise save the maximized state)
            if not self.win.is_maximized():
                width, height = self.win.get_default_size()  # Get current window size
                self.settings_manager.set_window_size(width, height)

            self.settings_manager.set_window_maximized(self.win.is_maximized())
        else:
            logging.info("Skipping window state save - initialization not completed")

        # Save all settings to disk
        if hasattr(self, 'settings_manager'):
            self.settings_manager.save_settings()

        # Clean up tray icon
        if hasattr(self, 'tray_icon') and self.tray_icon:
            logging.info("Cleaning up tray icon on shutdown")
            self.tray_icon._cleanup()


if __name__ == "__main__":
    app = GameShelfApp()

    # Set up signal handler for Ctrl+C (SIGINT)
    def signal_handler(sig, frame):
        """Handle interrupt signals gracefully"""
        logging.info("Kill signal received, exiting...\n")
        if hasattr(app, 'win') and app.win:
            app.on_shutdown(app)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    app.run(sys.argv)

