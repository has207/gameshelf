import os
import subprocess
import threading
import time
import psutil
from pathlib import Path
from typing import Optional, Callable

from gi.repository import GLib
from data import Game


class ProcessTracker:
    """
    Manages game process launching, monitoring, and tracking play time.
    """
    def __init__(self, data_handler):
        self.data_handler = data_handler

    def launch_game(self, game: Game, runner_command: str, file_path: Optional[str] = None, on_exit_callback: Optional[Callable] = None) -> bool:
        """
        Launch a game with the specified runner command and optional file path.

        Args:
            game: The game to launch
            runner_command: The command to run
            file_path: Optional path to the game file to launch
            on_exit_callback: Optional callback function to call when the game exits

        Returns:
            True if the game was launched successfully, False otherwise
        """
        # Don't launch if the game is already running
        if game.is_running(self.data_handler.data_dir):
            return False

        try:
            # Split the command into its parts
            cmd = runner_command.split()

            # Get installation data to check if it's a Wii U game
            installation_data = self.data_handler.get_installation_data(game)

            # Check if this is a Wii U game
            is_wiiu_game = False
            if installation_data and "is_wiiu" in installation_data and installation_data["is_wiiu"]:
                is_wiiu_game = True

            # For Wii U games, we directly pass the game directory to the emulator
            if is_wiiu_game and "directory" in installation_data:
                directory = installation_data["directory"]
                print(f"Launching Wii U game: {game.title} with command: {runner_command} {directory}")
                cmd.append(directory)
            # Regular games use the file path
            elif file_path:
                # Combine directory and file if needed - handle both absolute and relative paths
                full_path = file_path
                if not os.path.isabs(file_path):
                    # Get installation data for the directory
                    if installation_data and "directory" in installation_data:
                        directory = installation_data["directory"]
                        full_path = os.path.join(directory, file_path)

                print(f"Launching game: {game.title} with command: {runner_command} {full_path}")
                cmd.append(full_path)
            else:
                print(f"Launching game: {game.title} with command: {runner_command}")

            # Launch the game
            process = subprocess.Popen(cmd)

            # Save the PID to the PID file
            self.data_handler.save_game_pid(game, process.pid)

            # Only increment play count if game launched successfully
            self.data_handler.increment_play_count(game)

            # Start tracking the process to monitor play time
            self.monitor_game_process(process.pid, game, on_exit_callback)

            return True
        except Exception as e:
            print(f"Error launching game: {e}")
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
                print(f"Process {pid} for game {game.title} no longer exists or has already exited")
                # We'll continue to update the playtime anyway

            # Calculate play time
            end_time = time.time()
            seconds_played = int(end_time - start_time)

            # Don't count very short sessions (less than 1 second)
            if seconds_played < 1:
                seconds_played = 1  # At least record 1 second for very short sessions

            print(f"Game {game.title} played for {seconds_played} seconds")

            # Update the play time in the data handler
            self.data_handler.increment_play_time(game, seconds_played)

            # Remove the PID file since the process has exited
            self.data_handler.clear_game_pid(game)

            # Call the callback on the main thread if provided
            if on_exit_callback:
                GLib.idle_add(on_exit_callback, game)

        except Exception as e:
            print(f"Error monitoring game process: {e}")
            # Make sure to clean up the PID file in case of error
            self.data_handler.clear_game_pid(game)

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
            print(f"Error killing process for game {game.title}: {e}")
            return False
