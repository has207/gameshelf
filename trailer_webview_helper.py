#!/usr/bin/env python3
"""
Trailer helper script that uses WebKit2 with GTK 3.0.

This script can either extract video URLs from YouTube search results,
or play videos directly in a WebKit window.

Usage:
    Extract URL: python3 trailer_webview_helper.py extract <search_url>
    Play video: python3 trailer_webview_helper.py play <embed_url> <window_title>

Args:
    mode: Either "extract" or "play"
    For extract: search_url - YouTube search URL to extract video from
    For play: embed_url - YouTube embed URL, window_title - Window title

Returns:
    For extract: Prints the video URL to stdout, or "ERROR: <message>" on failure
    For play: Opens video player window
"""
import gi
import sys
import logging
from urllib.parse import urlparse

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Important: This must be run in a separate process from any GTK 4 application
# Use GTK 3.0 specifically for WebKit2 compatibility
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2, GLib, Gio


class TrailerURLExtractor:
    def __init__(self, url):
        self.url = url
        self.video_url = None
        self.webview = None

        logger.info(f"Creating TrailerURLExtractor with URL: {url}")

        # Create a hidden webview for URL extraction
        self.webview = WebKit2.WebView()
        logger.info("WebView created for URL extraction")

        # Load the URL
        logger.info(f"Loading URL: {url}")
        self.webview.load_uri(url)

        # Connect to load events to extract video URL
        self.webview.connect("load-changed", self.on_load_changed)

        # Set timeout to avoid hanging
        GLib.timeout_add(10000, self.timeout_handler)

        logger.info("URL extraction setup complete")

    def on_load_changed(self, webview, load_event):
        """Handle page load events to extract video URL"""
        current_uri = webview.get_uri()
        logger.info(f"Load event: {load_event}, URI: {current_uri}")

        if load_event == WebKit2.LoadEvent.FINISHED:
            logger.info(f"Page finished loading: {current_uri}")

            # Check if we're on a watch page (video page)
            if current_uri and '/watch' in current_uri:
                # We've navigated to a video page, extract the URL
                logger.info(f"Video page detected: {current_uri}")
                self.video_url = current_uri
                print(current_uri)  # Output the URL to stdout
                Gtk.main_quit()
            else:
                # Still on search results, try to extract first video URL
                logger.info(f"Search results page, will try to extract first video URL in 2 seconds")
                GLib.timeout_add(2000, self.extract_video_url)

    def extract_video_url(self):
        """Extract the first video URL from search results"""
        logger.info("Attempting to extract video URL")

        js_code = """
        function getFirstVideoURL() {
            const selectors = [
                '#contents ytd-video-renderer:first-child a#thumbnail',
                '#contents ytd-video-renderer:first-child h3 a',
                'ytd-video-renderer:first-child a[href*="/watch"]',
                '.ytd-item-section-renderer ytd-video-renderer:first-child a',
                'a[href*="/watch"]:first-of-type'
            ];

            for (let selector of selectors) {
                const link = document.querySelector(selector);
                if (link && link.href && link.href.includes('/watch')) {
                    return link.href;
                }
            }
            return null;
        }

        const videoURL = getFirstVideoURL();
        if (videoURL) {
            // Navigate to the video URL
            location.href = videoURL;
        }
        """

        self.webview.run_javascript(js_code, None, self.on_javascript_finished, None)
        logger.info("JavaScript injection completed")
        return False  # Don't repeat the timeout

    def on_javascript_finished(self, webview, result, user_data):
        """Handle JavaScript execution completion"""
        try:
            logger.info("JavaScript execution finished")
        except Exception as e:
            logger.error(f"JavaScript execution error: {e}")

    def timeout_handler(self):
        """Handle timeout - exit if no video URL found"""
        logger.error("Timeout reached, no video URL extracted")
        print("ERROR: Timeout - no video found")
        Gtk.main_quit()
        return False


class VideoPlayerWindow(Gtk.Window):
    def __init__(self, embed_url, title):
        super().__init__(title=title)
        self.set_default_size(854, 480)  # 480p aspect ratio
        self.set_position(Gtk.WindowPosition.CENTER)

        # Set window properties to group with main app
        self.set_wmclass("GameShelf", "GameShelf")
        self.set_role("trailer-player")

        # Set icon to match main app
        try:
            import os
            icon_path = os.path.join(os.path.dirname(__file__), "gameshelf-transparent.png")
            if os.path.exists(icon_path):
                self.set_icon_from_file(icon_path)
        except:
            pass


        # Create WebView
        self.webview = WebKit2.WebView()

        # Configure webview settings for optimal video playback
        settings = self.webview.get_settings()
        settings.set_enable_javascript(True)
        settings.set_enable_media_stream(True)
        settings.set_enable_webaudio(True)
        # Disable hardware acceleration to fix GBM buffer issues
        settings.set_enable_accelerated_2d_canvas(False)
        settings.set_enable_webgl(False)
        settings.set_hardware_acceleration_policy(WebKit2.HardwareAccelerationPolicy.NEVER)
        settings.set_enable_media(True)
        settings.set_media_playback_requires_user_gesture(False)
        settings.set_allow_modal_dialogs(True)
        settings.set_allow_file_access_from_file_urls(True)
        settings.set_allow_universal_access_from_file_urls(True)

        # Set user agent to help with YouTube compatibility
        settings.set_user_agent("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

        # Create scrolled window
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_window.add(self.webview)

        # Add to window
        self.add(scrolled_window)

        # Load the embed URL
        self.webview.load_uri(embed_url)

        # Connect to load events to trigger autoplay
        self.webview.connect("load-changed", self.on_video_load_changed)
        self.webview.connect("load-failed", self.on_load_failed)

        # Connect window close event
        self.connect("delete-event", self.on_window_close)

    def on_video_load_changed(self, webview, load_event):
        """Handle page load events to trigger autoplay"""
        if load_event == WebKit2.LoadEvent.FINISHED:
            logger.info("Page finished loading, will click center of screen in 2 seconds")
            GLib.timeout_add(2000, self.click_center)

    def on_load_failed(self, webview, load_event, failing_uri, error):
        """Handle load failures"""
        logger.error(f"Load failed: {load_event}, URI: {failing_uri}, Error: {error}")
        return False

    def click_center(self):
        """Simulate a click via JavaScript to start video"""
        logger.info("Simulating click via JavaScript")

        click_js = """
        console.log('Simulating click to start video');

        // Create and dispatch click event at center of page
        const clickEvent = new MouseEvent('click', {
            view: window,
            bubbles: true,
            cancelable: true,
            clientX: window.innerWidth / 2,
            clientY: window.innerHeight / 2
        });

        document.body.dispatchEvent(clickEvent);

        // Also try clicking on any video elements directly
        const videos = document.querySelectorAll('video');
        videos.forEach(video => video.dispatchEvent(clickEvent));
        """

        self.webview.run_javascript(click_js)
        return False  # Don't repeat timeout

    def on_window_close(self, window, event):
        """Handle window close event"""
        logger.info("Video player window closing")
        Gtk.main_quit()
        return False



class VideoPlayerApp(Gtk.Application):
    def __init__(self, embed_url, window_title):
        # Use exact same app ID as main app but with different flags to avoid conflicts
        super().__init__(application_id="com.gameshelf.app", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.embed_url = embed_url
        self.window_title = window_title

    def do_activate(self):
        window = VideoPlayerWindow(self.embed_url, self.window_title)
        self.add_window(window)
        window.show_all()


def main():
    if len(sys.argv) < 2:
        logger.error("Usage: python3 trailer_webview_helper.py <mode> [args...]")
        logger.error("  extract <search_url>")
        logger.error("  play <embed_url> <window_title>")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "extract":
        if len(sys.argv) != 3:
            logger.error("Usage: python3 trailer_webview_helper.py extract <search_url>")
            sys.exit(1)

        url = sys.argv[2]

        # Validate URL
        try:
            parsed_url = urlparse(url)
            if not parsed_url.scheme or not parsed_url.netloc:
                logger.error(f"Invalid URL: {url}")
                sys.exit(1)
        except Exception as e:
            logger.error(f"Error parsing URL: {e}")
            sys.exit(1)

        # Create URL extractor
        try:
            extractor = TrailerURLExtractor(url)

            # Run GTK main loop
            Gtk.main()

        except Exception as e:
            logger.error(f"Error creating URL extractor: {e}")
            sys.exit(1)

    elif mode == "play":
        if len(sys.argv) != 4:
            logger.error("Usage: python3 trailer_webview_helper.py play <embed_url> <window_title>")
            sys.exit(1)

        embed_url = sys.argv[2]
        window_title = sys.argv[3]

        logger.info(f"Starting video player with URL: {embed_url}")
        logger.info(f"Window title: {window_title}")

        # Set environment variables to help with window grouping
        import os
        os.environ['WM_CLASS'] = 'GameShelf'
        os.environ['DESKTOP_STARTUP_ID'] = 'gameshelf-trailer'

        # Create and run application
        try:
            app = VideoPlayerApp(embed_url, window_title)
            app.run()

        except Exception as e:
            logger.error(f"Error creating video player: {e}")
            sys.exit(1)
    else:
        logger.error(f"Unknown mode: {mode}")
        logger.error("Valid modes: extract, play")
        sys.exit(1)


if __name__ == "__main__":
    main()
