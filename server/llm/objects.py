"""Object type definitions for room-scan detections/annotations."""

from enum import Enum

__all__ = ["OBJECT_TYPES"]


class OBJECT_TYPES(str, Enum):
    """Detectable object types."""

    TRASHES = "Trashes"
    TABLES = "Tables"
