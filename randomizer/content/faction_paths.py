"""Infer active-faction production paths from installed Reloaded rules.

Broad ``Owner`` lists are common in C&C Reloaded and are not sufficient roster
evidence. This module resolves concrete prerequisites, generic prerequisite
groups, factories, and SuperWeapon provider buildings against the five reviewed
production families. Unknown or incomplete paths remain unresolved.
"""

from functools import lru_cache

from randomizer.config.game_profile import CONTENT_FACTIONS
from randomizer.config.static import load_static_config
from randomizer.content.inventory import (
    FACTION_HOUSE_VARIANTS,
    read_rules_sections,
)


_FACTIONS_CONFIG = load_static_config('factions.json')
_ALL_FACTIONS = frozenset(CONTENT_FACTIONS)
_GENERAL_PREREQUISITES = {
    'POWER': 'PrerequisitePower',
    'FACTORY': 'PrerequisiteFactory',
    'BARRACKS': 'PrerequisiteBarracks',
    'RADAR': 'PrerequisiteRadar',
    'TECH': 'PrerequisiteTech',
    'PROC': 'PrerequisiteProc',
}


def _split(value):
    return tuple(
        item.strip().upper()
        for item in str(value or '').split(',')
        if item.strip() and item.strip().lower() not in {'none', '<none>'}
    )


def _active_eligible_factions(values):
    owners = set(_split(values.get('Owner')))
    required = set(_split(values.get('RequiredHouses')))
    forbidden = set(_split(values.get('ForbiddenHouses')))
    result = []
    for faction, houses in FACTION_HOUSE_VARIANTS.items():
        if faction not in _ALL_FACTIONS:
            continue
        normalized_houses = {house.upper() for house in houses}
        allowed_houses = normalized_houses.intersection(owners) - forbidden
        if required:
            allowed_houses.intersection_update(required)
        if not allowed_houses:
            continue
        result.append(faction)
    return frozenset(result)


def _is_deferred_identifier(type_id):
    normalized = str(type_id or '').upper()
    return normalized.startswith(('ROBOT', 'CABAL'))


def _anchor_scopes():
    scopes = {}
    sections = _FACTIONS_CONFIG
    display = {
        'allies': 'Allies',
        'soviets': 'Soviets',
        'yuri': 'Yuri',
        'gdi': 'GDI',
        'nod': 'Nod',
    }
    for family in sections['active_families']:
        faction = display[family]
        scope = frozenset({faction})
        for category_ids in sections['production_buildings'][family].values():
            for type_id in category_ids:
                normalized = str(type_id).upper()
                scopes[normalized] = scopes.get(normalized, frozenset()).union(
                    scope
                )
        for key in ('engineer_by_family',):
            normalized = str(sections[key][family]).upper()
            scopes[normalized] = scopes.get(normalized, frozenset()).union(
                scope
            )
        for key in ('amphibious_transports', 'miners'):
            for type_id in sections[key][family]:
                normalized = str(type_id).upper()
                scopes[normalized] = scopes.get(
                    normalized, frozenset()
                ).union(scope)
    for mcv_id, yard_id in sections['conyard_by_mcv'].items():
        faction = next(
            display[family]
            for family in sections['active_families']
            if yard_id in sections['production_buildings'][family]['base']
        )
        scope = frozenset({faction})
        scopes[str(mcv_id).upper()] = scope
        scopes[str(yard_id).upper()] = scope
    return scopes


def _registry_ids(sections, name):
    return tuple(
        str(value).upper()
        for value in sections.get(name, {}).values()
        if str(value).strip()
    )


def _complete_union(tokens, scopes):
    active_tokens = [token for token in tokens if not _is_deferred_identifier(token)]
    if not active_tokens or any(token not in scopes for token in active_tokens):
        return None
    result = frozenset().union(*(scopes[token] for token in active_tokens))
    return result or None


@lru_cache(maxsize=1)
def installed_faction_path_index():
    """Return complete token and building scopes for installed rules."""
    sections, source = read_rules_sections()
    normalized_sections = {
        str(name).upper(): values for name, values in sections.items()
    }
    building_ids = _registry_ids(sections, 'BuildingTypes')
    scopes = _anchor_scopes()
    evidence = {
        type_id: ('reviewed production-family anchor',)
        for type_id in scopes
    }

    # RequiredHouses/ForbiddenHouses can safely break prerequisite cycles when
    # they reduce a registered building to one active campaign faction. This
    # is path evidence only; it never approves the building as reward content.
    for type_id in building_ids:
        values = normalized_sections.get(type_id, {})
        eligible = _active_eligible_factions(values)
        if len(eligible) != 1 or type_id in scopes:
            continue
        scopes[type_id] = eligible
        evidence[type_id] = ('installed exact house gates',)

    for _pass in range(30):
        changed = False

        for type_id in building_ids:
            values = normalized_sections.get(type_id, {})
            eligible = _active_eligible_factions(values)
            if not eligible:
                continue
            prerequisite_tokens = _split(values.get('Prerequisite'))
            known_scopes = [
                scopes[token] for token in prerequisite_tokens
                if token in scopes
            ]
            unresolved = [
                token for token in prerequisite_tokens
                if token not in scopes and not _is_deferred_identifier(token)
            ]
            inferred = eligible
            for token_scope in known_scopes:
                inferred = inferred.intersection(token_scope)
            if not inferred:
                continue
            inferred = frozenset(inferred)
            # A concrete family token such as GACNST is sufficient to bound
            # the building to that family even while a broad alias such as
            # RADAR is still being resolved. The unresolved alias may make the
            # path unavailable, but it cannot make the building available to
            # a faction excluded by the concrete prerequisite.
            if unresolved and len(inferred) != 1:
                continue
            if scopes.get(type_id) == inferred:
                continue
            if type_id in scopes and not inferred.issubset(scopes[type_id]):
                continue
            scopes[type_id] = inferred
            evidence[type_id] = tuple(
                ['installed house gates']
                + [f'Prerequisite={token}' for token in prerequisite_tokens]
                + [f'unresolved upper bound={token}' for token in unresolved]
            )
            changed = True

        generic = normalized_sections.get('GENERICPREREQUISITES', {})
        for token, value in generic.items():
            normalized_token = str(token).upper()
            inferred = _complete_union(_split(value), scopes)
            if inferred and scopes.get(normalized_token) != inferred:
                scopes[normalized_token] = inferred
                evidence[normalized_token] = (
                    f'GenericPrerequisites.{token}={value}',
                )
                changed = True

        general = normalized_sections.get('GENERAL', {})
        for token, key in _GENERAL_PREREQUISITES.items():
            value = general.get(key, '')
            inferred = _complete_union(_split(value), scopes)
            if inferred and scopes.get(token) != inferred:
                scopes[token] = inferred
                evidence[token] = (f'General.{key}={value}',)
                changed = True

        if not changed:
            break

    return {
        'rules_source': source,
        'scopes': scopes,
        'evidence': evidence,
        'building_count': len(building_ids),
    }


def content_record_faction_path(record, section):
    """Return complete source path scope for one content-catalogue record."""
    index = installed_faction_path_index()
    scopes = index['scopes']
    prerequisites = tuple(
        str(value).upper() for value in record.get('prerequisite', ())
    )
    built_at = tuple(str(value).upper() for value in record.get('built_at', ()))
    if section == 'powers':
        provider = str(record.get('provider_building_id') or '').upper()
        prerequisites = (provider,) if provider else ()

    unresolved_prerequisites = [
        token for token in prerequisites
        if token not in scopes and not _is_deferred_identifier(token)
    ]
    unresolved_factories = [
        token for token in built_at
        if token not in scopes and not _is_deferred_identifier(token)
    ]
    if unresolved_prerequisites or unresolved_factories:
        return {
            'complete': False,
            'factions': frozenset(),
            'prerequisites': prerequisites,
            'built_at': built_at,
            'unresolved_tokens': tuple(
                unresolved_prerequisites + unresolved_factories
            ),
        }

    path_scope = _ALL_FACTIONS
    for token in prerequisites:
        if token in scopes:
            path_scope = path_scope.intersection(scopes[token])
    if built_at:
        factory_scope = frozenset().union(
            *(scopes[token] for token in built_at if token in scopes)
        )
        path_scope = path_scope.intersection(factory_scope)

    has_specific_path = bool(
        prerequisites or built_at
    ) and path_scope != _ALL_FACTIONS
    return {
        'complete': True,
        'specific': has_specific_path,
        'factions': frozenset(path_scope),
        'prerequisites': prerequisites,
        'built_at': built_at,
        'unresolved_tokens': (),
    }
