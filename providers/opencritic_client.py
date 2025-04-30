#!/usr/bin/env python3
"""
OpenCritic API Client

A Python client for accessing the OpenCritic API. Ported from the Playnite OpenCriticMetadata extension.
"""

import requests
import datetime
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from metadata_provider import MetadataProvider, Game, Genre, SearchResultItem, Company, Platform, Image, ImageCollection


@dataclass
class OpenCriticImage(Image):
    """Image information for a game"""
    og: Optional[str] = None
    sm: Optional[str] = None

    @property
    def url(self) -> Optional[str]:
        """Get the full URL for the original image"""
        if self.og:
            return f"https://img.opencritic.com/{self.og}"
        return None

    @property
    def thumbnail_url(self) -> Optional[str]:
        """Get the full URL for the thumbnail image"""
        if self.sm:
            return f"https://img.opencritic.com/{self.sm}"
        return None


class OpenCriticClient(MetadataProvider):
    """Client for accessing the OpenCritic API"""

    def __init__(self):
        """Initialize the client with the API base URL"""
        self.base_url = "https://api.opencritic.com/api/"
        self.session = requests.Session()
        self.session.headers.update({
            "Referer": "https://opencritic.com/",
            "User-Agent": "Python/OpenCriticClient"
        })

    def search(self, query: str) -> List[SearchResultItem]:
        """
        Search for games by name

        Args:
            query: The search query

        Returns:
            A list of search results
        """
        url = f"{self.base_url}meta/search"
        params = {"criteria": query.replace(" ", "+")}

        response = self.session.get(url, params=params)
        if not response.ok:
            print(f"Error searching for '{query}': {response.status_code} {response.reason}")
            return []

        data = response.json()
        results = []

        for item in data:
            if item.get("relation") == "game":
                results.append(SearchResultItem(
                    id=item["id"],
                    name=item["name"],
                    relation=item["relation"]
                ))

        return results

    def get_details(self, game_id: int) -> Optional[Game]:
        """
        Get detailed information about a game

        Args:
            game_id: The OpenCritic game ID

        Returns:
            Detailed game information or None if not found
        """
        url = f"{self.base_url}game/{game_id}"

        response = self.session.get(url)
        if not response.ok:
            print(f"Error fetching game {game_id}: {response.status_code} {response.reason}")
            return None

        data = response.json()
        return self._parse_game_details(data)

    def _parse_game_details(self, data: Dict[str, Any]) -> Game:
        """Parse the game details JSON into an Game object"""
        # Parse image data
        images = None
        if "images" in data and data["images"]:
            images_data = data["images"]
            screenshots = []

            if "screenshots" in images_data and images_data["screenshots"]:
                for screenshot in images_data["screenshots"]:
                    screenshots.append(OpenCriticImage(
                        og=screenshot.get("og"),
                        sm=screenshot.get("sm")
                    ))

            # Parse box, square, and masthead images
            box = None
            if "box" in images_data and images_data["box"]:
                box = OpenCriticImage(
                    og=images_data["box"].get("og"),
                    sm=images_data["box"].get("sm")
                )

            square = None
            if "square" in images_data and images_data["square"]:
                square = OpenCriticImage(
                    og=images_data["square"].get("og"),
                    sm=images_data["square"].get("sm")
                )

            masthead = None
            if "masthead" in images_data and images_data["masthead"]:
                masthead = OpenCriticImage(
                    og=images_data["masthead"].get("og"),
                    sm=images_data["masthead"].get("sm")
                )

            images = ImageCollection(
                box=box,
                square=square,
                masthead=masthead,
                screenshots=screenshots
            )

        # Parse companies (developers, publishers)
        companies = []
        if "companies" in data and data["companies"]:
            for company in data["companies"]:
                companies.append(Company(
                    name=company.get("name", ""),
                    type=company.get("type", "")
                ))

        # Parse genres
        genres = []
        if "genres" in data and data["genres"]:
            for genre in data["genres"]:
                genres.append(Genre(
                    id=genre.get("id", 0),
                    name=genre.get("name", "")
                ))

        # Parse platforms
        platforms = []
        if "platforms" in data and data["platforms"]:
            for platform in data["platforms"]:
                release_date = None
                if "releaseDate" in platform:
                    try:
                        release_date = datetime.datetime.fromisoformat(platform["releaseDate"].replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                platforms.append(Platform(
                    id=platform.get("id", 0),
                    name=platform.get("name", ""),
                    short_name=platform.get("shortName"),
                    release_date=release_date
                ))

        # Parse release date
        first_release_date = None
        if "firstReleaseDate" in data and data["firstReleaseDate"]:
            try:
                first_release_date = datetime.datetime.fromisoformat(data["firstReleaseDate"].replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        # Create and return the game object
        return Game(
            id=data.get("id", 0),
            name=data.get("name", ""),
            is_major_release=data.get("isMajorRelease", False),
            images=images,
            num_reviews=data.get("numReviews", 0),
            num_top_critic_reviews=data.get("numTopCriticReviews", 0),
            median_score=data.get("medianScore", 0.0),
            top_critic_score=data.get("topCriticScore", 0.0),
            percentile=data.get("percentile", 0.0),
            percent_recommended=data.get("percentRecommended", 0.0),
            description=data.get("description"),
            first_release_date=first_release_date,
            companies=companies,
            genres=genres,
            platforms=platforms,
            url=data.get("url")
        )


def display_game_details(game: Game):
    """Display game details in a readable format"""
    print("\nGame Details:")
    print(f"Title: {game.name}")

    if game.description:
        max_len = 200
        description = game.description[:max_len] + "..." if len(game.description) > max_len else game.description
        print(f"Description: {description}")

    print(f"URL: {game.url}")
    print(f"Critic Score: {game.top_critic_score:.1f}")
    print(f"User Score: {game.median_score:.1f}")

    if game.first_release_date:
        print(f"Release Date: {game.first_release_date.strftime('%Y-%m-%d')}")

    if game.genres:
        print(f"Genres: {', '.join(g.name for g in game.genres)}")

    # Display developers
    developers = [c.name for c in game.companies if c.type.upper() == "DEVELOPER"]
    if developers:
        print(f"Developers: {', '.join(developers)}")

    # Display publishers
    publishers = [c.name for c in game.companies if c.type.upper() == "PUBLISHER"]
    if publishers:
        print(f"Publishers: {', '.join(publishers)}")

    # Display platforms
    if game.platforms:
        print(f"Platforms: {', '.join(p.name for p in game.platforms)}")

    # Display image information
    if game.images:
        if game.images.box and game.images.box.url:
            print(f"Cover Image: {game.images.box.url}")

        if game.images.screenshots:
            print(f"Screenshots: {len(game.images.screenshots)} available")
            for i, screenshot in enumerate(game.images.screenshots[:3]):
                if screenshot.url:
                    print(f"- {screenshot.url}")


def main():
    """Main entry point for the OpenCritic API client"""
    print("OpenCritic API Client")
    print("=====================")

    client = OpenCriticClient()

    while True:
        query = input("\nEnter game name to search (or 'exit' to quit): ")
        if not query or query.lower() == "exit":
            print("Exiting...")
            break

        print(f"Searching for: {query}")
        results = client.search(query)

        if not results:
            print("No results found.")
            continue

        print(f"Found {len(results)} results:")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result.name} (ID: {result.id})")

        selection = input("Enter number to view details (or 0 to search again): ")
        try:
            selection = int(selection)
            if selection < 1 or selection > len(results):
                print("Invalid selection or search again requested.")
                continue
        except ValueError:
            print("Invalid selection. Please enter a number.")
            continue

        selected_game = results[selection - 1]
        print(f"Fetching details for {selected_game.name}...")

        details = client.get_details(selected_game.id)

        if not details:
            print("Failed to retrieve game details.")
            continue

        display_game_details(details)


if __name__ == "__main__":
    main()
