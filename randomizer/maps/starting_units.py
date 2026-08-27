"""Mission-start unit policy for native buffs and production clones.

Map-authored objects keep their original TechnoType IDs because campaign
triggers can compare those IDs directly.  A player-production clone may carry
the same earned buffs, but it is only a factory/sidebar identity; it is never
substituted into an authored placement.
"""

from dataclasses import dataclass

from .houses import (
    canonical_house_name,
    map_house_records,
    player_controlled_houses,
    resolve_configured_helper_houses,
)
from .ini import all_section_value_maps


PLACEMENT_SECTIONS = ('Infantry', 'Units', 'Aircraft', 'Structures')


@dataclass(frozen=True)
class StartingUnitBuffPlan:
    """Native type-level buff eligibility for authored starting objects."""

    friendly_type_ids: frozenset
    opponent_type_ids: frozenset
    native_direct_type_ids: frozenset
    shared_type_ids: frozenset


def starting_unit_buff_plan(
    lines,
    configured_helper_houses=(),
    excluded_player_houses=(),
):
    """Classify placed TechnoTypes without changing any placement identity.

    ``native_direct_type_ids`` contains friendly starting types that no
    opponent also starts with.  The later direct-buff pass still performs its
    stricter global ownership and shared-weapon checks before editing a native
    TechnoType.  Player-built copies use their isolated production clone.
    """
    sections = all_section_value_maps(lines)
    records = map_house_records(lines, sections=sections)
    excluded = {
        str(house or '').strip().lower()
        for house in excluded_player_houses
        if str(house or '').strip()
    }
    player_houses = [
        house
        for house in player_controlled_houses(lines, records=records)
        if house.lower() not in excluded
    ]
    helper_houses, _ = resolve_configured_helper_houses(
        records,
        configured_helper_houses,
        player_houses,
    )
    friendly_houses = {
        house.lower() for house in player_houses + helper_houses
    }

    friendly_types = set()
    opponent_types = set()
    sections_by_lower = {
        str(name).lower(): values for name, values in sections.items()
    }
    for section in PLACEMENT_SECTIONS:
        for value in sections_by_lower.get(section.lower(), {}).values():
            tokens = [token.strip() for token in str(value).split(',')]
            if len(tokens) < 2 or not tokens[1]:
                continue
            raw_house, type_id = tokens[0], tokens[1].upper()
            house = canonical_house_name(records, raw_house)
            if house and house.lower() in friendly_houses:
                friendly_types.add(type_id)
            else:
                # Neutral, unknown, and hostile ownership are all unsafe for
                # a global native TechnoType buff.
                opponent_types.add(type_id)

    shared = friendly_types.intersection(opponent_types)
    return StartingUnitBuffPlan(
        friendly_type_ids=frozenset(friendly_types),
        opponent_type_ids=frozenset(opponent_types),
        native_direct_type_ids=frozenset(friendly_types - shared),
        shared_type_ids=frozenset(shared),
    )
