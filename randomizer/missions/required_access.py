"""Keep exact native types used by player construction events buildable.

Event 19 compares a BuildingTypes index, not an Image or a clone identity.
These mission-local grants are independent of rewards and never alter saved
progression. Explicit reviews cover objectives expressed through other events.
"""

from randomizer.maps.houses import (
    canonical_house_name, map_house_records, player_controlled_houses,
)
from randomizer.maps.ini import all_section_value_maps
from randomizer.core.collections import comma_items
from randomizer.missions.overrides import MISSION_REQUIRED_ACCESS_RULES


def mission_required_access_rules(mission, lines, installed_sections):
    sections = all_section_value_maps(lines)
    records = map_house_records(lines, sections=sections)
    players = set(player_controlled_houses(lines, records=records))
    registries = dict(installed_sections.get('BuildingTypes', {}))
    registries.update(sections.get('BuildingTypes', {}))
    # The engine resolves numeric events against registry order, not the
    # arbitrary INI keys used when adding randomizer types.
    building_ids = list(dict.fromkeys(str(v).upper() for v in registries.values()))
    required = set()
    for event_id, value in sections.get('Events', {}).items():
        trigger = sections.get('Triggers', {}).get(event_id, '').split(',')
        if not trigger or canonical_house_name(records, trigger[0]) not in players:
            continue
        tokens = [token.strip() for token in str(value).split(',')]
        try:
            count = int(tokens[0])
            groups = []
            offset = 1
            for _ in range(count):
                size = 4 if tokens[offset + 1] == '2' else 3
                group = tokens[offset:offset + size]
                if len(group) != size:
                    raise ValueError('truncated event')
                groups.append(group)
                offset += size
            if offset != len(tokens):
                continue
            for group in groups:
                if group[0] == '19' and group[1] == '0':
                    index = int(group[2])
                    if 0 <= index < len(building_ids):
                        required.add(building_ids[index])
        except (ValueError, IndexError):
            continue

    reviewed = MISSION_REQUIRED_ACCESS_RULES.get(mission['code'], {})
    required.update(reviewed)
    # A required building can itself depend on a suppressed power provider
    # (Waste Facility -> Missile Silo). Keep exact building dependencies too.
    pending = list(required)
    registered = set(building_ids)
    while pending:
        source_id = pending.pop()
        values = {k.lower(): v for k, v in installed_sections.get(source_id, {}).items()}
        values.update(sections.get(source_id, {}))
        values.update({k.lower(): v for k, v in reviewed.get(source_id, {}).items()})
        for dependency in comma_items(values.get('prerequisite', '')):
            dependency = dependency.upper()
            if dependency in registered and dependency not in required:
                required.add(dependency)
                pending.append(dependency)

    rules = {}
    for source_id in sorted(required):
        installed = {k.lower(): v for k, v in installed_sections.get(source_id, {}).items()}
        authored = sections.get(source_id, {})
        # Keep faction production and authored prerequisite chains intact.
        values = {'TechLevel': '1'}
        for key in ('Prerequisite', 'PrerequisiteOverride', 'Prerequisite.Negative',
                    'RequiredHouses', 'ForbiddenHouses', 'FactoryOwners.Forbidden'):
            values[key] = authored.get(key.lower(), installed.get(key.lower()))
        limit = authored.get('buildlimit', installed.get('buildlimit'))
        try:
            values['BuildLimit'] = limit if int(limit) > 0 else None
        except (TypeError, ValueError):
            values['BuildLimit'] = None
        rules[source_id] = values
    for section, values in reviewed.items():
        rules.setdefault(section, {}).update(values)
    return rules
