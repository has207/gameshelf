import os
import subprocess
import threading
import time
import psutil
import logging
from pathlib import Path
from typing import Optional, Callable, Set

from gi.repository import GLib
from data import Game


# Set up logger
logger = logging.getLogger(__name__)


class ProcessTracker:
    """
    Manages game process launching, monitoring, and tracking play time.
    """
    def __init__(self, data_handler):
        self.data_handler = data_handler
        self.app_window = None  # Reference to main application window
        self.minimize_to_tray_on_game_launch = True  # Whether to minimize to tray when launching games
        self.directory_monitors = {}  # Track directory monitoring threads

    def launch_game(self, game: Game, runner_command: str, file_path: Optional[str] = None,
                on_exit_callback: Optional[Callable] = None,
                launcher_id: Optional[str] = None) -> bool:
        """
        Launch a game with the specified runner command and optional file path or launcher ID.

        Args:
            game: The game to launch
            runner_command: The command to run
            file_path: Optional path to the game file to launch
            on_exit_callback: Optional callback function to call when the game exits
            launcher_id: Optional launcher-specific ID for the game

        Returns:
            True if the game was launched successfully, False otherwise
        """
        # Don't launch if the game is already running
        if game.is_running(self.data_handler.data_dir):
            return False

        try:
            # Split the command into its parts
            cmd = runner_command.split()

            # Check if this game should be launched with its directory

            # If launcher_id is provided, use that instead of file_path
            if launcher_id is not None:
                # Modify the last part of the command to append launcher_id without a space
                if cmd:
                    # Get the last element of the command
                    last_cmd = cmd[-1]
                    # Replace it with last element + launcher ID
                    cmd[-1] = last_cmd + launcher_id
                    logger.info(f"Launching game: {game.title} with command: {' '.join(cmd)}")
                else:
                    # If command is empty, just use the launcher_id
                    logger.info(f"Launching game: {game.title} with launcher ID: {launcher_id}")
                    cmd.append(launcher_id)
            # For games that launch from directory, directly pass the game directory to the runner
            elif game.should_launch_directory() and hasattr(game, 'installation_directory') and game.installation_directory:
                directory = game.installation_directory
                logger.info(f"Launching Wii U game: {game.title} with command: {runner_command} {directory}")
                cmd.append(directory)
            # Regular games use the file path
            elif file_path:
                # Combine directory and file if needed - handle both absolute and relative paths
                full_path = file_path
                if not os.path.isabs(file_path):
                    # Get installation directory from the game object
                    if hasattr(game, 'installation_directory') and game.installation_directory:
                        directory = game.installation_directory
                        full_path = os.path.join(directory, file_path)

                logger.info(f"Launching game: {game.title} with command: {runner_command} {full_path}")
                cmd.append(full_path)
            else:
                logger.info(f"Launching game: {game.title} with command: {runner_command}")

            # Launch the game
            try:
                process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
            except FileNotFoundError as e:
                logger.error(f"Runner command not found: {cmd[0]} - {e}")
                logger.error(f"Make sure the runner '{cmd[0]}' is installed and accessible in PATH")
                return False
            except PermissionError as e:
                logger.error(f"Permission denied launching: {' '.join(cmd)} - {e}")
                return False
            except Exception as e:
                logger.error(f"Failed to launch command: {' '.join(cmd)} - {e}")
                return False

            # Check if the process started successfully
            try:
                # Give the process a moment to initialize
                time.sleep(0.1)

                # Check if the process is still running (poll returns None if running)
                if process.poll() is not None:
                    # Process has already exited, likely due to an error
                    stdout, stderr = process.communicate()
                    exit_code = process.returncode

                    # Log only the stderr output if available
                    if stderr:
                        logger.error(f"Error output: {stderr.decode().strip()}")
                    else:
                        logger.error(f"Game launch failed immediately - command: {' '.join(cmd)}")

                    return False
            except Exception as e:
                logger.error(f"Error checking process status: {e}")
                return False

            # Save the PID to the PID file
            self.data_handler.save_game_pid(game, process.pid)

            # Only increment play count if game launched successfully
            self.data_handler.increment_play_count(game)

            # Check if this is a Steam game that should use directory monitoring
            if (hasattr(game, 'launcher_type') and game.launcher_type == "STEAM" and
                hasattr(game, 'installation_directory') and game.installation_directory):
                # Use directory monitoring for Steam games
                logger.info(f"Using directory monitoring for Steam game: {game.title}")
                self.start_directory_monitoring(game, game.installation_directory, on_exit_callback)
            else:
                # Use traditional PID monitoring for other games
                self.monitor_game_process(process.pid, game, on_exit_callback)

            # Minimize the main window to tray if enabled
            if self.minimize_to_tray_on_game_launch and self.app_window:
                logger.info(f"Minimizing main window to tray while playing {game.title}")

                # Show notification before minimizing
                try:
                    # Create notification toast
                    from gi.repository import Adw
                    toast = Adw.Toast.new(f"Playing {game.title} - GameShelf minimized to tray")
                    toast.set_timeout(3)  # 3 seconds

                    # Try to show the notification
                    content = self.app_window.get_content()
                    if content is not None and isinstance(content, Adw.ToastOverlay):
                        content.add_toast(toast)
                except Exception as e:
                    logger.debug(f"Could not show notification toast: {e}")

                # Schedule minimizing on the main thread to ensure it happens properly
                GLib.idle_add(self.app_window.hide)

            return True
        except Exception as e:
            logger.error(f"Error launching game: {e}")
            return False

    def monitor_game_process(self, pid: int, game: Game, on_exit_callback: Optional[Callable] = None):
        """
        Monitor a game process and update playtime when it exits.

        Args:
            pid: The process ID to monitor
            game: The game being played
            on_exit_callback: Optional callback function to call when the game exits
        """
        # Start a new thread to monitor the process
        monitor_thread = threading.Thread(
            target=self._process_monitor_thread,
            args=(pid, game, on_exit_callback),
            daemon=True  # Make it a daemon so it doesn't block program exit
        )
        monitor_thread.start()

    def _process_monitor_thread(self, pid: int, game: Game, on_exit_callback: Optional[Callable] = None):
        """
        Thread function to monitor a game process and update playtime.

        Args:
            pid: The process ID to monitor
            game: The game being played
            on_exit_callback: Optional callback function to call when the game exits
        """
        try:
            # Get the file creation time for the pid.yaml file to use as our start time
            pid_file = Path(game.get_pid_path(self.data_handler.data_dir))
            start_time = pid_file.stat().st_ctime

            # Try to get the process
            try:
                process = psutil.Process(pid)
                # Wait for process to exit
                process.wait()
            except psutil.NoSuchProcess:
                # Process doesn't exist or already exited
                logger.warning(f"Process {pid} for game {game.title} no longer exists or has already exited")
                # We'll continue to update the playtime anyway

            # Calculate play time
            end_time = time.time()
            seconds_played = int(end_time - start_time)

            # Don't count very short sessions (less than 1 second)
            if seconds_played < 1:
                seconds_played = 1  # At least record 1 second for very short sessions

            logger.info(f"Game {game.title} played for {seconds_played} seconds")

            # Update the play time in the data handler
            self.data_handler.increment_play_time(game, seconds_played)

            # Remove the PID file since the process has exited
            self.data_handler.clear_game_pid(game)


            # Restore the main window from tray if it was minimized
            if self.minimize_to_tray_on_game_launch and self.app_window:
                logger.info(f"Game {game.title} exited - restoring main window from tray")

                # Show notification after game exits
                def restore_window_with_notification():
                    # Present the window first
                    self.app_window.present()

                    # Then show notification
                    try:
                        # Create notification toast
                        from gi.repository import Adw
                        toast = Adw.Toast.new(f"{game.title} has closed - Played for {seconds_played//60} min, {seconds_played%60} sec")
                        toast.set_timeout(5)  # 5 seconds

                        # Try to show the notification
                        content = self.app_window.get_content()
                        if content is not None and isinstance(content, Adw.ToastOverlay):
                            content.add_toast(toast)
                    except Exception as e:
                        logger.debug(f"Could not show notification toast: {e}")

                    return False  # Don't repeat the timeout

                # Schedule window restore with notification on the main thread
                GLib.idle_add(restore_window_with_notification)

            # Call the callback on the main thread if provided
            if on_exit_callback:
                GLib.idle_add(on_exit_callback, game)

        except Exception as e:
            logger.error(f"Error monitoring game process: {e}")
            # Make sure to clean up the PID file in case of error
            self.data_handler.clear_game_pid(game)

            # Restore window even in case of error
            if self.minimize_to_tray_on_game_launch and self.app_window:
                logger.info(f"Error occurred, restoring main window from tray")

                # Show error notification
                def restore_window_with_error():
                    # Present the window first
                    self.app_window.present()

                    # Then show notification
                    try:
                        # Create notification toast
                        from gi.repository import Adw
                        toast = Adw.Toast.new(f"Error monitoring game {game.title} - process tracking ended")
                        toast.set_timeout(5)  # 5 seconds

                        # Try to show the notification
                        content = self.app_window.get_content()
                        if content is not None and isinstance(content, Adw.ToastOverlay):
                            content.add_toast(toast)
                    except Exception as toast_error:
                        logger.debug(f"Could not show notification toast: {toast_error}")

                    return False  # Don't repeat the timeout

                # Schedule window restore with notification on the main thread
                GLib.idle_add(restore_window_with_error)


    def is_game_running(self, game: Game) -> bool:
        """
        Check if a game is currently running.

        Args:
            game: The game to check

        Returns:
            True if the game is running, False otherwise
        """
        return game.is_running(self.data_handler.data_dir)

    def get_running_pid(self, game: Game) -> Optional[int]:
        """
        Get the PID of a running game.

        Args:
            game: The game to check

        Returns:
            The PID if the game is running, None otherwise
        """
        return self.data_handler.get_game_pid(game)

    def kill_game_process(self, game: Game) -> bool:
        """
        Kill a running game process.

        Args:
            game: The game to kill

        Returns:
            True if the process was killed successfully, False otherwise
        """
        pid = self.get_running_pid(game)
        if not pid:
            return False

        try:
            process = psutil.Process(pid)
            process.terminate()
            # Wait up to 5 seconds for process to terminate
            process.wait(5)
            return True
        except psutil.NoSuchProcess:
            # Process already terminated
            self.data_handler.clear_game_pid(game)


            return True
        except Exception as e:
            logger.error(f"Error killing process for game {game.title}: {e}")
            return False

    def start_directory_monitoring(self, game: Game, install_directory: str, on_exit_callback: Optional[Callable] = None) -> bool:
        """
        Start monitoring processes in a game's installation directory for Steam/Epic games.

        Args:
            game: The game to monitor
            install_directory: Path to the game's installation directory
            on_exit_callback: Optional callback function to call when the game exits

        Returns:
            True if monitoring started successfully, False otherwise
        """
        if game.id in self.directory_monitors:
            logger.warning(f"Already monitoring directory for {game.title}")
            return False

        try:
            install_path = Path(install_directory)
            if not install_path.exists():
                logger.error(f"Install directory does not exist: {install_directory}")
                return False

            logger.info(f"Starting directory monitoring for {game.title} in {install_directory}")

            # Save a marker file to indicate the game is being monitored
            self.data_handler.save_game_pid(game, -1)  # Use -1 to indicate directory monitoring


            # Start tracking thread
            monitor_thread = threading.Thread(
                target=self._directory_monitor_thread,
                args=(game, install_path, on_exit_callback),
                daemon=True
            )
            monitor_thread.start()
            self.directory_monitors[game.id] = monitor_thread

            # Only increment play count if monitoring started successfully
            self.data_handler.increment_play_count(game)


            # Minimize window if enabled
            if self.minimize_to_tray_on_game_launch and self.app_window:
                logger.info(f"Minimizing main window to tray while monitoring {game.title}")
                try:
                    from gi.repository import Adw
                    toast = Adw.Toast.new(f"Monitoring {game.title} - GameShelf minimized to tray")
                    toast.set_timeout(3)

                    content = self.app_window.get_content()
                    if content is not None and isinstance(content, Adw.ToastOverlay):
                        content.add_toast(toast)
                except Exception as e:
                    logger.debug(f"Could not show notification toast: {e}")

                GLib.idle_add(self.app_window.hide)

            return True

        except Exception as e:
            logger.error(f"Error starting directory monitoring: {e}")
            return False

    def _directory_monitor_thread(self, game: Game, install_path: Path, on_exit_callback: Optional[Callable] = None):
        """
        Thread function to monitor processes in a game's installation directory.

        Args:
            game: The game being monitored
            install_path: Path to the game's installation directory
            on_exit_callback: Optional callback function to call when monitoring stops
        """
        try:
            # Get start time from the pid.yaml file
            pid_file = Path(game.get_pid_path(self.data_handler.data_dir))
            start_time = pid_file.stat().st_ctime

            logger.info(f"Started directory monitoring for {game.title} at {install_path}")

            # Monitor for processes in the install directory
            running_processes: Set[int] = set()
            poll_interval = 2  # Check every 2 seconds

            while True:
                try:
                    current_processes = self._get_processes_in_directory(install_path)

                    # Check for new processes
                    new_processes = current_processes - running_processes
                    if new_processes:
                        logger.info(f"Detected {len(new_processes)} new process(es) for {game.title}")
                        running_processes.update(new_processes)

                    # Check for stopped processes
                    stopped_processes = running_processes - current_processes
                    if stopped_processes:
                        logger.info(f"Detected {len(stopped_processes)} stopped process(es) for {game.title}")
                        running_processes -= stopped_processes

                    # If no processes are running, wait a bit more to see if any start
                    if not running_processes:
                        # Wait a bit longer to see if any processes start
                        time.sleep(poll_interval * 2)
                        current_processes = self._get_processes_in_directory(install_path)
                        if not current_processes:
                            logger.info(f"No processes found in {install_path} for {game.title}, stopping monitoring")
                            break
                        else:
                            running_processes.update(current_processes)

                    time.sleep(poll_interval)

                except Exception as e:
                    logger.error(f"Error during directory monitoring: {e}")
                    break

            # Calculate play time
            end_time = time.time()
            seconds_played = int(end_time - start_time)

            if seconds_played < 1:
                seconds_played = 1

            logger.info(f"Game {game.title} monitored for {seconds_played} seconds")

            # Update play time
            self.data_handler.increment_play_time(game, seconds_played)

            # Clean up
            self.data_handler.clear_game_pid(game)
            if game.id in self.directory_monitors:
                del self.directory_monitors[game.id]


            # Restore window
            if self.minimize_to_tray_on_game_launch and self.app_window:
                logger.info(f"Directory monitoring ended for {game.title} - restoring main window")

                def restore_window_with_notification():
                    self.app_window.present()
                    try:
                        from gi.repository import Adw
                        toast = Adw.Toast.new(f"{game.title} monitoring ended - Played for {seconds_played//60} min, {seconds_played%60} sec")
                        toast.set_timeout(5)

                        content = self.app_window.get_content()
                        if content is not None and isinstance(content, Adw.ToastOverlay):
                            content.add_toast(toast)
                    except Exception as e:
                        logger.debug(f"Could not show notification toast: {e}")
                    return False

                GLib.idle_add(restore_window_with_notification)

            # Call callback
            if on_exit_callback:
                GLib.idle_add(on_exit_callback, game)

        except Exception as e:
            logger.error(f"Error in directory monitoring thread: {e}")
            # Clean up on error
            self.data_handler.clear_game_pid(game)
            if game.id in self.directory_monitors:
                del self.directory_monitors[game.id]

    def _get_processes_in_directory(self, install_path: Path) -> Set[int]:
        """
        Get all process IDs for processes running from the specified directory.

        Args:
            install_path: Path to check for processes

        Returns:
            Set of process IDs
        """
        processes = set()
        try:
            for proc in psutil.process_iter(['pid', 'exe', 'cwd']):
                try:
                    proc_info = proc.info

                    # Check if executable is in the install directory
                    if proc_info['exe']:
                        exe_path = Path(proc_info['exe'])
                        if install_path in exe_path.parents or exe_path.parent == install_path:
                            processes.add(proc_info['pid'])
                            continue

                    # Check if current working directory is in the install directory
                    if proc_info['cwd']:
                        cwd_path = Path(proc_info['cwd'])
                        if install_path in cwd_path.parents or cwd_path == install_path:
                            processes.add(proc_info['pid'])

                except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                    # Process might have terminated or we don't have access
                    continue

        except Exception as e:
            logger.error(f"Error getting processes in directory {install_path}: {e}")

        return processes

    def stop_directory_monitoring(self, game: Game) -> bool:
        """
        Stop directory monitoring for a game.

        Args:
            game: The game to stop monitoring

        Returns:
            True if monitoring was stopped, False if not monitoring
        """
        if game.id not in self.directory_monitors:
            return False

        logger.info(f"Stopping directory monitoring for {game.title}")

        # The monitoring thread will clean itself up when it detects no processes
        # We just need to clear the PID file to signal it should stop
        self.data_handler.clear_game_pid(game)

        return True
