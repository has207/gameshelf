import threading
import tempfile
import requests
from io import BytesIO

from gi.repository import Gtk, Adw, GObject, GdkPixbuf, Gdk, GLib

from controllers.common import get_template_path
from providers.opencritic_client import OpenCriticClient
from providers.launchbox_client import LaunchBoxMetadata
from providers.metadata_provider import Game as MetadataGame


@Gtk.Template(filename=get_template_path("metadata_preview_dialog.ui"))
class MetadataPreviewDialog(Adw.Window):
    """Dialog for previewing and confirming game metadata"""
    __gtype_name__ = "MetadataPreviewDialog"

    # Define custom signals
    __gsignals__ = {
        "metadata-accepted": (GObject.SignalFlags.RUN_FIRST, None, (object, str)),
    }

    # UI elements
    dialog_title: Adw.WindowTitle = Gtk.Template.Child()
    accept_button: Gtk.Button = Gtk.Template.Child()
    cancel_button: Gtk.Button = Gtk.Template.Child()
    game_image: Gtk.Picture = Gtk.Template.Child()
    game_title: Gtk.Label = Gtk.Template.Child()
    release_date: Gtk.Label = Gtk.Template.Child()
    publishers: Gtk.Label = Gtk.Template.Child()
    developers: Gtk.Label = Gtk.Template.Child()
    platforms: Gtk.Label = Gtk.Template.Child()
    genres: Gtk.Label = Gtk.Template.Child()
    score: Gtk.Label = Gtk.Template.Child()
    description_text: Gtk.TextView = Gtk.Template.Child()

    def __init__(self, parent_window, controller, game_id, game_name, metadata_client=None, provider_name="OpenCritic"):
        super().__init__()
        self.parent_window = parent_window
        self.controller = controller
        self.set_transient_for(parent_window)
        self.game_id = game_id
        self.game_name = game_name
        self.game_metadata = None
        self.image_path = None
        self.provider_name = provider_name

        # Use provided metadata client or initialize OpenCritic client by default
        self.metadata_client = metadata_client or OpenCriticClient()

        # Set the window title to include the game name and provider
        self.dialog_title.set_title(f"Preview: {game_name} ({provider_name})")

        # Set initial title
        self.game_title.set_text(game_name)

        # Disable the accept button until metadata is loaded
        self.accept_button.set_sensitive(False)

        # Start loading the game details
        self._load_game_details()

    def _load_game_details(self):
        """Load game details in a background thread"""
        # Start a loading spinner in the title bar
        spinner = Gtk.Spinner()
        spinner.set_spinning(True)
        spinner.set_size_request(16, 16)
        self.dialog_title.set_subtitle("Loading...")

        # Start the loading in a separate thread
        thread = threading.Thread(
            target=self._load_game_details_thread
        )
        thread.daemon = True
        thread.start()

    def _load_game_details_thread(self):
        """Background thread for loading game details"""
        try:
            # Fetch the game details
            game = self.metadata_client.get_details(self.game_id)

            # Check if we got valid results
            if game:
                # Store the metadata
                self.game_metadata = game

                # Download the cover image if available
                image_path = None
                if game.images and game.images.box and game.images.box.url:
                    image_path = self._download_image(game.images.box.url)

                # Update the UI in the main thread
                GLib.idle_add(self._update_game_details, game, image_path)
            else:
                GLib.idle_add(self._show_loading_error, "Failed to retrieve game details")
        except Exception as e:
            print(f"Error loading game details for ID {self.game_id}: {e}")
            GLib.idle_add(self._show_loading_error, str(e))

    def _download_image(self, image_url):
        """Download an image from a URL and save it to a temporary file"""
        try:
            response = requests.get(image_url, stream=True)
            if response.status_code == 200:
                # Create a temporary file to save the image
                tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                tmp_file.write(response.content)
                tmp_file.close()
                return tmp_file.name
            return None
        except Exception as e:
            print(f"Error downloading image from {image_url}: {e}")
            return None

    def _update_game_details(self, game, image_path):
        """Update the UI with game details (called in main thread)"""
        # Store the image path
        self.image_path = image_path

        # Update the dialog title
        self.dialog_title.set_subtitle("")

        # Update the game title
        self.game_title.set_text(game.name)

        # Update release date
        if game.first_release_date:
            self.release_date.set_text(game.first_release_date.strftime("%B %d, %Y"))
        else:
            self.release_date.set_text("Unknown")

        # Update publishers
        publishers = [c.name for c in game.companies if c.type.upper() == "PUBLISHER"]
        if publishers:
            self.publishers.set_text(", ".join(publishers))
        else:
            self.publishers.set_text("Unknown")

        # Update developers
        developers = [c.name for c in game.companies if c.type.upper() == "DEVELOPER"]
        if developers:
            self.developers.set_text(", ".join(developers))
        else:
            self.developers.set_text("Unknown")

        # Update platforms
        if game.platforms:
            platform_names = [p.name for p in game.platforms]
            self.platforms.set_text(", ".join(platform_names))
        else:
            self.platforms.set_text("Unknown")

        # Update genres
        if game.genres:
            genre_names = [g.name for g in game.genres]
            self.genres.set_text(", ".join(genre_names))
        else:
            self.genres.set_text("Unknown")

        # Update score
        if game.top_critic_score > 0:
            self.score.set_text(f"{game.top_critic_score:.1f}/100")
        else:
            self.score.set_text("Not rated")

        # Update description
        if game.description:
            buffer = self.description_text.get_buffer()
            buffer.set_text(game.description)
        else:
            buffer = self.description_text.get_buffer()
            buffer.set_text("No description available")

        # Update image if available
        if image_path:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                    image_path, 200, 260, True)
                if pixbuf:
                    self.game_image.set_paintable(Gdk.Texture.new_for_pixbuf(pixbuf))
            except Exception as e:
                print(f"Error loading game image: {e}")

        # Enable the accept button
        self.accept_button.set_sensitive(True)

        return False  # Remove from idle queue

    def _show_loading_error(self, error_message):
        """Show an error message in the UI (called in main thread)"""
        self.dialog_title.set_subtitle("Error")

        # Update description to show error
        buffer = self.description_text.get_buffer()
        buffer.set_text(f"Error loading game details: {error_message}")

        # Disable the accept button
        self.accept_button.set_sensitive(False)

        return False  # Remove from idle queue

    @Gtk.Template.Callback()
    def on_cancel_clicked(self, button):
        """Handle cancel button click"""
        self.close()

    @Gtk.Template.Callback()
    def on_accept_clicked(self, button):
        """Handle accept button click"""
        if self.game_metadata:
            # Emit our signal with the metadata and image path
            self.emit("metadata-accepted", self.game_metadata, self.image_path)
            self.close()