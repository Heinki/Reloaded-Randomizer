"""Verify every Reloaded power reward becomes an isolated player clone."""

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.core.paths import BATTLE_INI
from randomizer.maps.base import randomizer_clone_type_id
from randomizer.maps.ini import (
    IniLines,
    all_section_value_maps,
    read_text,
    section_value_map_preserve,
)
from randomizer.maps.pipeline import prepare_hooked_map
from randomizer.maps.rules import is_generated_hooked_map
from randomizer.missions.catalogue import parse_missions
from randomizer.rewards.catalogue import REWARD_POOL
from tools.core_gameplay_smoke import _Harness


def _remove_generated(path):
    path = Path(path)
    if not path.exists():
        return
    if not is_generated_hooked_map(path):
        raise RuntimeError(f'Refusing to remove unmarked map: {path}')
    path.unlink()


def main():
    power_rewards = [
        reward for reward in REWARD_POOL
        if reward.get('kind') == 'superweapon'
    ]
    power_buff_rewards = [
        reward for reward in REWARD_POOL
        if reward.get('kind') == 'buff' and reward.get('power_buff_type')
    ]
    payload_unit_buffs = [
        reward for reward in REWARD_POOL
        if reward.get('kind') == 'buff'
        and str(reward.get('unit') or '').upper() in {'E1', 'TSE1', 'TSE2'}
        and reward.get('buff_type') == 'health'
    ]
    rewards = power_rewards + power_buff_rewards + payload_unit_buffs
    mission = next(
        mission for mission in parse_missions(BATTLE_INI)
        if mission['code'] == 'ALL01_RA2'
    )
    harness = _Harness(
        rewards,
        mission['side'],
        mission['campaign'],
        seed='RLR-POWER-CLONE-SMOKE',
    )
    hook = None
    failures = []
    try:
        hook = prepare_hooked_map(harness, mission)
        lines = IniLines(
            read_text(Path(hook['generated_map'])).splitlines()
        )
        registered = {
            str(value).upper()
            for value in section_value_map_preserve(
                lines, 'SuperWeaponTypes'
            ).values()
        }
        sections = all_section_value_maps(lines)

        def value(values, field):
            return str((values or {}).get(str(field).lower(), ''))

        clones = {}
        for reward in power_rewards:
            source = str(reward.get('superweapon') or '')
            clone = str(
                reward.get('superweapon_clone')
                or randomizer_clone_type_id(source)
            )
            clones[source] = clone
            values = section_value_map_preserve(lines, clone)
            if clone.upper() not in registered:
                failures.append(f'{source}: clone is not registered ({clone})')
            if str(values.get('SW.AllowPlayer', '')).lower() != 'yes':
                failures.append(f'{source}: clone is not player-enabled ({clone})')
            if str(values.get('SW.AllowAI', '')).lower() != 'no':
                failures.append(f'{source}: clone is not AI-isolated ({clone})')

        def require_value(power_id, field, expected):
            clone = clones[power_id]
            actual = value(sections.get(clone, {}), field)
            if actual != str(expected):
                failures.append(
                    f'{power_id}.{field}: expected {expected!r}, got {actual!r}'
                )

        require_value('SpawnCarryallFromAirSW', 'Money.Amount', '-850')
        require_value(
            'SpawnCarryallFromAirSW',
            'Deliver.Types',
            'TSCARRYALL_DUMMY,TSCARRYALL_DUMMY',
        )
        require_value('ParaDropSpecial', 'ParaDrop.Num', '8')
        require_value('SpyPlaneSpecial', 'SpyPlane.Count', '2')
        require_value('TiberiumShowerSpecial', 'ParaDrop.Num', '2')
        require_value('DropPodSpecial', 'DropPod.Minimum', '8')
        require_value('DropPodSpecial', 'DropPod.Maximum', '10')
        require_value('IronCurtainSpecial', 'Protect.Duration', '690')
        require_value('ForceShieldSpecial', 'Protect.Duration', '518')

        chemical = sections.get(clones['TiberiumShowerSpecial'], {})
        chemical_payload = value(chemical, 'ParaDrop.Types')
        if chemical_payload == 'TIBBOMB' or not chemical_payload:
            failures.append('Chemical Bomb payload was not isolated to its clone.')
        elif value(sections.get(chemical_payload, {}), 'Strength') != '5750':
            failures.append('Chemical Bomb cloned payload health was not increased.')

        hunter = sections.get(clones['HuntSeekSpecial'], {})
        hunter_payload = value(hunter, 'HunterSeeker.Type')
        if hunter_payload == 'GHUNTER' or not hunter_payload:
            failures.append('Hunter Seeker payload was not isolated to its clone.')
        elif value(sections.get(hunter_payload, {}), 'Strength') != '5750':
            failures.append('Hunter Seeker cloned payload health was not increased.')

        emp = sections.get(clones['EMPulseSpecial'], {})
        emp_warhead = value(emp, 'SW.Warhead')
        emp_values = sections.get(emp_warhead, {})
        if not emp_warhead or emp_warhead == 'EMPuls':
            failures.append('EM Pulse warhead was not isolated to its clone.')
        if value(emp_values, 'EMP.Duration') != '1500':
            failures.append('EM Pulse status effect was not increased.')
        if value(emp_values, 'Versus.super_heavy_armor') != '100%':
            failures.append('EM Pulse all-vehicle targeting was not generated.')
        emp_cannon = value(emp, 'EMPulse.Cannons')
        emp_cannon_values = sections.get(emp_cannon, {})
        if not emp_cannon or emp_cannon == 'GAPULS' or emp_cannon == 'NAPULS':
            failures.append('EM Pulse did not use a private portable cannon.')
        if value(emp, 'SW.RangeMinimum') != '-1':
            failures.append('EM Pulse minimum targeting range was not removed.')
        if value(emp, 'SW.RangeMaximum') != '-1':
            failures.append('EM Pulse maximum targeting range was not removed.')
        if value(emp, 'SW.Inhibitors'):
            failures.append('EM Pulse inhibitors were not removed.')
        if value(emp, 'SW.AuxBuildings'):
            failures.append('EM Pulse foreign-tech gate was not removed.')
        if value(emp, 'SW.FireIntoShroud').lower() != 'yes':
            failures.append('EM Pulse cannot target shrouded cells.')
        if value(emp_cannon_values, 'Primary') != 'RLRPEMPWEAPON':
            failures.append('EM Pulse portable cannon lacks its private weapon.')
        if value(emp_cannon_values, 'InvisibleInGame').lower() != 'yes':
            failures.append('EM Pulse portable cannon is not hidden.')
        emp_weapon = sections.get('RLRPEMPWEAPON', {})
        if value(emp_weapon, 'Range') != '384':
            failures.append('EM Pulse private cannon range was not unrestricted.')
        if value(emp_weapon, 'Warhead') != emp_warhead:
            failures.append('EM Pulse private weapon does not use buffed warhead.')

        paradrop_types = str(
            value(
                sections.get(clones['ParaDropSpecial'], {}),
                'ParaDrop.Types',
            )
        ).split(',')
        if not paradrop_types or any(
            not type_id or type_id == 'E1' or type_id not in sections
            for type_id in paradrop_types
        ):
            failures.append(
                'Paratrooper Drop did not use player unit clones: '
                + ','.join(paradrop_types)
            )

        drop_pod_types = str(
            value(
                sections.get(clones['DropPodSpecial'], {}),
                'DropPod.Types',
            )
        ).split(',')
        if len(drop_pod_types) != 4 or any(
            not type_id or type_id in {'TSE1', 'TSE2'} or type_id not in sections
            for type_id in drop_pod_types
        ):
            failures.append('Drop Pods did not use four player unit clones.')
        for type_id in set(drop_pod_types):
            values = sections.get(type_id, {})
            if value(values, 'Selectable').lower() != 'yes':
                failures.append(
                    f'Drop Pod payload clone is not selectable: {type_id}.'
                )
            if value(values, 'IsSelectableCombatant').lower() != 'yes':
                failures.append(
                    f'Drop Pod payload clone is not controllable: {type_id}.'
                )
        isolated_log = any(
            'Prepared isolated building-free power rewards for:'
            in entry['message']
            for entry in harness.logs
        )
        if not isolated_log:
            failures.append('Power clone preparation was not reported.')
    finally:
        if hook:
            _remove_generated(hook['root_map'])
            _remove_generated(hook['generated_map'])

    report = {
        'valid': not failures and len(power_rewards) == 18,
        'power_reward_count': len(power_rewards),
        'power_buff_reward_count': len(power_buff_rewards),
        'isolated_clone_count': len(power_rewards),
        'failures': failures,
    }
    if failures:
        report['clone_logs'] = [
            entry['message'] for entry in harness.logs
            if any(
                token in entry['message'].lower()
                for token in ('clone', 'buff', 'deliver', 'payload')
            )
        ]
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
