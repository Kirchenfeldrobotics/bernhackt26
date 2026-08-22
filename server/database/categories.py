"""The category vocabulary.

Fill this in once the categories are decided. Categories are stored as plain
strings in the database, so adding one here needs no migration.
"""

CATEGORIES: list[str] = [
    # TODO: e.g. "Retail", "Logistics", "Manufacturing", ...
]


def is_valid(category: str | None) -> bool:
    """True if the category is known (or deliberately unset)."""
    if category is None:
        return True
    return not CATEGORIES or category in CATEGORIES
