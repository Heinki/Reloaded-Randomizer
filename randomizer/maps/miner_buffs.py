"""Isolate refinery production and safely upgrade starting player miners."""

from randomizer.core.collections import comma_items, unique_in_order
from randomizer.maps.base import _collision_safe_type_id
from randomizer.maps.buff_values import _register_map_type
from randomizer.maps.houses import map_house_records, player_controlled_houses
from randomizer.maps.ini import (
    all_section_value_maps, merge_ini_section_values, section_value_map_preserve,
)
from randomizer.maps.production import PLAYER_ORIGINAL_PRODUCTION_GATE_ID
from randomizer.maps.prerequisites import expand_prerequisite_paths
from randomizer.maps.special_buildings import refinery_free_unit_pairs
from randomizer.missions.access import MINERS


def _values(sections, name):
    return next((
        {str(key).lower(): str(value) for key, value in values.items()}
        for section, values in sections.items()
        if str(section).casefold() == str(name).casefold()
    ), {})


def _key_spellings(lines, installed_sections, name):
    spellings = {
        str(key).lower(): str(key)
        for section, values in installed_sections.items()
        if str(section).casefold() == str(name).casefold()
        for key in values
    }
    spellings.update({
        str(key).lower(): str(key)
        for key in section_value_map_preserve(lines, name)
    })
    return spellings


def player_refinery_rules(
    lines, installed_sections, native_sections, clone_handled, *,
    preserved_native_ids=(),
):
    """Expose private refineries unless mission checks require native types."""
    sections = all_section_value_maps(lines)
    rules, refineries = {}, {}
    refinery_pairs = refinery_free_unit_pairs(native_sections, installed_sections)
    reserved = {str(name).casefold() for name in installed_sections}
    reserved.update(str(name).casefold() for name in sections)
    preserved_native_ids = {str(item).upper() for item in preserved_native_ids}
    for refinery, miner in refinery_pairs.items():
        # Event 19 checks the BuildingTypes index. GroupAs cannot make
        # a private refinery satisfy it. The pipeline already grants and
        # protects these exact native types; do not gate them again here.
        if refinery in preserved_native_ids:
            continue
        miner_clone = str((clone_handled.get(miner) or {}).get('clone_id') or '')
        if not miner_clone:
            continue
        values = _values(installed_sections, refinery)
        values.update(_values(native_sections, refinery))
        if int(values.get('techlevel', '-1')) < 0:
            continue
        clone = _collision_safe_type_id('RLRP' + refinery, 'player-refinery:' + refinery, reserved)
        miner_values = _values(sections, miner_clone)
        # Lookup maps normalize keys. Standalone engine rules must retain the
        # installed/authored spelling, especially FreeUnit and TechLevel.
        spellings = _key_spellings(lines, installed_sections, refinery)
        cloned = {
            spellings.get(key, key): value for key, value in values.items()
            if key not in {
                'image', 'groupas', 'freeunit', 'owner', 'requiredhouses',
                'techlevel', 'aibuildthis', 'forbiddenhouses', 'factoryowners',
                'factoryowners.forbidden', 'prerequisite.negative',
                'prerequisite.stolentechs', 'buildlimit',
            }
        }
        cloned.update({
            'Image': values.get('image') or refinery,
            'GroupAs': values.get('groupas') or refinery,
            'FreeUnit': miner_clone,
            'Owner': miner_values['owner'],
            'RequiredHouses': miner_values['requiredhouses'],
            'TechLevel': '1', 'AIBuildThis': 'no',
        })
        rules[clone] = cloned
        _register_map_type(rules, lines, installed_sections, 'BuildingTypes', clone)
        negatives = comma_items(values.get('prerequisite.negative', ''))
        rules[refinery] = {'Prerequisite.Negative': ','.join(unique_in_order([
            *negatives, PLAYER_ORIGINAL_PRODUCTION_GATE_ID,
        ]))}
        refineries[refinery] = clone
        clone_handled[refinery] = {
            'clone_id': clone, 'selection_group': cloned['GroupAs'],
            'reference_clone_id': '', 'clone_base_values': {},
            'unit_buff_types': set(), 'clone_unit_buff_types': set(),
            'clone_weapon_buff_types': set(), 'weapon_clone_ids': {},
        }
    # Dock compares exact BuildingTypes, including captured private refineries.
    # Adding destinations changes no native AI miner stats.
    miner_sources = {values[0] for values in MINERS.values()}
    miner_sources.update(refinery_pairs.values())
    for source in sorted(miner_sources):
        details = clone_handled.get(source, {})
        native_values = _values(installed_sections, source)
        native_values.update(_values(native_sections, source))
        native_docks = comma_items(native_values.get('dock', ''))
        for identifier in unique_in_order([
            source, str(details.get('clone_id') or ''), str(details.get('reference_clone_id') or ''),
        ]):
            if not identifier:
                continue
            values = _values(installed_sections, identifier)
            values.update(_values(sections, identifier))
            docks = unique_in_order(native_docks + comma_items(values.get('dock', '')))
            additions = [refineries[dock.upper()] for dock in docks if dock.upper() in refineries]
            if additions or docks != comma_items(values.get('dock', '')):
                rules.setdefault(identifier, {})['Dock'] = ','.join(unique_in_order(docks + additions))
            if identifier.upper() != source.upper():
                # A captured player miner must lose player upgrades, including
                # reference clones used by authored mission placements/teams.
                rules.setdefault(identifier, {})['Convert.HumanToComputer'] = source
    replacements = {
        source.upper(): unique_in_order(
            str(details.get(key) or '')
            for key in ('clone_id', 'reference_clone_id')
            if str(details.get(key) or '')
        )
        for source, details in clone_handled.items()
    }
    # Deployable refineries such as YAREFN have no FreeUnit, but their private
    # forms must still satisfy PROC and any exact refinery prerequisite.
    refinery_replacements = dict(refineries)
    for _miner, _factory, refinery in MINERS.values():
        clone = str((clone_handled.get(refinery) or {}).get('clone_id') or '')
        if clone:
            refinery_replacements[refinery] = clone
    generic = _values(installed_sections, 'GenericPrerequisites')
    generic.update(_values(sections, 'GenericPrerequisites'))
    generic_spellings = _key_spellings(lines, installed_sections, 'GenericPrerequisites')
    for key, value in generic.items():
        originals = comma_items(value)
        additions = [refinery_replacements[item.upper()] for item in originals
                     if item.upper() in refinery_replacements]
        if additions:
            rules.setdefault('GenericPrerequisites', {})[generic_spellings.get(key, key)] = ','.join(
                unique_in_order(originals + additions)
            )

    # PROC is a built-in prerequisite group, separate from Ares' custom groups.
    general = _values(installed_sections, 'General')
    general.update(_values(sections, 'General'))
    processors = comma_items(general.get('prerequisiteproc', ''))
    additions = [refinery_replacements[item.upper()] for item in processors
                 if item.upper() in refinery_replacements]
    if additions:
        rules.setdefault('General', {})['PrerequisiteProc'] = ','.join(
            unique_in_order(processors + additions)
        )
    # Ares supports multiple non-building alternatives. Preserve the native
    # mobile miner and add its private player forms, so undeployed miners also
    # satisfy the authored PROC gate on Yuri's vehicle factory.
    alternates = comma_items(general.get('prerequisiteprocalternate', ''))
    expanded_alternates = unique_in_order([
        *alternates,
        *(clone for item in alternates for clone in replacements.get(item.upper(), ())),
    ])
    if expanded_alternates != alternates:
        rules.setdefault('General', {})['PrerequisiteProcAlternate'] = ','.join(expanded_alternates)

    for details in clone_handled.values():
        for key in ('clone_id', 'reference_clone_id'):
            clone = str(details.get(key) or '')
            if not clone:
                continue
            values = _values(sections, clone)
            values.update(_values(rules, clone))
            rules.setdefault(clone, {}).update(expand_prerequisite_paths(values, replacements))

    return rules, refineries


def upgrade_starting_player_miners(lines, installed_sections, native_sections, clone_handled):
    """Rewrite only human miner placements without exact scripted type checks.

    Preserve every other placement field, including mission tag and health.
    The returned exact replacements are checked by the authored identity audit.
    """
    sections = all_section_value_maps(lines)
    records = map_house_records(lines, sections=sections)
    allowed_houses = {house.casefold() for house in player_controlled_houses(lines, records=records)}
    sources = {values[0] for values in MINERS.values()}
    sources.update(refinery_free_unit_pairs(native_sections, installed_sections).values())
    scripted = {
        token.strip().upper()
        for section in ('Events', 'Actions')
        for value in native_sections.get(section, {}).values()
        for token in str(value).split(',')
    }
    replacements, rules = {}, {}
    for key, value in sections.get('Units', {}).items():
        tokens = str(value).split(',')
        if len(tokens) < 2 or tokens[0].strip().casefold() not in allowed_houses:
            continue
        source = tokens[1].strip().upper()
        clone = str((clone_handled.get(source) or {}).get('clone_id') or '')
        if source not in sources or source in scripted or not clone:
            continue
        tokens[1] = clone
        rules.setdefault('Units', {})[key] = ','.join(tokens)
        replacements[('Units', str(key).casefold())] = clone
    merge_ini_section_values(lines, rules)
    return replacements


def validate_refinery_miner_isolation(
    lines, installed_sections, native_sections, clone_handled, *,
    preserved_native_ids=(),
):
    """Reject shared spawn leaks and broken private refinery/miner links."""
    sections = all_section_value_maps(lines)
    clone_ids = {
        str(details.get(key) or '').upper()
        for details in clone_handled.values()
        for key in ('clone_id', 'reference_clone_id')
    } - {''}
    failures = []
    refinery_pairs = refinery_free_unit_pairs(native_sections, installed_sections)
    preserved_native_ids = {str(item).upper() for item in preserved_native_ids}
    registered_buildings = {
        value.upper()
        for entries in (installed_sections, sections)
        for value in _values(entries, 'BuildingTypes').values()
    }
    registered_units = {
        value.upper()
        for entries in (installed_sections, sections)
        for value in _values(entries, 'VehicleTypes').values()
    }
    for refinery, miner in refinery_pairs.items():
        values = _values(installed_sections, refinery)
        values.update(_values(sections, refinery))
        for key in ('freeunit', 'freeunit2'):
            if any(unit.upper() in clone_ids for unit in comma_items(values.get(key, ''))):
                failures.append(f'{refinery}.{key} points to a player clone')
        clone = str((clone_handled.get(refinery) or {}).get('clone_id') or '')
        miner_clone = str((clone_handled.get(miner) or {}).get('clone_id') or '')
        if refinery in preserved_native_ids:
            if clone:
                failures.append(f'{refinery} uses a clone despite exact mission checks')
            negatives = {item.upper() for item in comma_items(values.get('prerequisite.negative', ''))}
            if PLAYER_ORIGINAL_PRODUCTION_GATE_ID.upper() in negatives:
                failures.append(f'{refinery} is blocked despite exact mission checks')
            if int(values.get('techlevel', '-1')) < 0:
                failures.append(f'{refinery} is unavailable despite exact mission checks')
            continue
        if not clone:
            authored = _values(installed_sections, refinery)
            authored.update(_values(native_sections, refinery))
            if miner_clone and int(authored.get('techlevel', '-1')) >= 0:
                failures.append(f'{refinery} has no private player refinery')
            continue
        if clone.upper() not in registered_buildings:
            failures.append(f'{clone} is not registered in BuildingTypes')
        if not miner_clone or miner_clone.upper() not in registered_units:
            failures.append(f'{clone} has no registered player miner')
        cloned = section_value_map_preserve(lines, clone)
        if cloned.get('FreeUnit', '').upper() != miner_clone.upper():
            failures.append(f'{clone}.FreeUnit does not spawn {miner_clone}')
        miner_values = _values(sections, miner_clone)
        required_houses = {house.upper() for house in comma_items(miner_values.get('requiredhouses', ''))}
        refinery_houses = {house.upper() for house in comma_items(cloned.get('RequiredHouses', ''))}
        if not required_houses or refinery_houses != required_houses:
            failures.append(f'{clone} does not retain its player miner ownership gate')
        if cloned.get('AIBuildThis', '').lower() != 'no':
            failures.append(f'{clone} permits AI refinery construction')

    refineries = {
        source.upper(): str((clone_handled.get(source) or {}).get('clone_id') or '')
        for source in refinery_pairs
    }
    miner_sources = {values[0] for values in MINERS.values()}
    miner_sources.update(refinery_pairs.values())
    for source in sorted(miner_sources):
        native_values = _values(installed_sections, source)
        native_values.update(_values(native_sections, source))
        native_docks = comma_items(native_values.get('dock', ''))
        expected_docks = unique_in_order(native_docks + [
            refineries[dock.upper()] for dock in native_docks
            if refineries.get(dock.upper())
        ])
        details = clone_handled.get(source, {})
        for identifier in unique_in_order([
            source, str(details.get('clone_id') or ''), str(details.get('reference_clone_id') or ''),
        ]):
            if not identifier:
                continue
            values = _values(installed_sections, identifier)
            values.update(_values(sections, identifier))
            docks = {dock.upper() for dock in comma_items(values.get('dock', ''))}
            for dock in expected_docks:
                if dock.upper() not in docks:
                    failures.append(f'{identifier} cannot dock at {dock}')
            if identifier.upper() != source.upper() and values.get(
                'convert.humantocomputer', ''
            ).upper() != source.upper():
                failures.append(f'{identifier} keeps player upgrades on AI capture')
    return failures
