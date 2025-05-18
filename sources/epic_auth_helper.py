#!/usr/bin/env python3
"""
Epic Games authentication helper script that uses WebKit2 with GTK 3.0.

This script is designed to be run as a subprocess by the main application
to handle the WebKit-based OAuth authentication flow without causing
GTK version conflicts with the main application (which uses GTK 4).

Usage:
    python3 epic_auth_helper.py

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


class EpicAuthWebViewWindow(Gtk.Window):
    def __init__(self, login_url, redirect_pattern):
        super().__init__(title="Epic Games Authentication")
        self.redirect_pattern = redirect_pattern
        self.auth_code = None
        self.has_redirected = False  # Track if we've attempted auth redirect

        # Create WebView with specific user agent to handle Epic's requirements
        self.webview = WebKit2.WebView()

        # Set user agent (important for Epic authentication to work properly)
        user_agent = "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Vivaldi/7.1.3570.39"
        settings = self.webview.get_settings()
        settings.set_property("user-agent", user_agent)

        # Connect to navigation events
        self.webview.connect("decide-policy", self.on_decide_policy)
        self.webview.connect("load-changed", self.on_load_changed)

        # Add to window (GTK 3.0 style)
        self.add(self.webview)
        self.set_default_size(900, 700)
        self.connect("destroy", Gtk.main_quit)

        # Load the login URL
        self.webview.load_uri(login_url)

    def on_load_changed(self, webview, load_event):
        """Handle page load events"""
        try:
            # If page finished loading
            if load_event == WebKit2.LoadEvent.FINISHED:
                # Get the current URL
                url = webview.get_uri()
                logger.info(f"Page loaded: {url}")

                # If we see the Epic account page, redirect to authorization
                if "/account/personal" in url and not self.has_redirected:
                    logger.info("Detected successful login, redirecting to authorization")
                    self.has_redirected = True
                    # Add a small delay before redirecting
                    GLib.timeout_add(500, lambda: self.webview.load_uri(self.redirect_pattern))

                # If we're on a page that might have the auth code
                elif "/id/api/redirect" in url:
                    logger.info("Authorization page loaded, extracting content")

                    # Extract content via JavaScript
                    script = """
                    (function() {
                        // Try to get content from pre tag first (Epic often puts JSON in pre tags)
                        var preElement = document.querySelector('pre');
                        if (preElement && preElement.textContent) {
                            return preElement.textContent;
                        }

                        // Fallback to full page text
                        return document.body.innerText || document.body.textContent;
                    })();
                    """

                    self.webview.evaluate_javascript(script, -1, None, None, None, self._handle_page_content)
        except Exception as e:
            logger.error(f"Error in load_changed handler: {e}")

    def on_decide_policy(self, webview, decision, decision_type):
        """Handle navigation events to capture the authorization code"""
        if decision_type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            nav_action = decision.get_navigation_action()
            request = nav_action.get_request()
            url = request.get_uri()

            logger.info(f"Navigation to: {url}")

            # Look for the authorization code in the URL
            if "code=" in url or "authorizationCode=" in url:
                logger.info("Found authorization code in URL")

                # Parse URL to extract authorization code
                parsed_url = urlparse(url)
                query_params = parse_qs(parsed_url.query)

                if 'code' in query_params:
                    self.auth_code = query_params['code'][0]
                    logger.info("Authorization code extracted from URL parameters!")
                    self._show_success_and_close()
                    return True

                elif 'authorizationCode' in query_params:
                    self.auth_code = query_params['authorizationCode'][0]
                    logger.info("Authorization code extracted from URL parameters!")
                    self._show_success_and_close()
                    return True

        # For all other navigations, allow them
        return False

    def _handle_page_content(self, webview, result):
        """Handle the page content from the authorization redirect"""
        try:
            js_value = webview.evaluate_javascript_finish(result)
            if js_value and js_value.is_string():
                content = js_value.to_string()
                logger.info(f"Page content extracted, length: {len(content)}")

                # First try: Look for JSON data that contains authorizationCode
                if "{" in content and "}" in content:
                    try:
                        # Extract the JSON part (there might be other text)
                        json_start = content.find('{')
                        json_end = content.rfind('}') + 1
                        json_content = content[json_start:json_end]

                        response_data = json.loads(json_content)
                        if "authorizationCode" in response_data:
                            self.auth_code = response_data["authorizationCode"]
                            logger.info("Authorization code extracted from JSON!")
                            self._show_success_and_close()
                            return
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse JSON, trying regex")

                # Second try: Use regex to find the authorization code
                import re
                auth_code_match = re.search(r'"authorizationCode"\s*:\s*"([^"]+)"', content)
                if auth_code_match:
                    self.auth_code = auth_code_match.group(1)
                    logger.info("Authorization code extracted with regex!")
                    self._show_success_and_close()
                    return

                # If we reach here, we couldn't extract the code
                logger.warning("Could not extract authorization code from content")

        except Exception as e:
            logger.error(f"Failed to parse page content: {e}")
            if 'content' in locals():
                content_preview = content[:100] + "..." if len(content) > 100 else content
                logger.debug(f"Content preview: {content_preview}")

    def _show_success_and_close(self):
        """Show success message and close the window"""
        # Show success message
        success_html = """
        <html>
            <head><title>Epic Games Authentication Successful</title></head>
            <body style="font-family: Arial, sans-serif; text-align: center; padding-top: 50px;">
                <h1 style="color: #0074E4;">Authentication Successful!</h1>
                <p>You have successfully authenticated with Epic Games.</p>
                <p>You can close this window and return to the application.</p>
            </body>
        </html>
        """
        self.webview.load_html(success_html, "about:blank")

        # Close window after a short delay
        GLib.timeout_add(2000, lambda: self.destroy() or Gtk.main_quit() or False)


def authenticate_epic():
    """
    Run the Epic Games OAuth authentication flow with WebKit and GTK 3.0

    Returns the authorization code or None if the flow was cancelled
    """
    # Epic Games Auth constants
    auth_encoded_string = "MzRhMDJjZjhmNDQxNGUyOWIxNTkyMTg3NmRhMzZmOWE6ZGFhZmJjY2M3Mzc3NDUwMzlkZmZlNTNkOTRmYzc2Y2Y="
    login_url = "https://www.epicgames.com/id/login"
    auth_code_url = "https://www.epicgames.com/id/api/redirect?clientId=34a02cf8f4414e29b15921876da36f9a&responseType=code"

    # Create the authentication window
    window = EpicAuthWebViewWindow(login_url, auth_code_url)
    window.show_all()  # GTK 3.0 style
    Gtk.main()

    return window.auth_code


if __name__ == "__main__":
    logger.info("Starting Epic OAuth authentication flow...")

    # Run authentication
    auth_code = authenticate_epic()

    if auth_code:
        logger.info("Authentication successful!")
        result = {"code": auth_code}
    else:
        logger.warning("Authentication failed or was cancelled.")
        result = {"error": "Authentication failed or was cancelled"}

    # Output the result as JSON to stdout
    print(json.dumps(result))