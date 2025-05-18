from typing import Optional, Callable
import os
import gi
import logging
from gi.repository import Gtk, Adw, GLib

# Set up logger
logger = logging.getLogger(__name__)

class SplashScreen(Adw.Window):
    """Splash screen window that displays while the application is initializing"""
    def __init__(self, image_path: str, timeout_ms: int = 2000, on_timeout: Optional[Callable] = None, application=None):
        super().__init__(title="GameShelf", application=application)
        self.set_decorated(False)  # No window decorations
        self.set_default_size(500, 500)  # Larger window for the splash image
        self.set_resizable(False)
        self.on_timeout_callback = on_timeout

        # Make sure the window is transparent to show the image properly
        self.set_opacity(1.0)

        # Apply splash screen styling
        self.add_css_class("splash-screen")

        # Create a direct container for the image with no margins
        content = Adw.Bin()
        content.set_halign(Gtk.Align.FILL)
        content.set_valign(Gtk.Align.FILL)

        self.set_content(content)

        # Load the image
        if os.path.exists(image_path):
            try:
                # Create a Gtk.Picture from file that fills the container
                image = Gtk.Picture.new_for_filename(image_path)

                # Configure to fill the entire window
                image.set_can_shrink(True)
                image.set_content_fit(Gtk.ContentFit.FILL)

                # Make the image fill the entire container
                image.set_halign(Gtk.Align.FILL)
                image.set_valign(Gtk.Align.FILL)
                image.set_hexpand(True)
                image.set_vexpand(True)

                content.set_child(image)
            except Exception as e:
                logger.error(f"Error loading splash image: {e}")
                # Fallback label if image fails to load
                label = Gtk.Label(label="Loading GameShelf...")
                label.add_css_class("title-1")
                content.set_child(label)
        else:
            # Fallback label if image doesn't exist
            label = Gtk.Label(label="Loading GameShelf...")
            label.add_css_class("title-1")
            content.set_child(label)

        # Set timeout to close the splash screen
        if timeout_ms > 0 and on_timeout is not None:
            # Store the timeout ID so we can cancel it if needed
            self.timeout_id = GLib.timeout_add(timeout_ms, self._on_timeout_callback)

            # Connect to destroy signal to clean up
            self.connect("destroy", self._on_destroyed)

    def _on_timeout_callback(self) -> bool:
        """Handle timeout, close splash screen and call the callback"""
        logger.debug("Splash screen timeout triggered")

        if hasattr(self, 'on_timeout_callback') and self.on_timeout_callback is not None:
            # Call the callback first, then close
            logger.debug("Calling startup callback")
            self.on_timeout_callback()

        # Close the splash window
        logger.debug("Closing splash screen")
        self.destroy()
        return False  # Don't repeat the timeout

    def _on_destroyed(self, window):
        """Handle window destroy event"""
        logger.debug("Splash screen destroyed")
        # Cancel the timeout if it's still pending
        if hasattr(self, 'timeout_id'):
            GLib.source_remove(self.timeout_id)