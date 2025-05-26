import datetime
from typing import List, Optional
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

from data_mapping import Genres, Platforms, AgeRatings, Features, Regions


@dataclass
class BaseModel:
    """Base model for metadata entities"""
    id: int
    name: str


@dataclass
class SearchResultItem(BaseModel):
    """Search result from metadata providers"""
    relation: str = ""
    platform: Optional[str] = None
    release_year: Optional[int] = None


@dataclass
class Company:
    """Company information (developer or publisher)"""
    name: str
    type: str


@dataclass
class Genre(BaseModel):
    """Genre information"""
    pass


@dataclass
class Platform(BaseModel):
    """Platform information for a game"""
    short_name: Optional[str] = None
    release_date: Optional[datetime.datetime] = None


class Image(ABC):
    @abstractmethod
    def url(self):
        pass

@dataclass
class ImageCollection:
    """Collection of images for a game"""
    box: Optional[Image] = None
    square: Optional[Image] = None
    masthead: Optional[Image] = None
    screenshots: List[Image] = field(default_factory=list)


@dataclass
class Game(BaseModel):
    """Detailed game information"""
    is_major_release: bool = False
    images: Optional[ImageCollection] = None
    num_reviews: int = 0
    num_top_critic_reviews: int = 0
    median_score: float = 0.0
    top_critic_score: float = 0.0
    percentile: float = 0.0
    percent_recommended: float = 0.0
    description: Optional[str] = None
    first_release_date: Optional[datetime.datetime] = None
    companies: List[Company] = field(default_factory=list)
    genres: List[Genre] = field(default_factory=list)
    platforms: List[Platform] = field(default_factory=list)
    url: Optional[str] = None
    rating: Optional[str] = None  # Age rating string (e.g., "E - Everyone")


class MetadataProvider(ABC):
    """Base class for metadata providers"""

    @abstractmethod
    def search(self, query: str) -> List[SearchResultItem]:
        """
        Search for games by name

        Args:
            query: The search query

        Returns:
            A list of search results
        """
        pass

    @abstractmethod
    def get_details(self, game_id: int) -> Optional[Game]:
        """
        Get detailed information about a game

        Args:
            game_id: game ID

        Returns:
            Detailed game information or None if not found
        """
        pass

    # Shared enum mapping methods
    def map_genres(self, genre_objects: List[Genre]) -> List[Genres]:
        """
        Map metadata provider Genre objects to our Genres enum values

        Args:
            genre_objects: List of Genre objects from metadata provider

        Returns:
            List of mapped Genres enum values
        """
        mapped_genres = []
        for genre_obj in genre_objects:
            if hasattr(genre_obj, 'name') and genre_obj.name:
                mapped_genre = Genres.try_from_string(genre_obj.name)
                if mapped_genre:
                    mapped_genres.append(mapped_genre)
        return mapped_genres

    def map_platforms(self, platform_objects: List[Platform]) -> List[Platforms]:
        """
        Map metadata provider Platform objects to our Platforms enum values

        Args:
            platform_objects: List of Platform objects from metadata provider

        Returns:
            List of mapped Platforms enum values
        """
        mapped_platforms = []
        for platform_obj in platform_objects:
            # Try name first, then short_name
            platform_name = None
            if hasattr(platform_obj, 'name') and platform_obj.name:
                platform_name = platform_obj.name
            elif hasattr(platform_obj, 'short_name') and platform_obj.short_name:
                platform_name = platform_obj.short_name

            if platform_name:
                mapped_platform = Platforms.try_from_string(platform_name)
                if mapped_platform:
                    mapped_platforms.append(mapped_platform)
        return mapped_platforms

    def map_single_genre(self, genre_name: str) -> Optional[Genres]:
        """
        Map a single genre string to our Genres enum

        Args:
            genre_name: Genre name string

        Returns:
            Mapped Genres enum value or None
        """
        return Genres.try_from_string(genre_name) if genre_name else None

    def map_single_platform(self, platform_name: str) -> Optional[Platforms]:
        """
        Map a single platform string to our Platforms enum

        Args:
            platform_name: Platform name string

        Returns:
            Mapped Platforms enum value or None
        """
        return Platforms.try_from_string(platform_name) if platform_name else None

    def map_single_age_rating(self, rating_name: str) -> Optional[AgeRatings]:
        """
        Map a single age rating string to our AgeRatings enum

        Args:
            rating_name: Age rating string

        Returns:
            Mapped AgeRatings enum value or None
        """
        return AgeRatings.try_from_string(rating_name) if rating_name else None

    def map_single_region(self, region_name: str) -> Optional[Regions]:
        """
        Map a single region string to our Regions enum

        Args:
            region_name: Region name string

        Returns:
            Mapped Regions enum value or None
        """
        return Regions.try_from_string(region_name) if region_name else None
