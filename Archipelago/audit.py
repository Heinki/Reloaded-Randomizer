"""Read-only validation for the C&C Reloaded APWorld foundation."""

import json
from pathlib import Path

from Archipelago.catalogue_contract import (
    GAME_NAME,
    ITEM_ID_BASE,
    ITEM_ID_END,
    LOCAL_VICTORY_ID_BASE,
    LOCAL_VICTORY_ID_END,
    LOCATION_ID_BASE,
    LOCATION_ID_END,
    MINIMUM_AP_VERSION,
    PACKAGE_NAMESPACE,
    WORLD_VERSION,
    snapshot_is_current,
)
from Archipelago.client.session import _scout_location_ids
from randomizer.config.game_profile import ENABLE_ARCHIPELAGO, FACTION_ORDER


ROOT = Path(__file__).resolve().parent
WORLD_ROOT = ROOT / 'APWorld' / PACKAGE_NAMESPACE
CATALOGUE_PATH = WORLD_ROOT / 'catalogue.json'
MANIFEST_PATH = WORLD_ROOT / 'archipelago.json'


def archipelago_foundation_report():
    snapshot = json.loads(CATALOGUE_PATH.read_text(encoding='utf-8'))
    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    required_files = (
        '__init__.py',
        'archipelago.json',
        'catalogue.json',
        'data.py',
        'options.py',
        'world.py',
        'docs/setup_en.md',
    )
    missing_files = [
        name for name in required_files if not (WORLD_ROOT / name).is_file()
    ]
    mission_codes = [mission['code'] for mission in snapshot['missions']]
    scenarios = [mission['scenario'].casefold() for mission in snapshot['missions']]
    location_ids = [int(entry['id']) for entry in snapshot['locations']]
    location_names = [entry['name'] for entry in snapshot['locations']]
    local_item_ids = [
        int(entry['item_id']) for entry in snapshot['local_victories']
    ]
    local_location_ids = [
        int(entry['location_id']) for entry in snapshot['local_victories']
    ]
    ranges_disjoint = (
        ITEM_ID_END < LOCATION_ID_BASE
        and LOCATION_ID_END < LOCAL_VICTORY_ID_BASE
    )
    ids_valid = bool(
        all(LOCATION_ID_BASE <= value <= LOCATION_ID_END for value in location_ids)
        and all(
            LOCAL_VICTORY_ID_BASE <= value <= LOCAL_VICTORY_ID_END
            for value in (*local_item_ids, *local_location_ids)
        )
        and len(location_ids) == len(set(location_ids))
        and len(location_names) == len(set(location_names))
        and len(local_item_ids) == len(set(local_item_ids))
        and len(local_location_ids) == len(set(local_location_ids))
        and not set(location_ids).intersection(local_location_ids)
    )
    python_identity_text = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in WORLD_ROOT.glob('*.py')
    ).casefold()
    identity_isolated = not any(
        token in python_identity_text
        for token in ('mental omega', 'mental_omega', 'morp')
    )
    snapshot_current = snapshot_is_current(snapshot)
    shop_purchase_scouting_valid = _scout_location_ids({
        'locations': {'MISSION': {'objective': [3, 1]}},
        'shop': {'purchase_locations': [5, 2]},
    }) == (1, 2, 3, 5)
    valid = all((
        not missing_files,
        snapshot_current,
        manifest == {
            'game': GAME_NAME,
            'minimum_ap_version': MINIMUM_AP_VERSION,
            'world_version': WORLD_VERSION,
            'authors': ['C&C Reloaded Randomizer contributors'],
        },
        snapshot['game'] == GAME_NAME,
        snapshot['package_namespace'] == PACKAGE_NAMESPACE,
        snapshot['active_factions'] == list(FACTION_ORDER),
        snapshot['deferred_factions'] == ['CABAL'],
        len(mission_codes) == 108,
        len(mission_codes) == len(set(mission_codes)),
        len(scenarios) == len(set(scenarios)),
        len(snapshot['local_victories']) == 108,
        ranges_disjoint,
        ids_valid,
        identity_isolated,
        shop_purchase_scouting_valid,
        not ENABLE_ARCHIPELAGO or snapshot['review_complete'],
    ))
    return {
        'game': snapshot['game'],
        'package_namespace': snapshot['package_namespace'],
        'world_version': snapshot['world_version'],
        'minimum_ap_version': snapshot['minimum_ap_version'],
        'catalogue_checksum': snapshot['catalogue_checksum'],
        'mission_count': len(mission_codes),
        'reserved_location_count': len(snapshot['locations']),
        'local_victory_count': len(snapshot['local_victories']),
        'approved_item_count': len(snapshot['items']),
        'id_ranges': snapshot['id_ranges'],
        'ranges_disjoint': ranges_disjoint,
        'ids_valid': ids_valid,
        'identity_isolated': identity_isolated,
        'shop_purchase_scouting_valid': shop_purchase_scouting_valid,
        'missing_files': missing_files,
        'snapshot_current': snapshot_current,
        'review': snapshot['review'],
        'review_complete': snapshot['review_complete'],
        'launcher_enabled': ENABLE_ARCHIPELAGO,
        'gameplay_ready': valid and snapshot['review_complete'],
        'valid': valid,
    }


def main():
    report = archipelago_foundation_report()
    print(json.dumps(report, indent=2))
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
