"""Exercise every active Reloaded unit-buff type through map generation."""

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.rewards.catalogue import BUFF_TYPES, REWARD_POOL
from randomizer.rewards.rules import tech_ids_for_rewards
from tools.core_gameplay_smoke import run


MISSION_BY_FACTION = {
    'Allies': 'ALL01_RA2',
    'Soviets': 'SOV01_RA2',
    'Yuri': 'YUR01',
    'GDI': 'GDI01A_TS',
    'Nod': 'NOD01A_TS',
}


def _access_ids():
    return {
        tech_id
        for reward in REWARD_POOL
        if reward.get('kind') == 'access'
        for tech_id in tech_ids_for_rewards([reward])
    }


def main():
    access_ids = _access_ids()
    results = []
    for definition in BUFF_TYPES:
        buff_type = definition['id']
        reward = next(
            reward for reward in REWARD_POOL
            if reward.get('kind') == 'buff'
            and reward.get('buff_type') == buff_type
            and str(reward.get('unit') or '').upper() in access_ids
            and reward.get('factions')
        )
        faction = reward['factions'][0]
        result = run(
            MISSION_BY_FACTION[faction],
            reward['unit'],
            buff_type,
        )
        results.append({
            'buff_type': buff_type,
            'mission': result['mission'],
            'unit': reward['unit'],
            'reward': reward['name'],
        })
    print(json.dumps({
        'valid': True,
        'buff_type_count': len(results),
        'results': results,
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
