"""Preserve production requirements across native and private building types."""

import hashlib
from itertools import product

from randomizer.core.collections import comma_items, unique_in_order
from randomizer.maps.ini import all_section_value_maps


def negative_prerequisite_safety_rules(lines, installed_sections):
    """Repair negative prerequisites that Reloaded's AI misindexes.

    The custom Phobos parser uses TechnoTypeClass::FindIndex for negative
    prerequisites, but HouseExt::PrerequisitesMet indexes BuildingTypes with
    the result. Vehicle self-references such as MOBWARG therefore can crash
    AI team selection. Map-added buildings also have combined-array indices
    beyond BuildingTypes. Wrap these in singleton generic groups: Ares keeps
    the exact gate, while Phobos either resolves a building-index group or
    ignores a map-only group it has not loaded. Such buildings are private
    player gates, not prerequisites for native AI production.

    Ares already ignores non-building references, so remove those without
    changing its production behavior or authored BuildLimit. Run last so
    generated clones and gates are included.
    """
    effective = {}
    for source in (installed_sections, all_section_value_maps(lines)):
        for name, values in source.items():
            effective.setdefault(str(name).upper(), {}).update({
                str(key).lower(): value for key, value in values.items()
            })
    buildings = {
        str(identifier).upper()
        for identifier in effective.get('BUILDINGTYPES', {}).values()
    }
    installed_buildings = {
        str(identifier).upper()
        for name, values in installed_sections.items()
        if str(name).casefold() == 'buildingtypes'
        for identifier in values.values()
    }
    generics = set(effective.get('GENERICPREREQUISITES', {}))
    generics.update(('power', 'factory', 'barracks', 'radar', 'tech', 'proc'))
    techno_ids = {
        str(identifier)
        for registry in ('INFANTRYTYPES', 'VEHICLETYPES', 'AIRCRAFTTYPES', 'BUILDINGTYPES')
        for identifier in effective.get(registry, {}).values()
    }
    map_buildings = buildings - installed_buildings
    techno_names = {name.upper() for name in techno_ids}
    rules, repaired = {}, {}
    for identifier in sorted(techno_ids):
        values = effective.get(identifier.upper(), {})
        prerequisites = comma_items(values.get('prerequisite.negative', ''))
        safe, changes = [], []
        for item in prerequisites:
            if item.upper() in map_buildings:
                digest = hashlib.sha256(item.upper().encode('utf-8')).hexdigest()[:16]
                group = 'RLRNEG' + digest
                # Never reuse an unrelated installed/map group or TechnoType.
                existing = effective.get('GENERICPREREQUISITES', {}).get(group.lower())
                if (group.upper() in techno_names
                        or (existing is not None and str(existing).upper() != item.upper())):
                    raise ValueError(f'Negative prerequisite safety group collision: {group}')
                rules.setdefault('GenericPrerequisites', {})[group] = item
                safe.append(group)
                changes.append(f'{item} via {group}')
            elif (item.upper() in buildings or item.lower() in generics
                  or item.lower() in {'none', '<none>'}):
                safe.append(item)
            else:
                changes.append(f'{item} (removed)')
        if changes:
            rules[identifier] = {'Prerequisite.Negative': ','.join(safe)}
            repaired[identifier] = changes
    return rules, repaired


def prerequisite_override_rules(lines, installed_sections):
    """Retain shortcut paths without bypassing house and unlock restrictions.

    Ares evaluates PrerequisiteOverride before Required/ForbiddenHouses and
    TechLevel. Equivalent alternate lists still enforce those restrictions.
    """
    effective = {}
    for source in (installed_sections, all_section_value_maps(lines)):
        for name, values in source.items():
            effective.setdefault(str(name).upper(), {}).update({
                str(key).lower(): value for key, value in values.items()
            })
    identifiers = {
        str(identifier)
        for registry in ('INFANTRYTYPES', 'VEHICLETYPES', 'AIRCRAFTTYPES', 'BUILDINGTYPES')
        for identifier in effective.get(registry, {}).values()
    }
    rules = {}
    for identifier in sorted(identifiers):
        values = effective.get(identifier.upper(), {})
        shortcuts = [
            item for item in comma_items(values.get('prerequisiteoverride', ''))
            if item.lower() not in {'none', '<none>'}
        ]
        if not shortcuts:
            continue
        count = int(values.get('prerequisite.lists', '0'))
        changes = {'PrerequisiteOverride': 'none'}
        for shortcut in shortcuts:
            count += 1
            changes[f'Prerequisite.List{count}'] = shortcut
        changes['Prerequisite.Lists'] = str(count)
        rules[identifier] = changes
    return rules


def expand_prerequisite_paths(values, replacements):
    """Add full AND paths, retaining every factory/support requirement."""
    paths = [comma_items(values.get('prerequisite.list0', values.get('prerequisite', '')))]
    extra_lists = int(values.get('prerequisite.lists', '0'))
    paths.extend(
        comma_items(values.get(f'prerequisite.list{index}', ''))
        for index in range(1, extra_lists + 1)
    )
    # An empty active path already permits production. Do not replace it with
    # a restrictive List0 or activate an authored but disabled extra list.
    if any(not path for path in paths):
        return {}
    seen = {tuple(item.upper() for item in path) for path in paths}
    rules = {}
    next_index = extra_lists + 1
    for path in paths:
        choices = [(item, *replacements.get(item.upper(), ())) for item in path]
        for alternate in product(*choices):
            identity = tuple(item.upper() for item in alternate)
            if identity in seen:
                continue
            seen.add(identity)
            # Keep authored list indices and their exact type references.
            rules[f'Prerequisite.List{next_index}'] = ','.join(alternate)
            next_index += 1
    if rules:
        rules['Prerequisite.Lists'] = str(next_index - 1)
    return rules


def player_building_prerequisite_rules(lines, installed_sections, clone_handled):
    """Let private buildings satisfy their native production gates.

    Ordinary campaign structures retain native identities and therefore are
    absent from the player clone list. Include every registered TechnoType,
    reading final map overrides after refinery and mission-access preparation.
    """
    sections = all_section_value_maps(lines)
    # Power plants, tech centers and defense/support buildings are also exact
    # prerequisite identities. Restricting this to yards and refineries leaves
    # an upgraded NODAPWR unable to satisfy POWER, blocking the whole tech tree.
    building_sources = {
        str(identifier).upper()
        for source_sections in (installed_sections, sections)
        for name, values in source_sections.items()
        if str(name).casefold() == 'buildingtypes'
        for identifier in values.values()
    }

    replacements = {
        source: unique_in_order(
            str(details[key])
            for key in ('clone_id', 'reference_clone_id')
            if details.get(key) and str(details[key]).upper() != source
        )
        for source in building_sources
        if (details := clone_handled.get(source))
    }
    replacements = {source: clones for source, clones in replacements.items() if clones}
    if not replacements:
        return {}

    effective = {}
    for source_sections in (installed_sections, sections):
        for name, values in source_sections.items():
            effective.setdefault(str(name).upper(), {}).update({
                str(key).lower(): (key, value) for key, value in values.items()
            })

    def expand_members(value):
        originals = comma_items(value)
        return unique_in_order([
            *originals,
            *(clone for item in originals for clone in replacements.get(item.upper(), ())),
        ])

    rules = {}
    for key, value in effective.get('GENERICPREREQUISITES', {}).values():
        expanded = expand_members(value)
        if expanded != comma_items(value):
            rules.setdefault('GenericPrerequisites', {})[key] = ','.join(expanded)
    for field in ('Power', 'Factory', 'Barracks', 'Radar', 'Tech', 'Proc'):
        key = 'Prerequisite' + field
        value = effective.get('GENERAL', {}).get(key.lower(), (key, ''))[1]
        expanded = expand_members(value)
        if expanded != comma_items(value):
            rules.setdefault('General', {})[key] = ','.join(expanded)

    techno_ids = {
        str(identifier)
        for registry in ('INFANTRYTYPES', 'VEHICLETYPES', 'AIRCRAFTTYPES', 'BUILDINGTYPES')
        for _key, identifier in effective.get(registry, {}).values()
    }
    for identifier in sorted(techno_ids):
        values = {
            key: value for key, (_spelling, value) in effective.get(identifier.upper(), {}).items()
        }
        additions = expand_prerequisite_paths(values, replacements)
        override = values.get('prerequisiteoverride', '')
        expanded_override = expand_members(override)
        if expanded_override != comma_items(override):
            additions['PrerequisiteOverride'] = ','.join(expanded_override)
        if additions:
            rules[identifier] = additions
    return rules
