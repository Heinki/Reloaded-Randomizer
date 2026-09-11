"""Rebuild explicit Reloaded Shop prices from reviewed catalogue tiers.

This maintainer command migrates legacy tier-wide pricing into exact target
records. Unit values preserve Reloaded's reviewed TechLevel tier policy. Power
values use Reloaded categories: offensive, secondary, and aid.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHOP_CONFIG_PATH = PROJECT_ROOT / 'configs' / 'shop_mode.json'
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.rewards.catalogue import REWARD_POOL
from randomizer.shop.catalogue import canonical_reward_for_id, catalogue_entry
from randomizer.shop.config import SHOP_CONFIG
from randomizer.shop.model import ShopRewardType

UNIT_PRICES = {
    'tier_1': (3, 2, 10, 5),
    'tier_2': (6, 4, 25, 8),
    'tier_3': (10, 6, 50, 12),
}
POWER_PRICES = {
    'offensive': (10, 6, 50, 12),
    'secondary': (6, 4, 25, 8),
    'aid': (5, 3, 25, 5),
}


def _entries():
    entries = []
    seen = set()
    excluded = set(SHOP_CONFIG.excluded_reward_ids)
    for reward in REWARD_POOL:
        entry = catalogue_entry(reward)
        if (
            entry is None
            or entry.reward_id in seen
            or entry.reward_id in excluded
        ):
            continue
        seen.add(entry.reward_id)
        entries.append(entry)
    return tuple(entries)


def _unit_prices(entries):
    access = {
        entry.target_id: entry for entry in entries
        if entry.reward_type is ShopRewardType.UNIT_ACCESS
    }
    buffs = {
        entry.target_id: entry for entry in entries
        if entry.reward_type is ShopRewardType.UNIT_BUFF
    }
    prices = {}
    for target_id in sorted(set(access) | set(buffs)):
        entry = access.get(target_id) or buffs[target_id]
        run_access, run_buff, permanent_access, permanent_buff = (
            UNIT_PRICES[entry.tier]
        )
        prices[target_id] = {
            'run_access': run_access if target_id in access else None,
            'run_buff': run_buff if target_id in buffs else None,
            'permanent_access': (
                permanent_access if target_id in access else None
            ),
            'permanent_buff': (
                permanent_buff if target_id in buffs else None
            ),
        }
    return prices


def _power_prices(entries):
    access = {
        entry.target_id: entry for entry in entries
        if entry.reward_type is ShopRewardType.POWER_ACCESS
    }
    buffs = {
        entry.target_id: entry for entry in entries
        if entry.reward_type is ShopRewardType.POWER_BUFF
    }
    prices = {}
    for target_id in sorted(set(access) | set(buffs)):
        source = access.get(target_id) or buffs[target_id]
        reward = canonical_reward_for_id(source.reward_id)
        category = str(reward.get('power_category') or 'aid')
        run_access, run_buff, permanent_access, permanent_buff = (
            POWER_PRICES[category]
        )
        prices[target_id] = {
            'run_access': run_access if target_id in access else None,
            'run_buff': run_buff if target_id in buffs else None,
            'permanent_access': (
                permanent_access if target_id in access else None
            ),
            'permanent_buff': (
                permanent_buff if target_id in buffs else None
            ),
        }
    return prices


def main():
    document = json.loads(SHOP_CONFIG_PATH.read_text(encoding='utf-8'))
    sections = document['sections']
    entries = _entries()
    legacy_keys = (
        'run_unit_prices',
        'run_buff_prices',
        'permanent_unit_prices',
        'permanent_buff_prices',
    )
    for key in legacy_keys:
        sections.pop(key, None)
    insertion = list(sections).index('permanent_upgrades')
    ordered = list(sections.items())
    ordered[insertion:insertion] = [
        ('power_target_prices', _power_prices(entries)),
        ('unit_target_prices', _unit_prices(entries)),
    ]
    document['sections'] = dict(ordered)
    SHOP_CONFIG_PATH.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    print(
        f'{SHOP_CONFIG_PATH}: '
        f'{len(document["sections"]["unit_target_prices"])} unit targets, '
        f'{len(document["sections"]["power_target_prices"])} power targets'
    )


if __name__ == '__main__':
    main()
