"""Regress reported Moonbase launch and Vega mission ending failures."""

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.core.paths import BATTLE_INI
from randomizer.maps.generated import assert_file_hash, file_sha256
from randomizer.maps.ini import IniLines, all_section_value_maps, read_text
from randomizer.maps.pipeline import prepare_hooked_map
from randomizer.missions.catalogue import parse_missions
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.rewards.catalogue import REWARD_POOL
from randomizer.rewards.rules import tech_ids_for_rewards
from tools.core_gameplay_smoke import _Harness, _remove_owned


class _MissionHarness(_Harness):
    def __init__(self, *args, progression_mode, **kwargs):
        super().__init__(*args, **kwargs)
        self.progression_mode = progression_mode

    def active_progression_mode(self):
        return self.progression_mode

    def mission_checks(self, _code):
        return [{'id': 'victory', 'name': 'Victory', 'unlocked': False}]


def main():
    missions = {
        mission['code']: mission for mission in parse_missions(BATTLE_INI)
    }
    passed = []
    for code, unit_id in (
        ('YUR13', 'LTNK'), ('GDI06A_TS', 'TSE1'), ('GDI06B_TS', 'TSE1'),
    ):
        mission = missions[code]
        source = resolve_installed_scenario(mission['scenario'])
        source_hash = file_sha256(source)
        original = all_section_value_maps(IniLines(read_text(source).splitlines()))
        access = next(
            reward for reward in REWARD_POOL
            if reward.get('kind') != 'buff'
            and unit_id in tech_ids_for_rewards([reward])
        )
        for reward_mode in ('Standard', 'Chaos', 'Randomizer Arsenal'):
            for progression_mode in ('Mission List', 'Grid Mode', 'Shop Mode'):
                harness = _MissionHarness(
                    [access], mission['side'], mission['campaign'],
                    seed='RLR-REPORTED-MISSION-SMOKE',
                    reward_mode=reward_mode,
                    progression_mode=progression_mode,
                )
                hook = None
                try:
                    hook = prepare_hooked_map(
                        harness, mission,
                        extra_rules=harness.mission_required_launch_rules(mission),
                    )
                    sections = all_section_value_maps(IniLines(read_text(
                        Path(hook['generated_map'])
                    ).splitlines()))
                    if sections['Basic'].get('endofgame') != 'yes':
                        raise ValueError(f'{code}: authored campaign can continue.')
                    if 'victory' not in hook['markers'].values():
                        raise ValueError(f'{code}: victory marker is missing.')
                    if code == 'YUR13' and sections['YAWEAP'].get('prerequisite') != (
                        original['YAWEAP']['prerequisite']
                    ):
                        raise ValueError('Moonbase lost its authored barracks gate.')
                    assert_file_hash(source, source_hash)
                    passed.append(f'{code}/{reward_mode}/{progression_mode}')
                finally:
                    if hook:
                        _remove_owned(hook['root_map'])
                        _remove_owned(hook['generated_map'])
    print(json.dumps({'valid': True, 'passed': len(passed), 'cases': passed}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
