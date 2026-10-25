"""Read-only inventory of Reloaded techno types grouped by faction.

The generated rosters are review candidates, not gameplay configuration.  The
Reloaded rules use broad Owner lists for map scripting, so every candidate must
still be checked for campaign availability before it becomes a randomizer
reward.
"""

import argparse
import hashlib
import json
from collections import OrderedDict
from pathlib import Path

from randomizer.config.game_profile import (
    ARCHIVE_GLOB,
    CONTENT_FACTIONS,
    ENABLE_CABAL,
    GAME_EXECUTABLE_NAME,
    RULES_INI_NAME,
)
from randomizer.core.mix import MixArchive, MixFormatError
from randomizer.core.paths import GAME_ROOT


DEFAULT_RULES_PATH = GAME_ROOT / 'Tools' / 'Map Editor' / 'rulesmd.ini'

TYPE_SECTIONS = OrderedDict((
    ('infantry', 'InfantryTypes'),
    ('vehicles', 'VehicleTypes'),
    ('aircraft', 'AircraftTypes'),
    ('buildings', 'BuildingTypes'),
))

FACTION_HOUSES = {
    'Allies': 'AlliesCountry',
    'Soviets': 'SovietCountry',
    'Yuri': 'YuriCountry',
    'GDI': 'GDICountry',
    'Nod': 'NodCountry',
    'CABAL': 'RobotCountry',
}

# Reloaded keeps separate country identities for several original/expansion
# campaign technology trees. Both identities belong to the same dashboard
# faction; CABAL remains deferred.
FACTION_HOUSE_VARIANTS = {
    'Allies': ('AlliesCountry', 'AlliesCountry2'),
    'Soviets': ('SovietCountry', 'SovietCountry2'),
    'Yuri': ('YuriCountry', 'YuriCountry2'),
    'GDI': ('GDICountry', 'GDICountry2'),
    'Nod': ('NodCountry', 'NodCountry2'),
    'CABAL': ('RobotCountry', 'RobotCountry2'),
}


def _strip_comment(value):
    return str(value).split(';', 1)[0].strip()


def _split_list(value):
    return {
        item.strip().lower()
        for item in _strip_comment(value).split(',')
        if item.strip()
    }


def is_cabal_content(type_id, values):
    """Identify CABAL technology without rejecting shared faction ownership.

    Prerequisites are AND gates; BuiltAt and Owner are alternative lists. A
    shared factory list containing ROBOTWEAP does not make Yuri's Repair Disk
    CABAL technology. A ROBOT-prefixed unit still belongs to CABAL when a
    Secret Lab offers it to another faction.
    """
    def deferred_id(identifier):
        return str(identifier).strip().upper().startswith(('ROBOT', 'CABAL'))

    fields = {str(key).casefold(): value for key, value in values.items()}
    if deferred_id(type_id) or 'cabal' in str(fields.get('name', '')).casefold():
        return True
    for key in ('prerequisite', 'deploysinto', 'undeploysinto'):
        if any(deferred_id(token) for token in _split_list(fields.get(key, ''))):
            return True
    for key in ('builtat', 'owner', 'requiredhouses'):
        tokens = _split_list(fields.get(key, '')) - {'none', '<none>'}
        if tokens and all(deferred_id(token) for token in tokens):
            return True
    return False


def cabal_type_ids(sections):
    """Identify CABAL types and their transforms independently of feature state."""
    from randomizer.content.transforms import TRANSFORM_REFERENCE_KEYS

    values_by_id = {str(name).upper(): values for name, values in sections.items()}
    registered = {
        str(identifier).upper()
        for registry in (*TYPE_SECTIONS.values(), 'SuperWeaponTypes')
        for identifier in sections.get(registry, {}).values()
    }
    deferred = {
        type_id for type_id in registered
        if is_cabal_content(type_id, values_by_id.get(type_id, {}))
    }
    while True:
        linked = {
            type_id for type_id in registered - deferred
            if any(
                token.upper() in deferred
                for key, value in values_by_id.get(type_id, {}).items()
                if str(key).casefold() in TRANSFORM_REFERENCE_KEYS
                for token in _split_list(value)
            )
        }
        if not linked:
            return frozenset(deferred)
        deferred.update(linked)


def is_deferred_cabal_content(type_id, values):
    """Apply the release feature flag to CABAL identity."""
    return not ENABLE_CABAL and is_cabal_content(type_id, values)


def deferred_cabal_type_ids(sections):
    """Return CABAL exclusions only while the faction feature is disabled."""
    return frozenset() if ENABLE_CABAL else cabal_type_ids(sections)


def _read_rules_text(text):
    """Parse Westwood INI text while retaining authored list order."""
    sections = OrderedDict()
    current = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(';'):
            continue
        header = _strip_comment(line)
        if header.startswith('[') and header.endswith(']'):
            current = header[1:-1].strip()
            sections.setdefault(current, OrderedDict())
            continue
        if current and '=' in line:
            key, value = line.split('=', 1)
            sections[current][key.strip()] = _strip_comment(value)
    return sections


def read_rules_sections(path=None):
    """Read loose rules, or the highest-precedence installed MIX member."""
    if path is not None:
        path = Path(path)
        return _read_rules_text(
            path.read_text(encoding='utf-8', errors='ignore')
        ), str(path.resolve())

    loose_rules = GAME_ROOT / RULES_INI_NAME
    if loose_rules.is_file():
        return _read_rules_text(
            loose_rules.read_text(encoding='utf-8', errors='ignore')
        ), str(loose_rules.resolve())

    skipped = []
    archives = sorted(
        GAME_ROOT.glob(ARCHIVE_GLOB),
        key=lambda item: item.name.lower(),
        reverse=True,
    )
    for archive_path in archives:
        try:
            with MixArchive(archive_path) as archive:
                data = archive.read(RULES_INI_NAME)
        except (OSError, MixFormatError) as exc:
            skipped.append(f'{archive_path.name}: {exc}')
            continue
        if data is not None:
            return _read_rules_text(
                data.decode('utf-8', errors='ignore')
            ), f'{archive_path.resolve()}::{RULES_INI_NAME}'

    fallback = DEFAULT_RULES_PATH
    if fallback.is_file():
        return _read_rules_text(
            fallback.read_text(encoding='utf-8', errors='ignore')
        ), str(fallback.resolve())
    detail = f' Rules scan errors: {"; ".join(skipped)}' if skipped else ''
    raise FileNotFoundError(
        f'Could not locate installed {RULES_INI_NAME}. '
        f'Searched {loose_rules}, {len(archives)} {ARCHIVE_GLOB} archives '
        f'in {GAME_ROOT}, and {fallback}. '
        f'Place the packaged launcher beside {GAME_EXECUTABLE_NAME} in a '
        'complete C&C Reloaded installation; source checkouts must be '
        f'directly inside that game folder.{detail}'
    )


def rules_fingerprint(sections):
    """Hash normalized rules content without machine-specific source paths."""
    payload = json.dumps(
        sections,
        ensure_ascii=False,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(payload).hexdigest()


def registered_techno_types(path=None):
    """Return every registered techno and its basic authored metadata."""
    sections, _source = read_rules_sections(path)
    result = OrderedDict()
    for category, registry_name in TYPE_SECTIONS.items():
        entries = []
        for identifier in sections.get(registry_name, {}).values():
            identifier = _strip_comment(identifier)
            if not identifier:
                continue
            rules = sections.get(identifier, {})
            entries.append({
                'id': identifier,
                'name': rules.get('Name', identifier),
                'ui_name': rules.get('UIName', ''),
                'owner': sorted(_split_list(rules.get('Owner', ''))),
                'required_houses': sorted(
                    _split_list(rules.get('RequiredHouses', ''))
                ),
                'forbidden_houses': sorted(
                    _split_list(rules.get('ForbiddenHouses', ''))
                ),
                'tech_level': rules.get('TechLevel', ''),
                'unbuildable': rules.get('Unbuildable', '').lower() == 'yes',
            })
        result[category] = entries
    return result


def _is_build_candidate(entry, house):
    house = house.lower()
    if entry['unbuildable'] or house in entry['forbidden_houses']:
        return False
    if entry['required_houses'] and house not in entry['required_houses']:
        return False
    if house not in entry['owner']:
        return False
    try:
        return int(entry['tech_level']) >= 0
    except (TypeError, ValueError):
        return False


def secret_lab_factions(sections):
    """Find player technology explicitly offered by installed Secret Labs.

    These types intentionally use TechLevel=-1 (or 11): capturing a lab
    unlocks them in Reloaded. They are player units, not script-only types.
    """
    boon_ids = set()
    for building_id in sections.get('BuildingTypes', {}).values():
        values = sections.get(building_id, {})
        if str(values.get('SecretLab', '')).lower() not in {'yes', 'true', '1'}:
            continue
        boon_ids.update(_split_list(values.get('SecretLab.PossibleBoons', '')))
    result = {}
    deferred = deferred_cabal_type_ids(sections)
    for type_id, values in sections.items():
        if type_id.lower() not in boon_ids or type_id.upper() in deferred:
            continue
        required = _split_list(values.get('SecretLab.RequiredHouses', ''))
        forbidden = _split_list(values.get('SecretLab.ForbiddenHouses', ''))
        owners = _split_list(values.get('Owner', ''))
        factions = tuple(
            faction for faction in CONTENT_FACTIONS
            if any(
                house.lower() in owners
                and house.lower() not in forbidden
                and (not required or house.lower() in required)
                for house in FACTION_HOUSE_VARIANTS[faction]
            )
        )
        if factions:
            result[type_id] = factions
    return result


def secret_lab_tech_level(values):
    """Price lab unlocks by their authored production prerequisites."""
    prerequisites = _split_list(values.get('Prerequisite', ''))
    if 'tech' in prerequisites:
        return 9
    if 'radar' in prerequisites or not prerequisites:
        return 6
    return 3


def faction_roster_candidates(path=None):
    """Group buildable candidates by canonical Reloaded faction house."""
    registered = registered_techno_types(path)
    rosters = OrderedDict()
    for faction in CONTENT_FACTIONS:
        house = FACTION_HOUSES[faction]
        rosters[faction] = OrderedDict()
        for category, entries in registered.items():
            rosters[faction][category] = [
                {'id': entry['id'], 'name': entry['name']}
                for entry in entries
                if _is_build_candidate(entry, house)
            ]
    return rosters


def inventory_report(path=None):
    """Return source provenance, raw registry totals, and candidate totals."""
    sections, source = read_rules_sections(path)
    registered = registered_techno_types(path)
    candidates = faction_roster_candidates(path)
    return {
        'rules_source': source,
        'rules_fingerprint_sha256': rules_fingerprint(sections),
        'registered_counts': {
            category: len(entries)
            for category, entries in registered.items()
        },
        'candidate_counts': {
            faction: {
                category: len(entries)
                for category, entries in categories.items()
            }
            for faction, categories in candidates.items()
        },
        'review_required': True,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Audit C&C Reloaded faction roster candidates.'
    )
    parser.add_argument(
        '--rules', type=Path,
        help='Optional path to extracted rules; defaults to installed MIX data.',
    )
    parser.add_argument(
        '--include-units', action='store_true',
        help='Include candidate IDs and names instead of counts only.',
    )
    arguments = parser.parse_args(argv)
    result = inventory_report(arguments.rules)
    if arguments.include_units:
        result['candidates'] = faction_roster_candidates(arguments.rules)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
