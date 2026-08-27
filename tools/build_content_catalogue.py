"""Build reviewable Reloaded faction content facts from installed rules."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.config.game_profile import CONTENT_FACTIONS
from randomizer.content.inventory import (
    FACTION_HOUSES,
    TYPE_SECTIONS,
    read_rules_sections,
    rules_fingerprint,
)


OUTPUT_PATH = PROJECT_ROOT / 'configs' / 'rewards' / 'reloaded_content_catalogue.json'
UNIT_CATEGORIES = tuple(
    category for category in TYPE_SECTIONS if category != 'buildings'
)
FACTORY_CATEGORIES = {
    'buildingtype': 'base',
    'infantrytype': 'infantry',
    'unittype': 'vehicles',
    'aircrafttype': 'aircraft',
}
REVIEW_STATUSES = {'candidate', 'pending_review', 'approved', 'excluded'}


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Build C&C Reloaded faction-content review metadata.',
    )
    parser.add_argument('--write', action='store_true')
    parser.add_argument(
        '--reset-reviews',
        action='store_true',
        help='Discard preserved approved/excluded review decisions.',
    )
    return parser.parse_args()


def _split(value):
    return tuple(
        item.strip()
        for item in str(value or '').split(',')
        if item.strip() and item.strip().lower() not in {'none', '<none>'}
    )


def _bool(values, key):
    return str(values.get(key, '')).strip().lower() in {'yes', 'true', '1'}


def _integer(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _registered_ids(sections, registry):
    return tuple(
        identifier
        for identifier in sections.get(registry, {}).values()
        if identifier and identifier.lower() not in {'none', '<none>'}
    )


def _faction_eligible(values, faction):
    house = FACTION_HOUSES[faction].lower()
    owners = {owner.lower() for owner in _split(values.get('Owner'))}
    required = {
        owner.lower() for owner in _split(values.get('RequiredHouses'))
    }
    forbidden = {
        owner.lower() for owner in _split(values.get('ForbiddenHouses'))
    }
    if house not in owners or house in forbidden:
        return False
    return not required or house in required


def _eligible_factions(values):
    return tuple(
        faction for faction in CONTENT_FACTIONS
        if _faction_eligible(values, faction)
    )


def _owner_factions(values):
    owners = {owner.lower() for owner in _split(values.get('Owner'))}
    return tuple(
        faction for faction, house in FACTION_HOUSES.items()
        if house.lower() in owners
    )


def _is_deferred_cabal_content(type_id, values):
    """Keep CABAL-native identities outside five-faction review scope."""
    normalized_id = str(type_id).upper()
    if normalized_id.startswith(('ROBOT', 'CABAL')):
        return True
    if "cabal's" in str(values.get('Name') or '').lower():
        return True
    production_tokens = (
        *_split(values.get('Prerequisite')),
        *_split(values.get('BuiltAt')),
        *_split(values.get('DeploysInto')),
        *_split(values.get('UndeploysInto')),
    )
    return any(
        str(token).upper().startswith(('ROBOT', 'CABAL'))
        for token in production_tokens
    )


def _review_flags(type_id, values, eligible_factions):
    flags = []
    tech_level = _integer(values.get('TechLevel'))
    if len(_owner_factions(values)) > 1:
        flags.append('broad_owner_list')
    if tech_level == 11:
        flags.append('hidden_tech_level')
    if not values.get('Prerequisite') and not values.get('BuiltAt'):
        flags.append('no_production_path')
    if not values.get('UIName'):
        flags.append('missing_ui_name')
    if _bool(values, 'Unbuildable'):
        flags.append('unbuildable')
    if _bool(values, 'Civilian') or _bool(values, 'Natural'):
        flags.append('civilian_or_natural')
    if _bool(values, 'Insignificant') or _bool(values, 'DontScore'):
        flags.append('non_scoring')
    if any(
        _bool(values, key)
        for key in ('Spawned', 'MissileSpawn', 'VirtualUnit')
    ):
        flags.append('spawned_or_virtual_payload')
    if str(type_id).upper() in {'DUMMY', 'DUMMYDUMMY'}:
        flags.append('dummy')
    return flags


def _default_status(eligible_factions, flags):
    hard_exclusions = {
        'unbuildable', 'civilian_or_natural', 'spawned_or_virtual_payload',
        'dummy',
    }
    if hard_exclusions.intersection(flags):
        return 'excluded'
    if (
        len(eligible_factions) == 1
        and 'no_production_path' not in flags
        and 'broad_owner_list' not in flags
    ):
        return 'candidate'
    return 'pending_review'


def _cameo(values, type_id):
    sidebar = str(values.get('SidebarPCX') or '').strip()
    image = str(values.get('Image') or type_id).strip()
    return {
        'sidebar_pcx': sidebar,
        'art_image': image,
        'status': 'candidate' if sidebar else 'pending_review',
    }


def _base_record(type_id, values, eligible_factions):
    flags = _review_flags(type_id, values, eligible_factions)
    default_status = _default_status(eligible_factions, flags)
    return {
        'id': type_id,
        'name': values.get('Name', type_id),
        'ui_name': values.get('UIName', ''),
        'image': values.get('Image', type_id),
        'tech_level': _integer(values.get('TechLevel')),
        'cost': _integer(values.get('Cost')),
        'build_limit': _integer(values.get('BuildLimit')),
        'owner': list(_split(values.get('Owner'))),
        'required_houses': list(_split(values.get('RequiredHouses'))),
        'forbidden_houses': list(_split(values.get('ForbiddenHouses'))),
        'prerequisite': list(_split(values.get('Prerequisite'))),
        'built_at': list(_split(values.get('BuiltAt'))),
        'eligible_factions': list(eligible_factions),
        'primary': values.get('Primary', ''),
        'secondary': values.get('Secondary', ''),
        'cameo': _cameo(values, type_id),
        'reviews': {
            faction: {
                'status': default_status,
                'flags': list(flags),
                'notes': '',
            }
            for faction in eligible_factions
        },
    }


def _unit_records(sections):
    records = {category: [] for category in UNIT_CATEGORIES}
    for category in UNIT_CATEGORIES:
        registry = TYPE_SECTIONS[category]
        for type_id in _registered_ids(sections, registry):
            values = sections.get(type_id, {})
            if _is_deferred_cabal_content(type_id, values):
                continue
            tech_level = _integer(values.get('TechLevel'))
            eligible = _eligible_factions(values)
            if tech_level is None or tech_level < 0 or not eligible:
                continue
            record = _base_record(type_id, values, eligible)
            record['category'] = category
            record['naval'] = _bool(values, 'Naval')
            record['harvester'] = _bool(values, 'Harvester')
            record['engineer'] = _bool(values, 'Engineer')
            record['trainable'] = not (
                str(values.get('Trainable', '')).strip().lower() == 'no'
            )
            record['deploys_into'] = values.get('DeploysInto', '')
            records[category].append(record)
    return records


def _building_records(sections):
    production = []
    defenses = []
    powers = []
    registered_powers = set(
        _registered_ids(sections, 'SuperWeaponTypes')
    )
    for type_id in _registered_ids(sections, 'BuildingTypes'):
        values = sections.get(type_id, {})
        if _is_deferred_cabal_content(type_id, values):
            continue
        tech_level = _integer(values.get('TechLevel'))
        eligible = _eligible_factions(values)
        if tech_level is None or tech_level < 0 or not eligible:
            continue
        factory = str(values.get('Factory') or '').strip().lower()
        if factory in FACTORY_CATEGORIES:
            record = _base_record(type_id, values, eligible)
            record['category'] = FACTORY_CATEGORIES[factory]
            record['construction_yard'] = _bool(values, 'ConstructionYard')
            record['naval'] = _bool(values, 'Naval')
            production.append(record)

        is_defense = (
            str(values.get('BuildCat') or '').strip().lower() == 'combat'
            or _bool(values, 'IsBaseDefense')
        )
        if is_defense:
            record = _base_record(type_id, values, eligible)
            record['category'] = 'defense'
            record['powered'] = _bool(values, 'Powered')
            defenses.append(record)

        power_ids = list(_split(values.get('SuperWeapon')))
        power_ids.extend(_split(values.get('SuperWeapon2')))
        power_ids.extend(_split(values.get('SuperWeapons')))
        for power_id in dict.fromkeys(power_ids):
            if power_id not in registered_powers:
                continue
            power_values = sections.get(power_id, {})
            if _is_deferred_cabal_content(power_id, power_values):
                continue
            flags = []
            if str(power_values.get('SW.ShowCameo', '')).lower() == 'no':
                flags.append('hidden_cameo')
            if len(_owner_factions(values)) > 1:
                flags.append('broad_provider_owner_list')
            status = 'candidate' if not flags and len(eligible) == 1 else 'pending_review'
            record = {
                'id': power_id,
                'name': power_values.get('Name', power_id),
                'ui_name': power_values.get('UIName', ''),
                'provider_building_id': type_id,
                'eligible_factions': list(eligible),
                'recharge_time': power_values.get('RechargeTime', ''),
                'type': power_values.get('Type', ''),
                'action': power_values.get('Action', ''),
                'cameo': _cameo(power_values, power_id),
                'reviews': {
                    faction: {
                        'status': status,
                        'flags': list(flags),
                        'notes': '',
                    }
                    for faction in eligible
                },
            }
            powers.append(record)
    return production, defenses, powers


def _record_key(section, category, record):
    if section == 'powers':
        return f'{section}:{record["provider_building_id"]}:{record["id"]}'
    return f'{section}:{category}:{record["id"]}'


def _iter_records(document):
    content = document.get('sections', {}).get('content', {})
    groups = []
    groups.extend(
        ('units', category, records)
        for category, records in content.get('units', {}).items()
    )
    groups.extend(
        (section, section, content.get(section, []))
        for section in ('production', 'defenses', 'powers')
    )
    for section, category, records in groups:
        for record in records:
            key = _record_key(section, category, record)
            for faction, review in record.get('reviews', {}).items():
                yield faction, key, record, review


def preserve_reviews(document):
    """Preserve manual decisions only for an unchanged rules fingerprint."""
    if not OUTPUT_PATH.is_file():
        return document
    try:
        existing = json.loads(OUTPUT_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return document
    if (
        existing.get('sections', {}).get('rules_fingerprint_sha256')
        != document['sections']['rules_fingerprint_sha256']
    ):
        return document
    existing_records = {
        (faction, key): review
        for faction, key, _record, review in _iter_records(existing)
    }
    for faction, key, _record, review in _iter_records(document):
        previous = existing_records.get((faction, key), {})
        if previous.get('status') not in {'approved', 'excluded'}:
            continue
        review['status'] = previous['status']
        review['notes'] = str(previous.get('notes') or '')
    return document


def refresh_review_summary(document):
    counts = Counter(
        review['status']
        for _faction, _key, _record, review in _iter_records(document)
    )
    document['sections']['review_summary'] = dict(sorted(counts.items()))
    document['sections']['review_complete'] = not (
        counts.get('candidate', 0) or counts.get('pending_review', 0)
    )
    return document


def build_catalogue():
    sections, _source = read_rules_sections()
    units = _unit_records(sections)
    production, defenses, powers = _building_records(sections)
    content = {
        'units': units,
        'production': production,
        'defenses': defenses,
        'powers': powers,
    }
    faction_index = {}
    counts = Counter()
    for faction in CONTENT_FACTIONS:
        faction_index[faction] = {
            'canonical_country': FACTION_HOUSES[faction],
            'units': {
                category: [
                    record['id'] for record in records
                    if faction in record['eligible_factions']
                ]
                for category, records in units.items()
            },
            'production': [
                record['id'] for record in production
                if faction in record['eligible_factions']
            ],
            'defenses': [
                record['id'] for record in defenses
                if faction in record['eligible_factions']
            ],
            'powers': [
                f'{record["provider_building_id"]}:{record["id"]}'
                for record in powers
                if faction in record['eligible_factions']
            ],
        }
    review_document = {'sections': {'content': content}}
    for _faction, _key, _record, review in _iter_records(review_document):
        counts[review['status']] += 1
    return {
        'schema_version': 1,
        'description': (
            'Installed C&C Reloaded faction-content review catalogue. '
            'Candidate status never enables gameplay.'
        ),
        'sections': {
            'catalogue_version': 1,
            'game_version': '2.7.0',
            'rules_source': 'expandmd02.mix::rulesmd.ini',
            'rules_fingerprint_sha256': rules_fingerprint(sections),
            'content': content,
            'faction_index': faction_index,
            'review_summary': dict(sorted(counts.items())),
            'review_complete': False,
        },
    }


def main():
    args = _parse_args()
    document = build_catalogue()
    if not args.reset_reviews:
        document = preserve_reviews(document)
    document = refresh_review_summary(document)
    if not args.write:
        print(json.dumps(document['sections']['review_summary'], indent=2))
        return 0
    OUTPUT_PATH.write_text(
        json.dumps(document, indent=2) + '\n',
        encoding='utf-8',
    )
    print(
        'Wrote Reloaded content review catalogue: '
        + json.dumps(document['sections']['review_summary'], sort_keys=True)
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
