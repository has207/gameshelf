#!/usr/bin/env python3
import os
import sys
import json
import time
import signal
import logging
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('AyatanaAppIndicator3', '0.1')
from gi.repository import Gtk, AyatanaAppIndicator3 as AppIndicator3, GLib

# Set up logging - use WARNING level to reduce noise
logging.basicConfig(level=logging.WARNING,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('tray_helper')

class TrayIconHelper:
    """
    Standalone tray icon helper using GTK3 and AppIndicator3.
    Communicates with parent process via files.
    """
    def __init__(self):
        self.command_file = sys.argv[1] if len(sys.argv) > 1 else None
        self.status_file = sys.argv[2] if len(sys.argv) > 2 else None

        if not self.command_file or not self.status_file:
            logger.error("Command file and status file paths are required")
            sys.exit(1)

        # Create the indicator
        self.indicator = AppIndicator3.Indicator.new(
            "gameshelf-tray",
            "application-x-executable",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )

        # If we have an icon path passed as the third argument, use it
        if len(sys.argv) > 3 and os.path.exists(sys.argv[3]):
            self.indicator.set_icon_full(sys.argv[3], "GameShelf")

        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)

        # Create the menu
        self.menu = Gtk.Menu()

        # Show/Hide item
        self.show_item = Gtk.MenuItem(label="Hide Window")
        self.show_item.connect("activate", self.on_show_hide_clicked)
        self.menu.append(self.show_item)

        # Add separator
        separator = Gtk.SeparatorMenuItem()
        self.menu.append(separator)

        # Quit item
        quit_item = Gtk.MenuItem(label="Quit")
        quit_item.connect("activate", self.on_quit_clicked)
        self.menu.append(quit_item)

        # Show all menu items
        self.menu.show_all()

        # Set the menu
        self.indicator.set_menu(self.menu)

        # Set up file monitoring for command file
        self.timeout_id = GLib.timeout_add(500, self.check_command_file)

        # Write initial status
        self.write_status("ready")

    def write_status(self, status, data=None):
        """Write status to the status file"""
        status_data = {
            "status": status,
            "timestamp": time.time()
        }

        if data:
            status_data["data"] = data

        try:
            with open(self.status_file, 'w') as f:
                json.dump(status_data, f)
        except Exception as e:
            logger.error(f"Error writing status file: {e}")

    def check_command_file(self):
        """Check for commands from the parent process"""
        try:
            if os.path.exists(self.command_file):
                with open(self.command_file, 'r') as f:
                    content = f.read().strip()
                    if not content:
                        return True

                    try:
                        command_data = json.loads(content)
                        command = command_data.get("command")

                        if command == "update_label":
                            is_visible = command_data.get("is_visible", True)
                            if is_visible:
                                self.show_item.set_label("Hide Window")
                            else:
                                self.show_item.set_label("Show Window")

                        elif command == "quit":
                            logger.info("Quit command received")
                            Gtk.main_quit()
                            return False

                        # Delete the command file after processing
                        try:
                            os.remove(self.command_file)
                        except:
                            # Create an empty file if we can't remove it
                            with open(self.command_file, 'w') as f:
                                f.write("")
                    except json.JSONDecodeError:
                        # Empty or malformed command files are common during startup/shutdown
                        if content:  # Only log if content exists but is invalid
                            logger.debug(f"Invalid JSON in command file: '{content}'")
        except Exception as e:
            logger.error(f"Error checking command file: {e}")

        return True  # Keep the timeout active

    def on_show_hide_clicked(self, widget):
        """Handle show/hide menu item click"""
        current_label = self.show_item.get_label()
        action = "show" if current_label == "Show Window" else "hide"

        self.write_status("action", {"action": action})

    def on_quit_clicked(self, widget):
        """Handle quit menu item click"""
        self.write_status("action", {"action": "quit"})
        GLib.timeout_add(300, Gtk.main_quit)  # Give time for the status to be written

# Create and run the tray icon
if __name__ == "__main__":
    try:
        # Handle SIGTERM gracefully
        def handle_sigterm(signum, frame):
            logger.info("Received SIGTERM, exiting...")
            Gtk.main_quit()

        signal.signal(signal.SIGTERM, handle_sigterm)

        # Create and start the tray icon
        tray_helper = TrayIconHelper()
        Gtk.main()
    except Exception as e:
        logger.error(f"Error in tray helper: {e}")
        sys.exit(1)
