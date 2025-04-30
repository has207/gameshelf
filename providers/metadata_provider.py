import datetime
from typing import List, Optional
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class BaseModel:
    """Base model for OpenCritic entities"""
    id: int
    name: str


@dataclass
class SearchResultItem(BaseModel):
    """Search result from the OpenCritic API"""
    relation: str = ""


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


@dataclass
class Image:
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


@dataclass
class ImageCollection:
    """Collection of images for a game"""
    box: Optional[Image] = None
    square: Optional[Image] = None
    masthead: Optional[Image] = None
    screenshots: List[Image] = field(default_factory=list)


@dataclass
class Game(BaseModel):
    """Detailed game information from the OpenCritic API"""
    has_lootboxes: Optional[bool] = None
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
            game_id: The OpenCritic game ID

        Returns:
            Detailed game information or None if not found
        """
        pass
