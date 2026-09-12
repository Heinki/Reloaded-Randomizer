"""Generate one access-reward map without Tk or launching the game."""

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.application.launch_controller import LaunchController
from randomizer.content.inventory import read_rules_sections
from randomizer.core.paths import BATTLE_INI
from randomizer.maps.generated import file_sha256, generated_map_name
from randomizer.maps.houses import player_country_from_map
from randomizer.maps.ini import IniLines, all_section_value_maps, read_text
from randomizer.maps.pipeline import prepare_hooked_map
from randomizer.maps.rules import is_generated_hooked_map
from randomizer.maps.starting_units import starting_unit_buff_plan
from randomizer.missions.catalogue import parse_missions
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.missions.access import (
    CHAOS_PRIMARY_PRODUCTION,
    TIER_ONE_AIRFIELDS,
    country_family,
)
from randomizer.rewards.catalogue import (
    BUFF_TARGETS,
    NAVAL_UNIT_IDS,
    REWARD_POOL,
)
from randomizer.rewards.rules import tech_ids_for_rewards


class _Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _Harness:
    randomized_tech_ids = LaunchController.randomized_tech_ids
    map_rules_for_launch = LaunchController.map_rules_for_launch
    mission_required_launch_rules = LaunchController.mission_required_launch_rules

    def __init__(
        self,
        rewards,
        faction,
        campaign,
        seed='RLR-CORE-SMOKE',
        reward_mode='Standard',
    ):
        self.rewards = list(rewards)
        self.seed = seed
        self.reward_mode = reward_mode
        self.state = None
        self.config = {}
        self.logs = []
        self.player_color_var = _Value('Default')
        self.rainbowizer_var = _Value(False)
        self.eva_voice_var = _Value('Mission default')
        self.campaign_filter = f'{faction} - {campaign}'

    def randomizer_launch_active(self):
        return True

    def active_launch_campaign_filter(self):
        return self.campaign_filter

    def active_launch_seed(self):
        return self.seed

    def active_progression_mode(self):
        return 'Mission List'

    def active_reward_mode(self):
        return self.reward_mode

    def active_reward_settings(self):
        return {
            'include_defensive_buildings': True,
            'include_special_buildings': False,
            'include_special_rewards': False,
            'buff_allied_helpers': False,
            'safe_player_country_buffs': True,
            'enemy_scaling': {},
            'failure_assistance': False,
            'excluded_unit_access_ids': [],
        }

    def randomize_unit_access_enabled(self):
        return True

    def share_chaos_role_buffs_enabled(self):
        return False

    def failure_assistance_enabled(self):
        return False

    def active_enemy_scaling_entries(self):
        return []

    def launch_rewards_for_mission(self, _code):
        return list(self.rewards)

    def active_launch_rewards(self):
        return list(self.rewards)

    def mission_effective_unlocked_tech_ids(
        self, _mission, _lines, additional_tech_ids=()
    ):
        return set(tech_ids_for_rewards(self.rewards)) | set(
            additional_tech_ids
        )

    def extract_campaign_map(self, scenario):
        return resolve_installed_scenario(scenario)

    def append_log(self, message, error=False):
        self.logs.append({'error': bool(error), 'message': str(message)})

    def mission_checks(self, _code):
        return []

    def mission_failure_stack(self, _code):
        return 0

    def cache_mission_assistance_units(self, *_args, **_kwargs):
        return None

    def record_enemy_reward_applications(self, *_args, **_kwargs):
        return None

    def active_starting_rewards_for_report(self):
        return []

    def active_progression_rewards_for_report(self):
        return list(self.rewards)

    def active_starting_tier_one_expanded_ids(self):
        return []

    def active_starting_tier_one_defense_expanded_ids(self):
        return []

    def active_starting_tier_one_unit_ids(self):
        return []

    def active_starting_tier_one_defense_ids(self):
        return []

    def active_unlocked_reward_tech_ids(self):
        return set(tech_ids_for_rewards(self.rewards))

    def active_standard_starter_families(self):
        return []

    def launch_state_document(self):
        return {}


def _remove_owned(path):
    path = Path(path)
    if not path.exists():
        return
    if not is_generated_hooked_map(path):
        raise RuntimeError(f'Refusing to remove unmarked map: {path}')
    path.unlink()


def _section_field(sections, section_id, field):
    values = next(
        (
            values for name, values in sections.items()
            if str(name).upper() == str(section_id).upper()
        ),
        {},
    )
    return next(
        (
            value for name, value in values.items()
            if str(name).lower() == str(field).lower()
        ),
        None,
    )


def run(
    mission_code='ALL01_RA2',
    reward_tech_id='E1',
    buff_type='',
    reward_mode='Standard',
):
    mission = next(
        mission for mission in parse_missions(BATTLE_INI)
        if mission['code'] == mission_code
    )
    access_reward = next(
        reward for reward in REWARD_POOL
        if reward.get('kind') == 'access'
        and reward_tech_id.upper() in tech_ids_for_rewards([reward])
    )
    rewards = [access_reward]
    if buff_type:
        rewards.append(next(
            reward for reward in REWARD_POOL
            if reward.get('kind') == 'buff'
            and str(reward.get('unit') or '').upper()
            == reward_tech_id.upper()
            and reward.get('buff_type') == buff_type
        ))
    source = resolve_installed_scenario(mission['scenario'])
    source_hash = file_sha256(source)
    source_lines = IniLines(read_text(source).splitlines())
    starting_plan = starting_unit_buff_plan(source_lines)
    tech_id = reward_tech_id.upper()
    starting_policy = (
        'shared_with_opponent'
        if tech_id in starting_plan.shared_type_ids
        else 'friendly_only'
        if tech_id in starting_plan.native_direct_type_ids
        else 'not_friendly_starting_type'
    )
    source_sections = all_section_value_maps(source_lines)
    installed_sections, _rules_source = read_rules_sections()
    harness = _Harness(
        rewards,
        mission['side'],
        mission['campaign'],
        seed='RLR-CORE-SMOKE-' + (buff_type or 'ACCESS').upper(),
        reward_mode=reward_mode,
    )
    hook = None
    try:
        access_rules = harness.mission_required_launch_rules(mission)
        hook = prepare_hooked_map(harness, mission, extra_rules=access_rules)
        generated = Path(hook['root_map'])
        generated_text = generated.read_text(encoding='utf-8', errors='ignore')
        generated_sections = all_section_value_maps(
            IniLines(generated_text.splitlines())
        )
        clone_id = 'RLRP' + reward_tech_id.upper()
        if buff_type == 'veteran':
            clone_id = 'compact veteran clone (validated)'
        elif f'[{clone_id}]' not in generated_text:
            raise ValueError(
                f'Generated clone section missing: {clone_id} '
                f'(mission={mission_code}, buff={buff_type or "none"})'
            )
        if buff_type != 'veteran':
            native_ui_description = (
                _section_field(source_sections, tech_id, 'UIDescription')
                or _section_field(
                    installed_sections, tech_id, 'UIDescription'
                )
            )
            clone_ui_description = _section_field(
                generated_sections, clone_id, 'UIDescription'
            )
            if native_ui_description:
                if clone_ui_description != native_ui_description:
                    raise ValueError(
                        f'Generated clone lost native tooltip for {tech_id}: '
                        f'expected {native_ui_description!r}, found '
                        f'{clone_ui_description!r}'
                    )
            elif not clone_ui_description:
                raise ValueError(
                    f'Generated clone tooltip missing for {tech_id}'
                )
        expected_access = access_rules.get(tech_id, {})
        if expected_access and buff_type != 'veteran':
            prerequisite_fields = {
                str(field): value
                for field, value in expected_access.items()
                if str(field).lower().startswith('prerequisite')
            }
            for field, expected in prerequisite_fields.items():
                actual = _section_field(generated_sections, clone_id, field)
                if actual != expected:
                    raise ValueError(
                        f'Generated access gate mismatch for {tech_id}/{field}: '
                        f'expected {expected!r}, found {actual!r}'
                    )
        if '[RLRPOriginalGate]' not in generated_text:
            raise ValueError('Generated native-production gate is missing.')
        if reward_mode == 'Chaos' and buff_type != 'veteran':
            player_country = player_country_from_map(source_lines)
            player_family = country_family({'country': player_country})
            target_category = str(
                BUFF_TARGETS.get(tech_id, {}).get('category') or ''
            )
            factory_category = {
                'infantry': 'infantry',
                'units': 'naval' if tech_id in NAVAL_UNIT_IDS else 'vehicles',
                'aircraft': 'air',
            }.get(target_category)
            conyard_id = CHAOS_PRIMARY_PRODUCTION.get(
                player_family, {}
            ).get('base')
            if (
                factory_category or target_category == 'defenses'
            ) and not conyard_id:
                raise ValueError(
                    f'No Construction Yard configured for '
                    f'{player_family or player_country}.'
                )
            if factory_category:
                factory_id = (
                    TIER_ONE_AIRFIELDS.get(player_family)
                    if factory_category == 'air'
                    else CHAOS_PRIMARY_PRODUCTION.get(
                        player_family, {}
                    ).get(factory_category)
                )
                if not factory_id:
                    raise ValueError(
                        f'No {factory_category} factory configured for '
                        f'{player_family or player_country}.'
                    )
                if _section_field(
                    generated_sections, factory_id, 'TechLevel'
                ) != '1':
                    raise ValueError(
                        f'Earned {tech_id} did not unlock {factory_id}.'
                    )
                if _section_field(
                    generated_sections, factory_id, 'Prerequisite'
                ) != conyard_id:
                    raise ValueError(
                        f'{factory_id} is not available directly behind '
                        f'{conyard_id}.'
                    )
            elif target_category == 'defenses':
                building_prerequisites = {
                    str(value).upper()
                    for field, value in generated_sections.get(
                        clone_id, {}
                    ).items()
                    if str(field).lower() == 'prerequisite'
                    or str(field).lower().startswith('prerequisite.list')
                }
                if conyard_id.upper() not in building_prerequisites:
                    raise ValueError(
                        f'Earned building {tech_id} is not available directly '
                        f'from {conyard_id}.'
                    )

            native_isolation = {
                'forbidden': {
                    item.strip().upper()
                    for item in str(_section_field(
                        generated_sections, tech_id, 'ForbiddenHouses'
                    ) or '').split(',')
                    if item.strip()
                },
                'negative': {
                    item.strip().upper()
                    for item in str(_section_field(
                        generated_sections,
                        tech_id,
                        'Prerequisite.Negative',
                    ) or '').split(',')
                    if item.strip()
                },
                'factory': {
                    item.strip().upper()
                    for item in str(_section_field(
                        generated_sections,
                        tech_id,
                        'FactoryOwners.Forbidden',
                    ) or '').split(',')
                    if item.strip()
                },
            }
            if not (
                player_country.upper() in native_isolation['forbidden']
                or 'RLRPORIGINALGATE' in native_isolation['negative']
                or player_country.upper() in native_isolation['factory']
            ):
                raise ValueError(
                    f'Native {tech_id} lacks Mental Omega-style player '
                    'production isolation.'
                )
        if buff_type:
            validation_lines = [
                entry['message'] for entry in harness.logs
                if entry['message'].startswith(
                    'Validated generated unit buffs:'
                )
            ]
            if not validation_lines or '1/1 effects' not in validation_lines[-1]:
                raise ValueError(
                    'Generated buff validation did not confirm one effect: '
                    + '; '.join(validation_lines)
                )
        native_field = {
            'health': 'Strength',
            'armor': 'Strength',
            'sight': 'Sight',
            'ammo': 'Ammo',
            'passenger_capacity': 'Passengers',
            'cloak': 'Cloakable',
            'sensors': 'Sensors',
            'cost': 'Cost',
            'speed': 'Speed',
        }.get(buff_type)
        native_starting_type_changed = None
        native_starting_source_value = None
        native_starting_generated_value = None
        if native_field:
            source_value = _section_field(
                source_sections, tech_id, native_field
            )
            generated_value = _section_field(
                generated_sections, tech_id, native_field
            )
            native_starting_source_value = source_value
            native_starting_generated_value = generated_value
            native_starting_type_changed = generated_value != source_value
            if (
                starting_policy == 'shared_with_opponent'
                and native_starting_type_changed
            ):
                raise ValueError(
                    f'Shared starting type received unsafe native buff: {tech_id}'
                )
        if file_sha256(source) != source_hash:
            raise ValueError('Authored source hash changed during generation.')
        return {
            'valid': True,
            'mission': mission_code,
            'reward_mode': reward_mode,
            'rewards': [reward['name'] for reward in rewards],
            'buff_type': buff_type or None,
            'clone': clone_id,
            'generated_name': generated.name,
            'log_entries': len(harness.logs),
            'starting_unit_isolation': [
                entry['message'] for entry in harness.logs
                if entry['message'].startswith(
                    'Starting-unit buff isolation:'
                )
            ],
            'guarded_buff_skips': [
                entry['message'] for entry in harness.logs
                if entry['message'].startswith('Skipped guarded unit/weapon')
            ],
            'guarded_buff_applications': [
                entry['message'] for entry in harness.logs
                if entry['message'].startswith('Applied guarded unit/weapon')
            ],
            'target_starting_policy': starting_policy,
            'native_starting_type_changed': native_starting_type_changed,
            'native_starting_source_value': native_starting_source_value,
            'native_starting_generated_value': native_starting_generated_value,
            'source_sha256': source_hash,
        }
    finally:
        if hook:
            _remove_owned(hook['root_map'])
            _remove_owned(hook['generated_map'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mission', default='ALL01_RA2')
    parser.add_argument('--tech', default='E1')
    parser.add_argument('--buff', default='')
    parser.add_argument(
        '--reward-mode',
        choices=('Standard', 'Chaos', 'Randomizer Arsenal'),
        default='Standard',
    )
    args = parser.parse_args()
    print(run(args.mission, args.tech, args.buff, args.reward_mode))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
