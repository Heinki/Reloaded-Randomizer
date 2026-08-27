"""Reproduce a large mixed unit-buff, access, and power reward launch."""

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.core.paths import BATTLE_INI
from randomizer.maps.generated import file_sha256
from randomizer.maps.pipeline import prepare_hooked_map
from randomizer.maps.rules import is_generated_hooked_map
from randomizer.missions.catalogue import parse_missions
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.rewards.catalogue import REWARD_BY_NAME
from tools.core_gameplay_smoke import _Harness


REWARD_NAMES = (
    'Tesla Tank Veteran Training I',
    'Nod Hover Transport Expanded Transport I',
    'Chaos Bomber Mobility I',
    'Chaos Bomber Logistics I',
    'Flak Track Mobility I',
    'Flak Track Drill I',
    'Shock Trooper Drill I',
    'GDI Limpet Drone Mobility I',
    'Sea Scorpion Sensor Suite I',
    'RPG Launcher Weapon Tuning I',
    'Sea Scorpion Armor Plating I',
    'Drop Pods Power',
    'Drop Pods Power Reinforced Payload I',
    'Tank Destroyer Recon Package I',
    'Tesla Tank Drill I',
    'Dreadnought Mobility I',
    'Dreadnought Reinforced Frames I',
    'GDI Power Turbine Veteran Training I',
    'Allied MCV Stealth Systems I',
    'Allied Patriot Missile Stealth Systems I',
    'Yuri Boomer Mobility I',
    'GDI MCV Mobility I',
    'Disc Thrower Logistics I',
    'Soviet Iron Curtain Device Access',
    'Stealth Harvester Reinforced Frames I',
    'Subterranean APC Reinforced Frames I',
    'Shock Trooper Recon Package I',
    'Drop Pods Power Accelerated Recharge I',
    'Harrier Weapon Tuning I',
    'Demolitions Truck Firepower I',
)

MISSION_CODES = (
    'ALL01_RA2',
    'SOV01_RA2',
    'ALL01',
    'SOV01',
    'YUR03',
    'GDI01A_TS',
    'NOD01A_TS',
    'GDI01A_FS',
    'NOD01A_FS',
)


def _remove_generated(path):
    path = Path(path)
    if not path.exists():
        return
    if not is_generated_hooked_map(path):
        raise RuntimeError(f'Refusing to remove unmarked map: {path}')
    path.unlink()


def main():
    missing_rewards = [name for name in REWARD_NAMES if name not in REWARD_BY_NAME]
    if missing_rewards:
        raise ValueError(f'Mixed smoke rewards missing: {missing_rewards}')
    rewards = [REWARD_BY_NAME[name] for name in REWARD_NAMES]
    missions = {mission['code']: mission for mission in parse_missions(BATTLE_INI)}
    failures = []
    for code in MISSION_CODES:
        mission = missions[code]
        source = resolve_installed_scenario(mission['scenario'])
        source_hash = file_sha256(source)
        harness = _Harness(
            rewards,
            mission['side'],
            mission['campaign'],
            seed='RLR-MIXED-REWARD-SMOKE',
        )
        hook = None
        try:
            hook = prepare_hooked_map(harness, mission)
            if not hook or not Path(hook['root_map']).is_file():
                raise RuntimeError('Generated launch map is missing.')
            if file_sha256(source) != source_hash:
                raise RuntimeError('Authored source changed during generation.')
            print(f'PASS {code}', flush=True)
        except Exception as exc:
            failures.append({'mission': code, 'error': str(exc)})
            print(f'FAIL {code}: {exc}', flush=True)
        finally:
            if hook:
                _remove_generated(hook['root_map'])
                _remove_generated(hook['generated_map'])

    report = {
        'valid': not failures,
        'mission_count': len(MISSION_CODES),
        'reward_count': len(rewards),
        'failures': failures,
    }
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
