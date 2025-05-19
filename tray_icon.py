#!/usr/bin/env python3

import os
import logging
import subprocess
import signal
import tempfile
import json
import time
import threading
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

# Set up logger
logger = logging.getLogger(__name__)

# Check if the tray icon helper script exists, create it if not
def create_tray_icon_helper():
    """
    Create a standalone GTK3 tray icon helper script.
    This avoids GTK4 compatibility issues with AppIndicator.
    """
    helper_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tray_helper.py")

    # Create the helper script if it doesn't exist or if we want to update it
    if not os.path.exists(helper_path) or True:  # Always update for now during development
        logger.info(f"Creating tray icon helper script at {helper_path}")

        script_content = '''#!/usr/bin/env python3
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
'''

        with open(helper_path, 'w') as f:
            f.write(script_content)

        # Make the helper script executable
        os.chmod(helper_path, 0o755)

    return helper_path


class GameShelfTrayIcon:
    """
    Creates and manages a system tray icon for GameShelf.
    Uses a separate GTK3 process to work around GTK4 AppIndicator incompatibility.
    """
    def __init__(self, app):
        """
        Initialize tray icon with application reference

        Args:
            app: GameShelfApp instance
        """
        self.app = app
        self.helper_process = None
        self.command_file = None
        self.status_file = None
        self.poll_thread = None
        self.stop_polling = threading.Event()

        # Flag for monitoring state
        self._monitoring_active = True

        # Track window visibility state
        self.window_visible = True

        # Initialize tray icon helper
        self._initialize_tray()

    def _initialize_tray(self):
        """Initialize the tray icon using the standalone helper process"""
        try:
            logger.info("Initializing system tray icon using helper process")

            # Create helper script if it doesn't exist
            helper_path = create_tray_icon_helper()

            # Get icon path
            icon_path = os.path.join(os.path.dirname(__file__), "gameshelf.png")
            if not os.path.exists(icon_path):
                logger.warning(f"Tray icon image not found at {icon_path}, using default icon")
                icon_path = ""

            # Create temporary files for communication
            fd_command, self.command_file = tempfile.mkstemp(prefix="gameshelf_tray_cmd_")
            os.close(fd_command)
            fd_status, self.status_file = tempfile.mkstemp(prefix="gameshelf_tray_status_")
            os.close(fd_status)

            logger.info(f"Using command file: {self.command_file}")
            logger.info(f"Using status file: {self.status_file}")

            # Start the helper process
            self.helper_process = subprocess.Popen(
                [helper_path, self.command_file, self.status_file, icon_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )

            # Start a thread to monitor the helper process output
            threading.Thread(
                target=self._monitor_helper_output,
                args=(self.helper_process,),
                daemon=True
            ).start()

            # Wait for the helper to be ready
            for _ in range(10):  # Try for 2 seconds total
                if self._check_status() == "ready":
                    logger.info("Tray icon helper process is ready")
                    break
                time.sleep(0.2)

            # Start status file polling
            self.stop_polling.clear()
            self.poll_thread = threading.Thread(
                target=self._poll_status_file,
                daemon=True
            )
            self.poll_thread.start()

            logger.info("System tray icon initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize system tray icon: {e}")
            self._cleanup()

    def _monitor_helper_output(self, process):
        """Monitor and log output from the helper process"""
        # Flag to track if process is being cleaned up
        self._monitoring_active = True

        # Handle stdout
        try:
            for line in process.stdout:
                if not self._monitoring_active:
                    break
                if line.strip():  # Only log non-empty lines
                    # Process the line to determine log level
                    if " - INFO - " in line:
                        # Regular info messages go to debug level
                        logger.debug(f"Helper: {line.strip()}")
                    elif " - WARNING - " in line:
                        logger.warning(f"Helper: {line.strip()}")
                    elif " - ERROR - " in line:
                        logger.error(f"Helper: {line.strip()}")
                    else:
                        # For other output use debug level
                        logger.debug(f"Helper: {line.strip()}")
        except Exception as e:
            if self._monitoring_active:  # Only log errors during active monitoring
                logger.error(f"Error monitoring helper output: {e}")

        # Handle stderr
        try:
            for line in process.stderr:
                if not self._monitoring_active:
                    break
                if line.strip():  # Only log non-empty lines
                    if "libayatana-appindicator-WARNING" in line:
                        # Just log library deprecation warnings as debug
                        logger.debug(f"Helper warning: {line.strip()}")
                    elif "INFO" in line and ("command file" in line or "status file" in line):
                        # Configuration info messages go to debug level
                        logger.debug(f"Helper: {line.strip()}")
                    else:
                        # True errors go to error level
                        logger.error(f"Helper error: {line.strip()}")
        except Exception as e:
            if self._monitoring_active:  # Only log errors during active monitoring
                logger.error(f"Error monitoring helper stderr: {e}")

    def _check_status(self):
        """Check the current status from the status file"""
        if not self.status_file or not os.path.exists(self.status_file):
            return None

        try:
            with open(self.status_file, 'r') as f:
                content = f.read().strip()
                if not content:
                    return None

                status_data = json.loads(content)
                return status_data.get("status")
        except (json.JSONDecodeError, FileNotFoundError, PermissionError) as e:
            logger.error(f"Error reading status file: {e}")
            return None

    def _send_command(self, command, **kwargs):
        """Send a command to the helper process"""
        if not self.command_file:
            logger.warning("Cannot send command: command file not available")
            return False

        try:
            command_data = {"command": command, **kwargs}
            with open(self.command_file, 'w') as f:
                json.dump(command_data, f)
            return True
        except Exception as e:
            logger.error(f"Error sending command: {e}")
            return False

    def _poll_status_file(self):
        """Poll the status file for actions from the tray icon"""
        logger.debug("Status file polling started")

        last_timestamp = 0

        while not self.stop_polling.is_set():
            try:
                if os.path.exists(self.status_file):
                    try:
                        with open(self.status_file, 'r') as f:
                            content = f.read().strip()
                            if not content:
                                continue

                            status_data = json.loads(content)

                            # Only process newer status updates
                            timestamp = status_data.get("timestamp", 0)
                            if timestamp > last_timestamp:
                                last_timestamp = timestamp

                                # Check for actions
                                if status_data.get("status") == "action" and "data" in status_data:
                                    action = status_data["data"].get("action")

                                    if action == "show":
                                        logger.info("Show window action received")
                                        GLib.idle_add(self._show_window)
                                    elif action == "hide":
                                        logger.info("Hide window action received")
                                        GLib.idle_add(self._hide_window)
                                    elif action == "quit":
                                        logger.info("Quit action received")
                                        GLib.idle_add(self.app.quit)
                    except (json.JSONDecodeError, FileNotFoundError) as e:
                        logger.error(f"Error reading status file: {e}")
            except Exception as e:
                logger.error(f"Error in status file polling: {e}")

            # Sleep to avoid high CPU usage
            time.sleep(0.5)

        logger.debug("Status file polling stopped")

    def update_show_hide_label(self, is_visible):
        """
        Update the show/hide menu label based on window visibility

        Args:
            is_visible: Whether the application window is visible
        """
        self.window_visible = is_visible
        # Send command to update the label in the helper process
        self._send_command("update_label", is_visible=is_visible)

    def _show_window(self):
        """Show the application window"""
        if hasattr(self.app, 'win') and self.app.win:
            self.app.win.present()
            self.window_visible = True
            self.update_show_hide_label(True)

    def _hide_window(self):
        """Hide the application window"""
        if hasattr(self.app, 'win') and self.app.win:
            self.app.win.hide()
            self.window_visible = False
            self.update_show_hide_label(False)

    def _cleanup(self):
        """Clean up resources"""
        # Signal monitoring to stop
        self._monitoring_active = False

        # Stop polling thread
        if self.poll_thread and self.poll_thread.is_alive():
            self.stop_polling.set()
            self.poll_thread.join(timeout=2.0)

        # Terminate helper process
        if self.helper_process:
            try:
                # Send a quit command to gracefully terminate
                try:
                    self._send_command("quit")
                    # Give it a moment to process
                    time.sleep(0.2)
                except:
                    pass

                # Consume any remaining output before terminating
                if hasattr(self.helper_process, 'stdout') and self.helper_process.stdout:
                    try:
                        # Use non-blocking read to get any remaining output
                        import fcntl
                        import os
                        flags = fcntl.fcntl(self.helper_process.stdout, fcntl.F_GETFL)
                        fcntl.fcntl(self.helper_process.stdout, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                        self.helper_process.stdout.read()
                    except:
                        pass

                if hasattr(self.helper_process, 'stderr') and self.helper_process.stderr:
                    try:
                        # Use non-blocking read to get any remaining output
                        import fcntl
                        import os
                        flags = fcntl.fcntl(self.helper_process.stderr, fcntl.F_GETFL)
                        fcntl.fcntl(self.helper_process.stderr, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                        self.helper_process.stderr.read()
                    except:
                        pass

                # Terminate the process if still running
                logger.info("Terminating tray helper process...")
                self.helper_process.terminate()
                self.helper_process.wait(timeout=1.0)
                logger.info("Tray helper process terminated")
            except Exception as e:
                logger.error(f"Error terminating helper process: {e}")

        # Clean up temporary files
        for file_path in [self.command_file, self.status_file]:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"Error removing temporary file {file_path}: {e}")

    def __del__(self):
        """Destructor to ensure cleanup"""
        self._cleanup()