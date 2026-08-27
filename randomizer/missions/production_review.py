"""Proof-only review of scripted player construction access.

Mental Omega records mission production exceptions explicitly. Reloaded uses
the same fail-closed result model, with source-derived evidence identifying
only player-owned MCV teams created by standard reinforcement Actions.
"""

from collections import Counter
import json

from randomizer.content.inventory import read_rules_sections
from randomizer.maps.houses import (
    canonical_house_name,
    map_house_records,
    player_controlled_houses,
)
from randomizer.maps.ini import (
    IniLines,
    all_section_value_maps,
    parse_action_groups,
    read_text,
)
from randomizer.maps.ownership import player_transfer_houses
from randomizer.maps.ownership import action_house_from_country_index
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.missions.metadata import MISSION_METADATA


REINFORCEMENT_ACTION_CODES = frozenset({'7', '80', '107'})
CREATE_TEAM_ACTION_CODE = '4'
CREATE_BUILDING_ACTION_CODE = '125'


def _effective_values(type_id, installed_sections, map_sections):
    wanted = str(type_id or '').lower()
    values = {}
    for sections in (installed_sections, map_sections):
        section_name = next(
            (name for name in sections if str(name).lower() == wanted),
            None,
        )
        if section_name:
            values.update(sections[section_name])
    return {str(key).lower(): value for key, value in values.items()}


def _is_mobile_construction_unit(type_id, installed_sections, map_sections):
    values = _effective_values(type_id, installed_sections, map_sections)
    deploys_into = str(values.get('deploysinto') or '').strip()
    if not deploys_into:
        return False
    deployed = _effective_values(
        deploys_into, installed_sections, map_sections
    )
    return str(deployed.get('constructionyard') or '').lower() == 'yes'


def _script_player_house(
    lines,
    script_id,
    sections,
    sections_by_lower,
    records,
    player_names,
):
    """Resolve native or Reloaded-converted Change House script Actions."""
    for key, value in sections_by_lower.get(str(script_id).lower(), {}).items():
        if not str(key).isdigit():
            continue
        tokens = [token.strip() for token in str(value).split(',', 1)]
        if len(tokens) < 2 or tokens[0] not in {'20', '19020'}:
            continue
        parameter = tokens[1].split(';', 1)[0].strip()
        if tokens[0] == '20':
            house = action_house_from_country_index(
                lines,
                parameter,
                records=records,
                sections=sections,
            )
        else:
            house = canonical_house_name(records, parameter)
        if house and house.lower() in player_names:
            return house
    return ''


def scripted_player_mcv_evidence(metadata, installed_sections):
    """Return source proof for action-created player-owned MCV teams."""
    source_path = resolve_installed_scenario(metadata['scenario'])
    lines = IniLines(read_text(source_path).splitlines())
    sections = all_section_value_maps(lines)
    sections_by_lower = {
        str(name).lower(): values for name, values in sections.items()
    }
    records = map_house_records(lines, sections=sections)
    player_houses = player_controlled_houses(lines, records=records)
    player_names = {house.lower() for house in player_houses}
    known_team_ids = {
        str(team_id).lower()
        for team_id in sections.get('TeamTypes', {}).values()
        if str(team_id).strip()
    }
    triggers = sections.get('Triggers', {})
    evidence = []

    for action_id, value in sections.get('Actions', {}).items():
        trigger = triggers.get(action_id)
        if trigger is None:
            continue
        trigger_tokens = [token.strip() for token in str(trigger).split(',')]
        trigger_name = trigger_tokens[2] if len(trigger_tokens) > 2 else ''
        if 'debug' in trigger_name.lower():
            continue
        trigger_owner = canonical_house_name(
            records, trigger_tokens[0] if trigger_tokens else ''
        )
        declared, groups = parse_action_groups(str(value))
        if declared != len(groups):
            continue
        for group in groups:
            action_code = group[0]
            if action_code not in REINFORCEMENT_ACTION_CODES | {
                CREATE_TEAM_ACTION_CODE
            }:
                continue
            team_id = str(group[2]).lower()
            if team_id not in known_team_ids:
                continue
            team = sections_by_lower.get(team_id, {})
            configured_owner = canonical_house_name(
                records, team.get('house', '')
            )
            runtime_owner = (
                trigger_owner
                if action_code == CREATE_TEAM_ACTION_CODE
                else configured_owner
            )
            scripted_owner = _script_player_house(
                lines,
                team.get('script', ''),
                sections,
                sections_by_lower,
                records,
                player_names,
            )
            if scripted_owner:
                runtime_owner = scripted_owner
            if not runtime_owner or runtime_owner.lower() not in player_names:
                continue
            taskforce_id = str(team.get('taskforce') or '').lower()
            for key, taskforce_value in sections_by_lower.get(
                taskforce_id, {}
            ).items():
                tokens = [
                    token.strip()
                    for token in str(taskforce_value).split(',')
                ]
                if (
                    not str(key).isdigit()
                    or len(tokens) < 2
                    or not _is_mobile_construction_unit(
                        tokens[1], installed_sections, sections
                    )
                ):
                    continue
                evidence.append({
                    'action_id': action_id,
                    'action_code': action_code,
                    'team_id': team_id,
                    'taskforce_id': taskforce_id,
                    'house': runtime_owner,
                    'ownership_source': (
                        'script_change_house'
                        if scripted_owner else 'creation_owner'
                    ),
                    'unit_id': tokens[1].upper(),
                })
    return evidence


def scripted_player_building_evidence(metadata, installed_sections):
    """Return player-owned structures created by standard Action 125."""
    source_path = resolve_installed_scenario(metadata['scenario'])
    lines = IniLines(read_text(source_path).splitlines())
    sections = all_section_value_maps(lines)
    records = map_house_records(lines, sections=sections)
    player_names = {
        house.lower()
        for house in player_controlled_houses(lines, records=records)
    }
    triggers = sections.get('Triggers', {})
    evidence = []

    for action_id, value in sections.get('Actions', {}).items():
        trigger = triggers.get(action_id)
        if trigger is None:
            continue
        trigger_tokens = [token.strip() for token in str(trigger).split(',')]
        trigger_name = trigger_tokens[2] if len(trigger_tokens) > 2 else ''
        if 'debug' in trigger_name.lower():
            continue
        trigger_owner = canonical_house_name(
            records, trigger_tokens[0] if trigger_tokens else ''
        )
        if not trigger_owner or trigger_owner.lower() not in player_names:
            continue
        declared, groups = parse_action_groups(str(value))
        if declared != len(groups):
            continue
        for group in groups:
            if group[0] != CREATE_BUILDING_ACTION_CODE:
                continue
            type_id = str(group[2] or '').strip()
            values = _effective_values(type_id, installed_sections, sections)
            construction_yard = (
                str(values.get('constructionyard') or '').strip().lower()
                == 'yes'
            )
            factory = str(values.get('factory') or '').strip()
            if not construction_yard and factory.lower() in {
                '', 'none', '<none>'
            }:
                continue
            evidence.append({
                'action_id': action_id,
                'action_code': CREATE_BUILDING_ACTION_CODE,
                'house': trigger_owner,
                'building_id': type_id.upper(),
                'construction_yard': construction_yard,
                'factory': factory,
            })
    return evidence


def scripted_player_object_transfer_evidence(metadata, installed_sections):
    """Return tagged production objects changed to a player House by Action 14."""
    source_path = resolve_installed_scenario(metadata['scenario'])
    lines = IniLines(read_text(source_path).splitlines())
    sections = all_section_value_maps(lines)
    records = map_house_records(lines, sections=sections)
    player_names = {
        house.lower()
        for house in player_controlled_houses(lines, records=records)
    }
    action_targets = {}
    for action_id, value in sections.get('Actions', {}).items():
        declared, groups = parse_action_groups(str(value))
        if declared != len(groups):
            continue
        targets = {
            action_house_from_country_index(
                lines,
                group[2],
                records=records,
                sections=sections,
            )
            for group in groups
            if group[0] == '14'
        } - {''}
        player_targets = {
            target for target in targets if target.lower() in player_names
        }
        if player_targets:
            action_targets[str(action_id).lower()] = sorted(player_targets)

    tags_by_action = {}
    for tag_id, value in sections.get('Tags', {}).items():
        tokens = [token.strip() for token in str(value).split(',')]
        trigger_id = tokens[2].lower() if len(tokens) > 2 else ''
        if trigger_id in action_targets:
            tags_by_action.setdefault(trigger_id, set()).add(
                str(tag_id).lower()
            )
            continue
        trigger_tokens = [
            token.strip()
            for token in str(
                sections.get('Triggers', {}).get(trigger_id, '')
            ).split(',')
        ]
        linked_trigger = (
            trigger_tokens[1].lower() if len(trigger_tokens) > 1 else ''
        )
        if linked_trigger in action_targets:
            tags_by_action.setdefault(linked_trigger, set()).add(
                str(tag_id).lower()
            )

    evidence = []
    for section_name in ('Structures', 'Units', 'Infantry', 'Aircraft'):
        for object_id, value in sections.get(section_name, {}).items():
            tokens = [token.strip() for token in str(value).split(',')]
            if len(tokens) < 2:
                continue
            token_set = {token.lower() for token in tokens[2:] if token}
            for action_id, tag_ids in tags_by_action.items():
                matched_tags = sorted(token_set.intersection(tag_ids))
                if not matched_tags:
                    continue
                type_id = tokens[1].upper()
                values = _effective_values(
                    type_id, installed_sections, sections
                )
                construction_yard = (
                    str(values.get('constructionyard') or '').lower() == 'yes'
                )
                factory = str(values.get('factory') or '').strip()
                deploys_into = str(values.get('deploysinto') or '').strip()
                deployed = _effective_values(
                    deploys_into, installed_sections, sections
                ) if deploys_into else {}
                mobile_construction_unit = (
                    str(deployed.get('constructionyard') or '').lower()
                    == 'yes'
                )
                mobile_factory = str(
                    deployed.get('factory') or ''
                ).strip()
                if not any((
                    construction_yard,
                    mobile_construction_unit,
                    factory.lower() not in {'', 'none', '<none>'},
                    mobile_factory.lower() not in {'', 'none', '<none>'},
                )):
                    continue
                evidence.append({
                    'action_id': action_id,
                    'source_house': canonical_house_name(records, tokens[0]),
                    'target_houses': action_targets.get(action_id, []),
                    'tag_ids': matched_tags,
                    'object_id': object_id,
                    'object_section': section_name,
                    'type_id': type_id,
                    'construction_yard': construction_yard,
                    'mobile_construction_unit': mobile_construction_unit,
                    'factory': factory,
                    'mobile_factory': mobile_factory,
                })
    return evidence


def transferred_house_build_evidence(metadata, installed_sections):
    """Return production assets owned by Houses later transferred to player."""
    source_path = resolve_installed_scenario(metadata['scenario'])
    lines = IniLines(read_text(source_path).splitlines())
    sections = all_section_value_maps(lines)
    records = map_house_records(lines, sections=sections)
    transfer_houses = player_transfer_houses(lines, records=records)
    wanted = {house.lower() for house in transfer_houses}
    evidence = []

    def add_asset(source, owner, type_id, reference_id):
        values = _effective_values(type_id, installed_sections, sections)
        deploys_into = str(values.get('deploysinto') or '').strip()
        deployed = _effective_values(
            deploys_into, installed_sections, sections
        ) if deploys_into else {}
        construction_yard = (
            str(values.get('constructionyard') or '').lower() == 'yes'
        )
        mobile_construction_unit = (
            str(deployed.get('constructionyard') or '').lower() == 'yes'
        )
        factory = str(values.get('factory') or '').strip()
        mobile_factory = str(deployed.get('factory') or '').strip()
        if not any((
            construction_yard,
            mobile_construction_unit,
            factory.lower() not in {'', 'none', '<none>'},
            mobile_factory.lower() not in {'', 'none', '<none>'},
        )):
            return
        evidence.append({
            'source': source,
            'house': owner,
            'reference_id': reference_id,
            'type_id': str(type_id).upper(),
            'construction_yard': construction_yard,
            'mobile_construction_unit': mobile_construction_unit,
            'factory': factory,
            'mobile_factory': mobile_factory,
        })

    for section_name in ('Structures', 'Units'):
        for object_id, value in sections.get(section_name, {}).items():
            tokens = [token.strip() for token in str(value).split(',')]
            if len(tokens) < 2:
                continue
            owner = canonical_house_name(records, tokens[0])
            if owner and owner.lower() in wanted:
                add_asset(section_name, owner, tokens[1], object_id)

    for action_id, value in sections.get('Actions', {}).items():
        trigger_tokens = [
            token.strip()
            for token in str(
                sections.get('Triggers', {}).get(action_id, '')
            ).split(',')
        ]
        owner = canonical_house_name(
            records, trigger_tokens[0] if trigger_tokens else ''
        )
        if not owner or owner.lower() not in wanted:
            continue
        if len(trigger_tokens) > 2 and 'debug' in trigger_tokens[2].lower():
            continue
        declared, groups = parse_action_groups(str(value))
        if declared != len(groups):
            continue
        for group in groups:
            if group[0] == CREATE_BUILDING_ACTION_CODE:
                add_asset('Action125', owner, group[2], action_id)
    return evidence


def production_review_report():
    """Report proven build access and unresolved production signals."""
    installed_sections, rules_source = read_rules_sections()
    failures = []
    proven_codes = []
    conyard_codes = []
    factory_signal_codes = []
    object_transfer_codes = []
    transferred_asset_codes = []
    unpromoted_codes = []
    transfer_signal_codes = []
    action_counts = Counter()
    details = []
    for metadata in MISSION_METADATA:
        code = metadata['code']
        try:
            evidence = scripted_player_mcv_evidence(
                metadata, installed_sections
            )
            building_evidence = scripted_player_building_evidence(
                metadata, installed_sections
            )
            object_transfer_evidence = scripted_player_object_transfer_evidence(
                metadata, installed_sections
            )
            lines = IniLines(read_text(
                resolve_installed_scenario(metadata['scenario'])
            ).splitlines())
            transfers = player_transfer_houses(lines)
            transferred_assets = transferred_house_build_evidence(
                metadata, installed_sections
            )
        except Exception as exc:
            failures.append({'code': code, 'error': str(exc)})
            continue
        if evidence:
            proven_codes.append(code)
            action_counts.update(item['action_code'] for item in evidence)
        if any(item['construction_yard'] for item in building_evidence):
            conyard_codes.append(code)
        if building_evidence:
            factory_signal_codes.append(code)
        if object_transfer_evidence:
            object_transfer_codes.append(code)
        if transferred_assets:
            transferred_asset_codes.append(code)
        proven_object_transfer = any(
            item['construction_yard']
            or item['mobile_construction_unit']
            for item in object_transfer_evidence
        )
        proven_transferred_asset = any(
            item['construction_yard']
            or item['mobile_construction_unit']
            for item in transferred_assets
        )
        if (
            evidence
            or code in conyard_codes
            or proven_object_transfer
            or proven_transferred_asset
        ):
            if (
                metadata['build_classification'] != 'base_build'
                or metadata['review']['build_classification'] != 'verified'
            ):
                unpromoted_codes.append(code)
        if transfers:
            transfer_signal_codes.append(code)
        if (
            evidence
            or building_evidence
            or object_transfer_evidence
            or transferred_assets
            or transfers
        ):
            details.append({
                'code': code,
                'scripted_player_mcv': evidence,
                'scripted_player_buildings': building_evidence,
                'scripted_player_object_transfers': object_transfer_evidence,
                'transferred_house_build_assets': transferred_assets,
                'whole_house_transfer_signals': transfers,
            })
    return {
        'rules_source': rules_source,
        'mission_count': len(MISSION_METADATA),
        'scripted_player_mcv_missions': len(proven_codes),
        'scripted_player_mcv_codes': proven_codes,
        'unpromoted_proven_base_build_codes': unpromoted_codes,
        'unpromoted_scripted_player_mcv_codes': unpromoted_codes,
        'scripted_mcv_action_counts': dict(sorted(action_counts.items())),
        'scripted_player_conyard_missions': len(conyard_codes),
        'scripted_player_conyard_codes': conyard_codes,
        'scripted_player_factory_signal_missions': len(factory_signal_codes),
        'scripted_player_factory_signal_codes': factory_signal_codes,
        'scripted_player_object_transfer_missions': len(object_transfer_codes),
        'scripted_player_object_transfer_codes': object_transfer_codes,
        'transferred_house_build_asset_missions': len(transferred_asset_codes),
        'transferred_house_build_asset_codes': transferred_asset_codes,
        'whole_house_transfer_signal_missions': len(transfer_signal_codes),
        'whole_house_transfer_signal_codes': transfer_signal_codes,
        'details': details,
        'failures': failures,
        'valid': not failures and not unpromoted_codes,
    }


def main():
    report = production_review_report()
    print(json.dumps(report, indent=2))
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
