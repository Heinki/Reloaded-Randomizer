"""Static safety audit for reviewed Reloaded objective/victory hooks."""

from collections import Counter

from randomizer.config.game_profile import TERMINAL_END_ACTION_CODES
from randomizer.maps.generated import file_sha256
from randomizer.maps.hooks import MAX_MAP_ACTION_LINE_LENGTH
from randomizer.maps.ini import (
    IniLines,
    parse_action_groups,
    read_text,
    section_lines,
    section_value_map_preserve,
)
from randomizer.maps.progress_hooks import (
    inject_check_markers,
    pending_check_hook_plan,
)
from randomizer.missions.metadata import MISSION_METADATA
from randomizer.missions.runtime_hook_evidence import (
    runtime_hook_evidence_report,
)
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.missions.overrides import (
    MISSION_OBJECTIVE_HOOK_ACTION_IDS,
    MISSION_OBJECTIVE_HOOK_ACTION_REDIRECTS,
    MISSION_VICTORY_HOOK_ACTION_IDS,
)


def _casefold_value(values, key):
    wanted = str(key).lower()
    return next(
        (value for current, value in values.items() if current.lower() == wanted),
        None,
    )


def _parsed_groups(values, action_id):
    value = _casefold_value(values, action_id)
    if value is None:
        return None
    declared_count, groups = parse_action_groups(value)
    if declared_count != len(groups):
        return None
    return groups


def progress_hook_audit_report():
    """Dry-run every reviewed victory hook without writing source maps."""
    failures = []
    winner_code_counts = Counter()
    reviewed_action_count = 0
    reviewed_objective_action_count = 0
    reviewed_objective_milestone_count = 0
    objective_mapped_missions = 0
    multi_branch_missions = 0
    max_generated_action_line_bytes = 0

    for metadata in MISSION_METADATA:
        code = metadata['code']
        source_path = resolve_installed_scenario(metadata['scenario'])
        source_hash_before = file_sha256(source_path)
        lines = IniLines(read_text(source_path).splitlines())
        original_actions = section_value_map_preserve(lines, 'Actions')
        expected_ids = tuple(metadata['verified_victory_action_ids'])
        configured_ids = tuple(MISSION_VICTORY_HOOK_ACTION_IDS.get(code, ()))
        if tuple(action_id.lower() for action_id in configured_ids) != tuple(
            action_id.lower() for action_id in expected_ids
        ):
            failures.append({
                'code': code,
                'error': 'victory policy differs from verified metadata',
            })
            continue
        if not configured_ids:
            failures.append({'code': code, 'error': 'no reviewed victory Action'})
            continue

        for candidate in metadata['candidate_terminal_actions']:
            if candidate['action_id'] in expected_ids:
                winner_code_counts.update(candidate['winner_codes'])

        objective_count = int(metadata['expected_objective_count'] or 0)
        configured_objectives = MISSION_OBJECTIVE_HOOK_ACTION_IDS.get(
            code, {}
        )
        checks = [
            {
                'id': f'objective_{index}',
                'name': f'Objective {index}',
                'unlocked': False,
            }
            for index in range(1, objective_count + 1)
        ] + [{'id': 'victory', 'name': 'Victory', 'unlocked': False}]
        plan, missing_victory, _completed_objectives = pending_check_hook_plan(
            lines,
            checks,
            configured_ids,
            MISSION_OBJECTIVE_HOOK_ACTION_IDS.get(code, {}),
            MISSION_OBJECTIVE_HOOK_ACTION_REDIRECTS.get(code, {}),
        )
        planned_ids = tuple(action_id.lower() for _check, action_id in plan)
        action_names = {
            str(action_id).lower(): action_id for action_id in original_actions
        }
        redirects = MISSION_OBJECTIVE_HOOK_ACTION_REDIRECTS.get(code, {})
        redirect_names = {
            str(source).lower(): str(target).lower()
            for source, target in redirects.items()
        }
        expected_objective_ids = []
        for action_id in configured_objectives:
            source_key = str(action_id).lower()
            target_key = redirect_names.get(source_key, source_key)
            expected_objective_ids.append(
                target_key if target_key in action_names else source_key
            )
        expected_planned_ids = tuple(expected_objective_ids) + tuple(
            action_id.lower() for action_id in expected_ids
        )
        if missing_victory or planned_ids != expected_planned_ids:
            failures.append({
                'code': code,
                'error': 'reviewed objective/victory plan incomplete',
                'expected': list(expected_planned_ids),
                'planned': list(planned_ids),
            })
            continue

        markers, hook_failures = inject_check_markers(
            lines,
            code,
            plan,
            metadata['player_house'],
        )
        if hook_failures:
            failures.append({
                'code': code,
                'error': 'marker injection failed',
                'action_ids': [action_id for _check, action_id in hook_failures],
            })
            continue
        expected_marker_values = {'victory'} | set(
            configured_objectives.values()
        )
        if (
            set(markers.values()) != expected_marker_values
            or any(not marker.startswith('RLR_') for marker in markers)
        ):
            failures.append({'code': code, 'error': 'invalid marker namespace'})
            continue

        patched_actions = section_value_map_preserve(lines, 'Actions')
        for action_id in configured_ids:
            before = _parsed_groups(original_actions, action_id)
            after = _parsed_groups(patched_actions, action_id)
            if before is None or after is None:
                failures.append({
                    'code': code,
                    'action_id': action_id,
                    'error': 'could not parse reviewed Action after injection',
                })
                continue
            terminal_index = next(
                (
                    index for index, group in enumerate(before)
                    if group and group[0] in TERMINAL_END_ACTION_CODES
                ),
                None,
            )
            if (
                terminal_index is None
                or len(after) != len(before) + 1
                or after[:terminal_index] != before[:terminal_index]
                or not after[terminal_index]
                or after[terminal_index][0] != '4'
                or not after[terminal_index][2].startswith('RLRVT')
                or after[terminal_index + 1:] != before[terminal_index:]
            ):
                failures.append({
                    'code': code,
                    'action_id': action_id,
                    'error': 'marker is not immediately before terminal Action',
                })

        generated_ids = []
        for section, prefix in (
            ('TeamTypes', 'RLRVT'),
            ('TaskForces', 'RLRVF'),
            ('ScriptTypes', 'RLRVS'),
        ):
            generated_ids.extend(
                value
                for value in section_value_map_preserve(lines, section).values()
                if value.startswith(prefix)
            )
        if len(generated_ids) != len(set(generated_ids)):
            failures.append({'code': code, 'error': 'duplicate generated hook ID'})

        action_line_bytes = [
            len(line.encode('utf-8'))
            for line in section_lines(lines, 'Actions')
            if '=' in line
        ]
        if action_line_bytes:
            mission_max = max(action_line_bytes)
            max_generated_action_line_bytes = max(
                max_generated_action_line_bytes,
                mission_max,
            )
            if mission_max > MAX_MAP_ACTION_LINE_LENGTH:
                failures.append({
                    'code': code,
                    'error': 'Action line exceeds engine limit',
                    'bytes': mission_max,
                })
        if file_sha256(source_path) != source_hash_before:
            failures.append({'code': code, 'error': 'source map hash changed'})

        reviewed_action_count += len(configured_ids)
        reviewed_objective_action_count += len(configured_objectives)
        reviewed_objective_milestone_count += objective_count
        objective_mapped_missions += bool(configured_objectives)
        if len(configured_ids) > 1:
            multi_branch_missions += 1

    failed_codes = {failure['code'] for failure in failures}
    runtime_evidence = runtime_hook_evidence_report()
    return {
        'mission_count': len(MISSION_METADATA),
        'statically_verified_missions': len(MISSION_METADATA) - len(failed_codes),
        'reviewed_victory_action_count': reviewed_action_count,
        'reviewed_objective_action_count': reviewed_objective_action_count,
        'reviewed_objective_milestone_count': (
            reviewed_objective_milestone_count
        ),
        'objective_mapped_missions': objective_mapped_missions,
        'winner_action_code_counts': dict(sorted(winner_code_counts.items())),
        'multi_branch_missions': multi_branch_missions,
        'max_generated_action_line_bytes': max_generated_action_line_bytes,
        'action_line_limit_bytes': MAX_MAP_ACTION_LINE_LENGTH,
        'runtime_marker_verified_missions': runtime_evidence[
            'verified_mission_count'
        ],
        'runtime_marker_verified_codes': runtime_evidence[
            'verified_mission_codes'
        ],
        'runtime_marker_remaining_missions': runtime_evidence[
            'remaining_mission_count'
        ],
        'runtime_evidence_rejected': runtime_evidence[
            'rejected_evidence'
        ],
        'runtime_validation_required': bool(
            runtime_evidence['remaining_mission_count']
        ),
        'failures': failures,
        'valid': not failures,
    }
