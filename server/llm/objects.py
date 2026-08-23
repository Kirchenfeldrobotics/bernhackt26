from enum import Enum

__all__ = ["ObjectType"]


# objects a later stage can actually place a fix against
class ObjectType(str, Enum):
    TRASHES = "Trashes"
    TABLES = "Tables"
