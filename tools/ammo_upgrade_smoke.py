"""Regress unlimited-ammo upgrades, old rewards, and finite aircraft ammo."""

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.content.inventory import read_rules_sections
from randomizer.core.paths import BATTLE_INI
from randomizer.maps import pipeline, tooltips
from randomizer.maps.ini import IniLines, all_section_value_maps, read_text
from randomizer.missions.catalogue import parse_missions
from randomizer.rewards.catalogue import (
    BUFF_TARGETS, REWARD_BY_BUFF_KEY, REWARD_BY_NAME, canonical_reward,
)
from randomizer.shop.catalogue import catalogue_entry, shop_catalogue
from tools.build_balance_catalogue import _candidate_buff_types
from tools.core_gameplay_smoke import run
from tools.reported_mission_smoke import _MissionHarness
from tools.review_buff_catalogue import review_document


def main():
    installed, _source = read_rules_sections()
    assert int(installed['APACHE']['Ammo']) == 2_147_483_645
    assert 'ammo' not in BUFF_TARGETS['APACHE']['allowed_buff_types']
    assert ('APACHE', 'ammo') not in REWARD_BY_BUFF_KEY
    assert ('ORCA', 'ammo') in REWARD_BY_BUFF_KEY
    assert ('TSORCA', 'ammo') in REWARD_BY_BUFF_KEY
    assert 'Harpy Ammo Reserves I' not in REWARD_BY_NAME
    assert not any(entry.reward_id == 'Harpy Ammo Reserves I' for entry in shop_catalogue())
    legacy = {
        'name': 'Harpy Ammo Reserves I', 'kind': 'buff',
        'unit': 'APACHE', 'buff_type': 'ammo', 'factions': ['Nod'],
    }
    for reward in (legacy, {'name': legacy['name']}):
        assert canonical_reward(reward)['retired_reward']
        assert catalogue_entry(reward) is None
    for ammo in (-1, 0, 2_147_483_645, 2_147_483_646, 2_147_483_647):
        assert 'ammo' not in _candidate_buff_types('aircraft', {'Ammo': str(ammo)}, [])
    assert 'ammo' in _candidate_buff_types('aircraft', {'Ammo': '4'}, [])

    # An old approved catalogue must not re-enable the Harpy ammo reward.
    stale_review = {'sections': {
        'buff_targets': [{
            'id': 'APACHE', 'candidate_buff_types': ['ammo', 'health'],
            'stats': {'ammo': 2_147_483_645}, 'review': {},
        }], 'powers': [],
    }}
    review_document(stale_review)
    reviewed = stale_review['sections']['buff_targets'][0]['review']
    assert reviewed['approved_buff_types'] == ['health']
    assert reviewed['excluded_buff_types'] == ['ammo']

    missions = {mission['code']: mission for mission in parse_missions(BATTLE_INI)}
    old_root, old_generated = pipeline.GAME_ROOT, pipeline.GENERATED_MAP_DIR
    old_assets = tooltips.RUNTIME_ASSET_DIR
    try:
        with tempfile.TemporaryDirectory(prefix='rlr-ammo-smoke-') as directory:
            root = Path(directory)
            pipeline.GAME_ROOT = root
            pipeline.GENERATED_MAP_DIR = root / 'generated'
            tooltips.RUNTIME_ASSET_DIR = root / 'assets'
            mission = missions['NOD01A_TS']
            harness = _MissionHarness(
                [REWARD_BY_NAME['Harpy Access'], *([legacy] * 100)],
                mission['side'], mission['campaign'], progression_mode='Shop Mode',
            )
            hook = pipeline.prepare_hooked_map(
                harness, mission, extra_rules=harness.mission_required_launch_rules(mission),
            )
            generated = all_section_value_maps(IniLines(read_text(Path(hook['generated_map'])).splitlines()))
            assert generated['RLRPAPACHE']['ammo'] == installed['APACHE']['Ammo']
            assert run('ALL01_RA2', 'ORCA', 'ammo')['valid']
    finally:
        pipeline.GAME_ROOT, pipeline.GENERATED_MAP_DIR = old_root, old_generated
        tooltips.RUNTIME_ASSET_DIR = old_assets
    print(json.dumps({'valid': True, 'harpy_ammo_upgrade_removed': True,
                      'legacy_upgrades_disabled': True, 'finite_ammo_upgrade_valid': True}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
