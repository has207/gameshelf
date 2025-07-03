import enum
import re

from typing import Optional, List


class BaseEnum(enum.Enum):
    """Base class for all enums with common helper methods"""

    def to_string(self) -> str:
        """Return the string value of this enum"""
        return self.value

    @classmethod
    def get_all_strings(cls) -> List[str]:
        """Return a list of all string values for this enum"""
        return [item.value for item in cls]

    @classmethod
    def try_from_string(cls, value_str: Optional[str]):
        """
        Try to convert a string to enum value, returning None if invalid

        Args:
            value_str: String representation of enum value

        Returns:
            Enum value or None if invalid
        """
        try:
            return cls.from_string(value_str)
        except Exception:
            return None

    @classmethod
    def to_string_list(cls, items: List) -> List[str]:
        """
        Convert a list of enum values to string values

        Args:
            items: List of enum values

        Returns:
            List of string representations
        """
        return [item.value for item in items]


class InvalidCompletionStatusError(Exception):
    """Exception raised when an invalid completion status is encountered."""
    pass


class InvalidPlatformError(Exception):
    """Exception raised when an invalid platform is encountered."""
    pass


class InvalidAgeRatingError(Exception):
    """Exception raised when an invalid age rating is encountered."""
    pass


class InvalidFeatureError(Exception):
    """Exception raised when an invalid feature is encountered."""
    pass


class InvalidGenreError(Exception):
    """Exception raised when an invalid genre is encountered."""
    pass


class InvalidRegionError(Exception):
    """Exception raised when an invalid region is encountered."""
    pass


class InvalidTagError(Exception):
    """Exception raised when an invalid tag is encountered."""
    pass


class InvalidLauncherTypeError(Exception):
    """Exception raised when an invalid launcher type is encountered."""
    pass


class CompletionStatus(BaseEnum):
    NOT_PLAYED = "Not Played"
    PLAN_TO_PLAY = "Plan to Play"
    PLAYING = "Playing"
    ON_HOLD = "On Hold"
    ABANDONED = "Abandoned"
    PLAYED = "Played"
    BEATEN = "Beaten"
    COMPLETED = "Completed"

    @classmethod
    def from_string(cls, status_str: Optional[str]) -> 'CompletionStatus':
        """
        Convert a string to the corresponding enum value

        Args:
            status_str: String representation of completion status

        Returns:
            CompletionStatus enum value

        Raises:
            InvalidCompletionStatusError: If the string doesn't match any valid status
        """
        if not status_str:
            return cls.NOT_PLAYED

        # Try direct match first
        for status in cls:
            if status.value == status_str:
                return status

        # Try case-insensitive match
        for status in cls:
            if status.value.lower() == status_str.lower():
                return status

        # Raise exception if no match found
        raise InvalidCompletionStatusError(f"Invalid completion status: {status_str}")


class Platforms(BaseEnum):
    COMMODORE_64 = "Commodore 64"
    NINTENDO_64 = "Nintendo 64"
    COMMODORE_AMIGA_CD32 = "Commodore Amiga CD32"
    PC_DOS = "PC (DOS)"
    NINTENDO_GAMECUBE = "Nintendo GameCube"
    COMMODORE_PET = "Commodore PET"
    NINTENDO_WII = "Nintendo Wii"
    NEC_TURBOGRAFX_CD = "NEC TurboGrafx-CD"
    NINTENDO_GAMEBOY_COLOR = "Nintendo Game Boy Color"
    SINCLAIR_ZX81 = "Sinclair ZX81"
    NINTENDO_WIIU = "Nintendo Wii U"
    BANDAI_WONDERSWAN = "Bandai WonderSwan"
    NINTENDO_SNES = "Nintendo SNES"
    SINCLAIR_ZXSPECTRUM = "Sinclair ZX Spectrum"
    NEC_SUPERGRAFX = "NEC SuperGrafx"
    PC_98 = "PC-98"
    COMMODORE_AMIGA = "Commodore Amiga"
    COLECO_VISION = "Coleco ColecoVision"
    NINTENDO_FAMICOM_DISK = "Nintendo Family Computer Disk System"
    NINTENDO_DS = "Nintendo DS"
    XBOX = "Microsoft Xbox"
    SEGA_MASTERSYSTEM = "Sega Master System"
    SEGA_CD = "Sega CD"
    SEGA_32X = "Sega 32X"
    ARCADE = "Arcade"
    BANDAI_WONDERSWAN_COLOR = "Bandai WonderSwan Color"
    PC_WINDOWS = "PC (Windows)"
    PC_MAC = "PC (Mac)"
    ATARI_8BIT = "Atari 8-bit"
    SNK_NEOGEOPOCKET_COLOR = "SNK Neo Geo Pocket Color"
    NINTENDO_GAMEBOY = "Nintendo Game Boy"
    PLAYSTATION3 = "Sony PlayStation 3"
    COMMODORE_PLUS4 = "Commodore Plus/4"
    ATARI_LYNX = "Atari Lynx"
    APPLE_II = "Apple II"
    MATTEL_INTELLIVISION = "Mattel Intellivision"
    PLAYSTATION = "Sony PlayStation"
    ATARI_5200 = "Atari 5200"
    PC_LINUX = "PC (Linux)"
    NINTENDO_NES = "Nintendo Entertainment System"
    THREE_DO = "3DO Interactive Multiplayer"
    NINTENDO_SWITCH = "Nintendo Switch"
    NINTENDO_GAMEBOY_ADVANCE = "Nintendo Game Boy Advance"
    ATARI_2600 = "Atari 2600"
    NINTENDO_3DS = "Nintendo 3DS"
    SNK_NEOGEOPOCKET = "SNK Neo Geo Pocket"
    PLAYSTATION5 = "Sony PlayStation 5"
    SEGA_DREAMCAST = "Sega Dreamcast"
    SNK_NEOGEO_CD = "SNK Neo Geo CD"
    AMSTRAD_CPC = "Amstrad CPC"
    ATARI_ST = "Atari ST/STE"
    WIRELESS = "Wireless"
    MACINTOSH = "Macintosh"
    SEGA_GAMEGEAR = "Sega Game Gear"
    COMMODORE_VIC20 = "Commodore VIC20"
    VECTREX = "GCE Vectrex"
    NEC_TURBOGRAFX_16 = "NEC TurboGrafx 16"
    SEGA_GENESIS = "Sega Genesis"
    ATARI_7800 = "Atari 7800"
    XBOX360 = "Microsoft Xbox 360"
    NINTENDO_VIRTUALBOY = "Nintendo Virtual Boy"
    XBOX_ONE = "Microsoft Xbox One"
    ATARI_JAGUAR = "Atari Jaguar"
    PLAYSTATION_VITA = "Sony PlayStation Vita"
    PLAYSTATION4 = "Sony PlayStation 4"
    XBOX_SERIES = "Microsoft Xbox Series"
    PSP = "Sony PSP"
    NEC_PCFX = "NEC PC-FX"
    PLAYSTATION2 = "Sony PlayStation 2"
    SEGA_SATURN = "Sega Saturn"
    UNKNOWN = "Unknown"

    @classmethod
    def from_string(cls, platform_str: Optional[str]) -> 'Platforms':
        """
        Convert a string to the corresponding enum value

        Args:
            platform_str: String representation of platform

        Returns:
            Platforms enum value

        Raises:
            InvalidPlatformError: If the string doesn't match any valid platform
        """
        if not platform_str:
            raise InvalidPlatformError("Platform string cannot be empty")

        # Normalize input
        platform_lower = platform_str.lower().strip()

        # Try direct match first
        for platform in cls:
            if platform.value == platform_str:
                return platform

        # Try case-insensitive match
        for platform in cls:
            if platform.value.lower() == platform_lower:
                return platform

        # Define alternative mappings for common variations
        mappings = {
            # PC variations
            "pc": cls.PC_WINDOWS,
            "windows": cls.PC_WINDOWS,
            "win": cls.PC_WINDOWS,
            "linux": cls.PC_LINUX,
            "dos": cls.PC_DOS,
            "mac": cls.MACINTOSH,
            "macos": cls.MACINTOSH,

            # PlayStation variations
            "ps1": cls.PLAYSTATION,
            "ps2": cls.PLAYSTATION2,
            "ps3": cls.PLAYSTATION3,
            "ps4": cls.PLAYSTATION4,
            "ps5": cls.PLAYSTATION5,
            "playstation": cls.PLAYSTATION,
            "playstation 1": cls.PLAYSTATION,
            "playstation 2": cls.PLAYSTATION2,
            "playstation 3": cls.PLAYSTATION3,
            "playstation 4": cls.PLAYSTATION4,
            "playstation 5": cls.PLAYSTATION5,
            "psp": cls.PSP,
            "vita": cls.PLAYSTATION_VITA,
            "ps vita": cls.PLAYSTATION_VITA,

            # Xbox variations
            "xbox": cls.XBOX,
            "xbox 360": cls.XBOX360,
            "xbox one": cls.XBOX_ONE,
            "xbox series": cls.XBOX_SERIES,
            "xbox series x": cls.XBOX_SERIES,
            "xbox series s": cls.XBOX_SERIES,

            # Nintendo variations
            "nes": cls.NINTENDO_NES,
            "snes": cls.NINTENDO_SNES,
            "n64": cls.NINTENDO_64,
            "gamecube": cls.NINTENDO_GAMECUBE,
            "wii": cls.NINTENDO_WII,
            "wii u": cls.NINTENDO_WIIU,
            "switch": cls.NINTENDO_SWITCH,
            "gameboy": cls.NINTENDO_GAMEBOY,
            "gbc": cls.NINTENDO_GAMEBOY_COLOR,
            "gba": cls.NINTENDO_GAMEBOY_ADVANCE,
            "ds": cls.NINTENDO_DS,
            "3ds": cls.NINTENDO_3DS,

            # Epic-specific variations
            "osx": cls.MACINTOSH,

            # Other common variations
            "arcade": cls.ARCADE,
            "mac": cls.MACINTOSH,
            "mobile": cls.WIRELESS,
            "unknown": cls.UNKNOWN
        }

        # Check alternative mappings
        if platform_lower in mappings:
            return mappings[platform_lower]

        # Try keyword matching for partial matches
        for keyword, platform_enum in mappings.items():
            if keyword in platform_lower:
                return platform_enum

        # Raise exception if no match found
        raise InvalidPlatformError(f"Invalid platform: {platform_str}")

    @classmethod
    def from_list(cls, platform_strings: List[str]) -> List['Platforms']:
        """
        Convert a list of strings to corresponding enum values

        Args:
            platform_strings: List of string representations of platforms

        Returns:
            List of Platforms enum values (invalid platforms are skipped)
        """
        platforms = []
        for platform_str in platform_strings:
            try:
                platform = cls.from_string(platform_str)
                platforms.append(platform)
            except InvalidPlatformError:
                # Skip invalid platforms
                pass
        return platforms


class AgeRatings(BaseEnum):
    CLASSIND_16 = "ClassInd 16"
    ACB_BLANK = "ACB "
    CERO_RP = "CERO RP"
    ACB_PG = "ACB PG"
    ACB_MA15 = "ACB MA15"
    PEGI_16 = "PEGI 16"
    ACB_R18 = "ACB R18"
    USK_6 = "USK 6"
    CERO_B = "CERO B"
    ESRB_E = "ESRB E"
    PEGI_7 = "PEGI 7"
    ESRB_M = "ESRB M"
    GRAC_12 = "GRAC 12"
    USK_18 = "USK 18"
    CERO_Z = "CERO Z"
    ESRB_E10 = "ESRB E10"
    PEGI_3 = "PEGI 3"
    GRAC_15 = "GRAC 15"
    ESRB_K_A = "ESRB K-A"
    CERO_D = "CERO D"
    ACB_M = "ACB M"
    CLASSIND_10 = "ClassInd 10"
    CERO_A = "CERO A"
    PEGI_12 = "PEGI 12"
    USK_0 = "USK 0"
    ACB_RC = "ACB RC"
    GRAC_18 = "GRAC 18"
    CLASSIND_12 = "ClassInd 12"
    CLASSIND_14 = "ClassInd 14"
    GRAC_TESTING = "GRAC TESTING"
    ESRB_RP = "ESRB RP"
    CLASSIND_G = "ClassInd G"
    CERO_C = "CERO C"
    USK_12 = "USK 12"
    USK_ALL = "USK ALL"
    CLASSIND_18 = "ClassInd 18"
    ESRB_RP_T_PLUS = "ESRB RP-T+"
    ESRB_E10_PLUS = "ESRB E10+"
    ESRB_T = "ESRB T"
    ESRB_NOT_RATED = "ESRB Not Rated"
    PEGI_18 = "PEGI 18"

    @classmethod
    def from_string(cls, rating_str: Optional[str]) -> 'AgeRatings':
        """
        Convert a string to the corresponding enum value

        Args:
            rating_str: String representation of age rating

        Returns:
            AgeRatings enum value

        Raises:
            InvalidAgeRatingError: If the string doesn't match any valid age rating
        """
        if not rating_str:
            raise InvalidAgeRatingError("Age rating string cannot be empty")

        # Try direct match first
        for rating in cls:
            if rating.value == rating_str:
                return rating

        # Try case-insensitive match
        for rating in cls:
            if rating.value.lower() == rating_str.lower():
                return rating

        # Raise exception if no match found
        raise InvalidAgeRatingError(f"Invalid age rating: {rating_str}")

    @classmethod
    def from_list(cls, rating_strings: List[str]) -> List['AgeRatings']:
        """
        Convert a list of strings to corresponding enum values

        Args:
            rating_strings: List of string representations of age ratings

        Returns:
            List of AgeRatings enum values (invalid ratings are skipped)
        """
        ratings = []
        for rating_str in rating_strings:
            try:
                rating = cls.from_string(rating_str)
                ratings.append(rating)
            except InvalidAgeRatingError:
                # Skip invalid ratings
                pass
        return ratings

    @classmethod
    def from_min_age(cls, min_age: int) -> List['AgeRatings']:
        """
        Convert minimum age integer to appropriate age rating enums from multiple systems

        Args:
            min_age: Minimum age requirement

        Returns:
            List of mapped AgeRatings enum values (PEGI, ESRB, CERO when available)
        """
        ratings = []

        if min_age <= 0:
            # Everyone/All ages
            ratings.extend([cls.ESRB_E, cls.PEGI_3, cls.CERO_A])
        elif min_age <= 3:
            # Ages 3+
            ratings.extend([cls.ESRB_E, cls.PEGI_3, cls.CERO_A])
        elif min_age <= 7:
            # Ages 7+
            ratings.extend([cls.ESRB_E, cls.PEGI_7, cls.CERO_A])
        elif min_age <= 10:
            # Ages 10+
            ratings.extend([cls.ESRB_E10_PLUS, cls.PEGI_7, cls.CERO_B])
        elif min_age <= 12:
            # Ages 12+
            ratings.extend([cls.ESRB_T, cls.PEGI_12, cls.CERO_B])
        elif min_age <= 13:
            # Ages 13+ (Teen)
            ratings.extend([cls.ESRB_T, cls.PEGI_12, cls.CERO_C])
        elif min_age <= 16:
            # Ages 16+
            ratings.extend([cls.ESRB_T, cls.PEGI_16, cls.CERO_C])
        elif min_age <= 17:
            # Ages 17+ (Mature)
            ratings.extend([cls.ESRB_M, cls.PEGI_16, cls.CERO_D])
        else:
            # Ages 18+
            ratings.extend([cls.ESRB_M, cls.PEGI_18, cls.CERO_Z])

        return ratings


class Features(BaseEnum):
    STEREO_SURROUND = "Stereo Surround"
    ONLINE_VERSUS_MULTIPLAYER = "Online Versus Multiplayer"
    MULTIPLAYER = "Multiplayer"
    MEMORY_CARD = "Memory Card"
    OFFLINE_COOP_MULTIPLAYER = "Offline Co-Op Multiplayer"
    CLOUD_SAVES = "Cloud Saves"
    BATTLE_ROYALE = "Battle Royale"
    CONTROLLER_SUPPORT = "Controller Support"
    DUALSHOCK = "DualShock"
    SPLIT_SCREEN = "Split Screen"
    COOPERATIVE = "Co-Operative"
    MEMORY_BLOCKS = "Memory Blocks"
    VR = "VR"
    SINGLE_PLAYER = "Single Player"
    MMO = "Massively Multiplayer Online (MMO)"
    VIBRATION = "Vibration"
    DUALSHOCK_4 = "DualShock 4"
    XBOX_PLAY_ANYWHERE = "Xbox Play Anywhere"
    FULL_CONTROLLER_SUPPORT = "Full Controller Support"
    NUMBER_OF_PLAYERS = "Number Of Players"

    @classmethod
    def from_string(cls, feature_str: Optional[str]) -> 'Features':
        """
        Convert a string to the corresponding enum value

        Args:
            feature_str: String representation of game feature

        Returns:
            Features enum value

        Raises:
            InvalidFeatureError: If the string doesn't match any valid feature
        """
        if not feature_str:
            raise InvalidFeatureError("Feature string cannot be empty")

        # Try direct match first
        for feature in cls:
            if feature.value == feature_str:
                return feature

        # Try case-insensitive match
        for feature in cls:
            if feature.value.lower() == feature_str.lower():
                return feature

        # Raise exception if no match found
        raise InvalidFeatureError(f"Invalid feature: {feature_str}")

    @classmethod
    def from_list(cls, feature_strings: List[str]) -> List['Features']:
        """
        Convert a list of strings to corresponding enum values

        Args:
            feature_strings: List of string representations of features

        Returns:
            List of Features enum values (invalid features are skipped)
        """
        features = []
        for feature_str in feature_strings:
            try:
                feature = cls.from_string(feature_str)
                features.append(feature)
            except InvalidFeatureError:
                # Skip invalid features
                pass
        return features


class Genres(BaseEnum):
    ACTION = "Action"
    ADVENTURE = "Adventure"
    ARCADE = "Arcade"
    AVATAR = "Avatar"
    BEAT_EM_UP = "Beat 'em Up"
    BOARD_GAME = "Board Game"
    CARD_BOARD_GAME = "Card & Board Game"
    CASINO = "Casino"
    CLASSICS = "Classics"
    CONSTRUCTION_MANAGEMENT_SIMULATION = "Construction and Management Simulation"
    EDUCATION = "Education"
    FIGHTING = "Fighting"
    FLYING = "Flying"
    HACK_AND_SLASH = "Hack and slash/Beat 'em up"
    HORROR = "Horror"
    INDIE = "Indie"
    KINECT = "Kinect"
    LIFE_SIMULATION = "Life Simulation"
    MMO = "MMO"
    MOBA = "MOBA"
    MOBA_MULTIPLAYER_ONLINE_BATTLE_ARENA = "MOBA (Multiplayer Online Battle Arena)"
    MUSIC = "Music"
    OTHER = "Other"
    PARTY = "Party"
    PINBALL = "Pinball"
    PLATFORM = "Platform"
    PLATFORMER = "Platformer"
    POINT_AND_CLICK = "Point-and-click"
    PRODUCTIVITY = "Productivity"
    PUZZLE = "Puzzle"
    QUIZ_TRIVIA = "Quiz/Trivia"
    RACING = "Racing"
    REAL_TIME_STRATEGY = "Real Time Strategy (RTS)"
    ROLE_PLAYING = "Role-Playing"
    ROLE_PLAYING_RPG = "Role-playing (RPG)"
    SANDBOX = "Sandbox"
    SCI_FI = "Sci-fi"
    SHOOTER = "Shooter"
    SIMULATOR = "Simulator"
    SPORT = "Sport"
    SPORTS = "Sports"
    STEALTH = "Stealth"
    STRATEGY = "Strategy"
    TACTICAL = "Tactical"
    TOOLS = "Tools"
    TURN_BASED = "Turn-based"
    TURN_BASED_STRATEGY = "Turn-based strategy (TBS)"
    UNIQUE = "Unique"
    UNKNOWN = "Unknown"
    VEHICLE_SIMULATION = "Vehicle Simulation"
    VISUAL_NOVEL = "Visual Novel"
    VR = "VR"
    WORD = "Word"

    @classmethod
    def from_string(cls, genre_str: Optional[str]) -> 'Genres':
        """
        Convert a string to the corresponding enum value

        Args:
            genre_str: String representation of genre

        Returns:
            Genres enum value

        Raises:
            InvalidGenreError: If the string doesn't match any valid genre
        """
        if not genre_str:
            raise InvalidGenreError("Genre string cannot be empty")

        # Normalize input
        genre_lower = genre_str.lower().strip()

        # Try direct match first
        for genre in cls:
            if genre.value == genre_str:
                return genre

        # Try case-insensitive match
        for genre in cls:
            if genre.value.lower() == genre_lower:
                return genre

        # Define alternative mappings for common variations
        mappings = {
            # RPG variations
            "rpg": cls.ROLE_PLAYING_RPG,
            "role playing": cls.ROLE_PLAYING_RPG,
            "role-playing": cls.ROLE_PLAYING_RPG,
            "roleplaying": cls.ROLE_PLAYING_RPG,
            "role_playing_games": cls.ROLE_PLAYING_RPG,

            # Platform variations
            "platform": cls.PLATFORMER,
            "platforming": cls.PLATFORMER,

            # Simulation variations
            "simulation": cls.SIMULATOR,
            "sim": cls.SIMULATOR,

            # Beat em up variations
            "beat em up": cls.BEAT_EM_UP,
            "beat 'em up": cls.BEAT_EM_UP,
            "hack and slash": cls.HACK_AND_SLASH,

            # Strategy variations
            "rts": cls.REAL_TIME_STRATEGY,
            "real time strategy": cls.REAL_TIME_STRATEGY,
            "tbs": cls.TURN_BASED_STRATEGY,
            "turn based strategy": cls.TURN_BASED_STRATEGY,
            "turn-based": cls.TURN_BASED,

            # Music/Rhythm variations
            "music/rhythm": cls.MUSIC,
            "rhythm": cls.MUSIC,

            # Family/Casual games
            "family": cls.PARTY,
            "casual": cls.PARTY,

            # Flying/Flight variations
            "flight": cls.FLYING,
            "flying": cls.FLYING,

            # Quiz/Trivia variations
            "quiz": cls.QUIZ_TRIVIA,
            "trivia": cls.QUIZ_TRIVIA,

            # Xbox-specific
            "kinect": cls.KINECT,
            "classics": cls.CLASSICS,
            "other": cls.OTHER,
            "card & board": cls.CARD_BOARD_GAME,
            "avatar": cls.AVATAR,
            "tools": cls.TOOLS,
            "word": cls.WORD,
            "multi-player online battle arena": cls.MOBA_MULTIPLAYER_ONLINE_BATTLE_ARENA,

            # Unique/Other catch-all
            "unique": cls.UNIQUE,

            # Other common variations
            "sci fi": cls.SCI_FI,
            "science fiction": cls.SCI_FI,
            "mmo": cls.MMO,
            "massively multiplayer": cls.MMO,
            "vr": cls.VR,
            "virtual reality": cls.VR
        }

        # Check alternative mappings
        if genre_lower in mappings:
            return mappings[genre_lower]

        # Try keyword matching for partial matches
        for keyword, genre_enum in mappings.items():
            if keyword in genre_lower:
                return genre_enum

        # Try splitting on delimiters and mapping individual parts
        delimiters = r'[&/,\s]+|(\s+and\s+)'
        parts = [part.strip().lower() for part in re.split(delimiters, genre_lower) if part and part.strip()]

        if len(parts) > 1:
            # Try to map each part
            for part in parts:
                # Try direct mapping first
                for genre in cls:
                    if genre.value.lower() == part:
                        return genre

                # Try alternative mappings
                if part in mappings:
                    return mappings[part]

        # Raise exception if no match found
        raise InvalidGenreError(f"Invalid genre: {genre_str}")

    @classmethod
    def from_list(cls, genre_strings: List[str]) -> List['Genres']:
        """
        Convert a list of strings to corresponding enum values

        Args:
            genre_strings: List of string representations of genres

        Returns:
            List of Genres enum values (invalid genres are skipped)
        """
        genres = []
        for genre_str in genre_strings:
            try:
                genre = cls.from_string(genre_str)
                genres.append(genre)
            except InvalidGenreError:
                # Skip invalid genres
                pass
        return genres


class Regions(BaseEnum):
    ASIA = "Asia"
    WORLD = "World"
    USA = "USA"
    EUROPE = "Europe"
    JAPAN = "Japan"

    @classmethod
    def from_string(cls, region_str: Optional[str]) -> 'Regions':
        """
        Convert a string to the corresponding enum value

        Args:
            region_str: String representation of region

        Returns:
            Regions enum value

        Raises:
            InvalidRegionError: If the string doesn't match any valid region
        """
        if not region_str:
            raise InvalidRegionError("Region string cannot be empty")

        # Try direct match first
        for region in cls:
            if region.value == region_str:
                return region

        # Try case-insensitive match
        for region in cls:
            if region.value.lower() == region_str.lower():
                return region

        # Raise exception if no match found
        raise InvalidRegionError(f"Invalid region: {region_str}")

    @classmethod
    def from_list(cls, region_strings: List[str]) -> List['Regions']:
        """
        Convert a list of strings to corresponding enum values

        Args:
            region_strings: List of string representations of regions

        Returns:
            List of Regions enum values (invalid regions are skipped)
        """
        regions = []
        for region_str in region_strings:
            try:
                region = cls.from_string(region_str)
                regions.append(region)
            except InvalidRegionError:
                # Skip invalid regions
                pass
        return regions


class LauncherType(BaseEnum):
    """Types of game launchers for external games"""
    EPIC = "Epic Games Store"
    GOG = "GOG Galaxy"
    STEAM = "Steam"
    AMAZON = "Amazon Games"
    NONE = "None"

    @classmethod
    def from_string(cls, launcher_str: Optional[str]) -> 'LauncherType':
        """
        Convert a string to the corresponding enum value

        Args:
            launcher_str: String representation of launcher type

        Returns:
            LauncherType enum value

        Raises:
            InvalidLauncherTypeError: If the string doesn't match any valid launcher type
        """
        if not launcher_str:
            return cls.NONE

        # Try direct match first
        for launcher in cls:
            if launcher.value == launcher_str or launcher.name == launcher_str:
                return launcher

        # Try case-insensitive match
        for launcher in cls:
            if launcher.value.lower() == launcher_str.lower() or launcher.name.lower() == launcher_str.lower():
                return launcher

        # Raise exception if no match found
        raise InvalidLauncherTypeError(f"Invalid launcher type: {launcher_str}")
