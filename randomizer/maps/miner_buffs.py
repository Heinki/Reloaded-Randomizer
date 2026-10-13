"""Isolate refinery production and safely upgrade starting player miners."""

from itertools import product
import re

from randomizer.core.collections import comma_items, unique_in_order
from randomizer.maps.base import _collision_safe_type_id
from randomizer.maps.buff_values import _register_map_type
from randomizer.maps.houses import map_house_records, player_controlled_houses
from randomizer.maps.ini import all_section_value_maps, merge_ini_section_values
from randomizer.maps.production import PLAYER_ORIGINAL_PRODUCTION_GATE_ID
from randomizer.maps.special_buildings import refinery_free_unit_pairs
from randomizer.missions.access import MINERS


def _values(sections, name):
    return next((
        {str(key).lower(): str(value) for key, value in values.items()}
        for section, values in sections.items()
        if str(section).casefold() == str(name).casefold()
    ), {})


def _expand_prerequisites(values, replacements):
    """Add full AND paths, retaining every factory/support requirement."""
    paths = [comma_items(values.get('prerequisite', ''))]
    paths.extend(
        comma_items(value) for key, value in values.items()
        if re.fullmatch(r'prerequisite\.list\d+', key)
    )
    paths = [path for path in paths if path]
    expanded = []
    for path in paths:
        choices = [(item, *replacements.get(item.upper(), ())) for item in path]
        for alternate in product(*choices):
            text = ','.join(alternate)
            if text not in expanded:
                expanded.append(text)
    if len(expanded) <= len({','.join(path) for path in paths}):
        return {}
    rules = {'Prerequisite.Lists': str(len(expanded))}
    rules.update({f'Prerequisite.List{index}': path for index, path in enumerate(expanded)})
    return rules


def player_refinery_rules(lines, installed_sections, native_sections, clone_handled):
    """Keep native refinery FreeUnit unchanged; expose private human copies."""
    sections = all_section_value_maps(lines)
    rules, refineries = {}, {}
    reserved = {str(name).casefold() for name in installed_sections}
    reserved.update(str(name).casefold() for name in sections)
    for refinery, miner in refinery_free_unit_pairs(native_sections, installed_sections).items():
        miner_clone = str((clone_handled.get(miner) or {}).get('clone_id') or '')
        if not miner_clone:
            continue
        values = _values(installed_sections, refinery)
        values.update(_values(native_sections, refinery))
        if int(values.get('techlevel', '-1')) < 0:
            continue
        clone = _collision_safe_type_id('RLRP' + refinery, 'player-refinery:' + refinery, reserved)
        miner_values = _values(sections, miner_clone)
        cloned = dict(values)
        cloned.update({
            'image': values.get('image') or refinery,
            'groupas': values.get('groupas') or refinery,
            'freeunit': miner_clone,
            'owner': miner_values['owner'],
            'requiredhouses': miner_values['requiredhouses'],
            'techlevel': '1', 'aibuildthis': 'no',
        })
        for key in ('forbiddenhouses', 'factoryowners', 'factoryowners.forbidden',
                    'prerequisite.negative', 'prerequisite.stolentechs', 'buildlimit'):
            cloned.pop(key, None)
        rules[clone] = cloned
        _register_map_type(rules, lines, installed_sections, 'BuildingTypes', clone)
        negatives = comma_items(values.get('prerequisite.negative', ''))
        rules[refinery] = {'Prerequisite.Negative': ','.join(unique_in_order([
            *negatives, PLAYER_ORIGINAL_PRODUCTION_GATE_ID,
        ]))}
        refineries[refinery] = clone
        clone_handled[refinery] = {
            'clone_id': clone, 'selection_group': cloned['groupas'],
            'reference_clone_id': '', 'clone_base_values': {},
            'unit_buff_types': set(), 'clone_unit_buff_types': set(),
            'clone_weapon_buff_types': set(), 'weapon_clone_ids': {},
        }
    if not refineries:
        return {}, refineries

    replacements = {
        source.upper(): unique_in_order(
            str(details.get(key) or '')
            for key in ('clone_id', 'reference_clone_id')
            if str(details.get(key) or '')
        )
        for source, details in clone_handled.items()
    }
    generic = _values(installed_sections, 'GenericPrerequisites')
    generic.update(_values(sections, 'GenericPrerequisites'))
    for key, value in generic.items():
        originals = comma_items(value)
        additions = [refineries[item.upper()] for item in originals if item.upper() in refineries]
        if additions:
            rules.setdefault('GenericPrerequisites', {})[key] = ','.join(unique_in_order(originals + additions))

    for details in clone_handled.values():
        for key in ('clone_id', 'reference_clone_id'):
            clone = str(details.get(key) or '')
            if not clone:
                continue
            values = _values(sections, clone)
            values.update(_values(rules, clone))
            rules.setdefault(clone, {}).update(_expand_prerequisites(values, replacements))

    # Dock compares exact BuildingTypes, including captured private refineries.
    # Adding destinations changes no native AI miner stats.
    miner_sources = {values[0] for values in MINERS.values()}
    miner_sources.update(refinery_free_unit_pairs(native_sections, installed_sections).values())
    for source in sorted(miner_sources):
        details = clone_handled.get(source, {})
        for identifier in unique_in_order([
            source, str(details.get('clone_id') or ''), str(details.get('reference_clone_id') or ''),
        ]):
            if not identifier:
                continue
            values = _values(installed_sections, identifier)
            values.update(_values(sections, identifier))
            docks = comma_items(values.get('dock', ''))
            additions = [refineries[dock.upper()] for dock in docks if dock.upper() in refineries]
            if additions:
                rules.setdefault(identifier, {})['Dock'] = ','.join(unique_in_order(docks + additions))
        clone = str(details.get('clone_id') or '')
        if clone:
            rules.setdefault(clone, {})['Convert.HumanToComputer'] = source
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


def validate_refinery_miner_isolation(lines, installed_sections, native_sections, clone_handled):
    """Reject shared refinery spawn fields that point to player clones."""
    sections = all_section_value_maps(lines)
    clone_ids = {
        str(details.get(key) or '').upper()
        for details in clone_handled.values()
        for key in ('clone_id', 'reference_clone_id')
    } - {''}
    failures = []
    for refinery in refinery_free_unit_pairs(native_sections, installed_sections):
        values = _values(installed_sections, refinery)
        values.update(_values(sections, refinery))
        for key in ('freeunit', 'freeunit2'):
            if any(unit.upper() in clone_ids for unit in comma_items(values.get(key, ''))):
                failures.append(f'{refinery}.{key} points to a player clone')
    return failures
