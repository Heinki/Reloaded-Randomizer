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


def _read_rules_text(text):
    """Parse Westwood INI text while retaining authored list order."""
    sections = OrderedDict()
    current = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(';'):
            continue
        if line.startswith('[') and line.endswith(']'):
            current = line[1:-1].strip()
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
    raise FileNotFoundError(f'Could not locate installed {RULES_INI_NAME}.{detail}')


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
