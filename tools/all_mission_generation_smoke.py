"""Generate and validate one representative randomized map for every mission."""

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.core.paths import BATTLE_INI
from randomizer.missions.catalogue import parse_missions
from tools.core_gameplay_smoke import run


STARTER_TECH_BY_SIDE = {
    'allies': 'E1',
    'soviets': 'E2',
    'yuri': 'INIT',
    'gdi': 'TSE1',
    'nod': 'TSNE1',
}


def main():
    missions = parse_missions(BATTLE_INI)
    failures = []
    for index, mission in enumerate(missions, 1):
        code = mission['code']
        try:
            run(
                code,
                STARTER_TECH_BY_SIDE[mission['side'].lower()],
                'health',
            )
            print(f'PASS {index:03}/{len(missions)} {code}', flush=True)
        except Exception as exc:
            failures.append({'mission': code, 'error': str(exc)})
            print(
                f'FAIL {index:03}/{len(missions)} {code}: {exc}',
                flush=True,
            )

    report = {
        'valid': not failures and len(missions) == 108,
        'mission_count': len(missions),
        'passed': len(missions) - len(failures),
        'failures': failures,
    }
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
