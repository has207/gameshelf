#!/usr/bin/env python3
"""
GOG authentication helper script that uses WebKit2 with GTK 3.0.

This script is designed to be run as a subprocess by the main application
to handle the WebKit-based OAuth authentication flow without causing
GTK version conflicts with the main application (which uses GTK 4).

Usage:
    python3 gog_auth_helper.py

Returns:
    JSON object with either a 'code' field containing the OAuth code
    or an 'error' field with an error message.
"""
import gi
import sys
import json
import os
import threading
import time
import logging
from urllib.parse import urlparse, parse_qs
import re

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr  # Log to stderr so we don't interfere with the JSON output
)
logger = logging.getLogger(__name__)

# Important: This must be run in a separate process from any GTK 4 application
# Use GTK 3.0 specifically for WebKit2 compatibility
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2, GLib


class GogAuthWebViewWindow(Gtk.Window):
    def __init__(self, auth_url, redirect_uri):
        super().__init__(title="GOG Authentication")
        self.redirect_uri = redirect_uri
        self.auth_code = None

        # Create WebView
        self.webview = WebKit2.WebView()
        self.webview.connect("decide-policy", self.on_decide_policy)
        self.webview.connect("load-changed", self.on_load_changed)

        # Set user agent to ensure compatibility
        settings = self.webview.get_settings()
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        settings.set_property("user-agent", user_agent)

        self.webview.load_uri(auth_url)

        # Add WebView to window (GTK 3.0 style)
        self.add(self.webview)
        self.set_default_size(800, 600)
        self.connect("destroy", Gtk.main_quit)

    def on_load_changed(self, webview, load_event):
        """Handle page load events"""
        if load_event == WebKit2.LoadEvent.FINISHED:
            url = webview.get_uri()
            logger.info(f"Page loaded: {url}")

            # Check if we're on the success page that should contain the auth code
            if "/on_login_success" in url:
                logger.info("GOG login success page detected, extracting auth code")

                # Use JavaScript to extract any potential auth code from the page
                script = """
                (function() {
                    // Look for auth code in URL parameters
                    var urlParams = new URLSearchParams(window.location.search);
                    var code = urlParams.get('code');
                    if (code) return code;

                    // Look for auth code in the page content
                    var bodyText = document.body.innerText || document.body.textContent || '';
                    var codeMatch = bodyText.match(/code[=:]\\s*([a-zA-Z0-9_-]+)/i);
                    if (codeMatch) return codeMatch[1];

                    // Look for any JSON that might contain a code
                    var scriptTags = document.querySelectorAll('script');
                    for (var i = 0; i < scriptTags.length; i++) {
                        var scriptContent = scriptTags[i].textContent;
                        if (scriptContent.includes('code') || scriptContent.includes('authorization')) {
                            try {
                                var jsonMatch = scriptContent.match(/\{[^}]*"code"[^}]*\}/);
                                if (jsonMatch) {
                                    var jsonData = JSON.parse(jsonMatch[0]);
                                    if (jsonData.code) return jsonData.code;
                                }
                            } catch (e) {}
                        }
                    }

                    return null;
                })();
                """

                self.webview.evaluate_javascript(script, -1, None, None, None, self._handle_auth_code_extraction)

    def on_decide_policy(self, webview, decision, decision_type):
        """Handle navigation events to capture the authorization code"""
        if decision_type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            nav_action = decision.get_navigation_action()
            request = nav_action.get_request()
            url = request.get_uri()

            logger.info(f"Navigation to: {url}")

            # Check if URL contains an auth code (various possible patterns)
            code_patterns = [
                r'[?&]code=([^&]+)',
                r'[?&]authorization_code=([^&]+)',
                r'/on_login_success.*[?&]code=([^&]+)'
            ]

            for pattern in code_patterns:
                match = re.search(pattern, url)
                if match:
                    self.auth_code = match.group(1)
                    logger.info("Authorization code extracted from URL!")
                    self._show_success_and_close()
                    decision.ignore()
                    return True

            # Check for GOG's success page
            if "/on_login_success" in url:
                # Don't prevent navigation, but we'll extract the code in load_changed
                logger.info("GOG success page detected, will extract code after page loads")

        # For all other navigations, allow them
        return False

    def _handle_auth_code_extraction(self, webview, result):
        """Handle the auth code extraction result from JavaScript"""
        try:
            js_value = webview.evaluate_javascript_finish(result)
            if js_value and js_value.is_string():
                extracted_code = js_value.to_string()
                if extracted_code and extracted_code != "null":
                    self.auth_code = extracted_code
                    logger.info("Authorization code extracted via JavaScript!")
                    self._show_success_and_close()
                    return

            logger.warning("Could not extract authorization code from page content")

        except Exception as e:
            logger.error(f"Failed to extract auth code: {e}")

    def _show_success_and_close(self):
        """Show success message and close the window"""
        # Show success message
        success_html = """
        <html>
            <head><title>GOG Authentication Successful</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding-top: 50px;">
                <h1 style="color: #8A2BE2;">Authentication Successful!</h1>
                <p>You have successfully authenticated with GOG.</p>
                <p>You can close this window and return to the application.</p>
            </body>
        </html>
        """
        self.webview.load_html(success_html, "about:blank")

        # Close window after a short delay
        def delayed_close():
            self.destroy()
            Gtk.main_quit()
            return False

        GLib.timeout_add(2000, delayed_close)


def authenticate_gog():
    """
    Run the GOG OAuth authentication flow with WebKit and GTK 3.0

    Returns the authorization code or None if the flow was cancelled
    """
    # GOG Authentication constants - these are based on the C# implementation
    client_id = "46899977096215655"
    redirect_uri = "https://embed.gog.com/on_login_success?origin=client"

    # Build the OAuth URL based on GOG's login pattern
    # This follows the pattern used in the C# version where they get the login URL dynamically
    auth_url = f"https://login.gog.com/auth?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&layout=client2"

    logger.info(f"Starting GOG authentication with URL: {auth_url}")

    # Create the authentication window
    window = GogAuthWebViewWindow(auth_url, redirect_uri)
    window.show_all()  # GTK 3.0 style
    Gtk.main()

    return window.auth_code


if __name__ == "__main__":
    logger.info("Starting GOG OAuth authentication flow...")

    # Run authentication
    auth_code = authenticate_gog()

    if auth_code:
        logger.info("Authentication successful!")
        result = {"code": auth_code}
    else:
        logger.warning("Authentication failed or was cancelled.")
        result = {"error": "Authentication failed or was cancelled"}

    # Output the result as JSON to stdout
    print(json.dumps(result))