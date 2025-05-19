import os
import subprocess
import threading
import time
import psutil
import logging
from pathlib import Path
from typing import Optional, Callable

from gi.repository import GLib
from data import Game

# Import Discord integration
from discord_integration import discord_presence

# Set up logger
logger = logging.getLogger(__name__)


class ProcessTracker:
    """
    Manages game process launching, monitoring, and tracking play time.
    Also handles Discord Rich Presence integration.
    """
    def __init__(self, data_handler):
        self.data_handler = data_handler
        self.current_game_discord_enabled = True  # Default value for Discord integration

    def launch_game(self, game: Game, runner_command: str, file_path: Optional[str] = None,
                on_exit_callback: Optional[Callable] = None, discord_enabled: bool = True,
                launcher_id: Optional[str] = None) -> bool:
        """
        Launch a game with the specified runner command and optional file path or launcher ID.

        Args:
            game: The game to launch
            runner_command: The command to run
            file_path: Optional path to the game file to launch
            on_exit_callback: Optional callback function to call when the game exits
            discord_enabled: Whether to enable Discord rich presence for this runner
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

            # Get installation data to check if it's a Wii U game
            installation_data = self.data_handler.get_installation_data(game)

            # Check if this is a Wii U game
            is_wiiu_game = False
            if installation_data and "is_wiiu" in installation_data and installation_data["is_wiiu"]:
                is_wiiu_game = True

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
            # For Wii U games, directly pass the game directory to the emulator
            elif is_wiiu_game and "directory" in installation_data:
                directory = installation_data["directory"]
                logger.info(f"Launching Wii U game: {game.title} with command: {runner_command} {directory}")
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

                logger.info(f"Launching game: {game.title} with command: {runner_command} {full_path}")
                cmd.append(full_path)
            else:
                logger.info(f"Launching game: {game.title} with command: {runner_command}")

            # Launch the game
            process = subprocess.Popen(cmd)

            # Save the PID to the PID file
            self.data_handler.save_game_pid(game, process.pid)

            # Only increment play count if game launched successfully
            self.data_handler.increment_play_count(game)

            # Start tracking the process to monitor play time
            self.monitor_game_process(process.pid, game, on_exit_callback)

            # Store discord_enabled in a class variable for later use when game exits
            self.current_game_discord_enabled = discord_enabled

            # Try to update Discord Rich Presence, but don't let it fail the game launch
            try:
                # Get platform information if enabled
                platform = None
                from discord_integration import SHOW_PLATFORM_INFO
                if SHOW_PLATFORM_INFO and hasattr(game, 'platforms') and game.platforms:
                    # Use the first platform's human-readable name
                    if game.platforms:
                        # Get the enum value's human-readable name
                        platform = game.platforms[0].value
                    else:
                        platform = None

                # Log whether Discord integration is enabled for this launch
                if discord_enabled:
                    logger.info(f"Discord integration enabled for this game launch")
                    # Only update Discord presence if it's enabled for this runner
                    discord_presence.game_started(game.title, platform, discord_enabled)
                else:
                    logger.info(f"Discord integration disabled for this game launch")
                    # Skip Discord integration entirely for this game
            except Exception as e:
                # Just log the error but don't let it affect game launch
                logger.error(f"Discord integration error (game will still launch): {e}")

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

            # Only clear Discord Rich Presence if it was enabled for this game
            if hasattr(self, 'current_game_discord_enabled') and self.current_game_discord_enabled:
                try:
                    logger.info(f"Game {game.title} exited - clearing Discord Rich Presence")
                    # Force disconnect from Discord to ensure status gets cleared
                    discord_presence.game_stopped()
                except Exception as e:
                    # Just log the error but don't let it affect game tracking
                    logger.error(f"Discord integration error on game exit: {e}")
            else:
                logger.info(f"Game {game.title} exited - Discord integration was disabled for this game")

            # Call the callback on the main thread if provided
            if on_exit_callback:
                GLib.idle_add(on_exit_callback, game)

        except Exception as e:
            logger.error(f"Error monitoring game process: {e}")
            # Make sure to clean up the PID file in case of error
            self.data_handler.clear_game_pid(game)

            # Update Discord Rich Presence in case of error
            if self.app_state_manager and self.app_state_manager.get_discord_enabled():
                discord_presence.game_stopped()

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

            # Only clear Discord Rich Presence if it was enabled for this game
            if hasattr(self, 'current_game_discord_enabled') and self.current_game_discord_enabled:
                try:
                    logger.info(f"Game {game.title} was killed - clearing Discord Rich Presence")
                    # Force disconnect from Discord to ensure status gets cleared
                    discord_presence.game_stopped()
                except Exception as e:
                    # Just log the error but don't let it affect game tracking
                    logger.error(f"Discord integration error on game exit: {e}")
            else:
                logger.info(f"Game {game.title} was killed - Discord integration was disabled for this game")

            return True
        except Exception as e:
            logger.error(f"Error killing process for game {game.title}: {e}")
            return False
