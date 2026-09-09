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


SNAPSHOT_SCHEMA_VERSION = 1
GAME_NAME = 'C&C Reloaded'
PACKAGE_NAMESPACE = 'cnc_reloaded'
WORLD_VERSION = '1.0.0'
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


# This published catalogue has identical item/mission semantics and IDs. Its
# checksum included release metadata, which is excluded from new checksums.
BACKWARD_COMPATIBLE_CATALOGUE_CHECKSUMS = frozenset({
    '0053e46817c9e2f6d952b803d9cb9784da2bb2fde3f9e72a211a057b20ad827d',
})


def projection_checksum(projection):
    content = {key: value for key, value in projection.items()
               if key not in {'world_version', 'randomizer_version'}}
    return sha256(_canonical_json(content).encode('utf-8')).hexdigest()


def snapshot_checksum_is_valid(snapshot):
    """Validate checked-in generated data without installed game assets."""
    if not isinstance(snapshot, dict):
        return False
    projection_keys = (
        'schema_version',
        'game',
        'package_namespace',
        'world_version',
        'minimum_ap_version',
        'randomizer_version',
        'supported_game_version',
        'active_factions',
        'deferred_factions',
        'maximum_rewards_per_check',
        'items',
        'missions',
    )
    if any(key not in snapshot for key in projection_keys):
        return False
    projection = {
        key: snapshot[key]
        for key in projection_keys
    }
    projection['items'] = [
        {key: value for key, value in item.items() if key != 'id'}
        for item in snapshot['items']
        if isinstance(item, dict)
    ]
    return snapshot.get('catalogue_checksum') == projection_checksum(projection)


def catalogue_sources_available():
    """Return whether live Reloaded inputs needed for regeneration exist."""
    if not BATTLE_INI.is_file():
        return False
    from randomizer.content.inventory import read_rules_sections

    try:
        read_rules_sections()
    except (FileNotFoundError, OSError):
        return False
    return True


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
    # Reward definitions intentionally inspect installed Reloaded rules. Keep
    # this import lazy so clean source checkouts can package and verify the
    # already-reviewed, checked-in catalogue without proprietary game assets.
    from randomizer.rewards.catalogue import MAX_REWARDS_PER_CHECK, REWARD_POOL
    from randomizer.rewards.weights import main_reward_weight_type

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
        # The launcher applies a finale multiplier to every active reward
        # check, then places all multiplier bonuses on the victory check.
        # Reserve the victory's own base slots plus the worst-case bonus for
        # every objective and victory check.  The previous ``base *
        # multiplier`` capacity was too small as soon as a multiplied mission
        # also exposed an objective (for example YUR13 needed 150 slots but
        # the APWorld reserved only 90).
        reward_multiplier = max(
            1, int(mission.get('reward_multiplier') or 1)
        )
        active_check_count = len(checks) + 1
        checks.append({
            'id': 'victory',
            'name': 'Mission Complete',
            'hint': 'Win the mission.',
            'maximum_slots': (
                MAX_REWARDS_PER_CHECK
                + active_check_count
                * MAX_REWARDS_PER_CHECK
                * (reward_multiplier - 1)
            ),
        })
        missions.append({
            'code': mission['code'],
            'title': mission['title'],
            'campaign': mission.get('campaign', ''),
            'faction': mission.get('faction', ''),
            'side': mission.get('side', ''),
            'scenario': mission['scenario'],
            'reward_multiplier': reward_multiplier,
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
        'compatible_catalogue_checksums': sorted(
            BACKWARD_COMPATIBLE_CATALOGUE_CHECKSUMS
        ),
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
    return (
        str(checksum or '') == runtime_catalogue_checksum()
        or str(checksum or '') in BACKWARD_COMPATIBLE_CATALOGUE_CHECKSUMS
    )


def snapshot_is_current(snapshot):
    return isinstance(snapshot, dict) and snapshot == build_snapshot(snapshot)
