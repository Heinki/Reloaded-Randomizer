"""Build the deterministic C&C Reloaded Archipelago catalogue.

The launcher owns mission and reward semantics.  The APWorld consumes this
generated snapshot so both sides use the same reviewed five-faction data.
"""

from hashlib import sha256
import json

from randomizer.config.game_profile import (
    CONTENT_FACTIONS,
    DEFERRED_CONTENT_FACTIONS,
    SUPPORTED_GAME_VERSION,
)
from randomizer.core.paths import BATTLE_INI
from randomizer.core.version import APP_VERSION
from randomizer.missions.catalogue import parse_missions
from randomizer.rewards.catalogue import MAX_REWARDS_PER_CHECK, REWARD_POOL
from randomizer.rewards.weights import main_reward_weight_type


SNAPSHOT_SCHEMA_VERSION = 1
GAME_NAME = 'C&C Reloaded'
PACKAGE_NAMESPACE = 'cnc_reloaded'
WORLD_VERSION = '0.3.0'
MINIMUM_AP_VERSION = '0.6.7'

# New mnemonic RL ranges. They never overlap Mental Omega's published IDs.
ITEM_ID_BASE = 0x524C000
ITEM_ID_END = 0x524FFFF
LOCATION_ID_BASE = 0x525C000
LOCATION_ID_END = 0x52EFFFF
LOCAL_VICTORY_ID_BASE = 0x52FF000
LOCAL_VICTORY_ID_END = LOCAL_VICTORY_ID_BASE + 0xFFF


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    )


def projection_checksum(projection):
    return sha256(_canonical_json(projection).encode('utf-8')).hexdigest()


def _item_classification(reward):
    if reward.get('enemy_reward'):
        return 'trap'
    return 'useful' if reward.get('kind') == 'buff' else 'progression'


def _check_name(check_id):
    if check_id == 'victory':
        return 'Mission Complete'
    return 'Objective ' + check_id.rsplit('_', 1)[-1]


def build_catalogue_projection():
    """Return stable AP data derived from live Reloaded catalogues."""
    items = [
        {
            'name': reward['name'],
            'classification': _item_classification(reward),
            'category': main_reward_weight_type(reward),
            'repeatable': reward.get('kind') == 'buff',
        }
        for reward in sorted(REWARD_POOL, key=lambda entry: entry['name'])
    ]

    missions = []
    for mission in parse_missions(BATTLE_INI):
        objective_hints = list(mission.get('objectives') or ())
        objective_count = max(0, int(mission.get('objective_count') or 0))
        checks = [
            {
                'id': f'objective_{index}',
                'name': f'Objective {index}',
                'hint': (
                    objective_hints[index - 1]
                    if index <= len(objective_hints)
                    else f'Complete reviewed objective milestone {index}.'
                ),
                'maximum_slots': MAX_REWARDS_PER_CHECK,
            }
            for index in range(1, objective_count + 1)
        ]
        checks.append({
            'id': 'victory',
            'name': 'Mission Complete',
            'hint': 'Win the mission.',
            'maximum_slots': (
                MAX_REWARDS_PER_CHECK
                * max(1, int(mission.get('reward_multiplier') or 1))
            ),
        })
        missions.append({
            'code': mission['code'],
            'title': mission['title'],
            'campaign': mission.get('campaign', ''),
            'faction': mission.get('faction', ''),
            'side': mission.get('side', ''),
            'scenario': mission['scenario'],
            'reward_multiplier': int(mission.get('reward_multiplier') or 1),
            'checks': checks,
        })

    return {
        'schema_version': SNAPSHOT_SCHEMA_VERSION,
        'game': GAME_NAME,
        'package_namespace': PACKAGE_NAMESPACE,
        'world_version': WORLD_VERSION,
        'minimum_ap_version': MINIMUM_AP_VERSION,
        'randomizer_version': APP_VERSION,
        'supported_game_version': SUPPORTED_GAME_VERSION,
        'active_factions': list(CONTENT_FACTIONS),
        'deferred_factions': list(DEFERRED_CONTENT_FACTIONS),
        'maximum_rewards_per_check': MAX_REWARDS_PER_CHECK,
        'items': items,
        'missions': missions,
    }


def _preserved_ids(existing, key):
    values = existing.get(key, ()) if isinstance(existing, dict) else ()
    return {
        entry['name']: int(entry['id'])
        for entry in values
        if isinstance(entry, dict)
        and isinstance(entry.get('name'), str)
        and isinstance(entry.get('id'), int)
    }


def build_snapshot(existing=None):
    """Assign stable IDs, retaining any IDs from a published snapshot."""
    projection = build_catalogue_projection()
    old_item_ids = _preserved_ids(existing or {}, 'items')
    old_location_ids = _preserved_ids(existing or {}, 'locations')

    used_item_ids = set(old_item_ids.values())
    next_item_id = max(used_item_ids, default=ITEM_ID_BASE - 1) + 1
    items = []
    for entry in projection['items']:
        item_id = old_item_ids.get(entry['name'])
        if item_id is None:
            while next_item_id in used_item_ids:
                next_item_id += 1
            item_id = next_item_id
            used_item_ids.add(item_id)
            next_item_id += 1
        if not ITEM_ID_BASE <= item_id <= ITEM_ID_END:
            raise ValueError(f'AP item ID range exhausted at {entry["name"]}.')
        items.append({**entry, 'id': item_id})

    used_location_ids = set(old_location_ids.values())
    next_location_id = max(
        used_location_ids,
        default=LOCATION_ID_BASE - 1,
    ) + 1
    locations = []
    for mission in projection['missions']:
        for check in mission['checks']:
            for slot in range(1, int(check['maximum_slots']) + 1):
                name = (
                    f'{mission["title"]} [{mission["code"]}] - '
                    f'{_check_name(check["id"])} '
                    f'- Reward {slot}'
                )
                location_id = old_location_ids.get(name)
                if location_id is None:
                    while next_location_id in used_location_ids:
                        next_location_id += 1
                    location_id = next_location_id
                    used_location_ids.add(location_id)
                    next_location_id += 1
                if not LOCATION_ID_BASE <= location_id <= LOCATION_ID_END:
                    raise ValueError(f'AP location ID range exhausted at {name}.')
                locations.append({
                    'name': name,
                    'id': location_id,
                    'mission': mission['code'],
                    'check': check['id'],
                    'slot': slot,
                })

    old_logic = {
        entry['mission']: entry
        for entry in (existing or {}).get('local_victories', ())
        if isinstance(entry, dict) and isinstance(entry.get('mission'), str)
    }
    local_victories = []
    for index, mission in enumerate(projection['missions']):
        code = mission['code']
        previous = old_logic.get(code, {})
        item_id = int(previous.get('item_id', LOCAL_VICTORY_ID_BASE + index))
        location_id = int(
            previous.get('location_id', LOCAL_VICTORY_ID_BASE + index)
        )
        if item_id in used_item_ids or location_id in used_location_ids:
            raise ValueError(f'Local-victory ID collision for {code}.')
        used_item_ids.add(item_id)
        used_location_ids.add(location_id)
        local_victories.append({
            'mission': code,
            'item_name': f'C&C Reloaded Local Victory: {code}',
            'item_id': item_id,
            'location_name': (
                f'{mission["title"]} [{code}] - Local Victory'
            ),
            'location_id': location_id,
        })

    return {
        **projection,
        'catalogue_checksum': projection_checksum(projection),
        'id_ranges': {
            'items': {'first': ITEM_ID_BASE, 'last': ITEM_ID_END},
            'locations': {'first': LOCATION_ID_BASE, 'last': LOCATION_ID_END},
            'local_victories': {
                'first': LOCAL_VICTORY_ID_BASE,
                'last': LOCAL_VICTORY_ID_END,
            },
        },
        'items': items,
        'locations': locations,
        'local_victories': local_victories,
        'options': {
            'launcher_settings': 'mapping',
            'generated_world': 'mapping',
        },
        'review': {
            'standalone_reward_items': len(items),
            'victory_missions_verified': len(projection['missions']),
            'objective_runtime_enabled': True,
            'cabal_deferred': True,
        },
        # AP uses the same full five-faction catalogue as standalone.
        'review_complete': bool(
            items and len(projection['missions']) == 108
        ),
    }


def runtime_catalogue_checksum():
    return projection_checksum(build_catalogue_projection())


def runtime_catalogue_is_compatible(checksum):
    return str(checksum or '') == runtime_catalogue_checksum()


def snapshot_is_current(snapshot):
    return isinstance(snapshot, dict) and snapshot == build_snapshot(snapshot)
