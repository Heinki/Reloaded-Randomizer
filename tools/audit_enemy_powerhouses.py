"""Audit special-unit production against all installed campaign maps.

No game launch or save changes. Generated launch copies are removed afterward.
"""

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.config.static import load_static_config
from randomizer.content.inventory import read_rules_sections
from randomizer.core.paths import BATTLE_INI
from randomizer.maps.enemy_powerhouses import enemy_powerhouse_rules
from randomizer.maps.enemy_scaling import active_hostile_enemy_houses, discover_hostile_ai_houses
from randomizer.maps.generated import file_sha256
from randomizer.maps.houses import map_house_records
from randomizer.maps.ini import IniLines, all_section_value_maps, merge_ini_section_values, read_text
from randomizer.maps.ownership import techno_type_possible_houses
from randomizer.maps.pipeline import prepare_hooked_map
from randomizer.missions.catalogue import parse_missions
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.missions.overrides import MISSION_NATIVE_RUNTIME_PRESERVE_ACTION_TEAMS
from randomizer.rewards.catalogue import REWARD_BY_NAME
from tools.core_gameplay_smoke import _Harness, _remove_owned

REWARD = REWARD_BY_NAME['AI Enemy Powerhouses']


class _PowerhouseHarness(_Harness):
    def __init__(self, mission):
        super().__init__([], mission['side'], mission['campaign'], seed='RLR-POWERHOUSE-AUDIT')
        self.applications = []

    def active_enemy_scaling_entries(self):
        return [{'reward': REWARD, 'source': 'campaign audit', 'earned_from': 'Enemy Powerhouses'}]

    def record_enemy_reward_applications(self, _code, applications):
        self.applications = [entry for entry in applications if entry['effect_id'] == 'powerhouse']


def _protected(mission):
    return bool(mission['code'] in MISSION_NATIVE_RUNTIME_PRESERVE_ACTION_TEAMS
                or mission.get('no_build') or mission.get('true_no_build')
                or mission.get('build_classification') in {'true_no_build', 'no_build_production'})


def _audit_actors(lines, applications, hostile_houses, installed):
    sections = all_section_value_maps(lines)
    records = map_house_records(lines, sections=sections)
    if any(count > 4 for count in Counter(entry['house'] for entry in applications).values()):
        raise ValueError('Enemy Powerhouses exceeded four teams per house')
    for entry in applications:
        actor = entry['added_unit_ids'][0]
        values = sections[actor]
        owners = techno_type_possible_houses(lines, values, records=records, sections=sections)
        if entry['house'] not in owners or set(owners) - set(hostile_houses):
            raise ValueError(f'{actor}: production isolation failed: {owners}')
        if values.get('buildlimit') != '1' or values.get('techlevel') != '1':
            raise ValueError(f'{actor}: not bounded and buildable')
        if values.get('prerequisite') != entry['factory']:
            raise ValueError(f'{actor}: incorrect factory prerequisite')
        if any(key.startswith('requiresstolen') or (key.startswith('prerequisite') and key != 'prerequisite')
               for key in values):
            raise ValueError(f'{actor}: inherited alternate/negative or stolen-tech prerequisite')
        team = sections[entry['target']]
        force = sections[team['taskforce']]
        if force.get('0') != f'1,{actor}' or team.get('max') != '1':
            raise ValueError(f'{actor}: incorrect team size or concurrent cap')
        if sections[team['script']].get('0') != '11,15':
            raise ValueError(f'{actor}: no attack mission')
        linked = any(str(raw).split(',')[1] == entry['target']
                     for raw in sections.get('AITriggerTypes', {}).values())
        if not linked and sections[entry['source_team_id']].get('autocreate') != 'yes':
            raise ValueError(f'{actor}: no production link')
        source_id = entry['source_unit_ids'][0]
        native = {str(key).lower(): value for key, value in installed[source_id].items()}
        if values.get('strength') != native.get('strength') or values.get('armor') != native.get('armor'):
            raise ValueError(f'{actor}: installed durability changed')
        if not any(actor in sections.get(registry, {}).values()
                   for registry in ('InfantryTypes', 'VehicleTypes', 'AircraftTypes')):
            raise ValueError(f'{actor}: missing TechnoType registration')


def main():
    installed, _ = read_rules_sections()
    rosters = load_static_config('rewards/enemy_scaling.json')['powerhouse_rosters']
    configured = {unit for roster in rosters.values() for pool in roster.values() for unit in pool}
    if configured - set(installed):
        raise ValueError(f'Missing installed special units: {sorted(configured - set(installed))}')
    missions = parse_missions(BATTLE_INI)
    families, units, protected, generated = Counter(), set(), 0, 0
    for index, mission in enumerate(missions, 1):
        source = resolve_installed_scenario(mission['scenario'])
        source_hash = file_sha256(source)
        lines = IniLines(read_text(source).splitlines())
        houses, _ = discover_hostile_ai_houses(lines)
        houses, _ = active_hostile_enemy_houses(lines, houses)
        options = dict(seed='RLR-POWERHOUSE-AUDIT', protected_mission=_protected(mission))
        plan = enemy_powerhouse_rules(lines, houses, [REWARD], installed, **options)
        if plan != enemy_powerhouse_rules(lines, houses, [REWARD], installed, **options):
            raise ValueError(f'{mission["code"]}: non-deterministic production plan')
        if enemy_powerhouse_rules(lines, houses, [], installed)[0]:
            raise ValueError(f'{mission["code"]}: production without reward')
        if _protected(mission):
            protected += 1
            if plan[0] or plan[1]:
                raise ValueError(f'{mission["code"]}: protected mission changed')
        original = all_section_value_maps(lines)
        registries = {'InfantryTypes', 'VehicleTypes', 'AircraftTypes', 'ScriptTypes',
                      'TeamTypes', 'TaskForces', 'AITriggerTypes', 'AITriggerTypesEnable'}
        if set(plan[0]).intersection(set(original) - registries):
            raise ValueError(f'{mission["code"]}: authored section mutation')
        planned = IniLines(list(lines))
        merge_ini_section_values(planned, plan[0])
        _audit_actors(planned, plan[1], houses, installed)
        for difficulty in range(3):
            for seed in range(4):
                _, applications, _ = enemy_powerhouse_rules(
                    lines, houses, [REWARD], installed, seed=f'roster-{seed}',
                    difficulty=difficulty, protected_mission=_protected(mission),
                )
                units.update(entry['source_unit_ids'][0] for entry in applications)
        harness = _PowerhouseHarness(mission)
        hook = None
        try:
            hook = prepare_hooked_map(harness, mission, extra_rules=harness.mission_required_launch_rules(mission))
            if hook:
                generated += 1
                launch_lines = IniLines(read_text(Path(hook['generated_map'])).splitlines())
                _audit_actors(launch_lines, harness.applications, houses, installed)
                families.update(entry['enemy_family'] for entry in harness.applications)
        finally:
            if hook:
                _remove_owned(hook['root_map'])
                _remove_owned(hook['generated_map'])
        if file_sha256(source) != source_hash:
            raise ValueError(f'{mission["code"]}: authored map hash changed')
        if index % 12 == 0:
            print(f'Audited {index}/{len(missions)} campaign maps', flush=True)
    if set(families) != set(rosters):
        raise ValueError(f'Missing faction production coverage: {families}')
    if not {'MMKIIPROTO', 'TANY', 'BORIS', 'CHITZ', 'EBRUTE', 'GBRUTE'} <= units:
        raise ValueError('Missing hidden-unit or hero coverage')
    print(json.dumps({
        'valid': True, 'missions': len(missions), 'generated': generated,
        'protected_missions': protected, 'production_teams_by_family': dict(families),
        'configured_special_units': len(configured), 'campaign_units_seen': len(units),
        'roster_without_campaign_factory_or_seed_selection': sorted(configured - units),
    }, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
