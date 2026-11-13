"""Resolve readable map titles for new catalogues and older saved campaigns."""

from pathlib import Path

from randomizer.core.paths import GAME_ROOT
from randomizer.skirmish_factions import map_metadata


def map_name(definition, *, root=None):
    """Keep authored titles; recover blanks from the native catalogue or filename."""
    name = str(definition.get('name') or '').strip()
    if name:
        return name
    try:
        metadata = map_metadata(GAME_ROOT if root is None else root, definition)
    except (OSError, ValueError):
        # An older save can refer to a removed custom map or catalogue entry.
        metadata = {}
    description = str(metadata.get('description') or '').strip()
    return description or Path(str(definition.get('path') or '').replace('\\', '/')).stem or 'Unnamed map'
