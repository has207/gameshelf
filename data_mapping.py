import enum

from typing import Optional, List


class InvalidCompletionStatusError(Exception):
    """Exception raised when an invalid completion status is encountered."""
    pass


class InvalidPlatformError(Exception):
    """Exception raised when an invalid platform is encountered."""
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
    PSP = "Sony PlayStation Portable"
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
