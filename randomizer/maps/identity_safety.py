"""Fail-closed preservation of authored terrain and TechnoType identities.

Reloaded campaign scripts frequently compare exact type IDs.  Generated maps
may add player-production clones and alter stats. Authored TaskForces, triggers,
events and actions remain intact. The final audit permits only explicitly
reviewed player-miner placement replacements with no exact scripted type checks.
"""

import re
from collections import Counter
from dataclasses import dataclass

from randomizer.core.collections import comma_items
from randomizer.maps.ini import (
    all_section_value_maps,
    section_value_map_preserve,
)


TECHNO_REGISTRY_SECTIONS = (
    'InfantryTypes',
    'VehicleTypes',
    'AircraftTypes',
    'BuildingTypes',
)
PLACEMENT_SECTIONS = ('Infantry', 'Units', 'Aircraft', 'Structures')
TERRAIN_SECTIONS = (
    'Map', 'IsoMapPack5', 'OverlayPack', 'OverlayDataPack', 'PreviewPack',
    'Terrain', 'Smudge',
)
PACKED_SECTIONS = {
    'isomappack5', 'overlaypack', 'overlaydatapack', 'previewpack',
}
TOKEN_PATTERN = re.compile(
    r'(?<![A-Za-z0-9_])[A-Za-z0-9_]+(?![A-Za-z0-9_])'
)


@dataclass(frozen=True)
class PositionedIdentity:
    section: str
    key: str
    type_id: str


@dataclass(frozen=True)
class RecordIdentity:
    section: str
    key: str
    type_counts: tuple


@dataclass(frozen=True)
class AuthoredIdentityContract:
    """Immutable terrain and references captured before randomizer mutation."""

    positioned: tuple
    records: tuple
    protected_type_ids: frozenset
    terrain_sections: tuple


def registered_techno_ids(installed_sections, map_sections=None):
    """Return installed and map-local TechnoType registry IDs."""
    installed_sections = installed_sections or {}
    map_sections = map_sections or {}
    result = set()
    for registry in TECHNO_REGISTRY_SECTIONS:
        for sections in (installed_sections, map_sections):
            result.update(
                str(type_id).strip().upper()
                for type_id in sections.get(registry, {}).values()
                if str(type_id).strip()
            )
    return result


def _identity_tokens(value, techno_ids):
    value = str(value).split(';', 1)[0]
    return [
        token.upper()
        for token in TOKEN_PATTERN.findall(value)
        if token.upper() in techno_ids
    ]


def _positioned_references(lines, map_sections, techno_ids):
    references = []
    for section in PLACEMENT_SECTIONS:
        for key, value in section_value_map_preserve(lines, section).items():
            tokens = [item.strip() for item in str(value).split(',')]
            if len(tokens) > 1 and tokens[1].upper() in techno_ids:
                references.append(PositionedIdentity(
                    section, str(key), tokens[1].upper()
                ))

    for taskforce_id in map_sections.get('TaskForces', {}).values():
        taskforce_id = str(taskforce_id).strip()
        if not taskforce_id:
            continue
        for key, value in section_value_map_preserve(
            lines, taskforce_id
        ).items():
            if not str(key).strip().isdigit():
                continue
            tokens = [item.strip() for item in str(value).split(',')]
            if len(tokens) > 1 and tokens[1].upper() in techno_ids:
                references.append(PositionedIdentity(
                    taskforce_id, str(key), tokens[1].upper()
                ))
    return references


def capture_authored_identity_contract(lines, installed_sections):
    """Capture every authored record containing a known TechnoType ID."""
    map_sections = all_section_value_maps(lines)
    sections_by_lower = {
        str(name).casefold(): values for name, values in map_sections.items()
    }
    techno_ids = registered_techno_ids(installed_sections, map_sections)
    positioned = _positioned_references(lines, map_sections, techno_ids)
    records = []
    protected = {reference.type_id for reference in positioned}
    for section in map_sections:
        if str(section).lower() in PACKED_SECTIONS:
            continue
        for key, value in section_value_map_preserve(lines, section).items():
            # Scenario paths are launcher lifecycle data, not TechnoType
            # references. "Yuri's Revenge" otherwise protects a spurious YURI
            # token and prevents clearing native campaign continuation links.
            if str(section).casefold() == 'basic' and str(key).casefold() in {
                'nextscenario', 'altnextscenario',
            }:
                continue
            counts = Counter(_identity_tokens(value, techno_ids))
            if not counts:
                continue
            protected.update(counts)
            records.append(RecordIdentity(
                str(section),
                str(key),
                tuple(sorted(counts.items())),
            ))
    return AuthoredIdentityContract(
        positioned=tuple(positioned),
        records=tuple(records),
        protected_type_ids=frozenset(protected),
        terrain_sections=tuple(
            (
                name,
                tuple(sections_by_lower[name.casefold()].items())
                if name.casefold() in sections_by_lower else None,
            )
            for name in TERRAIN_SECTIONS
        ),
    )


def validate_authored_identity_contract(contract, lines, allowed_positioned_replacements=None):
    """Reject changed terrain and removed or renamed authored identities."""
    # Terrain and packed tile/overlay data are never randomizer inputs to
    # mutate. Fail before launch if a rule merge changes them, including the
    # theater that selects the tile graphics. Compare ordered entries so a
    # reordered packed stream cannot pass by retaining the same keys.
    sections = {
        str(name).casefold(): values
        for name, values in all_section_value_maps(lines).items()
    }
    changed_terrain = [
        name for name, expected in contract.terrain_sections
        if (
            tuple(sections[name.casefold()].items())
            if name.casefold() in sections else None
        ) != expected
    ]
    if changed_terrain:
        raise ValueError(
            'Generated map changed authored terrain sections: '
            + ', '.join(changed_terrain)
        )
    allowed_positioned_replacements = allowed_positioned_replacements or {}
    failures = []
    for reference in contract.positioned:
        values = section_value_map_preserve(lines, reference.section)
        current = next(
            (
                value for key, value in values.items()
                if str(key).lower() == reference.key.lower()
            ),
            None,
        )
        tokens = [] if current is None else [
            item.strip() for item in str(current).split(',')
        ]
        current_type = tokens[1].upper() if len(tokens) > 1 else ''
        expected_type = str(allowed_positioned_replacements.get(
            (reference.section, reference.key.lower()), reference.type_id,
        )).upper()
        if current_type != expected_type:
            failures.append(
                f'[{reference.section}] {reference.key}: '
                f'{reference.type_id} became {current_type or "<missing>"}'
            )

    techno_ids = set(contract.protected_type_ids)
    for reference in contract.records:
        values = section_value_map_preserve(lines, reference.section)
        current = next(
            (
                value for key, value in values.items()
                if str(key).lower() == reference.key.lower()
            ),
            None,
        )
        current_counts = Counter(
            _identity_tokens(current or '', techno_ids)
        )
        if (
            reference.key.casefold() == 'prerequisiteoverride'
            and str(current or '').strip().casefold() in {'none', '<none>'}
        ):
            # Production shortcut normalization moves each OR member into a
            # singleton alternate path. Accept that equivalent reference move
            # only while the shortcut is disabled and the path is active;
            # a member buried in an AND list does not preserve its shortcut.
            values_by_lower = {
                str(key).casefold(): value for key, value in values.items()
            }
            count = int(values_by_lower.get('prerequisite.lists', '0'))
            for index in range(1, count + 1):
                members = comma_items(values_by_lower.get(
                    f'prerequisite.list{index}', ''
                ))
                if len(members) == 1:
                    current_counts.update(_identity_tokens(members[0], techno_ids))
        replacement = allowed_positioned_replacements.get(
            (reference.section, reference.key.lower())
        )
        if replacement:
            # Only the exact placement's type token is allowlisted above;
            # every other authored type reference still has to be present.
            original = next(
                item.type_id for item in contract.positioned
                if item.section == reference.section and item.key.lower() == reference.key.lower()
            )
            current_counts[original] += 1
        for type_id, expected_count in reference.type_counts:
            if current_counts[type_id] < expected_count:
                failures.append(
                    f'[{reference.section}] {reference.key}: lost authored '
                    f'{type_id} reference '
                    f'({current_counts[type_id]}/{expected_count})'
                )

    if failures:
        raise ValueError(
            'Generated map changed protected authored TechnoType identities: '
            + '; '.join(failures[:20])
        )
    return {
        'protected_type_count': len(contract.protected_type_ids),
        'positioned_reference_count': len(contract.positioned),
        'record_reference_count': len(contract.records),
        'terrain_section_count': sum(
            values is not None for _name, values in contract.terrain_sections
        ),
    }
