"""Build Reloaded-native mission metadata from Battle.ini and authored maps."""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path, PureWindowsPath


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.config.game_profile import (
    CONTENT_FACTIONS,
    FACTION_ALIASES,
    TERMINAL_END_ACTION_CODES,
    TERMINAL_WIN_ACTION_CODES,
)
from randomizer.content.inventory import read_rules_sections
from randomizer.maps.generated import file_sha256
from randomizer.maps.houses import (
    canonical_house_name,
    map_house_records,
    player_controlled_houses,
    player_house_from_map,
)
from randomizer.maps.identity_safety import capture_authored_identity_contract
from randomizer.maps.ini import (
    IniLines,
    all_section_value_maps,
    parse_action_groups,
    read_text,
)
from randomizer.maps.starting_units import starting_unit_buff_plan
from randomizer.missions.installation import (
    installed_mission_catalogue,
    resolve_installed_scenario,
)


METADATA_PATH = PROJECT_ROOT / 'configs' / 'mission_catalogue.json'
MISSION_POLICY_PATH = PROJECT_ROOT / 'configs' / 'missions.json'
PLACEMENT_SECTIONS = ('Infantry', 'Units', 'Aircraft', 'Structures')
MISSION_NUMBER_PATTERN = re.compile(
    r'\bMission\s+(\d+)(?:\s*\((\d+)\s*/\s*(\d+)\))?',
    flags=re.IGNORECASE,
)


def _normalize_faction(side):
    side = str(side or '').strip().lower()
    if side in FACTION_ALIASES:
        return FACTION_ALIASES[side]
    for alias, faction in FACTION_ALIASES.items():
        if alias in side:
            return faction
    return ''


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Build verified C&C Reloaded 2.7.0 mission metadata.',
    )
    parser.add_argument(
        '--write',
        action='store_true',
        help='Write mission metadata while preserving verified reviews.',
    )
    parser.add_argument(
        '--reset-reviews',
        action='store_true',
        help='Discard preserved reviews when writing regenerated metadata.',
    )
    parser.add_argument(
        '--reset-policy',
        action='store_true',
        help='Also reset missions.json to empty Reloaded-only policy.',
    )
    return parser.parse_args()


def _effective_values(type_id, installed_sections, map_sections):
    type_lower = str(type_id).lower()
    installed_name = next(
        (name for name in installed_sections if str(name).lower() == type_lower),
        None,
    )
    map_name = next(
        (name for name in map_sections if str(name).lower() == type_lower),
        None,
    )
    values = {}
    if installed_name:
        values.update(installed_sections.get(installed_name, {}))
    if map_name:
        values.update(map_sections.get(map_name, {}))
    return {str(key).lower(): value for key, value in values.items()}


def _placed_player_types(lines, records, player_houses):
    sections = all_section_value_maps(lines)
    friendly = {house.lower() for house in player_houses}
    result = set()
    for section in PLACEMENT_SECTIONS:
        for value in sections.get(section, {}).values():
            tokens = [token.strip() for token in str(value).split(',')]
            if len(tokens) < 2:
                continue
            house = canonical_house_name(records, tokens[0])
            if house and house.lower() in friendly:
                result.add(tokens[1].upper())
    return result


def _production_evidence(player_types, installed_sections, map_sections):
    construction_yards = []
    production_structures = []
    mobile_construction_units = []
    mobile_production_units = []
    for type_id in sorted(player_types):
        values = _effective_values(type_id, installed_sections, map_sections)
        factory = str(values.get('factory') or '').strip()
        construction_yard = (
            str(values.get('constructionyard') or '').strip().lower() == 'yes'
        )
        if construction_yard:
            construction_yards.append(type_id)
        if factory and factory.lower() not in {'none', '<none>'}:
            production_structures.append(type_id)
        deploys_into = str(values.get('deploysinto') or '').strip()
        if deploys_into:
            deployed_values = _effective_values(
                deploys_into,
                installed_sections,
                map_sections,
            )
            if (
                str(deployed_values.get('constructionyard') or '')
                .strip()
                .lower()
                == 'yes'
            ):
                mobile_construction_units.append(type_id)
            deployed_factory = str(
                deployed_values.get('factory') or ''
            ).strip()
            if (
                deployed_factory.lower() not in {'', 'none', '<none>'}
                and type_id not in mobile_construction_units
            ):
                mobile_production_units.append(type_id)
    return {
        'construction_yard_type_ids': construction_yards,
        'production_structure_type_ids': production_structures,
        'mobile_construction_unit_type_ids': mobile_construction_units,
        'mobile_production_unit_type_ids': mobile_production_units,
        'has_initial_construction_yard': bool(construction_yards),
        'has_initial_production_structure': bool(production_structures),
        'has_initial_mobile_construction_unit': bool(mobile_construction_units),
        'has_initial_mobile_production_unit': bool(mobile_production_units),
    }


def _action_candidates(lines):
    sections = all_section_value_maps(lines)
    terminal = []
    objectives = []
    parse_failures = []
    for action_id, value in sections.get('Actions', {}).items():
        try:
            _count, groups = parse_action_groups(str(value))
        except Exception as exc:
            parse_failures.append({'action_id': str(action_id), 'error': str(exc)})
            continue
        action_codes = [str(group[0]) for group in groups if group]
        terminal_codes = [
            code for code in action_codes if code in TERMINAL_END_ACTION_CODES
        ]
        objective_codes = [code for code in action_codes if code == '11']
        if terminal_codes:
            terminal.append({
                'action_id': str(action_id),
                'codes': terminal_codes,
                'winner_codes': [
                    code for code in terminal_codes
                    if code in TERMINAL_WIN_ACTION_CODES
                ],
            })
        if objective_codes:
            objectives.append({
                'action_id': str(action_id),
                'codes': objective_codes,
            })
    return terminal, objectives, parse_failures


def _initial_allied_houses(records, player_houses):
    players = {house.lower() for house in player_houses}
    result = []
    for player_house in player_houses:
        for ally in records.get(player_house, {}).get('allies', ()):
            house = canonical_house_name(records, ally)
            if house and house.lower() not in players and house not in result:
                result.append(house)
    return result


def build_metadata():
    missions = installed_mission_catalogue()
    installed_sections, _rules_source = read_rules_sections()
    campaign_orders = Counter()
    records = []

    for global_order, mission in enumerate(missions, start=1):
        source_path = resolve_installed_scenario(mission['scenario'])
        lines = IniLines(read_text(source_path).splitlines())
        map_sections = all_section_value_maps(lines)
        houses = map_house_records(lines, sections=map_sections)
        player_house = player_house_from_map(lines, records=houses)
        player_houses = player_controlled_houses(lines, records=houses)
        faction = _normalize_faction(mission['side'])
        campaign = PureWindowsPath(mission['scenario']).parts[2]
        campaign_key = (campaign, faction)
        campaign_orders[campaign_key] += 1
        match = MISSION_NUMBER_PATTERN.search(mission['title'])
        mission_number = int(match.group(1)) if match else None
        part = int(match.group(2)) if match and match.group(2) else None
        part_count = int(match.group(3)) if match and match.group(3) else None
        identity = capture_authored_identity_contract(lines, installed_sections)
        starting_plan = starting_unit_buff_plan(lines)
        placed_player_types = _placed_player_types(lines, houses, player_houses)
        production_evidence = _production_evidence(
            placed_player_types,
            installed_sections,
            map_sections,
        )
        candidate_build_classification = None
        if (
            production_evidence['has_initial_construction_yard']
            or production_evidence['has_initial_mobile_construction_unit']
        ):
            candidate_build_classification = 'base_build'
        elif (
            production_evidence['has_initial_production_structure']
            or production_evidence['has_initial_mobile_production_unit']
        ):
            candidate_build_classification = 'no_build_production'
        terminal, objectives, action_failures = _action_candidates(lines)
        verified_victory_action_ids = [
            action['action_id']
            for action in terminal
            if action['winner_codes']
        ]
        records.append({
            'code': mission['code'],
            'scenario': mission['scenario'],
            'title': mission['title'],
            'faction': faction,
            'campaign': campaign,
            'global_order': global_order,
            'campaign_order': campaign_orders[campaign_key],
            'mission_number': mission_number,
            'part': part,
            'part_count': part_count,
            'relationship': {
                'series_key': (
                    f'{campaign}:{faction}:{mission_number}'
                    if mission_number is not None else ''
                ),
                'kind': 'pending_review',
                'related_codes': [],
            },
            'source_sha256': file_sha256(source_path),
            'player_house': player_house,
            'player_houses': player_houses,
            'initial_allied_houses': _initial_allied_houses(houses, player_houses),
            'authored_houses': list(houses),
            'starting_force': {
                'friendly_type_ids': sorted(starting_plan.friendly_type_ids),
                'opponent_type_ids': sorted(starting_plan.opponent_type_ids),
                'shared_type_ids': sorted(starting_plan.shared_type_ids),
                'player_placed_type_ids': sorted(placed_player_types),
                **production_evidence,
            },
            'identity_contract': {
                'protected_type_count': len(identity.protected_type_ids),
                'positioned_reference_count': len(identity.positioned),
                'authored_record_count': len(identity.records),
            },
            'candidate_terminal_actions': terminal,
            'candidate_objective_actions': objectives,
            'action_parse_failures': action_failures,
            'candidate_build_classification': candidate_build_classification,
            'build_classification': None,
            'expected_objective_count': None,
            'difficulty_class': None,
            'reward_class': None,
            'verified_victory_action_ids': verified_victory_action_ids,
            'review': {
                'battle_ini': 'verified',
                'source_hash': 'verified',
                'identity_contract': 'verified',
                'houses': 'candidate',
                'starting_force': 'candidate',
                'relationships': 'candidate',
                'build_classification': (
                    'candidate'
                    if candidate_build_classification
                    else 'pending_review'
                ),
                'objectives': 'pending_review',
                'difficulty_class': 'pending_review',
                'reward_class': 'pending_review',
                'victory_actions': (
                    'verified'
                    if verified_victory_action_ids
                    else 'pending_review'
                ),
            },
        })

    groups = {}
    for record in records:
        if record['code'].upper().startswith('TSDEMO'):
            record['relationship']['series_key'] = (
                f'{record["campaign"]}:{record["faction"]}:{record["code"]}'
            )
        key = record['relationship']['series_key']
        if key:
            groups.setdefault(key, []).append(record)
    for group in groups.values():
        related_codes = [record['code'] for record in group]
        has_parts = any(record['part'] is not None for record in group)
        kind = (
            'sequential_parts'
            if has_parts else 'alternate_candidates'
            if len(group) > 1 else 'standalone'
        )
        for record in group:
            record['relationship']['kind'] = kind
            record['relationship']['related_codes'] = [
                code for code in related_codes if code != record['code']
            ]

    return {
        'schema_version': 1,
        'description': (
            'C&C Reloaded 2.7.0 mission metadata derived from Battle.ini and '
            'authored maps. Candidate fields require manual review before '
            'gameplay catalogues are enabled.'
        ),
        'sections': {
            'catalogue_version': 1,
            'game_version': '2.7.0',
            'rules_source': 'expandmd02.mix::rulesmd.ini',
            'mission_count': len(records),
            'missions': records,
        },
    }


def preserve_verified_reviews(metadata):
    """Carry approved judgments forward when the authored map is unchanged."""
    if not METADATA_PATH.is_file():
        return metadata
    try:
        existing_document = json.loads(METADATA_PATH.read_text(encoding='utf-8'))
        existing_records = {
            str(record['code']).upper(): record
            for record in existing_document['sections']['missions']
        }
    except (KeyError, TypeError, ValueError, OSError):
        return metadata

    preserved_fields = {
        'houses': (),
        'starting_force': (),
        'relationships': ('relationship',),
        'build_classification': ('build_classification',),
        'objectives': ('expected_objective_count',),
        'difficulty_class': ('difficulty_class',),
        'reward_class': ('reward_class',),
        'victory_actions': ('verified_victory_action_ids',),
    }
    for record in metadata['sections']['missions']:
        existing = existing_records.get(record['code'].upper())
        if (
            not existing
            or existing.get('source_sha256') != record['source_sha256']
        ):
            continue
        existing_review = existing.get('review', {})
        for review_key, fields in preserved_fields.items():
            if existing_review.get(review_key) != 'verified':
                continue
            if any(field not in existing for field in fields):
                continue
            for field in fields:
                record[field] = existing[field]
            record['review'][review_key] = 'verified'
    return metadata


def clean_mission_policy(metadata):
    codes = [record['code'] for record in metadata['sections']['missions']]
    empty_mapping_sections = (
        'build_classification_reviews',
        'house_policy_reviews',
        'objective_reviews',
        'difficulty_reviews',
        'reward_class_reviews',
        'house_config', 'helper_buff_excluded_houses',
        'player_production_houses', 'player_production_house_reviews',
        'player_power_houses',
        'native_trigger_reference_ids', 'disabled_triggers',
        'native_techno_clone_exclusions', 'reward_excluded_player_houses',
        'clone_only_country_buff_types', 'scripted_player_buff_taskforces',
        'scripted_player_buff_taskforce_access_requirements',
        'team_house_overrides', 'original_mcv_access',
        'native_production_gate_exclusions', 'native_production_aliases',
        'objective_hook_action_ids', 'objective_hook_action_redirects',
        'special_infantry_factory_exclusions',
        'native_runtime_action_team_factory_forbidden_houses',
        'native_runtime_player_forbidden_ids',
        'unsafe_static_provider_superweapon_ids',
        'native_runtime_weapon_preserve_ids',
        'native_runtime_identity_preserve_ids', 'objective_clone_event_refs',
        'required_access_rules', 'techno_base_rules', 'map_section_rules',
        'native_direct_buff_exclusions', 'native_variant_buff_rules',
        'native_tech_unlock_ids',
        'native_tech_unlock_keep_source_disabled_ids',
        'native_unlock_owned_access_rules',
        'superweapon_techno_clone_overrides',
        'time_freeze_immune_techno_ids',
        'standard_starter_families_by_campaign',
    )
    sections = {
        'catalogue': {
            'faction_order': list(CONTENT_FACTIONS),
            'fallback_objective_count': 0,
            'starting_unlocked_missions': 3,
            'low_level_mission_count': 5,
            'low_level_stage_max': 6,
            'operation_stage_score': 9,
            'fallback_stage_score': 12,
            'finale_stage_score': 24,
            'finale_mission_codes': [],
            'operation_mission_codes': [],
        },
        'mission_reward_multipliers': {
            'default_multiplier': 1,
            'class_multipliers': {'standard': 1},
            'mission_classes': {'standard': codes},
            'mission_overrides': {},
        },
        'build_classifications': {
            record['code']: (
                record['build_classification']
                if record['review']['build_classification'] == 'verified'
                else 'base_build'
            )
            for record in metadata['sections']['missions']
        },
        'native_runtime_preserve_action_teams': [],
        'all_conyard_defense_access_missions': [],
        'victory_hook_action_ids': {
            record['code']: list(record['verified_victory_action_ids'])
            for record in metadata['sections']['missions']
            if record['verified_victory_action_ids']
        },
    }
    sections.update({name: {} for name in empty_mapping_sections})
    return {
        'schema_version': 1,
        'description': (
            'C&C Reloaded-only mission policy. Victory Actions are derived '
            'from authored winner codes; other exceptions require map review.'
        ),
        'sections': sections,
    }


def main():
    args = _parse_args()
    metadata = build_metadata()
    if not args.reset_reviews:
        metadata = preserve_verified_reviews(metadata)
    policy = clean_mission_policy(metadata)
    if not args.write:
        print(json.dumps({
            'mission_count': metadata['sections']['mission_count'],
            'metadata_path': str(METADATA_PATH),
            'mission_policy_path': str(MISSION_POLICY_PATH),
        }, indent=2))
        return 0
    METADATA_PATH.write_text(
        json.dumps(metadata, indent=2) + '\n', encoding='utf-8'
    )
    if args.reset_policy:
        MISSION_POLICY_PATH.write_text(
            json.dumps(policy, indent=2) + '\n', encoding='utf-8'
        )
    message = f'Wrote {len(metadata["sections"]["missions"])} missions'
    if args.reset_policy:
        message += ' and reset Reloaded mission policy'
    print(message + '.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
