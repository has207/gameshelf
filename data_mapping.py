import enum

from typing import Optional


class InvalidCompletionStatusError(Exception):
    """Exception raised when an invalid completion status is encountered."""
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
