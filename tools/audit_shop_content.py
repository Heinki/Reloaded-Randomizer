"""Audit every installed unit and superweapon against the reviewed Shop roster.

Run from an installed game checkout. The full JSON report records excluded
and pending entries as well as approved content; it never promotes candidates.
"""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from randomizer.config.game_profile import ENABLE_CABAL
from randomizer.config.static import load_static_config
from randomizer.content.inventory import (
    read_rules_sections, rules_fingerprint, deferred_cabal_type_ids,
)
from randomizer.rewards.catalogue import ALWAYS_AVAILABLE_TECH_IDS, REWARD_POOL, BUFF_TARGETS
from randomizer.rewards.reloaded_roster import APPROVED_CLONE_SOURCE_IDS
from randomizer.shop.catalogue import shop_catalogue
from randomizer.shop.model import ShopRewardType
from tools.build_content_catalogue import _unit_records


def audit(*, assets=False):
    rules, source = read_rules_sections()
    content = load_static_config('rewards/reloaded_content_catalogue.json')
    balance = load_static_config('rewards/reloaded_balance_catalogue.json')
    prices = load_static_config('shop_mode.json')
    failures = []
    deferred = deferred_cabal_type_ids(rules)
    if rules_fingerprint(rules) != content['rules_fingerprint_sha256']:
        failures.append('Installed rules differ from the reviewed catalogue')
    entries = shop_catalogue()  # Also validates exact price coverage.
    access = {e.target_id: e for e in entries if e.reward_type is ShopRewardType.UNIT_ACCESS}
    leaked = deferred.intersection(
        set(BUFF_TARGETS) | set(APPROVED_CLONE_SOURCE_IDS) | {e.target_id for e in entries}
    )
    failures.extend(f'{unit}: CABAL content leaked into runtime stock' for unit in sorted(leaked))
    for records in (*content['content']['units'].values(), content['content']['defenses'], content['content']['production']):
        for record in records:
            if record['id'].upper() in deferred and any(
                r['status'] == 'approved' for r in record['reviews'].values()
            ):
                failures.append(f'{record["id"]}: CABAL content still approved')
    units = []
    registries = {'infantry': 'InfantryTypes', 'vehicles': 'VehicleTypes', 'aircraft': 'AircraftTypes'}
    candidates = _unit_records(rules)
    for category, registry in registries.items():
        records = {r['id']: r for r in content['content']['units'][category]}
        missing = {r['id'] for r in candidates[category]} - records.keys()
        failures.extend(f'{unit}: missing content review' for unit in sorted(missing))
        for unit in dict.fromkeys(rules[registry].values()):
            native = rules.get(unit, {})
            record = records.get(unit, {})
            approved = [f for f, r in record.get('reviews', {}).items() if r['status'] == 'approved']
            entry = access.get(unit.upper())
            if unit.upper().endswith('_AI') or unit.upper() in deferred:
                status = 'AI-only or deferred CABAL'
            elif entry:
                status = 'Shop access'
                if set(approved) != set(entry.factions):
                    failures.append(f'{unit}: Shop faction mismatch')
            elif unit.upper() in ALWAYS_AVAILABLE_TECH_IDS:
                status = 'Core utility access; no purchase required'
            elif approved:
                status = 'ERROR: approved unit missing Shop access'
                failures.append(f'{unit}: approved unit missing Shop access')
            elif record:
                status = 'Not approved; see faction reviews'
            else:
                status = 'Not a player production candidate (hidden/story/scenery/support form)'
            units.append({
                'id': unit, 'name': native.get('Name', unit), 'category': category,
                'tech_level': native.get('TechLevel'), 'status': status,
                'prerequisite': native.get('Prerequisite', ''),
                'built_at': native.get('BuiltAt', ''),
                'reviews': record.get('reviews', {}),
                'shop_reward': entry.reward_id if entry else None,
                'shop_prices': prices['unit_target_prices'].get(unit.upper()),
            })

    rewards = {r['superweapon'].upper(): r for r in REWARD_POOL if r.get('kind') == 'superweapon'}
    reviewed = {r['id'].upper(): r for r in balance['powers']}
    powers = []
    for power in dict.fromkeys(rules['SuperWeaponTypes'].values()):
        native = rules.get(power, {})
        reward = rewards.get(power.upper(), {})
        record = reviewed.get(power.upper(), {})
        overrides = reward.get('superweapon_rules') or {}
        powers.append({
            'id': power, 'type': native.get('Type'), 'name': native.get('Name'),
            'ui_name': native.get('UIName'),
            'native_cameo': native.get('SidebarPCX') or native.get('SidebarImage'),
            'shop_reward': reward.get('name'), 'description': reward.get('description'),
            'factions': reward.get('factions'),
            'effective_type': overrides.get('Type', native.get('Type')),
            'effective_cameo': overrides.get('SidebarPCX') or native.get('SidebarPCX') or native.get('SidebarImage'),
            'providers': record.get('providers', []),
            'review': record.get('review'),
            'status': 'Shop power' if reward else 'Internal, AI, deferred or unapproved power; not a standalone reward',
        })
    registered = {p.upper() for p in rules['SuperWeaponTypes'].values()}
    failures.extend(f'{p}: unregistered Shop power' for p in rewards.keys() - registered)
    names = Counter(r['name'] for r in REWARD_POOL)
    failures.extend(f'{n}: duplicate reward name' for n, count in names.items() if count > 1)
    if assets:
        from randomizer.ui.cameos import ensure_superweapon_cameos, ensure_unit_cameos
        cameos = ensure_superweapon_cameos(rewards, synchronous=True)
        failures.extend(f'{p}: missing power cameo' for p in rewards.keys() - cameos.keys())
        # Buffs must resolve the same effective PCX as access cards.
        from randomizer.application.shop_controller import ShopController
        specs = [ShopController._shop_power_cameo_for_item(None, r['name']) for r in REWARD_POOL
                 if r.get('kind') == 'superweapon' or r.get('power_buff_type')]
        resolved = ensure_superweapon_cameos(
            [p for p, _, _ in specs], {p: pcx for p, _, pcx in specs if pcx}, synchronous=True)
        failures.extend(f'{p}: missing access/buff cameo' for p, _, _ in specs if p not in resolved)
        unit_cameos = ensure_unit_cameos(access, synchronous=True)
        failures.extend(f'{u}: missing unit cameo' for u in access.keys() - unit_cameos.keys())
    return {
        'rules_source': source, 'rules_fingerprint_sha256': rules_fingerprint(rules),
        'unit_count': len(units), 'registered_power_count': len(powers),
        'shop_unit_access_count': len(access), 'shop_power_count': len(rewards),
        'unit_status_counts': dict(Counter(u['status'] for u in units)),
        'assets_checked': assets, 'units': units, 'powers': powers,
        'cabal_enabled': ENABLE_CABAL,
        'disabled_content_excluded': not leaked,
        'failures': failures, 'valid': not failures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = audit(assets=args.assets)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in {'units', 'powers'}}, indent=2))
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
