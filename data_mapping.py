import enum

from typing import Optional, List


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


class CompletionStatus(enum.Enum):
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


class Platforms(enum.Enum):
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

        # Try direct match first
        for platform in cls:
            if platform.value == platform_str:
                return platform

        # Try case-insensitive match
        for platform in cls:
            if platform.value.lower() == platform_str.lower():
                return platform

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


class AgeRatings(enum.Enum):
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


class Features(enum.Enum):
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


class Genres(enum.Enum):
    MOBA = "MOBA"
    TACTICAL = "Tactical"
    STRATEGY = "Strategy"
    ARCADE = "Arcade"
    PLATFORM = "Platform"
    FLIGHT_SIMULATOR = "Flight Simulator"
    TURN_BASED_STRATEGY = "Turn-based strategy (TBS)"
    ROLE_PLAYING_RPG = "Role-playing (RPG)"
    STEALTH = "Stealth"
    SIMULATOR = "Simulator"
    SHOOTER = "Shooter"
    HACK_AND_SLASH = "Hack and slash/Beat 'em up"
    PRODUCTIVITY = "Productivity"
    ACTION = "Action"
    SPORTS = "Sports"
    BEAT_EM_UP = "Beat 'em Up"
    QUIZ_TRIVIA = "Quiz/Trivia"
    REAL_TIME_STRATEGY = "Real Time Strategy (RTS)"
    TURN_BASED = "Turn-based"
    HORROR = "Horror"
    SANDBOX = "Sandbox"
    CARD_BOARD_GAME = "Card & Board Game"
    MUSIC = "Music"
    ROLE_PLAYING = "Role-Playing"
    CONSTRUCTION_MANAGEMENT_SIMULATION = "Construction and Management Simulation"
    VISUAL_NOVEL = "Visual Novel"
    VEHICLE_SIMULATION = "Vehicle Simulation"
    EDUCATION = "Education"
    SCI_FI = "Sci-fi"
    MMO = "MMO"
    SPORT = "Sport"
    INDIE = "Indie"
    BOARD_GAME = "Board Game"
    PLATFORMER = "Platformer"
    PINBALL = "Pinball"
    PUZZLE = "Puzzle"
    LIFE_SIMULATION = "Life Simulation"
    RACING = "Racing"
    POINT_AND_CLICK = "Point-and-click"
    PARTY = "Party"
    CASINO = "Casino"
    ADVENTURE = "Adventure"
    FIGHTING = "Fighting"
    MOBA_MULTIPLAYER_ONLINE_BATTLE_ARENA = "MOBA (Multiplayer Online Battle Arena)"

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

        # Try direct match first
        for genre in cls:
            if genre.value == genre_str:
                return genre

        # Try case-insensitive match
        for genre in cls:
            if genre.value.lower() == genre_str.lower():
                return genre

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


class Regions(enum.Enum):
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
