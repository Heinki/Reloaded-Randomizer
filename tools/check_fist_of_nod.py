"""Regressions for the Fist of Nod's randomized vehicle production."""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from randomizer.content.inventory import read_rules_sections
from randomizer.core.paths import BATTLE_INI
from randomizer.maps.generated import file_sha256
from randomizer.maps.ini import IniLines, all_section_value_maps, read_text
from randomizer.maps.pipeline import prepare_hooked_map
from randomizer.missions.access import (
    mission_basic_unit_rules, mission_production_buildings,
)
from randomizer.missions.catalogue import parse_missions
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.rewards.catalogue import NAVAL_UNIT_IDS, REWARD_POOL
from randomizer.rewards.rules import tech_ids_for_rewards
from tools.core_gameplay_smoke import _Harness, _section_field


def prerequisite_paths(sections, unit_id):
    """Read the engine's normal and enabled alternative prerequisite lists."""
    count = int(_section_field(sections, unit_id, 'Prerequisite.Lists') or 0)
    return [
        tuple(str(value).upper().split(','))
        for field in ('Prerequisite', *(
            f'Prerequisite.List{index}' for index in range(1, count + 1)
        ))
        if (value := _section_field(sections, unit_id, field))
    ]


class FistOfNodChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.missions = {m['code']: m for m in parse_missions(BATTLE_INI)}
        cls.installed, _ = read_rules_sections()

    def generate(self, code, mode, rewards):
        mission = self.missions[code]
        harness = _Harness(
            rewards, mission['side'], mission['campaign'], reward_mode=mode,
        )
        source = resolve_installed_scenario(mission['scenario'])
        source_hash = file_sha256(source)
        with TemporaryDirectory() as temporary:
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
        self.assertEqual(file_sha256(source), source_hash)
        return sections

    def test_mobile_only_production_is_discovered(self):
        # No Construction Yard, MCV, or conventional war factory exists.
        lines = IniLines([
            '[Basic]', 'Player=Nod', '[Countries]', '0=NodCountry',
            '[Houses]', '0=Nod', '[Nod]', 'Country=NodCountry',
            '[Units]', '0=Nod,MOBWARN,256,10,10,0,Guard,None,0,-1,0,-1,1,1',
        ])
        self.assertIn('DNWEAP', mission_production_buildings(lines))
        rules = mission_basic_unit_rules(lines, earned_access_ids={'TSBIKE'})
        self.assertIn(('DNWEAP',), prerequisite_paths(rules, 'TSBIKE'))
        self.assertNotIn('TICKT', rules)

    def test_earned_vehicle_rosters_use_native_and_cloned_fist(self):
        nod_vehicle_rewards = [
            reward for reward in REWARD_POOL
            if reward.get('kind') == 'access'
            and reward.get('access_category') == 'units'
            and 'Nod' in reward.get('factions', ())
            and not tech_ids_for_rewards([reward]).intersection(NAVAL_UNIT_IDS)
        ]
        other_rewards = [
            reward for reward in REWARD_POOL
            if reward.get('kind') == 'access'
            and tech_ids_for_rewards([reward]).intersection({'MTNK', 'TSNE1', 'APACHE', 'HYDRASUB'})
        ]
        nod_ids = tech_ids_for_rewards(nod_vehicle_rewards)
        for mode in ('Standard', 'Chaos', 'Randomizer Arsenal'):
            with self.subTest(mode=mode):
                sections = self.generate('NOD08A_FS', mode, nod_vehicle_rewards + other_rewards)
                for source_id in nod_ids:
                    clone_id = 'RLRP' + source_id
                    paths = prerequisite_paths(sections, clone_id)
                    self.assertIn(('DNWEAP',), paths, clone_id)
                    self.assertIn(('RLRPDNWEAP',), paths, clone_id)
                    self.assertEqual(_section_field(sections, clone_id, 'TechLevel'), '1')
                for source_id in ('TSNE1', 'APACHE', 'HYDRASUB'):
                    paths = prerequisite_paths(sections, 'RLRP' + source_id)
                    self.assertNotIn(('DNWEAP',), paths, source_id)
                    self.assertNotIn(('RLRPDNWEAP',), paths, source_id)
                foreign_paths = prerequisite_paths(sections, 'RLRPMTNK')
                if mode == 'Standard':
                    self.assertNotIn(('DNWEAP',), foreign_paths)
                else:
                    self.assertIn(('DNWEAP',), foreign_paths)
                self.assertEqual(_section_field(sections, 'RLRPMOBWARN', 'DeploysInto'), 'RLRPDNWEAP')
                self.assertEqual(_section_field(sections, 'RLRPDNWEAP', 'UndeploysInto'), 'RLRPMOBWARN')
                self.assertEqual(_section_field(sections, 'RLRPDNWEAP', 'Factory'), 'UnitType')
                self.assertIn('RLRPDNWEAP', sections['BuildingTypes'].values())
                # The deployed form cannot be built directly from a Yard.
                self.assertNotEqual(_section_field(sections, 'RLRPDNWEAP', 'TechLevel'), '1')
                for field in ('Owner', 'RequiredHouses'):
                    self.assertEqual(
                        _section_field(sections, 'RLRPDNWEAP', field),
                        _section_field(sections, 'RLRPMOBWARN', field),
                    )
                self.assertFalse(any(
                    value.split(',')[1] == 'RLRPDNWEAP'
                    for value in sections.get('Structures', {}).values()
                ))

    def test_starting_fist_does_not_grant_unearned_units(self):
        reward = next(
            reward for reward in REWARD_POOL
            if reward.get('kind') == 'access'
            and 'TSBIKE' in tech_ids_for_rewards([reward])
        )
        for mode in ('Standard', 'Chaos', 'Randomizer Arsenal'):
            with self.subTest(mode=mode):
                sections = self.generate('NOD08A_FS', mode, [reward])
                self.assertIn(('DNWEAP',), prerequisite_paths(sections, 'RLRPTSBIKE'))
                self.assertNotIn('RLRPTICKT', sections)
                self.assertNotIn('RLRPMOBWARN', sections)
                self.assertEqual(sections['Units']['6'].split(',')[1], 'MOBWARN')
                # Enemy and scripted factory transforms retain native identity.
                self.assertEqual(
                    _section_field(sections, 'DNWEAP', 'UndeploysInto')
                    or _section_field(self.installed, 'DNWEAP', 'UndeploysInto'),
                    'MOBWARN',
                )

    def test_foreign_chaos_fist_keeps_factory_ownership_on_undeploy(self):
        rewards = [
            reward for reward in REWARD_POOL
            if reward.get('kind') == 'access'
            and tech_ids_for_rewards([reward]).intersection({'MOBWARN', 'TSBIKE'})
        ]
        sections = self.generate('ALL02_RA2', 'Chaos', rewards)
        self.assertIn(('RLRPDNWEAP',), prerequisite_paths(sections, 'RLRPTSBIKE'))
        for field in ('Owner', 'RequiredHouses'):
            self.assertEqual(
                _section_field(sections, 'RLRPDNWEAP', field),
                _section_field(sections, 'RLRPMOBWARN', field),
            )
        self.assertEqual(_section_field(sections, 'RLRPDNWEAP', 'UndeploysInto'), 'RLRPMOBWARN')


if __name__ == '__main__':
    unittest.main()
