#!/usr/bin/env python3
"""
Xbox authentication helper script that uses WebKit2 with GTK 3.0.

This script is designed to be run as a subprocess by the main application
to handle the WebKit-based OAuth authentication flow without causing
GTK version conflicts with the main application (which uses GTK 4).

Usage:
    python3 xbox_auth_helper.py <client_id> <redirect_uri> <scope>

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
from urllib.parse import urlparse, parse_qs

# Important: This must be run in a separate process from any GTK 4 application
# Use GTK 3.0 specifically for WebKit2 compatibility
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, WebKit2, GLib


class XboxAuthWebViewWindow(Gtk.Window):
    def __init__(self, auth_url, redirect_uri):
        super().__init__(title="Xbox Authentication")
        self.redirect_uri = redirect_uri
        self.auth_code = None

        # Create WebView
        self.webview = WebKit2.WebView()
        self.webview.connect("decide-policy", self.on_decide_policy)
        self.webview.load_uri(auth_url)

        # Add WebView to window (GTK 3.0 style)
        self.add(self.webview)
        self.set_default_size(800, 600)
        self.connect("destroy", Gtk.main_quit)

    def on_decide_policy(self, webview, decision, decision_type):
        if decision_type == WebKit2.PolicyDecisionType.NAVIGATION_ACTION:
            nav_action = decision.get_navigation_action()
            request = nav_action.get_request()
            url = request.get_uri()

            # Check if the URL contains the code parameter for OAuth
            if "oauth20_desktop.srf" in url and "code=" in url:
                # Extract the code
                parsed_url = urlparse(url)
                query_params = parse_qs(parsed_url.query)

                if 'code' in query_params:
                    self.auth_code = query_params['code'][0]
                    # Send debug output to stderr instead of stdout
                    print(f"Authorization code extracted!", file=sys.stderr)

                    # Show success message
                    success_html = """
                    <html>
                        <head><title>Xbox Authentication Successful</title></head>
                        <body style="font-family: Arial, sans-serif; text-align: center; padding-top: 50px;">
                            <h1 style="color: #107C10;">Authentication Successful!</h1>
                            <p>You have successfully authenticated with Xbox Live.</p>
                            <p>You can close this window and return to the application.</p>
                        </body>
                    </html>
                    """
                    webview.load_html(success_html, "about:blank")

                    # Close window after a short delay using GTK's timeout
                    def delayed_close():
                        self.destroy()
                        Gtk.main_quit()
                        return False  # Don't repeat the timeout

                    # Schedule the window to close in 2 seconds
                    GLib.timeout_add(2000, delayed_close)

                    # Prevent following the redirect
                    decision.ignore()
                    return True

        # For all other navigations, allow them
        return False


def authenticate_xbox(client_id, redirect_uri, scope):
    """
    Run the OAuth authentication flow with WebKit and GTK 3.0

    Returns the authorization code or None if the flow was cancelled
    """
    # Build the OAuth URL
    query_params = {
        'client_id': client_id,
        'response_type': 'code',
        'approval_prompt': 'auto',
        'scope': scope,
        'redirect_uri': redirect_uri
    }
    query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
    auth_url = f"https://login.live.com/oauth20_authorize.srf?{query_string}"

    # Open the authentication window
    window = XboxAuthWebViewWindow(auth_url, redirect_uri)
    window.show_all()  # GTK 3.0 style
    Gtk.main()

    return window.auth_code


if __name__ == "__main__":
    # Redirect all debug output to stderr
    def debug_print(*args, **kwargs):
        kwargs['file'] = sys.stderr
        print(*args, **kwargs)

    # Get parameters from command line
    if len(sys.argv) < 4:
        result = {"error": "Missing parameters: client_id, redirect_uri, scope"}
    else:
        client_id = sys.argv[1]
        redirect_uri = sys.argv[2]
        scope = sys.argv[3]

        debug_print("Starting OAuth authentication flow...")

        # Run authentication
        auth_code = authenticate_xbox(client_id, redirect_uri, scope)

        if auth_code:
            debug_print("Authentication successful!")
            result = {"code": auth_code}
        else:
            debug_print("Authentication failed or was cancelled.")
            result = {"error": "Authentication failed or was cancelled"}

    # Output the result as JSON to stdout (with no extra output)
    print(json.dumps(result))