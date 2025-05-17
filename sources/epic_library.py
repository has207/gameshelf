#!/usr/bin/env python3
"""
Epic Games Library Client

This script provides functionality to authenticate with the Epic Games Store
and retrieve a user's owned games. It runs authentication in a separate process
to avoid GTK version conflicts.
"""

import os
import sys
import json
import time
import subprocess
import requests
import logging
import shlex
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class EpicLibraryClient:
    """Client for Epic Games Store authentication and game library retrieval"""

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize the Epic client

        Args:
            data_dir: Directory to store authentication tokens and cache
                     If None, defaults to ~/.epic_library
        """
        # Set up data directory
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path.home() / ".epic_library"

        # Create directory if it doesn't exist
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Set up token and cache paths
        self.tokens_path = self.data_dir / "tokens.json"
        self.catalog_cache_dir = self.data_dir / "catalogcache"
        self.catalog_cache_dir.mkdir(exist_ok=True)

        # Authentication constants
        self.auth_encoded_string = "MzRhMDJjZjhmNDQxNGUyOWIxNTkyMTg3NmRhMzZmOWE6ZGFhZmJjY2M3Mzc3NDUwMzlkZmZlNTNkOTRmYzc2Y2Y="
        self.client_id = "34a02cf8f4414e29b15921876da36f9a"  # Epic Games client ID

        # API endpoints
        # These are the default values, but they should be updated from the Epic portal configuration when available
        self.oauth_url = "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/token"
        self.account_url = "https://account-public-service-prod03.ol.epicgames.com/account/api/public/account/"
        self.assets_url = "https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/public/assets/Windows?label=Live"
        self.catalog_url = "https://catalog-public-service-prod06.ol.epicgames.com/catalog/api/shared/namespace/"
        self.playtime_url = "https://library-service.live.use1a.on.epicgames.com/library/api/public/playtime/account/{}/all"

        # Try to load API endpoints from Epic's config file
        self._load_epic_portal_config()

    def _load_epic_portal_config(self):
        """
        Load API endpoints from Epic's portal configuration file
        This attempts to mimic the behavior in the C# EpicAccountClient constructor
        """
        # Find Epic Launcher installation directory (simplified)
        epic_install_paths = [
            os.path.expandvars(r"%ProgramFiles%\Epic Games"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Epic Games"),
            os.path.expandvars(r"C:\Program Files\Epic Games"),
            os.path.expandvars(r"C:\Program Files (x86)\Epic Games")
        ]

        portal_config_path = None
        for path in epic_install_paths:
            potential_path = os.path.join(path, "Launcher", "Portal", "Config", "DefaultPortalRegions.ini")
            if os.path.exists(potential_path):
                portal_config_path = potential_path
                break

        if not portal_config_path:
            logger.info("Epic portal config not found, using default API endpoints")
            return

        try:
            # Parse the INI file
            from configparser import ConfigParser
            config = ConfigParser()
            # INI files from Epic need a header to be properly parsed with ConfigParser
            with open(portal_config_path, 'r') as f:
                ini_content = f.read()

            # Add headers for each section found
            ini_content_with_headers = ini_content
            for section in ["Portal.OnlineSubsystemMcp.OnlineIdentityMcp Prod",
                            "Portal.OnlineSubsystemMcp.BaseServiceMcp Prod",
                            "Portal.OnlineSubsystemMcp.OnlineCatalogServiceMcp Prod",
                            "Portal.OnlineSubsystemMcp.OnlineLibraryServiceMcp Prod"]:
                if section in ini_content and not f"[{section}]" in ini_content:
                    ini_content_with_headers = ini_content_with_headers.replace(
                        section, f"[{section}]", 1
                    )

            config.read_string(ini_content_with_headers)

            # Update API endpoints from config
            identity_domain = config["Portal.OnlineSubsystemMcp.OnlineIdentityMcp Prod"]["Domain"].rstrip('/')
            base_domain = config["Portal.OnlineSubsystemMcp.BaseServiceMcp Prod"]["Domain"].rstrip('/')
            catalog_domain = config["Portal.OnlineSubsystemMcp.OnlineCatalogServiceMcp Prod"]["Domain"].rstrip('/')
            library_domain = config["Portal.OnlineSubsystemMcp.OnlineLibraryServiceMcp Prod"]["Domain"].rstrip('/')

            self.oauth_url = f"https://{identity_domain}/account/api/oauth/token"
            self.account_url = f"https://{identity_domain}/account/api/public/account/"
            self.assets_url = f"https://{base_domain}/launcher/api/public/assets/Windows?label=Live"
            self.catalog_url = f"https://{catalog_domain}/catalog/api/shared/namespace/"
            self.playtime_url = f"https://{library_domain}/library/api/public/playtime/account/{{}}/all"

            logger.info("Loaded API endpoints from Epic portal configuration")

        except Exception as e:
            logger.error(f"Failed to parse Epic portal config: {e}")
            # Fallback to default endpoints

    def authenticate(self):
        """
        Initiate Epic authentication flow using GTK WebView in a separate process

        Returns:
            bool: True if authentication succeeded, False otherwise
        """
        logger.info("Starting Epic authentication process...")

        # Get the path to the auth helper script
        current_dir = Path(__file__).parent
        auth_helper_path = current_dir / "epic_auth_helper.py"

        # Check if the helper script exists
        if not auth_helper_path.exists():
            logger.error(f"Error: Authentication helper script not found at {auth_helper_path}")
            return False

        try:
            # Make sure the helper script is executable
            os.chmod(auth_helper_path, 0o755)

            # Run the authentication helper as a completely separate process
            # This ensures no GTK version conflicts
            cmd = [
                sys.executable,
                str(auth_helper_path)
            ]

            logger.info("Starting authentication process in separate process...")

            # Use Popen instead of run so we can detach the process
            # This prevents the main app from waiting and becoming unresponsive
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                # Set start_new_session=True to completely detach the process
                start_new_session=True
            )

            # Wait for the process to complete, but don't let it hang
            # the main application if it takes too long
            try:
                stdout, stderr = process.communicate(timeout=5*60)  # 5 minute timeout
                exit_code = process.returncode

                if exit_code != 0:
                    logger.error(f"Authentication process failed with exit code {exit_code}")
                    logger.error(f"Error: {stderr}")
                    return False

                # Parse the JSON output from the helper script
                try:
                    # Remove any extra text before the JSON
                    json_start = stdout.find('{')
                    if json_start >= 0:
                        json_str = stdout[json_start:]
                        auth_result = json.loads(json_str)
                        if 'error' in auth_result:
                            logger.error(f"Authentication error: {auth_result['error']}")
                            return False
                        elif 'code' in auth_result:
                            auth_code = auth_result['code']
                        else:
                            logger.error("Unexpected authentication result")
                            return False
                    else:
                        logger.error("No JSON found in authentication output")
                        logger.debug(f"Output: {stdout}")
                        return False
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse authentication result: {e}")
                    logger.debug(f"Output: {stdout}")
                    logger.debug(f"Error: {stderr}")
                    return False

            except subprocess.TimeoutExpired:
                # Process took too long, the user probably closed the window
                logger.error("Authentication timeout - process took too long")
                process.terminate()
                try:
                    process.wait(timeout=5)  # Give it 5 seconds to terminate gracefully
                except subprocess.TimeoutExpired:
                    process.kill()  # Force kill if it doesn't terminate
                return False

        except Exception as e:
            logger.error(f"Error running authentication: {e}")
            return False

        try:
            # Check if we got an authorization code
            if not auth_code:
                logger.error("Authentication failed or was cancelled.")
                return False
        except UnboundLocalError:
            # Handle case where auth_code was never set
            logger.error("Authentication process did not complete properly")
            return False

        # Exchange the code for tokens
        return self._authenticate_with_auth_code(auth_code)

    def _authenticate_with_auth_code(self, auth_code: str) -> bool:
        """
        Exchange an authorization code for OAuth tokens

        Args:
            auth_code: The authorization code from the login process

        Returns:
            bool: True if token exchange succeeded, False otherwise
        """
        try:
            # Set up the request headers
            headers = {
                "Authorization": f"basic {self.auth_encoded_string}",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            # Set up the request data
            data = {
                "grant_type": "authorization_code",
                "code": auth_code,
                "token_type": "eg1"
            }

            # Make the token request
            response = requests.post(self.oauth_url, headers=headers, data=data)
            response.raise_for_status()

            # Save the tokens
            with open(self.tokens_path, 'w') as f:
                json.dump(response.json(), f, indent=4)

            # Set secure permissions for token file
            os.chmod(self.tokens_path, 0o600)

            logger.info("Authentication successful, tokens saved")
            return True

        except Exception as e:
            logger.error(f"Failed to exchange auth code for tokens: {e}")
            return False

    def is_authenticated(self) -> bool:
        """
        Check if the user is authenticated and tokens are valid

        Returns:
            bool: True if authenticated with valid tokens, False otherwise
        """
        tokens = self._load_tokens()
        if not tokens:
            return False

        try:
            # Try to use the token to access account info
            account_id = tokens.get("account_id")
            if not account_id:
                return False

            # Make a request to verify the token is valid
            headers = {
                "Authorization": f"{tokens['token_type']} {tokens['access_token']}"
            }

            response = requests.get(f"{self.account_url}{account_id}", headers=headers)

            # Check if the response is valid
            if response.status_code == 200:
                account_data = response.json()
                return account_data.get("id") == account_id

            # If we got an authentication error, try to refresh the token
            if response.status_code in [401, 403]:
                return self._refresh_tokens(tokens)

            return False

        except Exception as e:
            logger.error(f"Error checking authentication: {e}")
            # Try to refresh the token if there was an error
            try:
                return self._refresh_tokens(tokens)
            except Exception as refresh_error:
                logger.error(f"Failed to refresh tokens: {refresh_error}")
                return False

    def _refresh_tokens(self, tokens: Dict[str, Any]) -> bool:
        """
        Refresh expired authentication tokens

        Args:
            tokens: The current tokens dictionary

        Returns:
            bool: True if token refresh succeeded, False otherwise
        """
        try:
            refresh_token = tokens.get("refresh_token")
            if not refresh_token:
                return False

            # Set up the request headers
            headers = {
                "Authorization": f"basic {self.auth_encoded_string}",
                "Content-Type": "application/x-www-form-urlencoded"
            }

            # Set up the request data
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "token_type": "eg1"
            }

            # Make the token request
            response = requests.post(self.oauth_url, headers=headers, data=data)
            response.raise_for_status()

            # Save the new tokens
            with open(self.tokens_path, 'w') as f:
                json.dump(response.json(), f, indent=4)

            logger.info("Successfully refreshed authentication tokens")
            return True

        except Exception as e:
            logger.error(f"Failed to refresh tokens: {e}")
            return False

    def _load_tokens(self) -> Optional[Dict[str, Any]]:
        """
        Load authentication tokens from the token file

        Returns:
            dict: Dictionary of token data or None if not found/valid
        """
        if not os.path.exists(self.tokens_path):
            return None

        try:
            with open(self.tokens_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load saved tokens: {e}")
            return None

    def get_owned_games(self, show_progress=True, skip_catalog=False, optimize_catalog=False) -> List[Dict[str, Any]]:
        """
        Get all games owned by the authenticated user

        Args:
            show_progress: Whether to display progress information
            skip_catalog: Skip fetching detailed catalog data to speed up the process
            optimize_catalog: Use batch catalog requests instead of individual ones

        Returns:
            list: List of game dictionaries with metadata

        Raises:
            Exception: If the user is not authenticated
        """
        if not self.is_authenticated():
            raise Exception("User is not authenticated. Please run login command first.")

        owned_games = []
        tokens = self._load_tokens()

        # Step 1: Get list of assets (owned games)
        logger.info("Fetching owned games from Epic...")
        assets = self._get_assets()
        if not assets:
            logger.warning("No assets found in Epic account")
            return owned_games

        # Step 2: Get playtime data
        logger.info("Fetching playtime data...")
        playtime_items = self._get_playtime_items()
        playtime_dict = {item.get("artifactId"): item.get("totalTime")
                         for item in playtime_items if "artifactId" in item}

        # Filter out non-game assets before processing
        # Skip Unreal Engine content and items without required fields
        filtered_assets = []
        for asset in assets:
            # Skip Unreal Engine content
            if asset.get("namespace") == "ue":
                continue

            # Skip items without required fields
            if not asset.get("namespace") or not asset.get("catalogItemId") or not asset.get("appName"):
                continue

            # Skip other obvious non-games (plugins, engines, etc.)
            app_name = asset.get("appName", "")
            if app_name.startswith("UE_"):
                continue

            if "DLC" in app_name and not asset.get("buildVersion"):
                continue

            filtered_assets.append(asset)

        if show_progress:
            print(f"Found {len(filtered_assets)} potential games to process")

        # Step 3: Process assets to generate game entries
        logger.info(f"Processing {len(filtered_assets)} assets...")

        processed = 0
        total_assets = len(filtered_assets)

        # Fast mode - skip detailed catalog data
        if skip_catalog:
            for game_asset in filtered_assets:
                # Show progress
                processed += 1
                if show_progress and processed % 20 == 0:
                    print(f"Processing games... {processed}/{total_assets}", end="\r")

                app_name = game_asset.get("appName", "")
                namespace = game_asset.get("namespace", "")
                catalog_item_id = game_asset.get("catalogItemId", "")

                # Extract the best possible title from available fields
                title = None

                # Try these fields in order of preference
                title_fields = ["displayName", "titleText", "title", "description", "productName"]
                for field in title_fields:
                    if game_asset.get(field):
                        title = game_asset.get(field)
                        break

                # Parse manifest data if available
                manifest = game_asset.get("manifest")
                if not title and manifest:
                    # Sometimes the manifest contains good title information
                    if isinstance(manifest, dict):
                        for field in ["displayName", "title"]:
                            if manifest.get(field):
                                title = manifest.get(field)
                                break

                # Additional source - sometimes the app name is more readable than the ID
                if not title or title == app_name:
                    # If app name is a UUID or appears to be an ID, it's not helpful as a title
                    is_id = (
                        # UUID format check
                        (len(app_name) == 32 and all(c in "0123456789abcdef" for c in app_name.lower())) or
                        # Random ID format check
                        app_name.count('_') > 3 or
                        # Starts with a hash-like number
                        app_name.startswith('0x')
                    )

                    # Try to extract a readable name from the app name if it's not an ID
                    if not is_id:
                        # Convert camelCase/snake_case to spaces
                        import re
                        app_name_spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', app_name)  # camelCase
                        app_name_spaced = re.sub(r'[_-]', ' ', app_name_spaced)          # snake_case and kebab-case

                        # Clean up multiple spaces
                        app_name_spaced = re.sub(r'\s+', ' ', app_name_spaced).strip()

                        if app_name_spaced:
                            title = app_name_spaced.title()  # Convert to Title Case

                # Final fallback - use the app name as is
                if not title:
                    title = app_name

                # Create basic game entry
                game_entry = {
                    "title": title,
                    "id": app_name,
                    "namespace": namespace,
                    "catalog_item_id": catalog_item_id,
                }

                # Add playtime if available
                if app_name in playtime_dict:
                    game_entry["playtime"] = playtime_dict[app_name]

                owned_games.append(game_entry)

        # Optimized mode - fetch catalog data in batches
        elif optimize_catalog:
            if show_progress:
                print(f"Processing {len(filtered_assets)} games in optimized batch mode")

            # Create a more efficient mapping of assets by namespace and ID for lookup
            assets_by_id = {}
            for asset in filtered_assets:
                app_name = asset.get("appName", "")
                catalog_item_id = asset.get("catalogItemId", "")
                namespace = asset.get("namespace", "")

                # Skip if no catalog item ID
                if not catalog_item_id:
                    continue

                # Store in lookup dictionary
                assets_by_id[(namespace, catalog_item_id)] = asset

            # Collect all catalog item IDs
            all_catalog_item_ids = [(asset.get("namespace", ""), asset.get("catalogItemId", ""))
                                    for asset in filtered_assets
                                    if asset.get("catalogItemId")]

            # Process in batches of 50 items (optimized while respecting API limitations)
            valid_games = []
            batch_size = 50
            total_batches = (len(all_catalog_item_ids) + batch_size - 1) // batch_size

            for batch_index in range(0, total_batches):
                start_idx = batch_index * batch_size
                end_idx = min((batch_index + 1) * batch_size, len(all_catalog_item_ids))
                batch_items = all_catalog_item_ids[start_idx:end_idx]

                if show_progress:
                    print(f"  Processing batch {batch_index + 1}/{total_batches} ({len(batch_items)} items)")

                # Process each namespace in this batch
                by_namespace = {}
                for namespace, catalog_id in batch_items:
                    if namespace not in by_namespace:
                        by_namespace[namespace] = []
                    by_namespace[namespace].append(catalog_id)

                # For each namespace, get the catalog items
                for namespace, catalog_ids in by_namespace.items():
                    try:
                        catalog_data = self._get_catalog_batch(namespace, catalog_ids)

                        # Process items from this namespace
                        for catalog_item_id in catalog_ids:
                            # Get the asset and catalog item
                            asset = assets_by_id.get((namespace, catalog_item_id))
                            catalog_item = catalog_data.get(catalog_item_id, {})

                            if not asset:
                                continue

                            app_name = asset.get("appName", "")

                            # Check if this is a valid game
                            if not self._is_valid_game(catalog_item, app_name):
                                continue

                            # Create game entry with basic info
                            game_entry = {
                                "title": catalog_item.get("title", asset.get("displayName") or app_name),
                                "id": app_name,
                                "namespace": namespace,
                                "catalog_item_id": catalog_item_id,
                            }

                            # Add playtime if available
                            if app_name in playtime_dict:
                                game_entry["playtime"] = playtime_dict[app_name]

                                # If playtime exists, we know the game has been played at least once
                                if playtime_dict[app_name] > 0:
                                    game_entry["play_count"] = 1

                            # Add description
                            if "description" in catalog_item:
                                game_entry["description"] = catalog_item["description"]

                            # Add developer
                            if "developer" in catalog_item:
                                game_entry["developer"] = catalog_item["developer"]

                            # Add developer ID
                            if "developerId" in catalog_item:
                                game_entry["developer_id"] = catalog_item["developerId"]

                            # Add release information
                            if "releaseInfo" in catalog_item and catalog_item["releaseInfo"]:
                                release_info = catalog_item["releaseInfo"][0]  # Use first release info

                                # Add release date
                                if "dateAdded" in release_info and release_info["dateAdded"]:
                                    game_entry["release_date"] = release_info["dateAdded"]

                                # Add platform details
                                if "platform" in release_info and release_info["platform"]:
                                    game_entry["platforms"] = release_info["platform"]
                            else:
                                game_entry["platforms"] = ["windows"]  # Default assumption

                            # Add custom attributes (contains info about game launcher requirements)
                            if "customAttributes" in catalog_item and catalog_item["customAttributes"]:
                                custom_attrs = {}
                                for key, attr in catalog_item["customAttributes"].items():
                                    if isinstance(attr, dict) and "value" in attr:
                                        custom_attrs[key] = attr["value"]

                                if custom_attrs:
                                    game_entry["custom_attributes"] = custom_attrs

                            # Add image URLs if available
                            if "keyImages" in catalog_item:
                                images = {}
                                for image in catalog_item["keyImages"]:
                                    if not isinstance(image, dict) or "type" not in image or "url" not in image:
                                        continue

                                    # Store all image types
                                    image_type = image["type"]
                                    images[image_type] = image["url"]

                                    # Also store in common fields for convenience
                                    if image_type == "DieselGameBoxTall":
                                        game_entry["box_tall_image"] = image["url"]
                                    elif image_type == "DieselGameBox":
                                        game_entry["box_image"] = image["url"]
                                    elif image_type == "Thumbnail":
                                        game_entry["thumbnail"] = image["url"]
                                    elif image_type == "OfferImageWide":
                                        game_entry["cover_image"] = image["url"]

                                # Store all images in a dedicated field
                                if images:
                                    game_entry["images"] = images

                            owned_games.append(game_entry)

                    except Exception as e:
                        logger.error(f"Error processing batch for namespace {namespace}: {e}")

            if show_progress:
                print(f"Processed {len(owned_games)} games using optimized batch processing")

        # Standard mode - fetch detailed catalog data one by one
        else:
            for game_asset in filtered_assets:
                # Show progress
                processed += 1
                if show_progress and processed % 10 == 0:
                    print(f"Processing games... {processed}/{total_assets}", end="\r")

                # Get catalog details for this asset
                try:
                    namespace = game_asset.get("namespace", "")
                    catalog_item_id = game_asset.get("catalogItemId", "")
                    app_name = game_asset.get("appName", "")

                    # Get catalog item with caching
                    catalog_item = self._get_catalog_item(namespace, catalog_item_id)

                    # Quick check for non-games
                    if not self._is_valid_game(catalog_item, app_name):
                        continue

                    # Create game entry with basic info
                    game_entry = {
                        "title": catalog_item.get("title", game_asset.get("displayName") or "Unknown"),
                        "id": app_name,
                        "namespace": namespace,
                        "catalog_item_id": catalog_item_id,
                    }

                    # Add playtime if available
                    if app_name in playtime_dict:
                        game_entry["playtime"] = playtime_dict[app_name]

                        # If playtime exists, we know the game has been played at least once
                        if playtime_dict[app_name] > 0:
                            game_entry["play_count"] = 1

                    # Add description
                    if "description" in catalog_item:
                        game_entry["description"] = catalog_item["description"]

                    # Add developer
                    if "developer" in catalog_item:
                        game_entry["developer"] = catalog_item["developer"]

                    # Add release information
                    if "releaseInfo" in catalog_item and catalog_item["releaseInfo"]:
                        release_info = catalog_item["releaseInfo"][0]  # Use first release info

                        # Add release date
                        if "dateAdded" in release_info and release_info["dateAdded"]:
                            game_entry["release_date"] = release_info["dateAdded"]

                        # Add platform details
                        if "platform" in release_info and release_info["platform"]:
                            game_entry["platforms"] = release_info["platform"]
                    else:
                        game_entry["platforms"] = ["windows"]  # Default assumption

                    # Add image URLs if available
                    if "keyImages" in catalog_item:
                        images = {}
                        for image in catalog_item["keyImages"]:
                            if not isinstance(image, dict) or "type" not in image or "url" not in image:
                                continue

                            # Store all image types
                            image_type = image["type"]
                            images[image_type] = image["url"]

                            # Also store in common fields for convenience
                            if image_type == "DieselGameBoxTall":
                                game_entry["box_tall_image"] = image["url"]
                            elif image_type == "DieselGameBox":
                                game_entry["box_image"] = image["url"]
                            elif image_type == "Thumbnail":
                                game_entry["thumbnail"] = image["url"]
                            elif image_type == "OfferImageWide":
                                game_entry["cover_image"] = image["url"]

                        # Store all images in a dedicated field
                        if images:
                            game_entry["images"] = images

                    owned_games.append(game_entry)

                except Exception as e:
                    logger.error(f"Error processing game asset {app_name}: {e}")
                    continue

        if show_progress:
            print(f"Processing games... {total_assets}/{total_assets} - Complete!")

        logger.info(f"Found {len(owned_games)} games in Epic account")
        return owned_games

    def _is_valid_game(self, catalog_item: Dict, app_name: str) -> bool:
        """
        Check if a catalog item represents a valid game

        Args:
            catalog_item: The catalog item to check
            app_name: The app name for logging

        Returns:
            bool: True if the item is a valid game, False otherwise
        """
        # Get the categories safely
        categories = catalog_item.get("categories", [])

        # Skip if no categories
        if not categories:
            return False

        # Check if this is an application
        is_application = False
        is_launchable_addon = False

        for cat in categories:
            if not isinstance(cat, dict) or "path" not in cat:
                continue
            if cat["path"] == "applications":
                is_application = True
            if cat["path"] == "addons/launchable":
                is_launchable_addon = True

        # Skip non-applications
        if not is_application:
            return False

        # Skip non-launchable DLCs/add-ons
        if catalog_item.get("mainGameItem") and not is_launchable_addon:
            return False

        # Skip digital extras, plugins, etc.
        skip_categories = ["digitalextras", "plugins", "plugins/engine"]

        for cat in categories:
            if not isinstance(cat, dict) or "path" not in cat:
                continue
            if any(skip_cat in cat["path"] for skip_cat in skip_categories):
                return False

        return True

    def _get_assets(self) -> List[Dict[str, Any]]:
        """
        Get all assets (games) owned by the user

        Returns:
            list: List of asset dictionaries from Epic API
        """
        tokens = self._load_tokens()
        if not tokens:
            return []

        try:
            # Set up the request headers
            headers = {
                "Authorization": f"{tokens['token_type']} {tokens['access_token']}"
            }

            # Make the request
            response = requests.get(self.assets_url, headers=headers)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to get assets: {e}")
            return []

    def _get_playtime_items(self) -> List[Dict[str, Any]]:
        """
        Get playtime data for all games

        Returns:
            list: List of playtime dictionaries from Epic API
        """
        tokens = self._load_tokens()
        if not tokens:
            return []

        try:
            # Set up the request headers
            headers = {
                "Authorization": f"{tokens['token_type']} {tokens['access_token']}"
            }

            # Format the URL with the account ID
            url = self.playtime_url.format(tokens.get("account_id", ""))

            # Make the request
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"Failed to get playtime items: {e}")
            return []

    def _get_catalog_batch(self, namespace: str, catalog_item_ids: List[str]) -> Dict[str, Any]:
        """
        Get catalog details for multiple items at once

        Args:
            namespace: The namespace of the items
            catalog_item_ids: List of catalog item IDs

        Returns:
            dict: Mapping of catalog item IDs to their details
        """
        # Skip if no IDs
        if not catalog_item_ids:
            return {}

        # Use cache for batch if available
        cache_key = f"{namespace}_batch_{len(catalog_item_ids)}.json"
        cache_path = self.catalog_cache_dir / cache_key

        # Check if any of the IDs are already cached individually
        cached_items = {}
        uncached_ids = []

        for item_id in catalog_item_ids:
            item_cache_path = self.catalog_cache_dir / f"{namespace}_{item_id}.json"
            if item_cache_path.exists():
                try:
                    with open(item_cache_path, 'r') as f:
                        cached_data = json.load(f)
                        if item_id in cached_data:
                            cached_items[item_id] = cached_data[item_id]
                            continue
                except Exception:
                    pass

            # If we get here, the item wasn't cached
            uncached_ids.append(item_id)

        # If all items were cached, return them
        if not uncached_ids:
            return cached_items

        # Get tokens for API request
        tokens = self._load_tokens()
        if not tokens:
            logger.error("No authentication tokens found")
            return cached_items

        try:
            # Set up the request headers
            headers = {
                "Authorization": f"{tokens['token_type']} {tokens['access_token']}"
            }

            # Format the URL - Epic allows multiple IDs with comma separation
            # But limit to 40 IDs per request to avoid URL length issues
            batch_ids = uncached_ids[:40]
            ids_param = ",".join(batch_ids)
            url = f"{self.catalog_url}{namespace}/bulk/items?id={ids_param}&country=US&locale=en-US&includeMainGameDetails=true"

            # Make the request
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            # Parse the response
            new_items = response.json()

            # Cache individual items
            for item_id in batch_ids:
                if item_id in new_items:
                    item_cache_path = self.catalog_cache_dir / f"{namespace}_{item_id}.json"
                    with open(item_cache_path, 'w') as f:
                        # Store in cache format - a dictionary with the ID as the key
                        json.dump({item_id: new_items[item_id]}, f)

            # Combine cached and new items
            cached_items.update(new_items)

            # If there are remaining IDs, recursively fetch them
            if len(uncached_ids) > 40:
                remaining_items = self._get_catalog_batch(namespace, uncached_ids[40:])
                cached_items.update(remaining_items)

            return cached_items

        except Exception as e:
            logger.warning(f"Failed to get catalog batch for namespace {namespace}: {e}")
            return cached_items

    def _get_catalog_item(self, namespace: str, catalog_item_id: str) -> Dict[str, Any]:
        """
        Get catalog details for a specific item, with caching

        Args:
            namespace: The namespace of the item
            catalog_item_id: The catalog item ID

        Returns:
            dict: Catalog item details

        Raises:
            Exception: If the catalog item could not be found
        """
        # Check if we have this item cached
        cache_filename = f"{namespace}_{catalog_item_id}.json"
        cache_path = self.catalog_cache_dir / cache_filename

        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    cached_data = json.load(f)
                    # Return the specific item from the cached bulk response
                    if catalog_item_id in cached_data:
                        return cached_data[catalog_item_id]
            except Exception as e:
                logger.debug(f"Failed to load catalog cache for {namespace}_{catalog_item_id}: {e}")

        # If not in cache, fetch from API
        tokens = self._load_tokens()
        if not tokens:
            raise Exception("No authentication tokens found")

        try:
            # Set up the request headers
            headers = {
                "Authorization": f"{tokens['token_type']} {tokens['access_token']}"
            }

            # Format the URL
            url = f"{self.catalog_url}{namespace}/bulk/items?id={catalog_item_id}&country=US&locale=en-US&includeMainGameDetails=true"

            # Make the request
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            # Parse the response
            catalog_data = response.json()

            # Save to cache
            with open(cache_path, 'w') as f:
                json.dump(catalog_data, f)

            # Return the specific item
            if catalog_item_id in catalog_data:
                return catalog_data[catalog_item_id]
            else:
                # Return empty dict with minimum required fields
                # This avoids breaking the workflow while still filtering the item
                logger.warning(f"Epic catalog item {catalog_item_id} in {namespace} not found")
                return {"categories": []}

        except Exception as e:
            logger.warning(f"Failed to get catalog item {catalog_item_id}: {e}")
            # Return empty dict with minimum required fields
            return {"categories": []}