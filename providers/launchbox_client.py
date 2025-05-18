#!/usr/bin/env python3

import os
import sys
import sqlite3
import argparse
import requests
import zipfile
import tempfile
import xml.etree.ElementTree as ET
import re
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import datetime
import logging

from providers.metadata_provider import MetadataProvider, Image, ImageCollection, SearchResultItem, Game, Genre, Platform, Company

# Set up logger
logger = logging.getLogger(__name__)
# Set logger level to DEBUG to see all messages
logger.setLevel(logging.DEBUG)

class LaunchBoxDatabase:
    """Handles interactions with the local LaunchBox metadata SQLite database."""

    DB_FILENAME = "LBGDB.sqlite"

    def __init__(self, data_directory: str):
        """Initialize the database handler with a path to store the database file.

        Args:
            data_directory: Directory to store the database.
        """
        os.makedirs(data_directory, exist_ok=True)
        self.data_directory = data_directory
        self.db_path = os.path.join(data_directory, self.DB_FILENAME)
        self.conn = None

    def get_connection(self):
        """Get a SQLite connection, creating one if it doesn't exist.

        Note: This creates a new connection for thread-safety.
        SQLite objects created in one thread can only be used in that same thread.
        """
        # Always create a new connection for thread safety
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def close(self):
        """Close the database connection."""
        # Since we're now creating new connections for each operation,
        # there's no persistent connection to close
        self.conn = None

    def database_exists(self) -> bool:
        """Check if the database file exists."""
        return os.path.exists(self.db_path)

    def create_tables(self):
        """Create the database tables if they don't exist."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Games table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS Games (
                DatabaseID TEXT PRIMARY KEY,
                Name TEXT,
                ReleaseDate TEXT,
                ReleaseYear INTEGER,
                Overview TEXT,
                MaxPlayers INTEGER,
                ReleaseType TEXT,
                Cooperative INTEGER,
                WikipediaURL TEXT,
                VideoURL TEXT,
                CommunityRating REAL,
                Platform TEXT,
                ESRB TEXT,
                CommunityRatingCount INTEGER,
                Genres TEXT,
                Developer TEXT,
                Publisher TEXT
            )
            ''')

            # Game names table with FTS5 (full-text search)
            cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS GameNames USING fts5(
                DatabaseID,
                Name
            )
            ''')

            # Game images table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS GameImages (
                DatabaseID TEXT,
                FileName TEXT,
                Type TEXT,
                Region TEXT,
                CRC32 INTEGER
            )
            ''')

            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS IX_ImageType ON GameImages(Type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS IX_ImageRegion ON GameImages(Region)')

            conn.commit()
        finally:
            cursor.close()
            conn.close()

    def _escape_fts5_query(self, query: str) -> str:
        """Escape special characters in FTS5 query syntax.

        FTS5 has special characters like !, *, ", etc.
        This function escapes them to treat them as literal characters.

        Args:
            query: The raw search query string

        Returns:
            Escaped query string safe for FTS5 MATCH queries
        """
        # Replace any special characters that have meaning in FTS5
        # Exclamation mark (!) is used for NOT operator
        # Double quotes (") are used for phrase searches
        # Asterisk (*) is used for prefix searches
        # Replace with corresponding escape sequences or remove
        special_chars = ['!', '"', '*', '(', ')', '^', ':', '&', '+', '-']

        # For simplicity, we'll just add double quotes around the entire term
        # which treats it as a literal phrase rather than trying to escape each character
        escaped_query = f'"{query}"'
        return escaped_query

    def search_games(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for games by name.

        Args:
            query: The search string
            limit: Maximum number of results to return

        Returns:
            List of matching games
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Escape special characters in the query for FTS5
            escaped_query = self._escape_fts5_query(query)

            # Use FTS5 to search game names
            cursor.execute('''
            SELECT
                g.*,
                gn.Name as MatchedName
            FROM
                GameNames gn
            INNER JOIN
                Games g ON g.DatabaseID = gn.DatabaseID
            WHERE
                GameNames MATCH ?
            ORDER BY
                rank
            LIMIT ?
            ''', (escaped_query, limit))

            results = []
            for row in cursor.fetchall():
                result = dict(row)
                # Convert ReleaseDate to datetime if it exists
                if result['ReleaseDate']:
                    try:
                        result['ReleaseDate'] = datetime.datetime.fromisoformat(result['ReleaseDate'])
                    except ValueError:
                        pass
                results.append(result)

            return results
        finally:
            # Ensure connection is closed
            cursor.close()
            conn.close()

    def search_games_by_title_and_platform(self, title: str, platform: str) -> List[Dict[str, Any]]:
        """Search for games by title match (case insensitive) and platform.
        Uses a series of increasingly lenient search methods:
        1. Exact title match in Games table
        2. Exact title match in GameNames table (alternate names)
        3. Title prefix match (for games that start with the search term)
        4. Spaces-as-wildcards match (replaces spaces with % wildcards)
        5. Wildcard-prefix match (prepends % and replaces spaces with % wildcards)

        Args:
            title: The game title to search for
            platform: The platform to search for

        Returns:
            List of matching games
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            results = []

            # 1. First try exact match on the main Games table
            cursor.execute('''
            SELECT
                g.*
            FROM
                Games g
            WHERE
                RTRIM(LOWER(g.Name)) = RTRIM(LOWER(?)) AND
                (LOWER(g.Platform) = LOWER(?) OR ? = '')
            LIMIT 10
            ''', (title, platform, platform))

            for row in cursor.fetchall():
                result = dict(row)
                # Convert ReleaseDate to datetime if it exists
                if result['ReleaseDate']:
                    try:
                        result['ReleaseDate'] = datetime.datetime.fromisoformat(result['ReleaseDate'])
                    except ValueError:
                        pass
                results.append(result)

            # 2. If we didn't find any results with exact title match,
            # try searching for the title in the GameNames FTS table
            if not results:
                logger.debug(f"No exact match found for '{title}', trying alternate names")

                # For the FTS table, we need to escape any special characters
                # but since we're doing a direct comparison instead of MATCH,
                # we don't need the FTS5 escaping here
                cursor.execute('''
                SELECT
                    g.*
                FROM
                    GameNames_content gn
                JOIN
                    Games g ON g.DatabaseID = gn.c0
                WHERE
                    RTRIM(LOWER(gn.c1)) = RTRIM(LOWER(?)) AND
                    (LOWER(g.Platform) = LOWER(?) OR ? = '')
                LIMIT 10
                ''', (title, platform, platform))

                for row in cursor.fetchall():
                    result = dict(row)
                    # Convert ReleaseDate to datetime if it exists
                    if result['ReleaseDate']:
                        try:
                            result['ReleaseDate'] = datetime.datetime.fromisoformat(result['ReleaseDate'])
                        except ValueError:
                            pass
                    results.append(result)

                if results:
                    logger.debug(f"Found {len(results)} matches via alternate names")

            # 3. If still no results, try a prefix match (title LIKE 'search%')
            if not results:
                logger.debug(f"No exact matches found for '{title}', trying prefix match")
                # Add wildcard to the end of the title
                title_prefix = title.strip() + '%'
                cursor.execute('''
                SELECT
                    g.*
                FROM
                    Games g
                WHERE
                    LOWER(g.Name) LIKE LOWER(?) AND
                    (LOWER(g.Platform) = LOWER(?) OR ? = '')
                ORDER BY LENGTH(g.Name) ASC
                LIMIT 10
                ''', (title_prefix, platform, platform))

                for row in cursor.fetchall():
                    result = dict(row)
                    # Convert ReleaseDate to datetime if it exists
                    if result['ReleaseDate']:
                        try:
                            result['ReleaseDate'] = datetime.datetime.fromisoformat(result['ReleaseDate'])
                        except ValueError:
                            pass
                    results.append(result)

                if results:
                    logger.debug(f"Found {len(results)} matches via prefix search")

            # 4. If still no results, try replacing spaces with wildcards (t%i%t%l%e%)
            if not results:
                logger.debug(f"No matches found for '{title}', trying spaces-as-wildcards match")
                # Replace spaces with % and keep the % at the end
                if ' ' in title:
                    wildcarded_title = title.strip().replace(' ', '%') + '%'
                    cursor.execute('''
                    SELECT
                        g.*
                    FROM
                        Games g
                    WHERE
                        LOWER(g.Name) LIKE LOWER(?) AND
                        (LOWER(g.Platform) = LOWER(?) OR ? = '')
                    ORDER BY LENGTH(g.Name) ASC
                    LIMIT 5
                    ''', (wildcarded_title, platform, platform))

                    for row in cursor.fetchall():
                        result = dict(row)
                        # Convert ReleaseDate to datetime if it exists
                        if result['ReleaseDate']:
                            try:
                                result['ReleaseDate'] = datetime.datetime.fromisoformat(result['ReleaseDate'])
                            except ValueError:
                                pass
                        results.append(result)

                    if results:
                        logger.debug(f"Found {len(results)} matches via spaces-as-wildcards search")

            # 5. If still no results, try prepending a wildcard (%title with spaces as %)
            if not results:
                logger.debug(f"No matches found for '{title}', trying wildcard-prefix match")
                # Prepend % and replace spaces with % and keep the % at the end
                wildcarded_title = '%' + title.strip().replace(' ', '%') + '%'
                cursor.execute('''
                SELECT
                    g.*
                FROM
                    Games g
                WHERE
                    LOWER(g.Name) LIKE LOWER(?) AND
                    (LOWER(g.Platform) = LOWER(?) OR ? = '')
                ORDER BY LENGTH(g.Name) ASC
                LIMIT 5
                ''', (wildcarded_title, platform, platform))

                for row in cursor.fetchall():
                    result = dict(row)
                    # Convert ReleaseDate to datetime if it exists
                    if result['ReleaseDate']:
                        try:
                            result['ReleaseDate'] = datetime.datetime.fromisoformat(result['ReleaseDate'])
                        except ValueError:
                            pass
                    results.append(result)

                if results:
                    logger.debug(f"Found {len(results)} matches via wildcard-prefix search")

            return results
        finally:
            # Ensure connection is closed
            cursor.close()
            conn.close()

    def get_game_by_id(self, database_id: str) -> Optional[Dict[str, Any]]:
        """Get a game by its database ID.

        Args:
            database_id: The game's DatabaseID

        Returns:
            Game data or None if not found
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT * FROM Games WHERE DatabaseID = ?', (database_id,))
            row = cursor.fetchone()

            if not row:
                return None

            result = dict(row)

            # Get game images - we need to make sure this query works even if database_id contains special characters
            cursor.execute('SELECT * FROM GameImages WHERE DatabaseID = ?', (database_id,))
            images = []
            for img_row in cursor.fetchall():
                images.append(dict(img_row))

            result['Images'] = images

            # Convert ReleaseDate to datetime if it exists
            if result['ReleaseDate']:
                try:
                    result['ReleaseDate'] = datetime.datetime.fromisoformat(result['ReleaseDate'])
                except ValueError:
                    pass

            # Convert Cooperative from integer to boolean
            if 'Cooperative' in result:
                result['Cooperative'] = bool(result['Cooperative'])

            return result
        finally:
            # Ensure connection is closed
            cursor.close()
            conn.close()

    def get_image_types(self) -> List[str]:
        """Get all image types available in the database."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT DISTINCT Type FROM GameImages')
            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    def get_regions(self) -> List[str]:
        """Get all regions available in the database."""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT DISTINCT Region FROM GameImages')
            return [row[0] for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()


class XmlData:
    """Container for data parsed from LaunchBox XML."""

    def __init__(self):
        self.games = []
        self.game_alternate_names = []
        self.game_images = []


class LaunchBoxXmlParser:
    """Parser for the LaunchBox Metadata.xml file."""

    def __init__(self, xml_path: str):
        """Initialize the parser with the path to the XML file.

        Args:
            xml_path: Path to the Metadata.xml file
        """
        self.xml_path = xml_path
        self.tree = None
        self.root = None

    def parse(self):
        """Parse the XML file."""
        self.tree = ET.parse(self.xml_path)
        self.root = self.tree.getroot()

    def get_data(self) -> XmlData:
        """Parse and return all data from the XML file.

        Returns:
            XmlData object containing games, alternate names, and images
        """
        if self.root is None:
            self.parse()

        data = XmlData()

        # Parse all games
        for game_elem in self.root.findall('./Game'):
            game = self._parse_game(game_elem)
            if game and game.get('DatabaseID'):
                data.games.append(game)

        # Parse all game alternate names
        for alt_name_elem in self.root.findall('./GameAlternateName'):
            alt_name = self._parse_game_alternate_name(alt_name_elem)
            if alt_name and alt_name.get('DatabaseID') and alt_name.get('Name'):
                data.game_alternate_names.append(alt_name)

        # Parse all game images
        for img_elem in self.root.findall('./GameImage'):
            img = self._parse_game_image(img_elem)
            if img and img.get('DatabaseID') and img.get('FileName') and img.get('Type'):
                data.game_images.append(img)

        logger.info(f"Parsed {len(data.games)} games, {len(data.game_alternate_names)} alternate names, {len(data.game_images)} images")
        return data

    def _parse_game(self, game_elem) -> dict:
        """Parse a Game element from the XML.

        Args:
            game_elem: XML element to parse

        Returns:
            Dict with game data
        """
        try:
            game = {}

            # Extract basic game info
            game['DatabaseID'] = self._get_element_text(game_elem, './DatabaseID')
            game['Name'] = self._get_element_text(game_elem, './Name')

            # Skip if no database ID
            if not game['DatabaseID']:
                return None

            # Release date and year
            release_date = self._get_element_text(game_elem, './ReleaseDate')
            if release_date:
                try:
                    parsed_date = datetime.datetime.strptime(release_date, '%Y-%m-%dT%H:%M:%S')
                    game['ReleaseDate'] = parsed_date.isoformat()
                    game['ReleaseYear'] = parsed_date.year
                except ValueError:
                    game['ReleaseDate'] = None
                    game['ReleaseYear'] = self._safe_int(self._get_element_text(game_elem, './ReleaseYear'))
            else:
                game['ReleaseDate'] = None
                game['ReleaseYear'] = self._safe_int(self._get_element_text(game_elem, './ReleaseYear'))

            # Other game details
            game['Overview'] = self._get_element_text(game_elem, './Overview')
            game['MaxPlayers'] = self._safe_int(self._get_element_text(game_elem, './MaxPlayers'))
            game['ReleaseType'] = self._get_element_text(game_elem, './ReleaseType')
            game['Cooperative'] = self._get_element_text(game_elem, './Cooperative') == 'true'
            game['WikipediaURL'] = self._get_element_text(game_elem, './WikipediaURL')
            game['VideoURL'] = self._get_element_text(game_elem, './VideoURL')
            game['CommunityRating'] = self._safe_float(self._get_element_text(game_elem, './CommunityRating'))
            game['Platform'] = self._get_element_text(game_elem, './Platform')
            game['ESRB'] = self._get_element_text(game_elem, './ESRB')
            game['CommunityRatingCount'] = self._safe_int(self._get_element_text(game_elem, './CommunityRatingCount'))

            # Extract genres, developers, publishers
            game['Genres'] = self._get_element_text(game_elem, './Genres')
            game['Developer'] = self._get_element_text(game_elem, './Developer')
            game['Publisher'] = self._get_element_text(game_elem, './Publisher')

            return game

        except Exception as e:
            logger.error(f"Error parsing game: {e}")
            return None

    def _parse_game_alternate_name(self, alt_name_elem) -> dict:
        """Parse a GameAlternateName element from the XML.

        Args:
            alt_name_elem: XML element to parse

        Returns:
            Dict with alternate name data
        """
        try:
            alt_name = {}
            alt_name['DatabaseID'] = self._get_element_text(alt_name_elem, './DatabaseID')
            alt_name['Name'] = self._get_element_text(alt_name_elem, './AlternateName')
            return alt_name
        except Exception as e:
            logger.error(f"Error parsing alternate name: {e}")
            return None

    def _parse_game_image(self, img_elem) -> dict:
        """Parse a GameImage element from the XML.

        Args:
            img_elem: XML element to parse

        Returns:
            Dict with image data
        """
        try:
            img = {}
            img['DatabaseID'] = self._get_element_text(img_elem, './DatabaseID')
            img['FileName'] = self._get_element_text(img_elem, './FileName')
            img['Type'] = self._get_element_text(img_elem, './Type')
            img['Region'] = self._get_element_text(img_elem, './Region')
            img['CRC32'] = self._safe_int(self._get_element_text(img_elem, './CRC32'))
            return img
        except Exception as e:
            logger.error(f"Error parsing image: {e}")
            return None

    def _get_element_text(self, parent, xpath):
        """Safely get element text or return None if element doesn't exist."""
        elem = parent.find(xpath)
        if elem is not None and elem.text:
            return elem.text
        return None

    def _safe_int(self, value):
        """Convert value to int or return 0 if not possible."""
        if not value:
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    def _safe_float(self, value):
        """Convert value to float or return 0.0 if not possible."""
        if not value:
            return 0.0
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0


class MetadataDownloader:
    """Handler for downloading LaunchBox metadata."""

    METADATA_URL = "https://gamesdb.launchbox-app.com/Metadata.zip"

    def __init__(self, data_directory: str):
        """Initialize downloader with a directory to store files.

        Args:
            data_directory: Directory to store downloaded and temporary files.
        """
        self.data_directory = data_directory

    def download_metadata(self, force: bool = False) -> Optional[str]:
        """Download the LaunchBox metadata zip file.

        Args:
            force: Force download even if local copy exists

        Returns:
            Path to the downloaded zip file, or None if download failed
        """
        logger.info(f"Downloading LaunchBox metadata from {self.METADATA_URL}")

        try:
            response = requests.get(self.METADATA_URL, stream=True)
            response.raise_for_status()

            # Get file size for progress reporting
            total_size = int(response.headers.get('content-length', 0))

            # Create a temporary file for the zip
            fd, zip_path = tempfile.mkstemp(suffix='.zip')
            os.close(fd)

            # Download with progress
            downloaded = 0
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        percent = int(100 * downloaded / total_size) if total_size > 0 else 0
                        sys.stdout.write(f"\rDownloading: {percent}% ({downloaded} / {total_size} bytes)")
                        sys.stdout.flush()

            logger.info("Progress complete")  # Progress reporting complete
            logger.info(f"Download complete: {zip_path}")
            return zip_path

        except requests.RequestException as e:
            logger.error(f"Error downloading metadata: {e}")
            return None

    def extract_metadata_xml(self, zip_path: str) -> Optional[str]:
        """Extract the Metadata.xml file from the zip archive.

        Args:
            zip_path: Path to the downloaded zip file

        Returns:
            Path to the extracted XML file, or None if extraction failed
        """
        logger.info(f"Extracting Metadata.xml from {zip_path}")

        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                # Find the Metadata.xml file
                xml_entry = None
                for entry in z.namelist():
                    if entry.lower() == 'metadata.xml':
                        xml_entry = entry
                        break

                if not xml_entry:
                    logger.error("Metadata.xml not found in the zip file")
                    return None

                # Create a temporary file for the XML
                fd, xml_path = tempfile.mkstemp(suffix='.xml')
                os.close(fd)

                # Extract the file
                with z.open(xml_entry) as source, open(xml_path, 'wb') as target:
                    shutil.copyfileobj(source, target)

                logger.info(f"Extraction complete: {xml_path}")

                # Clean up control characters (as done in the C# version)
                cleaned_xml_path = self._clean_control_characters(xml_path)

                return cleaned_xml_path

        except (zipfile.BadZipFile, KeyError, IOError) as e:
            logger.error(f"Error extracting metadata: {e}")
            return None

    def _clean_control_characters(self, xml_path: str) -> str:
        """Clean control character entities from the XML file.

        Args:
            xml_path: Path to the original XML file

        Returns:
            Path to the cleaned XML file
        """
        logger.info("Cleaning control character entities from XML")

        # Create a temporary file for the cleaned XML
        fd, cleaned_xml_path = tempfile.mkstemp(suffix='.xml')
        os.close(fd)

        # Regular expression to match hex entities (similar to the C# version)
        hex_entity_regex = re.compile(r'&#x[0-9A-F]{1,2};')

        with open(xml_path, 'r', encoding='utf-8', errors='ignore') as source, \
             open(cleaned_xml_path, 'w', encoding='utf-8') as target:
            for line in source:
                clean_line = hex_entity_regex.sub('', line)
                target.write(clean_line)

        return cleaned_xml_path


class LaunchBoxMetadata(MetadataProvider):
    """Main class for interacting with LaunchBox metadata."""

    def __init__(self, data_directory: str = "data"):
        """Initialize the metadata manager.

        Args:
            data_directory: Directory to store the database and other files.
                            Defaults to 'data'
        """
        # Create provider-specific directory
        launchbox_dir = os.path.join(data_directory, "providers", "launchbox")
        os.makedirs(launchbox_dir, exist_ok=True)

        self.data_directory = launchbox_dir
        self.database = LaunchBoxDatabase(launchbox_dir)
        self.downloader = MetadataDownloader(launchbox_dir)

    def initialize_database(self, force: bool = False) -> bool:
        """Initialize or update the LaunchBox metadata database.

        Args:
            force: Force download even if the database already exists

        Returns:
            True if initialization was successful, False otherwise
        """
        if self.database.database_exists() and not force:
            logger.info("Database already exists. Use --force to re-initialize.")
            return True

        logger.info("Initializing LaunchBox metadata database")

        # Download metadata zip
        zip_path = self.downloader.download_metadata(force=force)
        if not zip_path:
            return False

        # Extract metadata XML
        xml_path = self.downloader.extract_metadata_xml(zip_path)
        if not xml_path:
            return False

        # Create database tables
        self.database.create_tables()

        # Parse XML data
        parser = LaunchBoxXmlParser(xml_path)
        try:
            data = parser.get_data()
        except ET.ParseError as e:
            logger.error(f"Error parsing XML: {e}")
            return False

        # Insert data into database
        conn = self.database.get_connection()
        cursor = conn.cursor()

        try:
            logger.info("Populating database from XML...")

            # Start a transaction for better performance
            conn.execute('BEGIN TRANSACTION')

            # Insert games
            game_count = 0
            for game in data.games:
                # Insert into Games table
                cursor.execute('''
                INSERT OR REPLACE INTO Games (
                    DatabaseID, Name, ReleaseDate, ReleaseYear, Overview, MaxPlayers,
                    ReleaseType, Cooperative, WikipediaURL, VideoURL, CommunityRating,
                    Platform, ESRB, CommunityRatingCount, Genres, Developer, Publisher
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    game['DatabaseID'], game['Name'], game['ReleaseDate'], game['ReleaseYear'],
                    game['Overview'], game['MaxPlayers'], game['ReleaseType'],
                    1 if game['Cooperative'] else 0, game['WikipediaURL'], game['VideoURL'],
                    game['CommunityRating'], game['Platform'], game['ESRB'],
                    game['CommunityRatingCount'], game['Genres'], game['Developer'], game['Publisher']
                ))

                game_count += 1
                if game_count % 1000 == 0:
                    sys.stdout.write(f"\rProcessed {game_count} games")
                    sys.stdout.flush()

            logger.info("Progress complete")  # Progress reporting complete

            # Insert game names (including base names and alternate names)
            logger.info("Adding game names to FTS index...")

            # Add base game names
            for game in data.games:
                cursor.execute('''
                INSERT OR REPLACE INTO GameNames (DatabaseID, Name) VALUES (?, ?)
                ''', (game['DatabaseID'], game['Name']))

            # Add alternate game names
            for alt_name in data.game_alternate_names:
                cursor.execute('''
                INSERT OR REPLACE INTO GameNames (DatabaseID, Name) VALUES (?, ?)
                ''', (alt_name['DatabaseID'], alt_name['Name']))

            # Insert game images
            image_count = 0
            logger.info("Adding game images...")

            for image in data.game_images:
                if not image.get('FileName') or not image.get('Type'):
                    continue  # Skip invalid images

                cursor.execute('''
                INSERT OR REPLACE INTO GameImages (DatabaseID, FileName, Type, Region, CRC32)
                VALUES (?, ?, ?, ?, ?)
                ''', (
                    image['DatabaseID'], image['FileName'], image['Type'],
                    image['Region'], image['CRC32']
                ))

                image_count += 1
                if image_count % 10000 == 0:
                    sys.stdout.write(f"\rAdded {image_count} images")
                    sys.stdout.flush()

            logger.info("Progress complete")  # Progress reporting complete

            # Commit the transaction
            conn.execute('COMMIT')
            logger.info(f"Database initialization complete. {game_count} games, {len(data.game_alternate_names)} alternate names, and {image_count} images added.")

            # Clean up temporary files
            if os.path.exists(zip_path):
                os.unlink(zip_path)
            if os.path.exists(xml_path):
                os.unlink(xml_path)

            return True

        except Exception as e:
            conn.execute('ROLLBACK')
            logger.error(f"Error populating database: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def search(self, query: str) -> List[SearchResultItem]:
        """Search for games by name.

        Args:
            query: The search string

        Returns:
            List of matching games as SearchResultItem objects
        """
        if not self.database.database_exists():
            logger.error("Database not initialized. Run initialize-database first.")
            return []

        raw_results = self.database.search_games(query, limit=10)
        results = []

        for item in raw_results:
            results.append(SearchResultItem(
                id=int(item['DatabaseID']) if item['DatabaseID'].isdigit() else 0,
                name=item['Name'],
                relation="game"
            ))

        return results

    def search_by_title_and_platform(self, title: str, platform_str: str) -> Optional[Game]:
        """Search for a game by title match (case insensitive) and platform.
        Uses progressive fallback search methods to find matches:
        1. Exact title match
        2. Alternate names match
        3. Prefix match (games that start with the search term)
        4. Spaces-as-wildcards match (replaces spaces with % wildcards)
        5. Wildcard-prefix match (prepends % and replaces spaces with % wildcards)

        For fuzzy matches (3-5), if exactly one result is found, it will be used.
        For multiple matches, only uses the first result if it's a strong match.

        If found, returns the full Game object with metadata.

        Args:
            title: The game title to search for
            platform_str: The platform name to search for (can be empty string for any platform)

        Returns:
            Game object with metadata if found, None otherwise
        """
        if not self.database.database_exists():
            logger.error("Database not initialized. Run initialize-database first.")
            return None

        # Log the original search parameters
        logger.debug(f"Searching for title: '{title}' on platform: '{platform_str}'")

        # Check if the title contains any special characters that might cause FTS5 issues
        if any(char in title for char in ['!', '"', '*', '(', ')', '^', ':', '&', '+', '-']):
            logger.debug(f"Title contains special characters that may affect FTS5 search")

        raw_results = self.database.search_games_by_title_and_platform(title, platform_str)

        if not raw_results:
            logger.debug(f"No matches found for title '{title}' and platform '{platform_str}'")
            return None

        # Log the search success and match type
        if len(raw_results) == 1:
            logger.debug(f"Found a single match for '{title}': '{raw_results[0]['Name']}'")
        else:
            logger.debug(f"Found {len(raw_results)} matches for '{title}', best match: '{raw_results[0]['Name']}'")

        # For fuzzy matches, only use the match if there's exactly one result
        # or if the first result is a strong match (title starts with our search)
        if len(raw_results) > 1:
            title_lower = title.lower().strip()
            # Check if the first result is a clear best match
            first_match_name = raw_results[0]['Name'].lower()

            # If the first match doesn't start with our search term and we have multiple results,
            # apply stricter validation for fuzzy matches
            if not first_match_name.startswith(title_lower) and not title_lower == first_match_name:
                # See if our search terms can be found within the match in the right order
                # This helps with cases where spaces have been replaced with other characters
                words = title_lower.split()
                if len(words) > 1:
                    word_idx = 0
                    search_pos = 0
                    # Check if all words appear in sequence (with anything in between)
                    for word in words:
                        word_pos = first_match_name[search_pos:].find(word)
                        if word_pos == -1:
                            # Word not found in remaining string
                            logger.debug(f"Multiple fuzzy matches found, but '{first_match_name}' is not a confident match for '{title}'")
                            return None
                        search_pos += word_pos + len(word)

                    # If we get here, all words were found in sequence
                    logger.debug(f"Using match '{first_match_name}' as it contains all search terms in sequence")
                else:
                    # Single word but no prefix match - not confident enough
                    logger.debug(f"Multiple fuzzy matches found, but none are confident matches for '{title}'")
                    return None
            else:
                logger.debug(f"Using first fuzzy match '{raw_results[0]['Name']}' as it starts with search term")

        # Use the first match
        game_id = raw_results[0]['DatabaseID']
        return self.get_details(int(game_id) if game_id.isdigit() else 0)

    def get_details(self, game_id: int) -> Optional[Game]:
        """Get detailed information about a specific game.

        Args:
            game_id: The game's ID

        Returns:
            Game details or None if not found
        """
        if not self.database.database_exists():
            logger.error("Database not initialized. Run initialize-database first.")
            return None

        raw_game = self.database.get_game_by_id(str(game_id))
        if not raw_game:
            return None

        # Create a list of genres from the comma-separated genres field
        genres = []
        if raw_game.get('Genres'):
            genre_list = raw_game['Genres'].split(',')
            for i, genre_name in enumerate(genre_list):
                genres.append(Genre(
                    id=i,
                    name=genre_name.strip()
                ))

        # Create a list of platforms from the platform field
        platforms = []
        if raw_game.get('Platform'):
            platforms.append(Platform(
                id=0,
                name=raw_game['Platform'],
                short_name=raw_game['Platform']
            ))

        # Create a list of companies (developers, publishers)
        companies = []
        if raw_game.get('Developer'):
            companies.append(Company(
                name=raw_game['Developer'],
                type="DEVELOPER"
            ))
        if raw_game.get('Publisher'):
            companies.append(Company(
                name=raw_game['Publisher'],
                type="PUBLISHER"
            ))

        # Create image collection
        images = None
        if 'Images' in raw_game and raw_game['Images']:
            # Group images by type
            box = None
            screenshots = []

            for img in raw_game['Images']:
                if not img.get('FileName'):
                    continue

                if img.get('Type') == 'Box - Front' and not box:
                    box = LaunchBoxImage(
                        filename=img['FileName'],
                        image_type=img.get('Type'),
                        region=img.get('Region')
                    )
                elif img.get('Type') == 'Screenshot':
                    screenshots.append(LaunchBoxImage(
                        filename=img['FileName'],
                        image_type=img.get('Type'),
                        region=img.get('Region')
                    ))

            # Create image collection
            images = ImageCollection(
                box=box,
                screenshots=screenshots
            )

        # Create and return the game object
        return Game(
            id=int(raw_game['DatabaseID']) if raw_game['DatabaseID'].isdigit() else 0,
            name=raw_game.get('Name', ''),
            description=raw_game.get('Overview'),
            first_release_date=raw_game.get('ReleaseDate'),
            images=images,
            genres=genres,
            platforms=platforms,
            companies=companies,
            url=raw_game.get('WikipediaURL')
        )

    def close(self):
        """Close database connections and clean up resources."""
        self.database.close()


def display_game_search_results(results: List[Dict[str, Any]]):
    """Display search results in a user-friendly format."""
    if not results:
        logger.info("No games found matching your search.")
        return

    logger.info(f"Found {len(results)} games:")
    logger.info("-" * 80)

    for i, game in enumerate(results, 1):
        title = game.get('Name', 'Unknown')
        platform = game.get('Platform', 'Unknown Platform')
        year = game.get('ReleaseYear', 'Unknown Year')
        matched_name = game.get('MatchedName', title)

        logger.info(f"{i}. {title} ({platform}, {year})")
        if matched_name != title:
            logger.info(f"   Matched: {matched_name}")

    logger.info("-" * 80)


class LaunchBoxImage(Image):
    """Image information for a game from LaunchBox database"""

    def __init__(self, filename: Optional[str] = None, image_type: Optional[str] = None, region: Optional[str] = None):
        self.filename = filename
        self.type = image_type
        self.region = region

    @property
    def url(self) -> Optional[str]:
        """Get the full URL for the image"""
        if self.filename:
            return f"https://images.launchbox-app.com/{self.filename}"
        return None

def get_launchbox_image_url(filename: str) -> str:
    """Get the full URL for a LaunchBox image filename.

    Args:
        filename: The image filename from the database

    Returns:
        The full URL to the image
    """
    return f"https://images.launchbox-app.com/{filename}"


def display_game_details(game: Dict[str, Any]):
    """Display detailed game information in a user-friendly format."""
    if not game:
        logger.info("Game not found.")
        return

    logger.info("\n" + "=" * 80)
    logger.info(f"Game: {game.get('Name', 'Unknown')}")
    logger.info("=" * 80)

    # Basic info
    logger.info(f"Platform: {game.get('Platform', 'Unknown')}")

    if game.get('ReleaseDate'):
        logger.info(f"Release Date: {game['ReleaseDate'].strftime('%Y-%m-%d')}")
    elif game.get('ReleaseYear'):
        logger.info(f"Release Year: {game['ReleaseYear']}")

    if game.get('Developer'):
        logger.info(f"Developer: {game['Developer']}")

    if game.get('Publisher'):
        logger.info(f"Publisher: {game['Publisher']}")

    if game.get('Genres'):
        logger.info(f"Genres: {game['Genres']}")

    if game.get('ESRB'):
        logger.info(f"ESRB Rating: {game['ESRB']}")

    if game.get('CommunityRating'):
        logger.info(f"Community Rating: {game['CommunityRating']}/5 ({game.get('CommunityRatingCount', 0)} votes)")

    if game.get('MaxPlayers'):
        logger.info(f"Max Players: {game['MaxPlayers']}")
        if game.get('Cooperative'):
            logger.info("Cooperative: Yes")

    # Links
    if game.get('WikipediaURL'):
        logger.info(f"Wikipedia: {game['WikipediaURL']}")

    if game.get('VideoURL'):
        logger.info(f"Video: {game['VideoURL']}")

    # Overview
    if game.get('Overview'):
        logger.info("\nOverview:")
        logger.info("-" * 80)
        logger.info(game['Overview'])
        logger.info("-" * 80)

    # Images
    if game.get('Images'):
        # Group images by type and region
        images_by_type = {}

        for img in game['Images']:
            img_type = img.get('Type', 'Unknown')
            region = img.get('Region', 'None')
            filename = img.get('FileName', '')

            if img_type not in images_by_type:
                images_by_type[img_type] = []

            image_url = get_launchbox_image_url(filename)

            images_by_type[img_type].append({
                'filename': filename,
                'url': image_url,
                'region': region,
                'crc32': img.get('CRC32', 0)
            })

        logger.info("\nImages:")
        logger.info("-" * 80)

        for img_type, images in sorted(images_by_type.items()):
            logger.info(f"\n{img_type} ({len(images)} images):")

            # Group by region for cleaner display
            by_region = {}
            for img in images:
                region = img['region'] or 'None'
                if region not in by_region:
                    by_region[region] = []
                by_region[region].append(img)

            # Display images grouped by region
            for region, region_images in sorted(by_region.items()):
                logger.info(f"  Region: {region}")
                for i, img in enumerate(region_images, 1):
                    logger.info(f"    {i}. {img['url']} (CRC32: {img['crc32']})")

        logger.info("-" * 80)


def analyze_xml_structure(xml_path):
    """Analyze the structure of the LaunchBox metadata XML file for debugging."""
    logger.info("\nAnalyzing XML structure...")

    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Count root-level elements
        logger.info("Root-level elements:")
        for child_tag in set(child.tag for child in root):
            count = len(root.findall(f'./{child_tag}'))
            logger.info(f"- {child_tag}: {count}")

        # Check for games
        games = root.findall('./Game')
        if games:
            logger.info(f"\nFound {len(games)} Game elements")
            sample_game = games[0]
            logger.info("Sample Game element structure:")
            for child in sample_game:
                if child.tag == 'Images':
                    logger.info(f"- {child.tag}: {len(child)} images")
                else:
                    logger.info(f"- {child.tag}: {child.text if child.text else '[empty]'}")

        # Check for images
        images_elements = root.findall('./Images')
        if images_elements:
            logger.info(f"\nFound {len(images_elements)} Images elements")
            sample_images = images_elements[0]
            logger.info("Sample Images element structure:")
            game_id = sample_images.find('./GameID')
            logger.info(f"- GameID: {game_id.text if game_id is not None and game_id.text else '[missing]'}")

            image_count = len(sample_images.findall('./Image'))
            logger.info(f"- Contains {image_count} Image elements")

            if image_count > 0:
                sample_image = sample_images.find('./Image')
                logger.info("  Sample Image element structure:")
                for child in sample_image:
                    logger.info(f"  - {child.tag}: {child.text if child.text else '[empty]'}")

        # Check for GameImage elements (which is what LaunchBox metadata actually uses)
        game_images = root.findall('./GameImage')
        if game_images:
            logger.info(f"\nFound {len(game_images)} GameImage elements")
            sample_image = game_images[0]
            logger.info("Sample GameImage element structure:")
            for child in sample_image:
                logger.info(f"- {child.tag}: {child.text if child.text else '[empty]'}")

            # Count images by type
            image_types = {}
            for i, img in enumerate(game_images):
                img_type = img.find('./Type')
                if img_type is not None and img_type.text:
                    if img_type.text not in image_types:
                        image_types[img_type.text] = 0
                    image_types[img_type.text] += 1

                if i >= 10000:  # Sample just the first 10k images to be fast
                    break

            logger.info("\nImage types (from sample):")
            for img_type, count in sorted(image_types.items(), key=lambda x: x[1], reverse=True):
                logger.info(f"- {img_type}: {count}")

    except Exception as e:
        logger.error(f"Error analyzing XML: {e}")


def main():
    parser = argparse.ArgumentParser(description="LaunchBox Metadata CLI")
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Initialize database
    init_parser = subparsers.add_parser('initialize-database', help='Initialize or update the LaunchBox metadata database')
    init_parser.add_argument('--force', action='store_true', help='Force redownload even if database exists')

    # Search
    search_parser = subparsers.add_parser('search', help='Search for games by name')
    search_parser.add_argument('query', help='Game name to search for')
    search_parser.add_argument('--limit', type=int, default=10, help='Maximum number of results (default: 10)')

    # Get details
    details_parser = subparsers.add_parser('details', help='Get detailed information about a specific game')
    details_parser.add_argument('game_id', help='Game database ID')

    # Interactive search
    interactive_parser = subparsers.add_parser('interactive', help='Interactive search mode')
    interactive_parser.add_argument('query', nargs='?', help='Initial game name to search for (optional)')

    # Analyze XML structure (for debugging)
    analyze_parser = subparsers.add_parser('analyze-xml', help='Analyze the structure of a LaunchBox metadata XML file')
    analyze_parser.add_argument('xml_path', help='Path to the XML file to analyze')

    # Debug database (for troubleshooting)
    debug_parser = subparsers.add_parser('debug-database', help='Show database statistics and diagnostics')

    args = parser.parse_args()

    if args.command == 'analyze-xml':
        analyze_xml_structure(args.xml_path)
        return

    # Create metadata handler
    metadata = LaunchBoxMetadata()

    try:
        if args.command == 'initialize-database':
            success = metadata.initialize_database(force=args.force)
            if not success:
                sys.exit(1)

        elif args.command == 'search':
            results = metadata.search(args.query, args.limit)
            display_game_search_results(results)

        elif args.command == 'details':
            game = metadata.get_details(args.game_id)
            display_game_details(game)

        elif args.command == 'interactive':
            logger.info("LaunchBox Metadata Interactive Mode")
            logger.info("----------------------------------")

            query = args.query
            while True:
                if not query:
                    query = input("\nEnter game name to search (or 'q' to quit): ")

                if query.lower() == 'q':
                    break

                results = metadata.search(query, limit=20)
                display_game_search_results(results)

                if results:
                    while True:
                        choice = input("\nEnter number for details (or press Enter to search again): ")
                        if not choice:
                            break

                        try:
                            idx = int(choice) - 1
                            if 0 <= idx < len(results):
                                game = metadata.get_details(results[idx]['DatabaseID'])
                                display_game_details(game)
                            else:
                                logger.info("Invalid selection. Please try again.")
                                continue
                        except ValueError:
                            logger.info("Invalid input. Please enter a number.")
                            continue

                        input("\nPress Enter to continue...")
                        break

                query = None  # Reset for next iteration

        elif args.command == 'debug-database':
            if not metadata.database.database_exists():
                logger.info("Database does not exist. Run initialize-database first.")
                return

            conn = metadata.database.get_connection()
            cursor = conn.cursor()

            # Check table counts
            cursor.execute('SELECT COUNT(*) FROM Games')
            games_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM GameNames')
            game_names_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM GameImages')
            images_count = cursor.fetchone()[0]

            logger.info(f"Database statistics:")
            logger.info(f"- Games: {games_count}")
            logger.info(f"- Game Names (FTS index): {game_names_count}")
            logger.info(f"- Game Images: {images_count}")

            if images_count > 0:
                cursor.execute('SELECT DISTINCT Type FROM GameImages')
                image_types = [row[0] for row in cursor.fetchall()]

                logger.info("\nImage types in database:")
                for img_type in sorted(image_types):
                    cursor.execute('SELECT COUNT(*) FROM GameImages WHERE Type = ?', (img_type,))
                    type_count = cursor.fetchone()[0]
                    logger.info(f"- {img_type}: {type_count}")
            else:
                logger.info("\nNo images found in database.")
                logger.info("This could be because:")
                logger.info("1. The LaunchBox XML doesn't contain image information")
                logger.info("2. There was an issue parsing the image data")
                logger.info("3. The database schema doesn't match the XML structure")
                logger.info("\nTry using the analyze-xml command on the extracted XML file to debug.")

        else:
            parser.print_help()
            logger.info("\nAvailable commands:")
            logger.info("  initialize-database  Initialize or update the LaunchBox metadata database")
            logger.info("  search               Search for games by name")
            logger.info("  details              Get detailed information about a specific game")
            logger.info("  interactive          Interactive search mode")
            logger.info("  analyze-xml          Analyze the structure of a LaunchBox metadata XML file")
            logger.info("  debug-database       Show database statistics and diagnostics")

    finally:
        metadata.close()


if __name__ == "__main__":
    main()
