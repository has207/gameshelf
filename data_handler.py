import os
import yaml
import time
import shutil
import enum
import logging
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple, Union

from data import Game, Runner, Source, SourceType, RomPath
from data_mapping import (
    CompletionStatus, InvalidCompletionStatusError,
    Platforms, InvalidPlatformError,
    AgeRatings, InvalidAgeRatingError,
    Features, InvalidFeatureError,
    Genres, InvalidGenreError,
    Regions, InvalidRegionError
)

import gi
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import GdkPixbuf

# Set up logger
logger = logging.getLogger(__name__)


class DataHandler:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.games_dir = self.data_dir / "games"
        self.runners_dir = self.data_dir / "runners"
        self.sources_dir = self.data_dir / "sources"

        # Get the project root directory for finding media directory
        self.project_root = Path(__file__).parent

        # Runner icon mapping
        self.runner_icon_map = {
            "steam": "steam-symbolic",
            "wine": "wine-symbolic",
            "native": "system-run-symbolic",
            "browser": "web-browser-symbolic",
            "emulator": "media-optical-symbolic",
        }

        # Ensure directories exist
        self.games_dir.mkdir(parents=True, exist_ok=True)
        self.runners_dir.mkdir(parents=True, exist_ok=True)
        self.sources_dir.mkdir(parents=True, exist_ok=True)

    def load_games(self) -> List[Game]:
        games = []
        for game_file in self.games_dir.glob("*/*/*/game.yaml"):
            try:
                # Extract the game ID from the directory structure
                game_id = self._extract_game_id_from_path(game_file)

                with open(game_file, "r") as f:
                    game_data = yaml.safe_load(f)
                    # Get the completion status string from game.yaml
                    completion_status_str = game_data.get("completion_status")
                    try:
                        # Convert string to enum
                        if completion_status_str:
                            completion_status = CompletionStatus.from_string(completion_status_str)
                        else:
                            completion_status = CompletionStatus.NOT_PLAYED
                    except InvalidCompletionStatusError as e:
                        logger.error(f"Error loading game {game_id} - invalid completion status '{completion_status_str}': {e}")
                        completion_status = CompletionStatus.NOT_PLAYED

                    # Extract platforms list if available
                    platforms = []
                    if "platforms" in game_data and isinstance(game_data["platforms"], list):
                        for platform_str in game_data["platforms"]:
                            try:
                                platform = Platforms.from_string(platform_str)
                                platforms.append(platform)
                            except InvalidPlatformError:
                                # Skip invalid platforms
                                logger.warning(f"Skipping invalid platform '{platform_str}' for game {game_id}")

                    # Extract age ratings list if available
                    age_ratings = []
                    if "age_ratings" in game_data and isinstance(game_data["age_ratings"], list):
                        for rating_str in game_data["age_ratings"]:
                            try:
                                rating = AgeRatings.from_string(rating_str)
                                age_ratings.append(rating)
                            except InvalidAgeRatingError:
                                # Skip invalid age ratings
                                logger.warning(f"Skipping invalid age rating '{rating_str}' for game {game_id}")

                    # Extract features list if available
                    features = []
                    if "features" in game_data and isinstance(game_data["features"], list):
                        for feature_str in game_data["features"]:
                            try:
                                feature = Features.from_string(feature_str)
                                features.append(feature)
                            except InvalidFeatureError:
                                # Skip invalid features
                                logger.warning(f"Skipping invalid feature '{feature_str}' for game {game_id}")

                    # Extract genres list if available
                    genres = []
                    if "genres" in game_data and isinstance(game_data["genres"], list):
                        for genre_str in game_data["genres"]:
                            try:
                                genre = Genres.from_string(genre_str)
                                genres.append(genre)
                            except InvalidGenreError:
                                # Skip invalid genres
                                logger.warning(f"Skipping invalid genre '{genre_str}' for game {game_id}")

                    # Extract regions list if available
                    regions = []
                    if "regions" in game_data and isinstance(game_data["regions"], list):
                        for region_str in game_data["regions"]:
                            try:
                                region = Regions.from_string(region_str)
                                regions.append(region)
                            except InvalidRegionError:
                                # Skip invalid regions
                                logger.warning(f"Skipping invalid region '{region_str}' for game {game_id}")

                    game = Game(
                        title=game_data.get("title", "Unknown Game"),
                        id=game_id,
                        created=game_data.get("created"),
                        hidden=game_data.get("hidden", False),
                        completion_status=completion_status,
                        platforms=platforms,
                        age_ratings=age_ratings,
                        features=features,
                        genres=genres,
                        regions=regions,
                        source=game_data.get("source")
                    )

                    # Load play count if exists
                    play_count_file = game_file.parent / "play_count.yaml"
                    if play_count_file.exists():
                        try:
                            with open(play_count_file, "r") as pc_file:
                                play_data = yaml.safe_load(pc_file)
                                if play_data and isinstance(play_data, dict):
                                    game.play_count = play_data.get("count", 0)
                        except Exception as pc_err:
                            logger.error(f"Error loading play count for {game_id}: {pc_err}")

                    # Load play time if exists
                    play_time_file = game_file.parent / "playtime.yaml"
                    if play_time_file.exists():
                        try:
                            with open(play_time_file, "r") as pt_file:
                                play_time_data = yaml.safe_load(pt_file)
                                if play_time_data and isinstance(play_time_data, dict):
                                    game.play_time = play_time_data.get("seconds", 0)
                        except Exception as pt_err:
                            logger.error(f"Error loading play time for {game_id}: {pt_err}")

                    # Load description if exists
                    description_file = game_file.parent / "description.yaml"
                    if description_file.exists():
                        try:
                            with open(description_file, "r") as desc_file:
                                desc_data = yaml.safe_load(desc_file)
                                if desc_data and isinstance(desc_data, dict):
                                    game.description = desc_data.get("text")
                        except Exception as desc_err:
                            logger.error(f"Error loading description for {game_id}: {desc_err}")

                    # Load launcher data if exists
                    launcher_data = self.get_launcher_data(game)
                    if launcher_data:
                        # Store launcher data in game object properties
                        game.launcher_type = launcher_data.get("type")
                        game.launcher_id = launcher_data.get("id")


                    games.append(game)
            except Exception as e:
                logger.error(f"Error loading game {game_file}: {e}")
        return games

    def load_runners(self) -> List[Runner]:
        runners = []
        for runner_file in self.runners_dir.glob("*.yaml"):
            try:
                with open(runner_file, "r") as f:
                    runner_data = yaml.safe_load(f)

                    # Extract platforms list if available
                    platforms = []
                    if "platforms" in runner_data and isinstance(runner_data["platforms"], list):
                        for platform_str in runner_data["platforms"]:
                            try:
                                platform = Platforms.from_string(platform_str)
                                platforms.append(platform)
                            except InvalidPlatformError:
                                # Skip invalid platforms
                                logger.warning(f"Skipping invalid platform '{platform_str}' for runner {runner_file.stem}")

                    # Get discord_enabled value (default to True if not present for backward compatibility)
                    # Log the value to debug if it's loading correctly
                    discord_enabled = runner_data.get("discord_enabled", True)
                    logger.debug(f"Loading runner {runner_file.stem} with discord_enabled={discord_enabled}")

                    runner = Runner(
                        title=runner_data.get("title", "Unknown Runner"),
                        image=runner_data.get("image", ""),
                        command=runner_data.get("command", ""),
                        id=runner_file.stem,
                        platforms=platforms,
                        discord_enabled=discord_enabled,
                        launcher_type=runner_data.get("launcher_type")
                    )
                    runners.append(runner)
            except Exception as e:
                logger.error(f"Error loading runner {runner_file}: {e}")
        return runners

    def save_game(self, game: Game, preserve_created_time: bool = False) -> bool:
        """
        Save a game to disk.

        Args:
            game: The game to save
            preserve_created_time: If True, won't overwrite game.created when assigning a new ID

        Returns:
            True if successful, False otherwise
        """
        if not game.id:
            next_id = self.get_next_game_id()
            game.id = str(next_id)
            if not preserve_created_time or game.created is None:
                game.created = time.time()

        game_data = {
            "title": game.title,
            "completion_status": game.completion_status.value
        }

        if game.created:
            game_data["created"] = game.created
        if game.hidden:
            game_data["hidden"] = game.hidden
        if game.platforms:
            # Save platform enum display values
            game_data["platforms"] = [platform.value for platform in game.platforms]

        if game.age_ratings:
            # Save age rating enum display values
            game_data["age_ratings"] = [rating.value for rating in game.age_ratings]

        if game.features:
            # Save feature enum display values
            game_data["features"] = [feature.value for feature in game.features]

        if game.genres:
            # Save genre enum display values
            game_data["genres"] = [genre.value for genre in game.genres]

        if game.regions:
            # Save region enum display values
            game_data["regions"] = [region.value for region in game.regions]

        # Save source if present
        if game.source:
            game_data["source"] = game.source

        try:
            game_dir = self._get_game_dir_from_id(game.id)
            game_dir.mkdir(parents=True, exist_ok=True)

            game_file = game_dir / "game.yaml"
            with open(game_file, "w") as f:
                yaml.dump(game_data, f)
            return True
        except Exception as e:
            logger.error(f"Error saving game {game.id}: {e}")
            return False

    def save_runner(self, runner: Runner) -> bool:
        if not runner.id:
            runner.id = runner.title.lower().replace(" ", "_")

        runner_data = {
            "title": runner.title,
            "image": runner.image,
            "command": runner.command,
            "discord_enabled": runner.discord_enabled if hasattr(runner, 'discord_enabled') else True
        }

        # Save launcher type if it exists
        if hasattr(runner, 'launcher_type') and runner.launcher_type:
            runner_data["launcher_type"] = runner.launcher_type

        # Save platform enum display values
        if runner.platforms:
            runner_data["platforms"] = [platform.value for platform in runner.platforms]

        try:
            with open(self.runners_dir / f"{runner.id}.yaml", "w") as f:
                yaml.dump(runner_data, f)
            return True
        except Exception as e:
            logger.error(f"Error saving runner {runner.id}: {e}")
            return False

    def save_game_image(self, source_path: str, game_id: str) -> bool:
        """
        Copy a game image to the game's directory as cover.jpg.

        Args:
            source_path: Path to the source image
            game_id: ID of the game

        Returns:
            True if the image was successfully saved, False otherwise
        """
        if not source_path or not os.path.exists(source_path):
            return False

        try:
            # Create game directory if it doesn't exist
            game_dir = self._get_game_dir_from_id(game_id)
            game_dir.mkdir(parents=True, exist_ok=True)

            # Always save as cover.jpg
            dest_path = game_dir / "cover.jpg"

            # Copy the file
            shutil.copy2(source_path, dest_path)
            return True
        except Exception as e:
            logger.error(f"Error copying image: {e}")
            return False

    def remove_game_image(self, game_id: str) -> bool:
        """
        Remove a game's cover image if it exists.

        Args:
            game_id: ID of the game

        Returns:
            True if the image was successfully removed or didn't exist, False if error
        """
        try:
            game_dir = self._get_game_dir_from_id(game_id)
            cover_path = game_dir / "cover.jpg"

            if cover_path.exists():
                cover_path.unlink()
            return True
        except Exception as e:
            logger.error(f"Error removing cover image for game {game_id}: {e}")
            return False

    def create_game_with_image(self, title: str, image_path: Optional[str] = None) -> Game:
        """
        Create a new game object with an image, handling ID generation and image copying.

        Args:
            title: The title of the game
            image_path: Optional path to an image file

        Returns:
            A new Game object
        """
        # Get the next numeric game ID
        next_id = self.get_next_game_id()
        game_id = str(next_id)

        # Create the game object with creation timestamp
        game = Game(
            id=game_id,
            title=title,
            created=time.time(),
            completion_status=CompletionStatus.NOT_PLAYED
        )

        # Save image if provided
        if image_path:
            self.save_game_image(image_path, game_id)

        return game

    def get_runner_icon(self, runner_id: str) -> str:
        """
        Get the icon name for a given runner ID.

        Args:
            runner_id: The ID of the runner

        Returns:
            The name of the icon to use for the runner
        """
        if not runner_id:
            return "application-x-executable-symbolic"

        # Try to match beginning of runner name to known icons
        for key, icon in self.runner_icon_map.items():
            if runner_id.lower().startswith(key):
                return icon

        # Default icon for unknown runners
        return "application-x-executable-symbolic"

    def load_game_image(self, game: Game, width: int = 200, height: int = 260) -> Optional[GdkPixbuf.Pixbuf]:
        """
        Load a game's image as a pixbuf, scaled to the specified dimensions.

        Args:
            game: The game to load the image for
            width: The desired width of the image
            height: The desired height of the image

        Returns:
            A pixbuf containing the game's image, or None if no image is available
        """
        try:
            cover_path = game.get_cover_path(self.data_dir)
            if not os.path.exists(cover_path):
                return None
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                cover_path, width, height, True)
        except Exception as e:
            logger.error(f"Error loading image for {game.title}: {e}")
            return None

    def get_default_icon_paintable(self, icon_name: str, size: int = 128) -> 'Gdk.Paintable':
        """
        Get a default icon as a paintable for use with GtkPicture widgets.

        Args:
            icon_name: The name of the icon to get
            size: The size of the icon

        Returns:
            A paintable that can be used with GtkPicture widgets
        """
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Gdk', '4.0')
        from gi.repository import Gtk, Gdk

        display = Gdk.Display.get_default()
        icon_theme = Gtk.IconTheme.get_for_display(display)
        # The empty list is for icon sizes, 1 is scale factor, Gtk.TextDirection.LTR is text direction
        return icon_theme.lookup_icon(icon_name, [], size, 1, Gtk.TextDirection.LTR, 0)

    def _get_game_dir_from_id(self, game_id: str) -> Path:
        """
        Get the game directory path from a game ID using the new structured format.
        For example, game ID 23 would be in data/games/000/000/023/

        Args:
            game_id: The ID of the game (will be converted to string and padded)

        Returns:
            Path to the game's directory
        """
        # Convert to string if it's an integer
        game_id_str = str(game_id)

        # Ensure ID is padded to 9 digits
        padded_id = game_id_str.zfill(9)

        # Split into 3 groups of 3 digits
        dir1, dir2, dir3 = padded_id[:3], padded_id[3:6], padded_id[6:]

        # Return the full path
        return self.games_dir / dir1 / dir2 / dir3

    def _extract_game_id_from_path(self, game_path: Path) -> str:
        """
        Extract a game ID from a directory path structured as 000/000/023.
        Handles the reverse of _get_game_dir_from_id.

        Args:
            game_path: Path to a game directory or file within it

        Returns:
            The game ID as a string with leading zeros removed
        """
        # If we're given a file, get its parent directory
        if game_path.is_file():
            game_path = game_path.parent

        # Extract the directory components
        dir3 = game_path.name
        dir2 = game_path.parent.name
        dir1 = game_path.parent.parent.name

        # Combine directory parts to get the padded ID
        padded_id = dir1 + dir2 + dir3

        # Convert to integer and back to string to remove leading zeros
        if padded_id.isdigit():
            return str(int(padded_id))
        else:
            return padded_id

    def get_next_game_id(self) -> int:
        """
        Get the next available game ID by finding the highest existing numeric ID
        and incrementing it by 1.

        Returns:
            The next available numeric ID for a game
        """
        try:
            # Look for the highest existing ID across all game directories
            highest_id = -1

            # Recursively search through all directories that might contain games
            for game_yaml in self.games_dir.glob("*/*/*/game.yaml"):
                try:
                    # Extract the ID from the path, which handles removing leading zeros
                    game_id = self._extract_game_id_from_path(game_yaml)

                    # Convert to integer for comparison
                    if game_id.isdigit():
                        id_int = int(game_id)
                        highest_id = max(highest_id, id_int)
                except Exception as inner_e:
                    logger.error(f"Error parsing game ID from {game_yaml}: {inner_e}")
                    continue

            # Start from the next ID after the highest found, or 0 if no numeric IDs exist
            return highest_id + 1
        except Exception as e:
            logger.error(f"Error getting next game ID: {e}")
            return 0

    def load_runner_image(self, runner: Runner, width: int = 64, height: int = 64) -> Optional[GdkPixbuf.Pixbuf]:
        """
        Load a runner's image as a pixbuf, scaled to the specified dimensions.

        Args:
            runner: The runner to load the image for
            width: The desired width of the image
            height: The desired height of the image

        Returns:
            A pixbuf containing the runner's image, or None if no image is available
        """
        try:
            if not runner.image or not os.path.exists(runner.image):
                return None
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                runner.image, width, height, True)
        except Exception as e:
            logger.error(f"Error loading image for {runner.title}: {e}")
            return None

    def update_play_count(self, game: Game, count: int) -> bool:
        """
        Update the play count for a game and save it to the play_count.yaml file.
        The file modification time will serve as the 'last played' timestamp.
        Also manages the completion status based on play count:
        - If count is 0 and status is Playing/Played/Beaten/Completed, reset to Not Played
        - If count > 0 and status is Not Played, change to Played

        Args:
            game: The game to update the play count for
            count: The new play count value

        Returns:
            True if the play count was successfully updated, False otherwise
        """
        game_dir = self._get_game_dir_from_id(game.id)
        play_count_file = game_dir / "play_count.yaml"

        try:
            # Check if we need to update completion status based on play count
            status_updated = False

            # Define states that should be reset to NOT_PLAYED when play count is 0
            playable_states = [
                CompletionStatus.PLAYING,
                CompletionStatus.PLAYED,
                CompletionStatus.BEATEN,
                CompletionStatus.COMPLETED
            ]

            # If count is 0 and the game is in a playable state, reset to NOT_PLAYED
            if count == 0 and game.completion_status in playable_states:
                game.completion_status = CompletionStatus.NOT_PLAYED
                status_updated = True
                logger.info(f"Resetting completion status for game {game.title} to NOT_PLAYED (play count = 0)")

            # If count > 0 and status is NOT_PLAYED, change to PLAYED
            elif count > 0 and game.completion_status == CompletionStatus.NOT_PLAYED:
                game.completion_status = CompletionStatus.PLAYED
                status_updated = True
                logger.info(f"Setting completion status for game {game.title} to PLAYED (play count = {count})")

            # Update the play count in the game object
            game.play_count = count

            # Create the play count data
            play_data = {"count": count}

            # Write to the file (this also updates the modification time)
            with open(play_count_file, "w") as f:
                yaml.dump(play_data, f)

            # If the completion status changed, update the game.yaml file
            if status_updated:
                self.save_game(game, True)
                logger.info(f"Updated completion status for {game.title} based on play count changes")

            return True
        except Exception as e:
            logger.error(f"Error updating play count for {game.id}: {e}")
            return False

    def increment_play_count(self, game: Game) -> bool:
        """
        Increment the play count for a game by 1.
        Uses update_play_count with current count + 1.
        This will automatically update the completion status if needed:
        - If the current status is NOT_PLAYED and play count becomes > 0, it changes to PLAYED

        Args:
            game: The game to increment the play count for

        Returns:
            True if the play count was successfully incremented, False otherwise
        """
        # Incrementing will always result in a count > 0, which means
        # the update_play_count method will handle changing NOT_PLAYED to PLAYED
        return self.update_play_count(game, game.play_count + 1)

    def update_play_time(self, game: Game, seconds: int) -> bool:
        """
        Update the play time for a game with a specific value.

        Args:
            game: The game to update the play time for
            seconds: The total seconds to set play time to

        Returns:
            True if the play time was successfully updated, False otherwise
        """
        game_dir = self._get_game_dir_from_id(game.id)
        play_time_file = game_dir / "playtime.yaml"

        try:
            # Set the play time to the provided value
            game.play_time = seconds

            # Create the play time data
            play_time_data = {"seconds": game.play_time}

            # Write to the file
            with open(play_time_file, "w") as f:
                yaml.dump(play_time_data, f)

            return True
        except Exception as e:
            logger.error(f"Error updating play time for {game.id}: {e}")
            return False

    def update_game_description(self, game: Game, description: str) -> bool:
        """
        Update the description for a game and save it to the description.yaml file.

        Args:
            game: The game to update the description for
            description: The new description text

        Returns:
            True if the description was successfully updated, False otherwise
        """
        game_dir = self._get_game_dir_from_id(game.id)
        description_file = game_dir / "description.yaml"

        try:
            # Update the description in the game object
            game.description = description

            # Create the description data
            desc_data = {"text": description}

            # Write to the file
            with open(description_file, "w") as f:
                yaml.dump(desc_data, f)

            return True
        except Exception as e:
            logger.error(f"Error updating description for {game.id}: {e}")
            return False

    def update_completion_status(self, game: Game, status: CompletionStatus) -> bool:
        """
        Update the completion status for a game and save it to game.yaml.

        Args:
            game: The game to update the completion status for
            status: The new completion status (enum)

        Returns:
            True if the completion status was successfully updated, False otherwise
        """
        try:
            # Update the completion status in the game object
            game.completion_status = status

            # Save the game to update the yaml file
            return self.save_game(game, True)
        except Exception as e:
            logger.error(f"Error updating completion status for {game.id}: {e}")
            return False

    def update_platforms(self, game: Game, platforms: List[Platforms]) -> bool:
        """
        Update the platforms list for a game and save it to game.yaml.

        Args:
            game: The game to update the platforms for
            platforms: The new list of platforms (enum values)

        Returns:
            True if the platforms were successfully updated, False otherwise
        """
        try:
            # Update the platforms in the game object
            game.platforms = platforms

            # Save the game to update the yaml file
            return self.save_game(game, True)
        except Exception as e:
            logger.error(f"Error updating platforms for {game.id}: {e}")
            return False

    def update_age_ratings(self, game: Game, age_ratings: List[AgeRatings]) -> bool:
        """
        Update the age ratings list for a game and save it to game.yaml.

        Args:
            game: The game to update the age ratings for
            age_ratings: The new list of age ratings (enum values)

        Returns:
            True if the age ratings were successfully updated, False otherwise
        """
        try:
            # Update the age ratings in the game object
            game.age_ratings = age_ratings

            # Save the game to update the yaml file
            return self.save_game(game, True)
        except Exception as e:
            logger.error(f"Error updating age ratings for {game.id}: {e}")
            return False

    def update_features(self, game: Game, features: List[Features]) -> bool:
        """
        Update the features list for a game and save it to game.yaml.

        Args:
            game: The game to update the features for
            features: The new list of features (enum values)

        Returns:
            True if the features were successfully updated, False otherwise
        """
        try:
            # Update the features in the game object
            game.features = features

            # Save the game to update the yaml file
            return self.save_game(game, True)
        except Exception as e:
            logger.error(f"Error updating features for {game.id}: {e}")
            return False

    def update_genres(self, game: Game, genres: List[Genres]) -> bool:
        """
        Update the genres list for a game and save it to game.yaml.

        Args:
            game: The game to update the genres for
            genres: The new list of genres (enum values)

        Returns:
            True if the genres were successfully updated, False otherwise
        """
        try:
            # Update the genres in the game object
            game.genres = genres

            # Save the game to update the yaml file
            return self.save_game(game, True)
        except Exception as e:
            logger.error(f"Error updating genres for {game.id}: {e}")
            return False

    def update_regions(self, game: Game, regions: List[Regions]) -> bool:
        """
        Update the regions list for a game and save it to game.yaml.

        Args:
            game: The game to update the regions for
            regions: The new list of regions (enum values)

        Returns:
            True if the regions were successfully updated, False otherwise
        """
        try:
            # Update the regions in the game object
            game.regions = regions

            # Save the game to update the yaml file
            return self.save_game(game, True)
        except Exception as e:
            logger.error(f"Error updating regions for {game.id}: {e}")
            return False

    def save_launcher_data(self, game: Game, launcher_type: str, launcher_id: str) -> bool:
        """
        Save launcher data for a game to a launcher.yaml file.

        Args:
            game: The game to save launcher data for
            launcher_type: The type of launcher (e.g., 'EGS', 'PSN', 'XBOX')
            launcher_id: The ID of the game in the launcher's namespace

        Returns:
            True if the launcher data was successfully saved, False otherwise
        """
        game_dir = self._get_game_dir_from_id(game.id)
        launcher_file = self._get_game_dir_from_id(game.id) / "launcher.yaml"

        try:
            # Create the launcher data
            launcher_data = {
                "type": launcher_type,
                "id": launcher_id
            }

            # Write to the file
            with open(launcher_file, "w") as f:
                yaml.dump(launcher_data, f)

            return True
        except Exception as e:
            logger.error(f"Error saving launcher data for {game.id}: {e}")
            return False

    def get_launcher_data(self, game: Game) -> Optional[Dict[str, str]]:
        """
        Get launcher data for a game from the launcher.yaml file.

        Args:
            game: The game to get launcher data for

        Returns:
            Dictionary with launcher data if found, None otherwise
        """
        launcher_file = Path(game.get_launcher_path(self.data_dir))

        if not launcher_file.exists():
            return None

        try:
            with open(launcher_file, "r") as f:
                launcher_data = yaml.safe_load(f)
                return launcher_data
        except Exception as e:
            logger.error(f"Error loading launcher data for {game.id}: {e}")

        return None

    def increment_play_time(self, game: Game, seconds_to_add: int) -> bool:
        """
        Add seconds to a game's play time.

        Args:
            game: The game to increment play time for
            seconds_to_add: The number of seconds to add

        Returns:
            True if the play time was successfully incremented, False otherwise
        """
        if seconds_to_add <= 0:
            return True  # Nothing to add

        # Calculate new total
        new_total = game.play_time + seconds_to_add

        # Update the play time with the new total
        return self.update_play_time(game, new_total)

    def set_last_played_time(self, game: Game, timestamp: float) -> bool:
        """
        Set the last played time for a game by updating the play_count.yaml file's
        modification time.

        Args:
            game: The game to update the last played time for
            timestamp: Unix timestamp (seconds since epoch) to set as the last played time

        Returns:
            True if the last played time was successfully updated, False otherwise
        """
        play_count_file = Path(game.get_play_count_path(self.data_dir))

        try:
            # Ensure the play count file exists
            if not play_count_file.exists():
                # If it doesn't exist, create it with a default count of 0
                # (this is appropriate since we're just setting the timestamp)
                play_data = {"count": game.play_count or 0}
                with open(play_count_file, "w") as f:
                    yaml.dump(play_data, f)

            # Set the access and modification times of the file
            os.utime(play_count_file, (timestamp, timestamp))

            return True
        except Exception as e:
            logger.error(f"Error setting last played time for {game.id}: {e}")
            return False

    def save_game_pid(self, game: Game, pid: int) -> bool:
        """
        Save the PID of a running game process to a pid.yaml file.

        Args:
            game: The game being played
            pid: The process ID of the game

        Returns:
            True if the PID was successfully saved, False otherwise
        """
        pid_file = Path(game.get_pid_path(self.data_dir))

        try:
            # Create the PID data
            pid_data = {"pid": pid}

            # Write to the file
            with open(pid_file, "w") as f:
                yaml.dump(pid_data, f)

            return True
        except Exception as e:
            logger.error(f"Error saving PID for {game.id}: {e}")
            return False

    def get_game_pid(self, game: Game) -> Optional[int]:
        """
        Get the PID of a running game process from the pid.yaml file.

        Args:
            game: The game to check

        Returns:
            The PID if the game is running, None otherwise
        """
        pid_file = Path(game.get_pid_path(self.data_dir))

        if not pid_file.exists():
            return None

        try:
            with open(pid_file, "r") as f:
                pid_data = yaml.safe_load(f)
                if pid_data and isinstance(pid_data, dict):
                    return pid_data.get("pid")
        except Exception as e:
            logger.error(f"Error getting PID for {game.id}: {e}")

        return None

    def clear_game_pid(self, game: Game) -> bool:
        """
        Remove the pid.yaml file for a game.

        Args:
            game: The game to clear the PID for

        Returns:
            True if the PID file was successfully removed, False otherwise
        """
        pid_file = Path(game.get_pid_path(self.data_dir))

        if not pid_file.exists():
            return True

        try:
            pid_file.unlink()
            return True
        except Exception as e:
            logger.error(f"Error clearing PID for {game.id}: {e}")
            return False

    def save_installation_data(self, game: Game, directory: str, files: List[str], total_size: int) -> bool:
        """
        Save installation data for a game to an installation.yaml file.

        Args:
            game: The game to save installation data for
            directory: The directory where the game files are located
            files: List of file paths relative to the directory
            total_size: Total size of all files in bytes

        Returns:
            True if the installation data was successfully saved, False otherwise
        """
        installation_file = Path(game.get_installation_path(self.data_dir))

        try:
            # Check if this is a Wii U game based on platforms
            is_wiiu_game = False
            if game.platforms:
                for platform in game.platforms:
                    if platform == Platforms.NINTENDO_WIIU:
                        is_wiiu_game = True
                        break

            # For Wii U games, we'll store the directory but not individual files
            # since we only need the game root folder to launch it
            if is_wiiu_game:
                # Create the installation data for Wii U games
                installation_data = {
                    "directory": directory,
                    "is_wiiu": True,  # Flag to identify this as a Wii U game
                    "size": total_size
                }
                logger.info(f"Saved Wii U game installation data for {game.title}")
            else:
                # For normal games, sort the files list and include them
                sorted_files = sorted(files, key=self._natural_sort_key)
                installation_data = {
                    "directory": directory,
                    "files": sorted_files,
                    "size": total_size
                }

            # Write to the file
            with open(installation_file, "w") as f:
                yaml.dump(installation_data, f)

            return True
        except Exception as e:
            logger.error(f"Error saving installation data for {game.id}: {e}")
            return False

    def _natural_sort_key(self, s):
        """
        Return a key suitable for natural sorting.
        For example, this will sort "disc2" after "disc1" and before "disc10".
        """
        import re
        # Split the string into text and numeric parts
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]

    def get_installation_data(self, game: Game) -> Optional[Dict[str, Any]]:
        """
        Get installation data for a game from the installation.yaml file.

        Args:
            game: The game to get installation data for

        Returns:
            Dictionary with installation data if found, None otherwise
        """
        installation_file = Path(game.get_installation_path(self.data_dir))

        if not installation_file.exists():
            return None

        try:
            with open(installation_file, "r") as f:
                installation_data = yaml.safe_load(f)
                return installation_data
        except Exception as e:
            logger.error(f"Error loading installation data for {game.id}: {e}")

        return None

    def remove_game(self, game: Game) -> bool:
        """
        Remove a game from the games directory.

        Args:
            game: The game to remove

        Returns:
            True if the game was successfully removed, False otherwise
        """
        game_dir = self._get_game_dir_from_id(game.id)

        try:
            if game_dir.exists():
                # Remove the entire game directory (which includes the cover image)
                shutil.rmtree(game_dir)

                # Try to clean up empty parent directories
                parent = game_dir.parent
                if parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()

                    # Try to clean up grandparent if empty too
                    grandparent = parent.parent
                    if grandparent.exists() and not any(grandparent.iterdir()):
                        grandparent.rmdir()

                return True
            else:
                logger.warning(f"Game directory {game_dir} not found")
                return False
        except Exception as e:
            logger.error(f"Error removing game {game.id}: {e}")
            return False

    def remove_runner(self, runner: Runner) -> bool:
        """
        Remove a runner from the runners directory.

        Args:
            runner: The runner to remove

        Returns:
            True if the runner was successfully removed, False otherwise
        """
        runner_file = self.runners_dir / f"{runner.id}.yaml"

        try:
            if runner_file.exists():
                runner_file.unlink()
                return True
            else:
                logger.warning(f"Runner file {runner_file} not found")
                return False
        except Exception as e:
            logger.error(f"Error removing runner {runner.id}: {e}")
            return False

    def get_source_by_id(self, source_id: str) -> Optional[Source]:
        """
        Get a source by its ID.

        Args:
            source_id: The ID of the source to retrieve

        Returns:
            The Source object if found, None otherwise
        """
        # Look for source in the sources directory
        source_dir = self.sources_dir / source_id
        if source_dir.exists():
            source_file = source_dir / "source.yaml"
            if source_file.exists():
                try:
                    with open(source_file, "r") as f:
                        source_data = yaml.safe_load(f)

                        # Handle source type conversion
                        if "type" in source_data:
                            try:
                                source_type = SourceType.from_string(source_data["type"])
                            except ValueError:
                                logger.warning(f"Invalid source type in {source_file}, defaulting to ROM_DIRECTORY")
                                source_type = SourceType.ROM_DIRECTORY
                        else:
                            source_type = SourceType.ROM_DIRECTORY

                        # Process file extensions
                        # Create the base source
                        source = Source(
                            id=source_id,
                            name=source_data.get("name", source_id),
                            source_type=source_type,
                            active=source_data.get("active", True),
                            config=source_data.get("config", {})
                        )

                        # Handle ROM paths for ROM_DIRECTORY sources
                        if source_type == SourceType.ROM_DIRECTORY and "rom_paths" in source_data:
                            rom_paths = []

                            for path_data in source_data["rom_paths"]:
                                # Process file extensions for each path
                                file_extensions = path_data.get("file_extensions", [])
                                if isinstance(file_extensions, str):
                                    file_extensions = [ext.strip() for ext in file_extensions.split(",") if ext.strip()]

                                rom_paths.append(RomPath(
                                    path=path_data.get("path", ""),
                                    file_extensions=file_extensions,
                                    name_regex=path_data.get("name_regex")
                                ))

                            source.rom_paths = rom_paths

                        return source
                except Exception as e:
                    logger.error(f"Error loading source {source_file}: {e}")

        return None

