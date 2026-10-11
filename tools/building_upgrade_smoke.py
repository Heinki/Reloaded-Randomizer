"""Check native/clone attachment parity and the reported Ion Uplink launch."""

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.content.inventory import read_rules_sections
from randomizer.core.collections import comma_items
from randomizer.core.paths import BATTLE_INI
from randomizer.maps.ini import (
    IniLines, all_section_value_maps, merge_ini_section_values, read_text,
)
from randomizer.maps.pipeline import prepare_hooked_map
from randomizer.maps.special_buildings import building_upgrade_clone_rules
from randomizer.missions.catalogue import parse_missions
from randomizer.rewards.catalogue import REWARD_POOL
from randomizer.rewards.rules import tech_ids_for_rewards
from tools.core_gameplay_smoke import _Harness, _remove_owned


def check_edge_cases():
    installed = {
        'BuildingTypes': dict(enumerate([
            'HOST', 'OTHER', 'UPGRADE', 'LISTUPGRADE', 'AIUPGRADE',
        ])),
        'UPGRADE': {'PowersUpBuilding': 'HOST', 'PowersUpToLevel': '-1'},
        'LISTUPGRADE': {
            'PowersUp.Buildings': 'HOST,OTHER', 'PowersUp.Owner': 'Self,Ally',
        },
        'AIUPGRADE': {'PowersUpBuilding': 'OTHER'},
    }
    lines = IniLines([
        '[BuildingTypes]', '10=P1', '11=REFHOST', '12=CLONEUPGRADE',
        '[CLONEUPGRADE]', 'powersupbuilding=HOST',
    ])
    handled = {
        'HOST': {'clone_id': 'P1', 'reference_clone_id': 'REFHOST'},
        'UPGRADE': {'clone_id': 'CLONEUPGRADE'},
        'OTHER': {'clone_id': 'ABSENT'},
    }
    rules = building_upgrade_clone_rules(lines, installed, handled)
    expected_hosts = {'HOST', 'P1', 'REFHOST'}
    assert set(comma_items(rules['UPGRADE']['PowersUp.Buildings'])) == expected_hosts
    assert set(comma_items(rules['CLONEUPGRADE']['PowersUp.Buildings'])) == expected_hosts
    assert rules['CLONEUPGRADE']['PowersUpBuilding'] == 'P1'
    assert 'PowersUpBuilding' not in rules['UPGRADE']
    assert set(comma_items(rules['LISTUPGRADE']['PowersUp.Buildings'])) == expected_hosts | {'OTHER'}
    assert 'AIUPGRADE' not in rules
    assert all(set(values) <= {'PowersUpBuilding', 'PowersUp.Buildings'} for values in rules.values())
    merge_ini_section_values(lines, rules)
    assert not building_upgrade_clone_rules(lines, installed, handled)

    # Map-authored host changes take precedence over installed attachment rules.
    override_lines = IniLines([
        '[BuildingTypes]', '10=P1', '11=REFHOST', '12=CLONEUPGRADE',
        '[UPGRADE]', 'PowersUpBuilding=OTHER',
    ])
    override_rules = building_upgrade_clone_rules(override_lines, installed, handled)
    assert 'UPGRADE' not in override_rules
    assert not building_upgrade_clone_rules(lines, installed, {})
    return ['compact/reference hosts', 'list-only attachment', 'absent clone',
            'native AI host', 'map override', 'idempotence', 'no clones']


def check_generated_launches():
    installed, _source = read_rules_sections()
    mission = next(
        mission for mission in parse_missions(BATTLE_INI)
        if mission['code'] == 'ALL09_RA2'
    )
    reports = []
    for source_ids in [('GAPLUG',), ('TSGAPLUG3',), ('GAPLUG', 'TSGAPLUG3')]:
        rewards = [
            next(reward for reward in REWARD_POOL
                 if reward.get('kind') == 'access'
                 and source_id in tech_ids_for_rewards([reward]))
            for source_id in source_ids
        ]
        harness = _Harness(
            rewards, mission['side'], mission['campaign'],
            seed='RLR-UPGRADE-SMOKE-' + '-'.join(source_ids),
            reward_mode='Chaos',
        )
        hook = None
        try:
            hook = prepare_hooked_map(harness, mission)
            sections = {
                name.lower(): values
                for name, values in all_section_value_maps(IniLines(
                    read_text(Path(hook['generated_map'])).splitlines()
                )).items()
            }
            registered = set(installed['BuildingTypes'].values())
            registered.update(sections.get('buildingtypes', {}).values())
            host_clone = 'RLRPGAPLUG'
            hosts = {'GAPLUG'}
            if host_clone in registered:
                hosts.add(host_clone)
            for upgrade_id in ('TSGAPLUG2', 'TSGAPLUG3', 'TSGAPLUG4'):
                for identifier in (upgrade_id, 'RLRP' + upgrade_id):
                    if identifier not in registered:
                        continue
                    values = {key.lower(): value for key, value in installed[upgrade_id].items()}
                    values.update(sections.get(identifier.lower(), {}))
                    actual_hosts = set(comma_items(values.get('powersup.buildings', '')))
                    actual_hosts.add(values['powersupbuilding'])
                    assert hosts <= actual_hosts, (identifier, hosts, actual_hosts)
                    assert set(actual_hosts) <= registered, (identifier, actual_hosts)
                    assert values['powersuptolevel'] == installed[upgrade_id]['PowersUpToLevel']
                    if identifier.startswith('RLRP') and host_clone in registered:
                        assert values['powersupbuilding'] == host_clone
            if host_clone in registered:
                assert sections[host_clone.lower()]['upgrades'] == installed['GAPLUG']['Upgrades']
            for source_id in source_ids:
                assert 'RLRP' + source_id in registered
            reports.append({'access': source_ids, 'hosts': sorted(hosts)})
        finally:
            if hook:
                _remove_owned(hook['root_map'])
                _remove_owned(hook['generated_map'])
    return reports


def main():
    edge_cases = check_edge_cases()
    launches = check_generated_launches()
    print(json.dumps({'valid': True, 'edge_cases': edge_cases, 'launches': launches}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
