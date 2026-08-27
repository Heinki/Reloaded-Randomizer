"""Fail-closed preservation of map-authored TechnoType identities.

Reloaded campaign scripts frequently compare exact type IDs.  Generated maps
may add player-production clones and alter stats, but they must not replace an
identity already present in a placement, TaskForce, trigger, event, action, or
other authored map record.
"""

import re
from collections import Counter
from dataclasses import dataclass

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
    """Immutable references captured before any randomizer mutation."""

    positioned: tuple
    records: tuple
    protected_type_ids: frozenset


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
    techno_ids = registered_techno_ids(installed_sections, map_sections)
    positioned = _positioned_references(lines, map_sections, techno_ids)
    records = []
    protected = {reference.type_id for reference in positioned}
    for section in map_sections:
        if str(section).lower() in PACKED_SECTIONS:
            continue
        for key, value in section_value_map_preserve(lines, section).items():
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
    )


def validate_authored_identity_contract(contract, lines):
    """Raise when generated output removes or renames an authored identity."""
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
        if current_type != reference.type_id:
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
    }
