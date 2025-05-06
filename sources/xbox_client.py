import os
import json
import requests
import subprocess
import sys
import shlex
from pathlib import Path
from datetime import datetime


class XboxLibrary:
    """Class to handle Xbox authentication and library management"""

    # Xbox API constants
    CLIENT_ID = "38cd2fa8-66fd-4760-afb2-405eb65d5b0c"
    REDIRECT_URI = "https://login.live.com/oauth20_desktop.srf"
    SCOPE = "Xboxlive.signin Xboxlive.offline_access"

    def __init__(self, token_dir=None):
        """
        Initialize the Xbox Library with token storage paths

        Args:
            token_dir: Directory to store authentication tokens
                      If None, defaults to ~/.xbox_api_client
        """
        # Set up data directories
        if token_dir:
            self.data_dir = Path(token_dir)
        else:
            self.data_dir = os.path.join(os.path.expanduser("~"), ".xbox_api_client")

        # Create directory if it doesn't exist
        os.makedirs(self.data_dir, exist_ok=True)

        # Set up token paths
        self.live_tokens_path = os.path.join(self.data_dir, "login.json")
        self.xsts_tokens_path = os.path.join(self.data_dir, "xsts.json")

    def authenticate(self):
        """
        Initiate Xbox authentication flow

        Returns:
            bool: True if authentication succeeded, False otherwise
        """
        # Get the path to the auth helper script
        current_dir = Path(__file__).parent
        auth_helper_path = current_dir / "xbox_auth_helper.py"

        # Check if the helper script exists
        if not auth_helper_path.exists():
            print(f"Error: Authentication helper script not found at {auth_helper_path}")
            return False

        try:
            # Make sure the helper script is executable
            os.chmod(auth_helper_path, 0o755)

            # Run the authentication helper as a completely separate process
            # This ensures no GTK version conflicts
            cmd = [
                sys.executable,
                str(auth_helper_path),
                self.CLIENT_ID,
                self.REDIRECT_URI,
                self.SCOPE
            ]

            print("Starting authentication process in separate process...")

            # Use Popen instead of run so we can detach the process
            # This prevents the main app from waiting and becoming unresponsive
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                # Set start_new_session=True to completely detach the process
                start_new_session=True
                # Removed preexec_fn as it was causing issues
            )

            # Wait for the process to complete, but don't let it hang
            # the main application if it takes too long
            try:
                stdout, stderr = process.communicate(timeout=5*60)  # 5 minute timeout
                exit_code = process.returncode

                if exit_code != 0:
                    print(f"Authentication process failed with exit code {exit_code}")
                    print(f"Error: {stderr}")
                    return False

                # Parse the JSON output from the helper script
                try:
                    # Remove any extra text before the JSON
                    json_start = stdout.find('{')
                    if json_start >= 0:
                        json_str = stdout[json_start:]
                        auth_result = json.loads(json_str)
                        if 'error' in auth_result:
                            print(f"Authentication error: {auth_result['error']}")
                            return False
                        elif 'code' in auth_result:
                            auth_code = auth_result['code']
                        else:
                            print("Unexpected authentication result")
                            return False
                    else:
                        print("No JSON found in authentication output")
                        print(f"Output: {stdout}")
                        return False
                except json.JSONDecodeError as e:
                    print(f"Failed to parse authentication result: {e}")
                    print(f"Output: {stdout}")
                    print(f"Error: {stderr}")
                    return False

            except subprocess.TimeoutExpired:
                # Process took too long, the user probably closed the window
                print("Authentication timeout - process took too long")
                process.terminate()
                try:
                    process.wait(timeout=5)  # Give it 5 seconds to terminate gracefully
                except subprocess.TimeoutExpired:
                    process.kill()  # Force kill if it doesn't terminate
                return False

        except Exception as e:
            print(f"Error running authentication: {e}")
            return False

        try:
            # Check if we got an authorization code
            if not auth_code:
                print("Authentication failed or was cancelled.")
                return False
        except UnboundLocalError:
            # Handle case where auth_code was never set
            print("Authentication process did not complete properly")
            return False

        # Exchange the code for tokens
        try:
            print("Getting OAuth tokens...")
            # Get OAuth tokens
            token_response = self._request_oauth_token(auth_code)
            print("OAuth tokens received successfully")

            # Store the Live tokens
            live_login_data = {
                "AccessToken": token_response["access_token"],
                "RefreshToken": token_response["refresh_token"],
                "ExpiresIn": token_response["expires_in"],
                "CreationDate": datetime.now().isoformat(),
                "UserId": token_response["user_id"],
                "TokenType": token_response["token_type"]
            }

            print("Getting Xbox XSTS tokens...")
            # Get Xbox XSTS tokens
            xsts_tokens = self._authenticate_with_xbox(live_login_data["AccessToken"])
            print("XSTS tokens received successfully")

            # Save tokens to files
            print("Saving tokens to files...")

            with open(self.live_tokens_path, 'w') as f:
                json.dump(live_login_data, f, indent=4)

            with open(self.xsts_tokens_path, 'w') as f:
                json.dump(xsts_tokens, f, indent=4)

            # Set secure permissions (0600) for token files
            os.chmod(self.live_tokens_path, 0o600)
            os.chmod(self.xsts_tokens_path, 0o600)

            print("Tokens saved successfully")
            return True

        except Exception as e:
            print(f"Error during authentication: {e}")
            return False

    def is_authenticated(self, try_refresh=True):
        """
        Check if the user is authenticated and refresh tokens if needed

        Args:
            try_refresh: Whether to try refreshing expired tokens

        Returns:
            bool: True if authenticated, False otherwise
        """
        # Check if tokens exist
        if not os.path.exists(self.xsts_tokens_path) or not os.path.exists(self.live_tokens_path):
            return False

        try:
            # Load the XSTS tokens
            with open(self.xsts_tokens_path, 'r') as f:
                tokens = json.load(f)

            # Set up headers
            headers = {
                'x-xbl-contract-version': '2',
                'Authorization': f'XBL3.0 x={tokens["DisplayClaims"]["xui"][0]["uhs"]};{tokens["Token"]}',
                'Accept-Language': 'en-US'
            }

            # Test token validity with a profile request
            request_data = {
                "settings": ["GameDisplayName"],
                "userIds": [int(tokens["DisplayClaims"]["xui"][0]["xid"])]
            }

            response = requests.post(
                'https://profile.xboxlive.com/users/batch/profile/settings',
                json=request_data,
                headers=headers
            )

            # If the request is successful, tokens are valid
            if response.status_code == 200:
                return True

            # If tokens have expired and refresh is requested
            if try_refresh and response.status_code in [401, 403]:
                print("Authentication expired. Refreshing tokens...")
                return self._refresh_tokens()

            return False

        except Exception as e:
            print(f"Error checking authentication: {e}")
            if try_refresh:
                return self._refresh_tokens()
            return False

    def get_game_library(self):
        """
        Get the user's Xbox game library

        Returns:
            list: List of game objects from Xbox API
        """
        # Ensure authenticated, try to refresh tokens if needed
        if not self.is_authenticated():
            raise Exception("User is not authenticated and token refresh failed")

        # Load the XSTS tokens
        with open(self.xsts_tokens_path, 'r') as f:
            tokens = json.load(f)

        # Set up the request headers
        headers = {
            'x-xbl-contract-version': '2',
            'Authorization': f'XBL3.0 x={tokens["DisplayClaims"]["xui"][0]["uhs"]};{tokens["Token"]}',
            'Accept-Language': 'en-US'
        }

        print("Fetching Xbox title history...")

        # Make the request to get the title history
        response = requests.get(
            f'https://titlehub.xboxlive.com/users/xuid({tokens["DisplayClaims"]["xui"][0]["xid"]})/titles/titlehistory/decoration/detail',
            headers=headers
        )

        response.raise_for_status()
        data = response.json()

        # Get the titles
        titles = data.get('titles', [])
        print(f"Retrieved {len(titles)} titles from Xbox")

        # Get playtime for all titles
        if titles:
            try:
                print("Fetching playtime data...")
                # Extract title IDs
                title_ids = [title.get('titleId') for title in titles if title.get('titleId')]

                # Get playtime data
                playtime_stats = self._get_user_stats_minutes_played(title_ids)

                # Add playtime data to titles
                playtime_dict = {stat.get('titleid'): stat.get('value') for stat in playtime_stats}
                for title in titles:
                    title_id = title.get('titleId')
                    if title_id in playtime_dict:
                        title['minutesPlayed'] = playtime_dict[title_id]

                print(f"Added playtime data for {len(playtime_stats)} titles")
            except Exception as e:
                print(f"Error fetching playtime data: {e}")

        # Save library to file for convenience
        library_file = os.path.join(self.data_dir, "game_library.json")
        with open(library_file, 'w') as f:
            json.dump(titles, f, indent=2)

        return titles

    def _request_oauth_token(self, auth_code):
        """Exchange authorization code for OAuth tokens (internal method)"""
        request_data = {
            'grant_type': 'authorization_code',
            'code': auth_code,
            'scope': self.SCOPE,
            'client_id': self.CLIENT_ID,
            'redirect_uri': self.REDIRECT_URI
        }

        response = requests.post(
            'https://login.live.com/oauth20_token.srf',
            data=request_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        response.raise_for_status()
        return response.json()

    def _authenticate_with_xbox(self, access_token):
        """Get Xbox authentication tokens (internal method)"""
        # First authenticate with Xbox Live
        auth_request_data = {
            "RelyingParty": "http://auth.xboxlive.com",
            "TokenType": "JWT",
            "Properties": {
                "AuthMethod": "RPS",
                "SiteName": "user.auth.xboxlive.com",
                "RpsTicket": f"d={access_token}"
            }
        }

        auth_response = requests.post(
            'https://user.auth.xboxlive.com/user/authenticate',
            json=auth_request_data,
            headers={'x-xbl-contract-version': '1'}
        )

        auth_response.raise_for_status()
        auth_tokens = auth_response.json()

        # Then authorize with XSTS
        auth_request_data = {
            "RelyingParty": "http://xboxlive.com",
            "TokenType": "JWT",
            "Properties": {
                "SandboxId": "RETAIL",
                "UserTokens": [auth_tokens["Token"]]
            }
        }

        auth_response = requests.post(
            'https://xsts.auth.xboxlive.com/xsts/authorize',
            json=auth_request_data,
            headers={'x-xbl-contract-version': '1'}
        )

        auth_response.raise_for_status()
        return auth_response.json()

    def _refresh_tokens(self):
        """Refresh authentication tokens (internal method)"""
        # Check if we have live tokens
        if not os.path.exists(self.live_tokens_path):
            print("No refresh token available. Need manual re-authentication.")
            return False

        try:
            # Load live tokens
            with open(self.live_tokens_path, 'r') as f:
                live_tokens = json.load(f)

            # Ensure we have a refresh token
            if 'RefreshToken' not in live_tokens:
                print("No refresh token found. Need manual re-authentication.")
                return False

            # Use refresh token to get new access token
            refresh_token = live_tokens['RefreshToken']

            # Prepare request
            request_data = {
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
                'scope': self.SCOPE,
                'client_id': self.CLIENT_ID,
                'redirect_uri': self.REDIRECT_URI
            }

            # Request new tokens
            print("Requesting new OAuth tokens...")
            response = requests.post(
                'https://login.live.com/oauth20_token.srf',
                data=request_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            )

            if response.status_code != 200:
                print(f"Token refresh failed: {response.status_code}")
                return False

            # Extract new tokens
            token_response = response.json()

            # Update live tokens
            live_login_data = {
                "AccessToken": token_response["access_token"],
                "RefreshToken": token_response["refresh_token"],
                "ExpiresIn": token_response["expires_in"],
                "CreationDate": datetime.now().isoformat(),
                "UserId": token_response["user_id"],
                "TokenType": token_response["token_type"]
            }

            # Get new Xbox XSTS tokens
            print("Authenticating with Xbox Live...")
            xsts_tokens = self._authenticate_with_xbox(live_login_data["AccessToken"])

            # Save updated tokens
            with open(self.live_tokens_path, 'w') as f:
                json.dump(live_login_data, f, indent=4)

            with open(self.xsts_tokens_path, 'w') as f:
                json.dump(xsts_tokens, f, indent=4)

            # Ensure permissions are secure
            os.chmod(self.live_tokens_path, 0o600)
            os.chmod(self.xsts_tokens_path, 0o600)

            print("Token refresh successful!")
            return True

        except Exception as e:
            print(f"Error refreshing tokens: {e}")
            return False

    def _get_user_stats_minutes_played(self, title_ids):
        """Get playtime statistics for a list of titles (internal method)"""
        # Ensure authenticated with automatic token refresh
        if not self.is_authenticated():
            raise Exception("User is not authenticated and token refresh failed")

        # Load the XSTS tokens
        with open(self.xsts_tokens_path, 'r') as f:
            tokens = json.load(f)

        # Set up headers
        headers = {
            'x-xbl-contract-version': '2',
            'Authorization': f'XBL3.0 x={tokens["DisplayClaims"]["xui"][0]["uhs"]};{tokens["Token"]}',
            'Accept-Language': 'en-US'
        }

        # Prepare the request data
        xuid = tokens["DisplayClaims"]["xui"][0]["xid"]
        request_data = {
            "arrangebyfield": "xuid",
            "stats": [
                {
                    "name": "MinutesPlayed",
                    "titleid": title_id
                } for title_id in title_ids
            ],
            "xuids": [xuid]
        }

        # Make the request
        response = requests.post(
            'https://userstats.xboxlive.com/batch',
            json=request_data,
            headers=headers
        )

        response.raise_for_status()
        data = response.json()

        # Extract stats
        stats_collection = data.get('statlistscollection', [])
        if stats_collection and len(stats_collection) > 0:
            return stats_collection[0].get('stats', [])

        return []

    def group_games_by_platform(self, titles):
        """
        Group games by platform type

        Args:
            titles: List of games from the API

        Returns:
            dict: Dictionary with keys 'pc', 'console', 'cross_platform', 'total'
        """
        pc_games = []
        console_games = []
        cross_platform_games = []

        for title in titles:
            if title.get('type') != 'Game':
                continue

            devices = title.get('devices', [])

            if 'PC' in devices and any(device in devices for device in ['Xbox360', 'XboxOne', 'XboxSeries']):
                cross_platform_games.append(title)
            elif 'PC' in devices:
                pc_games.append(title)
            elif any(device in devices for device in ['Xbox360', 'XboxOne', 'XboxSeries']):
                console_games.append(title)

        total_games = len(pc_games) + len(console_games) + len(cross_platform_games)

        return {
            'pc': pc_games,
            'console': console_games,
            'cross_platform': cross_platform_games,
            'total': total_games
        }


# Example usage for direct script execution
class XboxConsoleApp:
    """
    Console application for running the Xbox client directly
    This is used when the module is run as a script
    """
    def __init__(self):
        self.xbox = XboxLibrary()

    def run(self):
        """Run the Xbox client as a standalone application"""
        print("Xbox Authentication and Library Demo")
        print("===================================")

        # For the command-line app, we need to make sure the helper exists
        # and it uses GTK 3.0 for WebKit compatibility
        helper_path = Path(__file__).parent / "xbox_auth_helper.py"
        if not helper_path.exists():
            print(f"Error: Authentication helper script not found at {helper_path}")
            print("Please ensure the helper script is properly installed.")
            sys.exit(1)

        # Check if authenticated
        auth_status = self.xbox.is_authenticated()
        print(f"Authentication status: {'✓ Authenticated' if auth_status else '✗ Not authenticated'}")

        # Authenticate if needed or requested
        if not auth_status or input("Re-authenticate anyway? (y/n): ").lower() == 'y':
            print("\nStarting authentication...")
            if not self.xbox.authenticate():
                print("\n✗ Authentication failed.")
                sys.exit(1)
            print("\n✓ Authentication successful!")
            print(f"Tokens saved to {self.xbox.data_dir}")

        # Fetch and display game library
        try:
            print("\nFetching game library...")
            titles = self.xbox.get_game_library()

            # Group and display games by platform
            game_groups = self.xbox.group_games_by_platform(titles)

            print(f"\nFound {game_groups['total']} games in your Xbox library:")

            # Display PC games
            if game_groups['pc']:
                print(f"\n=== PC Games ({len(game_groups['pc'])}) ===")
                for i, game in enumerate(sorted(game_groups['pc'], key=lambda g: g.get('name', '')), 1):
                    if i > 5:
                        break
                    minutes = game.get('minutesPlayed')
                    playtime = f" - {minutes} minutes played" if minutes else ""
                    print(f"{i}. {game.get('name', 'Unknown')}{playtime}")

            # Display console games
            if game_groups['console']:
                print(f"\n=== Console Games ({len(game_groups['console'])}) ===")
                for i, game in enumerate(sorted(game_groups['console'], key=lambda g: g.get('name', '')), 1):
                    if i > 5:
                        break
                    devices = ", ".join(game.get('devices', []))
                    minutes = game.get('minutesPlayed')
                    playtime = f" - {minutes} minutes played" if minutes else ""
                    print(f"{i}. {game.get('name', 'Unknown')} ({devices}){playtime}")

            # Display cross-platform games
            if game_groups['cross_platform']:
                print(f"\n=== Cross-Platform Games ({len(game_groups['cross_platform'])}) ===")
                for i, game in enumerate(sorted(game_groups['cross_platform'], key=lambda g: g.get('name', '')), 1):
                    if i > 5:
                        break
                    minutes = game.get('minutesPlayed')
                    playtime = f" - {minutes} minutes played" if minutes else ""
                    print(f"{i}. {game.get('name', 'Unknown')}{playtime}")

            print(f"\nTotal: {game_groups['total']} games found")
            print(f"\nComplete game library saved to: {os.path.join(self.xbox.data_dir, 'game_library.json')}")

        except Exception as e:
            print(f"\nError: {e}")


if __name__ == "__main__":
    # Run the app when script is executed directly
    app = XboxConsoleApp()
    app.run()
