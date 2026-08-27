"""Build reviewable Reloaded buff-target and superweapon source facts."""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.config.game_profile import CONTENT_FACTIONS, SUPPORTED_GAME_VERSION
from randomizer.content.inventory import (
    FACTION_HOUSES,
    read_rules_sections,
    rules_fingerprint,
)


CONTENT_PATH = PROJECT_ROOT / 'configs' / 'rewards' / 'reloaded_content_catalogue.json'
OUTPUT_PATH = PROJECT_ROOT / 'configs' / 'rewards' / 'reloaded_balance_catalogue.json'
REVIEW_STATUSES = {'candidate', 'pending_review', 'approved', 'excluded'}
WEAPON_FIELDS = ('Damage', 'ROF', 'Range', 'Burst', 'Projectile', 'Warhead')
BUFF_ORDER = (
    'health', 'armor', 'damage', 'reload', 'range', 'speed', 'sight',
    'cost', 'production', 'veteran', 'ammo', 'passenger_capacity',
    'sensors', 'cloak',
)


def _split(value):
    return [
        item.strip()
        for item in str(value or '').split(',')
        if item.strip() and item.strip().lower() not in {'none', '<none>'}
    ]


def _number(value):
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _bool(values, key):
    return str(values.get(key, '')).strip().lower() in {'yes', 'true', '1'}


def _source_name(source):
    archive, separator, member = str(source).partition('::')
    return Path(archive).name + (f'::{member}' if separator else '')


def _content_document():
    return json.loads(CONTENT_PATH.read_text(encoding='utf-8'))['sections']


def _nonexcluded_factions(record):
    return [
        faction
        for faction, review in record.get('reviews', {}).items()
        if faction in CONTENT_FACTIONS and review.get('status') != 'excluded'
    ]


def _candidate_records(content):
    for category, records in content['content']['units'].items():
        for record in records:
            factions = _nonexcluded_factions(record)
            if factions:
                yield category, record, factions
    for record in content['content']['defenses']:
        factions = _nonexcluded_factions(record)
        if factions:
            yield 'defenses', record, factions


def _weapon_ids(values):
    result = []
    for key in ('Primary', 'Secondary', 'ElitePrimary', 'EliteSecondary'):
        result.extend(_split(values.get(key)))
    return list(dict.fromkeys(result))


def _weapon_fact(weapon_id, sections, section_names):
    source_id = section_names.get(weapon_id.lower(), weapon_id)
    values = sections.get(source_id, {})
    fact = {'id': weapon_id}
    for field in WEAPON_FIELDS:
        value = values.get(field, '')
        fact[field.lower()] = (
            _number(value) if field in {'Damage', 'ROF', 'Range', 'Burst'} else value
        )
    fact['source_present'] = bool(values)
    return fact


def _candidate_buff_types(category, values, weapons):
    candidates = []
    strength = _number(values.get('Strength'))
    cost = _number(values.get('Cost'))
    speed = _number(values.get('Speed'))
    sight = _number(values.get('Sight'))
    ammo = _number(values.get('Ammo'))
    passengers = _number(values.get('Passengers'))
    if strength is not None and strength > 0:
        candidates.extend(('health', 'armor'))
    if any((weapon.get('damage') or 0) > 1 for weapon in weapons):
        candidates.append('damage')
    if any((weapon.get('rof') or 0) > 1 for weapon in weapons):
        candidates.append('reload')
    if any((weapon.get('range') or 0) > 0 for weapon in weapons):
        candidates.append('range')
    if category != 'defenses' and speed is not None and speed > 0:
        candidates.append('speed')
    if sight is not None and sight > 0:
        candidates.extend(('sight', 'sensors'))
    if cost is not None and cost > 0:
        candidates.extend(('cost', 'production'))
    if str(values.get('Trainable', '')).strip().lower() != 'no':
        candidates.append('veteran')
    if ammo is not None and ammo > 0:
        candidates.append('ammo')
    if passengers is not None and passengers > 0:
        candidates.append('passenger_capacity')
    candidates.append('cloak')
    return [buff_type for buff_type in BUFF_ORDER if buff_type in candidates]


def _build_buff_targets(content, sections):
    candidates = list(_candidate_records(content))
    section_names = {str(name).lower(): name for name in sections}
    weapon_users = defaultdict(set)
    for _category, record, _factions in candidates:
        values = sections.get(record['id'], {})
        for weapon_id in _weapon_ids(values):
            weapon_users[weapon_id.upper()].add(record['id'])

    targets = []
    for category, record, factions in candidates:
        type_id = record['id']
        values = sections.get(type_id, {})
        weapons = [
            _weapon_fact(weapon_id, sections, section_names)
            for weapon_id in _weapon_ids(values)
        ]
        shared_weapons = {
            weapon['id']: sorted(weapon_users[weapon['id'].upper()])
            for weapon in weapons
            if len(weapon_users[weapon['id'].upper()]) > 1
        }
        flags = []
        if not values:
            flags.append('missing_rules_section')
        if not weapons:
            flags.append('no_direct_weapon')
        if any(not weapon['source_present'] for weapon in weapons):
            flags.append('missing_weapon_section')
        if shared_weapons:
            flags.append('shared_weapon_requires_clone')
        if str(values.get('Trainable', '')).strip().lower() == 'no':
            flags.append('nontrainable')
        if any(_bool(values, key) for key in ('Spawned', 'MissileSpawn', 'VirtualUnit')):
            flags.append('spawned_or_virtual')
        target = {
            'id': type_id,
            'category': category,
            'name': values.get('Name', record.get('name', type_id)),
            'eligible_factions': factions,
            'stats': {
                'strength': _number(values.get('Strength')),
                'armor': values.get('Armor', ''),
                'cost': _number(values.get('Cost')),
                'speed': _number(values.get('Speed')),
                'sight': _number(values.get('Sight')),
                'ammo': _number(values.get('Ammo')),
                'passengers': _number(values.get('Passengers')),
                'trainable': str(values.get('Trainable', '')).strip().lower() != 'no',
                'cloakable': _bool(values, 'Cloakable'),
                'sensors': _bool(values, 'Sensors'),
            },
            'weapons': weapons,
            'shared_weapon_users': shared_weapons,
            'candidate_buff_types': _candidate_buff_types(category, values, weapons),
            'review': {
                'status': 'pending_review',
                'approved_buff_types': [],
                'excluded_buff_types': [],
                'flags': flags,
                'notes': '',
            },
        }
        targets.append(target)
    return targets


def _faction_eligible(values, faction):
    house = FACTION_HOUSES[faction].lower()
    owners = {item.lower() for item in _split(values.get('Owner'))}
    required = {item.lower() for item in _split(values.get('RequiredHouses'))}
    forbidden = {item.lower() for item in _split(values.get('ForbiddenHouses'))}
    return house in owners and house not in forbidden and (not required or house in required)


def _power_providers(sections):
    providers = defaultdict(list)
    deferred_power_ids = set()
    for building_id in sections.get('BuildingTypes', {}).values():
        values = sections.get(building_id, {})
        power_ids = []
        for key in ('SuperWeapon', 'SuperWeapon2', 'SuperWeapons'):
            power_ids.extend(_split(values.get(key)))
        for power_id in dict.fromkeys(power_ids):
            building_text = f'{building_id} {values.get("Name", "")}'.lower()
            if (
                building_id.upper().startswith(('ROBOT', 'CABAL'))
                or "cabal's" in building_text
            ):
                deferred_power_ids.add(power_id.upper())
                continue
            if building_id.upper() == 'TEST_BUILDING':
                continue
            factions = [
                faction for faction in CONTENT_FACTIONS
                if _faction_eligible(values, faction)
            ]
            providers[power_id.upper()].append({
                'building_id': building_id,
                'eligible_factions': factions,
            })
    return providers, deferred_power_ids


def _power_buff_candidates(values):
    result = []
    recharge = _number(values.get('RechargeTime'))
    money = _number(values.get('Money.Amount'))
    sw_range = str(values.get('SW.Range', '')).strip()
    damage = _number(values.get('SW.Damage'))
    power_type = str(values.get('Type', '')).lower()
    if recharge is not None and recharge > 0:
        result.append('recharge')
    if money not in (None, 0):
        result.append('cost')
    if sw_range and sw_range.lower() not in {'none', '<none>'}:
        result.append('area')
    if damage is not None and damage > 1:
        result.append('damage')
    if power_type in {'paradrop', 'unitdelivery', 'droppod', 'spyplane'}:
        result.append('payload')
    if power_type in {'psychicreveal', 'spyplane'}:
        result.append('vision')
    return result


def _deferred_power(power_id, values, providers, deferred_power_ids):
    text = f'{power_id} {values.get("Name", "")}'.lower()
    return (
        any(token in text for token in ('cabal', 'robot'))
        or power_id.upper() in deferred_power_ids
    ) and not any(provider['eligible_factions'] for provider in providers)


def _build_powers(sections):
    provider_index, deferred_power_ids = _power_providers(sections)
    records = []
    deferred_count = 0
    for power_id in sections.get('SuperWeaponTypes', {}).values():
        values = sections.get(power_id, {})
        providers = provider_index.get(power_id.upper(), [])
        if _deferred_power(power_id, values, providers, deferred_power_ids):
            deferred_count += 1
            continue
        factions = sorted({
            faction
            for provider in providers
            for faction in provider['eligible_factions']
        }, key=CONTENT_FACTIONS.index)
        show_cameo = str(values.get('SW.ShowCameo', '')).strip().lower()
        ui_name = str(values.get('UIName', '')).strip()
        identifier = power_id.lower()
        name = str(values.get('Name', power_id))
        flags = []
        if not providers:
            flags.append('no_registered_provider')
        if not factions:
            flags.append('no_active_faction_provider')
        if show_cameo in {'no', 'false'}:
            flags.append('hidden_cameo')
        if not ui_name or ui_name.upper() == 'TXT_EMPTY':
            flags.append('missing_or_empty_ui_name')
        if any(token in f'{identifier} {name.lower()}' for token in ('test', 'dummy')):
            flags.append('test_or_dummy')
        if identifier.startswith('ai') or '_ai' in identifier:
            flags.append('ai_identifier')
        recharge = _number(values.get('RechargeTime'))
        if recharge is not None and recharge < 0.2:
            flags.append('near_instant_internal_recharge')
        if not values.get('Type') and not values.get('Action'):
            flags.append('missing_type_and_action')
        status = (
            'excluded'
            if 'test_or_dummy' in flags
            else 'candidate'
            if providers and factions and not flags
            else 'pending_review'
        )
        records.append({
            'id': power_id,
            'name': name,
            'ui_name': ui_name,
            'type': values.get('Type', ''),
            'action': values.get('Action', ''),
            'recharge_time': recharge,
            'money_amount': _number(values.get('Money.Amount')),
            'range': values.get('SW.Range', ''),
            'damage': _number(values.get('SW.Damage')),
            'warhead': values.get('SW.Warhead', ''),
            'show_cameo': show_cameo not in {'no', 'false'},
            'providers': providers,
            'eligible_factions': factions,
            'candidate_buff_types': _power_buff_candidates(values),
            'review': {'status': status, 'flags': flags, 'notes': ''},
        })
    return records, deferred_count


def _preserve_reviews(document):
    if not OUTPUT_PATH.is_file():
        return document
    try:
        old = json.loads(OUTPUT_PATH.read_text(encoding='utf-8'))['sections']
    except (OSError, ValueError, KeyError):
        return document
    new = document['sections']
    if old.get('rules_fingerprint_sha256') != new['rules_fingerprint_sha256']:
        return document
    old_targets = {record['id']: record['review'] for record in old.get('buff_targets', [])}
    for record in new['buff_targets']:
        previous = old_targets.get(record['id'], {})
        if previous.get('status') not in {'approved', 'excluded'}:
            continue
        record['review'].update({
            'status': previous['status'],
            'approved_buff_types': list(previous.get('approved_buff_types', ())),
            'excluded_buff_types': list(previous.get('excluded_buff_types', ())),
            'notes': str(previous.get('notes') or ''),
        })
    old_powers = {record['id']: record['review'] for record in old.get('powers', [])}
    for record in new['powers']:
        previous = old_powers.get(record['id'], {})
        if previous.get('status') not in {'approved', 'excluded'}:
            continue
        record['review']['status'] = previous['status']
        record['review']['notes'] = str(previous.get('notes') or '')
    return document


def _refresh_summary(document):
    sections = document['sections']
    target_counts = Counter(record['review']['status'] for record in sections['buff_targets'])
    power_counts = Counter(record['review']['status'] for record in sections['powers'])
    sections['review_summary'] = {
        'buff_targets': dict(sorted(target_counts.items())),
        'powers': dict(sorted(power_counts.items())),
    }
    sections['review_complete'] = not any(
        status in {'candidate', 'pending_review'}
        for records in (sections['buff_targets'], sections['powers'])
        for status in (record['review']['status'] for record in records)
    )
    return document


def build_document():
    sections, source = read_rules_sections()
    content = _content_document()
    if content['rules_fingerprint_sha256'] != rules_fingerprint(sections):
        raise RuntimeError('Reloaded content catalogue fingerprint is stale.')
    targets = _build_buff_targets(content, sections)
    powers, deferred_power_count = _build_powers(sections)
    return _refresh_summary({
        'schema_version': 1,
        'description': 'Installed Reloaded buff-target and superweapon review facts. No candidate enables gameplay.',
        'sections': {
            'catalogue_version': 1,
            'game_version': SUPPORTED_GAME_VERSION,
            'rules_source': _source_name(source),
            'rules_fingerprint_sha256': rules_fingerprint(sections),
            'active_factions': list(CONTENT_FACTIONS),
            'deferred_factions': ['CABAL'],
            'buff_targets': targets,
            'powers': powers,
            'deferred_power_count': deferred_power_count,
            'review_summary': {},
            'review_complete': False,
        },
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    document = _refresh_summary(_preserve_reviews(build_document()))
    sections = document['sections']
    if not args.write:
        print(json.dumps(sections['review_summary'], indent=2))
        return 0
    OUTPUT_PATH.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
    print(
        f'Wrote {OUTPUT_PATH.name}: {len(sections["buff_targets"])} targets, '
        f'{len(sections["powers"])} powers, {sections["deferred_power_count"]} deferred powers'
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
