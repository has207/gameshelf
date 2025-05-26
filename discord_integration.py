#!/usr/bin/env python3

import os
import time
import threading
import logging
import gc
from typing import Optional

# Use the local pypresence module from 3rd_party
from pathlib import Path
import sys
# Add 3rd party to sys.path
sys.path.insert(0, str(Path(__file__).parent / "3rd_party"))
from pypresence import Presence

# Application client ID for Discord Developer Portal
# You'll need to create a Discord application at https://discord.com/developers/applications
# and use its client ID here - this ID is specific to your Discord application
DISCORD_CLIENT_ID = "1372963900873642055"

# Note: Discord chat member list will only ever show "Playing [Application Name]"
# where [Application Name] is set in the Discord Developer Portal.
# The full rich presence with game title only shows when clicking user profiles.

# Discord settings
SHOW_PLATFORM_INFO = True  # Whether to show platform info in Discord presence

# Set up logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class DiscordPresence:
    """
    Manages Discord Rich Presence for GameShelf.
    """
    def __init__(self):
        """Initialize the Discord integration."""
        self.client = None
        self.connected = False
        self.current_game = None
        self.current_platform = None
        self.start_time = None
        self._stop_event = threading.Event()
        self._presence_thread = None

        logger.info("Discord integration initialized - will only connect when a game is launched")

    def is_discord_running(self) -> bool:
        """
        Check if Discord is running on the system.

        Returns:
            bool: True if Discord is running, False otherwise
        """
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                process_name = proc.info['name'].lower()
                if 'discord' in process_name:
                    logger.info(f"Found Discord process: {process_name}")
                    return True

            logger.warning("No Discord process found running - Rich Presence requires Discord to be running")
            return False
        except Exception as e:
            logger.error(f"Error checking for Discord process: {e}")
            return False

    def connect(self) -> bool:
        """
        Connect to Discord Rich Presence.

        Returns:
            bool: True if connection successful, False otherwise
        """
        if self.connected:
            return True

        # Check if Discord is running
        if not self.is_discord_running():
            logger.warning("Discord is not running - Rich Presence not available")
            return False

        # Check if we have a valid client ID
        if not DISCORD_CLIENT_ID:
            logger.warning("No Discord client ID set - Rich Presence is disabled")
            return False

        # Validate client ID format
        if not isinstance(DISCORD_CLIENT_ID, str) or not DISCORD_CLIENT_ID.strip():
            logger.error(f"Invalid Discord client ID: {DISCORD_CLIENT_ID}")
            return False

        try:
            # Log connection attempt with detailed client ID information
            logger.info(f"Connecting to Discord with client ID: '{DISCORD_CLIENT_ID}' (length: {len(DISCORD_CLIENT_ID)})")

            # Additional validation
            if not DISCORD_CLIENT_ID.isdigit():
                logger.warning(f"Warning: Discord client ID should only contain numbers")

            # Discord application IDs are typically 18-19 digits
            if len(DISCORD_CLIENT_ID) < 17 or len(DISCORD_CLIENT_ID) > 20:
                logger.warning(f"Warning: Discord client ID length ({len(DISCORD_CLIENT_ID)}) is unusual. Valid IDs are typically 18-19 digits")

            try:
                # Create client
                self.client = Presence(DISCORD_CLIENT_ID)

                # Try to connect with extra debug info
                logger.info("Attempting to connect to Discord...")
                self.client.connect()

                # Mark as connected if successful
                self.connected = True
                logger.info("Successfully connected to Discord Rich Presence")
            except Exception as e:
                # More detailed error logging
                import traceback
                logger.error(f"Discord connection error details: {e}")
                logger.debug(traceback.format_exc())
                raise

            # Don't set any initial presence - we only show Discord presence when games are running
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Discord: {e}")
            self.connected = False
            self.client = None
            return False

    def disconnect(self) -> None:
        """Disconnect from Discord Rich Presence."""
        if not self.connected or not self.client:
            return

        try:
            self.client.clear()
            self.client.close()
            logger.info("Disconnected from Discord Rich Presence")
        except Exception as e:
            logger.error(f"Error disconnecting from Discord: {e}")
        finally:
            self.connected = False
            self.client = None
            self.current_game = None

    def update_presence(self, state: str, details: str,
                        large_image: str = "gameshelf",
                        start_timestamp: Optional[int] = None) -> bool:
        """
        Update the Discord Rich Presence.

        Args:
            state: Bottom row of presence
            details: Top row of presence
            large_image: Key for the large image
            start_timestamp: Unix timestamp for game start (for elapsed time)

        Returns:
            bool: True if update successful, False otherwise
        """
        if not self.connected or not self.client:
            logger.warning("Cannot update presence - not connected to Discord")
            return False

        try:
            # Make sure details and state aren't too long (Discord limits)
            if details and len(details) > 128:
                details = details[:125] + "..."
            if state and len(state) > 128:
                state = state[:125] + "..."

            logger.info(f"Sending to Discord - details: '{details}', state: '{state}', timestamp: {start_timestamp}")

            # Now that we have uploaded an image asset, include it in the presence
            update_params = {
                "instance": True,
                "details": details,
                "large_image": "gameshelf",  # The name of your uploaded asset
                "large_text": "GameShelf"
            }

            # Add state if provided
            if state:
                update_params["state"] = state

            # Only add timestamp for game playing (not for browsing)
            if start_timestamp:
                update_params["start"] = start_timestamp

            # Try to clear first to ensure state is fresh
            try:
                self.client.clear()
            except:
                pass

            # Now update with new presence
            result = self.client.update(**update_params)
            logger.info(f"Discord update result: {result}")
            logger.debug(f"Updated Discord presence: {details} - {state}")
            return True
        except Exception as e:
            logger.error(f"Failed to update Discord presence: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            # Attempt to reconnect
            self.connected = False
            return False

    def game_started(self, game_title: str, platform: str = None, discord_enabled: bool = True) -> None:
        """
        Update presence when a game is started.

        Args:
            game_title: Title of the game
            platform: Game platform (optional)
            discord_enabled: Whether Discord presence is enabled for this runner
        """
        # Add detailed logging
        logger.info(f"Game started: '{game_title}', platform: '{platform}', discord_enabled: {discord_enabled}")

        # If Discord presence is disabled for this runner, don't update
        if not discord_enabled:
            logger.info(f"Discord presence disabled for this runner - skipping update")
            return

        # Make sure game title isn't empty
        if not game_title:
            game_title = "Unknown Game"

        if not self.connect():
            logger.warning("Could not connect to Discord - cannot update presence")
            return

        self.current_game = game_title
        self.current_platform = platform  # Store platform to maintain it in refresh
        self.start_time = int(time.time())

        # Now that we have assets, we can use both fields properly
        details = f"Playing {game_title}"

        if platform:
            state = f"on {platform}"
        else:
            state = "Playing"

        logger.info(f"Updating Discord presence to: {details} | {state}")

        # Force a reconnect to ensure Discord is properly initialized
        if self.client:
            try:
                self.client.clear()
            except Exception as e:
                logger.debug(f"Error clearing previous presence: {e}")

        # Try to make a fresh connection
        self.connected = False
        self.client = None
        if not self.connect():
            logger.warning("Reconnect failed - cannot update presence")
            return

        # Simplify the update to just the essential information
        success = self.update_presence(state, details, None, self.start_time)
        if success:
            logger.info("Successfully updated Discord presence for game start")
        else:
            logger.warning("Failed to update Discord presence for game start")

        # Start presence update thread if not running
        if not self._presence_thread or not self._presence_thread.is_alive():
            self._stop_event.clear()
            self._presence_thread = threading.Thread(
                target=self._presence_update_thread,
                daemon=True
            )
            self._presence_thread.start()

    def game_stopped(self) -> None:
        """Clear presence when a game is stopped."""
        logger.info("Game stopped - clearing Discord presence")

        # Signal the thread to stop
        if self._presence_thread and self._presence_thread.is_alive():
            logger.info("Stopping presence update thread")
            self._stop_event.set()
            self._presence_thread.join(timeout=2.0)
            logger.info("Presence update thread stopped")

        # Reset internal state
        self.current_game = None
        self.current_platform = None
        self.start_time = None

        # Clear presence completely - completely disconnect from Discord
        try:
            if self.client and self.connected:
                try:
                    # First send an empty update to more reliably clear the display
                    logger.info("Sending empty update to Discord")
                    try:
                        # Set empty state and details to clear the display
                        self.client.update(state=None, details=None)
                        # Small delay to allow Discord to process
                        time.sleep(0.2)
                    except Exception as e:
                        logger.warning(f"Error sending empty update: {e}")

                    # Then try to clear the presence
                    logger.info("Clearing Discord presence")
                    self.client.clear()
                    logger.info("Cleared Discord rich presence")
                except Exception as e:
                    logger.warning(f"Error clearing presence: {e}")

                try:
                    # Then close the connection
                    logger.info("Closing Discord connection")
                    self.client.close()
                    logger.info("Disconnected from Discord")
                except Exception as e:
                    logger.warning(f"Error closing Discord connection: {e}")

                # Make sure we reset the state even if errors occurred
                self.client = None
                self.connected = False
        except Exception as e:
            logger.error(f"Error during Discord cleanup: {e}")
            # Reset state even if there was an error
            self.client = None
            self.connected = False

        # Force garbage collection to clean up any resources
        gc.collect()

        logger.info("Discord integration fully reset")

    def _presence_update_thread(self) -> None:
        """
        Thread to keep presence updated and handle reconnection if needed.
        """
        logger.info("Starting presence update thread")

        refresh_count = 0

        while not self._stop_event.is_set():
            try:
                refresh_count += 1

                # Check if we have a current game - if not, we shouldn't be reconnecting or updating presence
                if not self.current_game:
                    logger.debug("No current game - skipping presence update")
                    self._stop_event.wait(15)  # Still wait between checks
                    continue

                if not self.connected and self.current_game:
                    # Try to reconnect
                    logger.info("Connection lost - attempting to reconnect")
                    if self.connect():
                        # Restore the game presence
                        details = f"Playing {self.current_game}"
                        if self.current_platform:
                            state = f"on {self.current_platform}"
                        else:
                            state = "Playing"
                        self.update_presence(state, details, None, self.start_time)
                        logger.info("Reconnected and restored game presence")

                # Sleep for a while before checking again
                self._stop_event.wait(15)  # Check every 15 seconds

                # Double-check we still have a current game - it may have been cleared during the wait
                if not self.current_game:
                    logger.debug("Game no longer active - skipping presence update")
                    continue

                # Ensure presence is still active with the current game
                if self.connected and self.current_game:
                    details = f"Playing {self.current_game}"
                    if self.current_platform:
                        state = f"on {self.current_platform}"
                    else:
                        state = "Playing"

                    # Every 4th refresh (about 1 minute), do a full reconnect
                    if refresh_count % 4 == 0:
                        logger.info(f"Periodic reconnect (refresh #{refresh_count})")
                        # Force a reconnect to ensure presence stays updated
                        self.connected = False
                        self.client = None
                        if self.connect():
                            logger.info("Periodic reconnect successful")

                    success = self.update_presence(state, details, "gameshelf", self.start_time)
                    if success:
                        logger.debug(f"Thread refresh #{refresh_count}: Successfully refreshed presence")
                    else:
                        logger.warning(f"Thread refresh #{refresh_count}: Failed to refresh presence")
            except Exception as e:
                logger.error(f"Error in presence update thread: {e}")
                # Don't let the thread die on error
                try:
                    import traceback
                    logger.debug(traceback.format_exc())
                except:
                    pass


# Singleton instance
discord_presence = DiscordPresence()
