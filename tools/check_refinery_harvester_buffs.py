"""Regressions for upgraded harvesters delivered by refinery construction."""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from randomizer.core.paths import BATTLE_INI
from randomizer.maps.ini import IniLines, all_section_value_maps, read_text
from randomizer.maps.pipeline import prepare_hooked_map
from randomizer.maps.special_buildings import (
    DEFAULT_REFINERY_MINER_IDS, refinery_free_unit_pairs,
    validate_original_refinery_contract,
)
from randomizer.missions.catalogue import parse_missions
from randomizer.rewards.catalogue import REWARD_BY_BUFF_KEY, canonical_reward
from randomizer.ui.cameos import installed_rules_registry
from tools.core_gameplay_smoke import _Harness, _section_field


class RefineryHarvesterBuffChecks(unittest.TestCase):
    def test_refinery_contract_matches_installed_reloaded_rules(self):
        self.assertEqual(validate_original_refinery_contract()['issues'], [])
        self.assertEqual(refinery_free_unit_pairs({}, {}), DEFAULT_REFINERY_MINER_IDS)

    def test_discovery_respects_map_overrides_and_skips_support_buildings(self):
        installed = {
            'BuildingTypes': {'0': 'TSPROC', '1': 'CUSTOMREF', '2': 'GAOREP'},
            'TSPROC': {'Refinery': 'yes', 'FreeUnit': 'TSHARV'},
            'CUSTOMREF': {'Refinery': 'yes', 'FreeUnit': 'SHARV'},
            'GAOREP': {'Refinery': 'yes'},
        }
        authored = {
            'BuildingTypes': {'3': 'MAPREF'},
            'tsproc': {'freeunit': 'tsnharv'},
            'mapref': {'refinery': 'yes', 'freeunit': 'cmin'},
        }
        pairs = refinery_free_unit_pairs(authored, installed)
        self.assertEqual(pairs['TSPROC'], 'TSNHARV')
        self.assertEqual(pairs['CUSTOMREF'], 'SHARV')
        self.assertEqual(pairs['MAPREF'], 'CMIN')
        self.assertNotIn('GAOREP', pairs)
        self.assertNotIn('YARIREFN', pairs)
        self.assertNotIn('FAREFN', pairs)
        for disabled in ('none', '<none>', ''):
            with self.subTest(disabled=disabled):
                authored['tsproc']['freeunit'] = disabled
                self.assertNotIn('TSPROC', refinery_free_unit_pairs(authored, installed))
        authored['tsproc'] = {'refinery': 'no'}
        self.assertNotIn('TSPROC', refinery_free_unit_pairs(authored, installed))

    def test_refinery_spawns_use_fully_upgraded_factory_harvesters(self):
        missions = {mission['code']: mission for mission in parse_missions(BATTLE_INI)}
        _powers, installed = installed_rules_registry()
        rewards = [
            canonical_reward(REWARD_BY_BUFF_KEY['HARV', buff_type])
            for buff_type in (
                'cloak', 'health', 'armor', 'speed', 'sight', 'sensors',
                'cost', 'production',
            )
        ]
        pairs = {
            'GAREFN': 'CMIN', 'NAREFN': 'HARV',
            'TSPROC': 'TSHARV', 'TSPROC2': 'TSNHARV',
        }
        for mode in ('Standard', 'Chaos'):
            for code in ('ALL02_RA2', 'SOV02_RA2', 'GDI02A_TS', 'NOD02A_TS', 'YUR02'):
                with self.subTest(mode=mode, mission=code), TemporaryDirectory() as temporary:
                    mission = missions[code]
                    harness = _Harness(
                        rewards, mission['side'], mission['campaign'],
                        reward_mode=mode,
                    )
                    with (
                        patch('randomizer.maps.pipeline.GAME_ROOT', Path(temporary)),
                        patch('randomizer.maps.pipeline.GENERATED_MAP_DIR', Path(temporary) / 'maps'),
                        patch('randomizer.maps.pipeline.stage_randomizer_tooltips', return_value=None),
                        patch('randomizer.maps.pipeline.deploy_superweapon_sidebar_assets'),
                    ):
                        hook = prepare_hooked_map(
                            harness, mission,
                            extra_rules=harness.mission_required_launch_rules(mission),
                        )
                    sections = all_section_value_maps(IniLines(read_text(hook['root_map']).splitlines()))
                    registered = set(sections['VehicleTypes'].values())
                    for refinery_id, miner_id in pairs.items():
                        spawned_id = _section_field(sections, refinery_id, 'FreeUnit')
                        self.assertEqual(spawned_id, 'RLRP' + miner_id, refinery_id)
                        self.assertIn(spawned_id, registered)
                        self.assertEqual(_section_field(sections, spawned_id, 'Cloakable'), 'yes')
                        self.assertEqual(_section_field(sections, spawned_id, 'Sensors'), 'yes')
                        self.assertLess(float(_section_field(sections, spawned_id, 'BuildTimeMultiplier')), 1)
                        self.assertLess(
                            float(_section_field(sections, spawned_id, 'Cost')),
                            float(_section_field(installed, miner_id, 'Cost')),
                        )
                        for field in ('Strength', 'Speed', 'Sight'):
                            self.assertGreater(
                                float(_section_field(sections, spawned_id, field)),
                                float(_section_field(installed, miner_id, field)),
                            )
                    # Yuri's normal vehicle-built Slave Miner still receives the same buffs.
                    self.assertIn('RLRPSMIN', registered)
                    self.assertEqual(_section_field(sections, 'RLRPSMIN', 'Cloakable'), 'yes')


if __name__ == '__main__':
    unittest.main()
