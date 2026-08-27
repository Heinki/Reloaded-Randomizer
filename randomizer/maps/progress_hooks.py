"""Plan and inject objective/victory progress markers."""

from randomizer.core.collections import unique_in_order
from randomizer.config.game_profile import TERMINAL_END_ACTION_CODES
from randomizer.maps.hooks import (
    action_line_ids,
    append_action_to_action_id,
    append_hook_team,
    append_parallel_global_hook,
    hook_marker_name,
    insert_actions_before_codes,
)
from randomizer.maps.ini import section_value_map_preserve

NEXT_OBJECTIVE_CHECK_ID = '__next_objective__'


def _unique_registered_id(lines, registry_section, prefix):
    """Allocate an unused registered type ID and matching map section name."""
    existing = {
        str(value).lower()
        for value in section_value_map_preserve(
            lines, registry_section
        ).values()
    }
    existing.update(
        line.strip()[1:-1].strip().lower()
        for line in lines
        if line.strip().startswith('[') and line.strip().endswith(']')
    )
    for index in range(1, 1000):
        candidate = f'{prefix}{index:03d}'
        if candidate.lower() not in existing:
            return candidate
    raise RuntimeError(f'Could not allocate a unique {prefix} map ID.')


def pending_check_hook_plan(
    lines,
    checks,
    configured_victory_action_ids=(),
    configured_objective_action_ids=None,
    objective_action_redirects=None,
):
    """Plan only reviewed objective and victory Action hooks."""
    configured_objective_action_ids = configured_objective_action_ids or {}
    objective_action_redirects = objective_action_redirects or {}
    available_action_ids = {
        action_id.lower(): action_id
        for action_id in action_line_ids(lines, lambda _groups: True)
    }
    configured_victory_action_ids = [
        available_action_ids[str(action_id).lower()]
        for action_id in configured_victory_action_ids
        if str(action_id).lower() in available_action_ids
    ]
    victory_action_ids = unique_in_order(configured_victory_action_ids)
    normalized_redirects = {
        str(source_id).lower(): str(target_id).lower()
        for source_id, target_id in objective_action_redirects.items()
    }

    plan = []
    objective_checks = [
        check for check in checks if check.get('id') != 'victory'
    ]
    completed_objectives = sum(
        1 for check in objective_checks if check.get('unlocked')
    )
    checks_by_id = {
        str(check.get('id')): check
        for check in objective_checks
    }
    for index, (action_id, check_id) in enumerate(
        configured_objective_action_ids.items(),
        start=1,
    ):
        source_key = str(action_id).lower()
        if source_key not in available_action_ids:
            continue
        check = checks_by_id.get(str(check_id))
        if check is None or check.get('unlocked'):
            continue
        redirected_key = normalized_redirects.get(
            source_key, source_key
        )
        if redirected_key not in available_action_ids:
            redirected_key = source_key
        redirected_action_id = available_action_ids[redirected_key]
        planned_check = dict(check)
        planned_check['marker_id'] = f'E{index:04d}'
        plan.append((planned_check, redirected_action_id))

    victory_check = next(
        (check for check in checks if check.get('id') == 'victory'),
        None,
    )
    missing_victory = False
    if victory_check and not victory_check.get('unlocked'):
        if victory_action_ids:
            # Explicit mission policy may name multiple mutually-exclusive
            # successful endings. Hook each branch with the same check marker;
            # watcher/state deduplication still records victory exactly once.
            plan.extend(
                (victory_check, action_id)
                for action_id in victory_action_ids
            )
        else:
            missing_victory = True
    return plan, missing_victory, completed_objectives


def inject_check_markers(lines, mission_code, plan, house):
    """Inject bounded marker actions and return marker map plus failures."""
    markers = {}
    failures = []
    for index, (check, action_id) in enumerate(plan, start=1):
        marker = hook_marker_name(
            mission_code,
            check.get('marker_id', check.get('id', f'check_{index}')),
        )
        team_id = _unique_registered_id(lines, 'TeamTypes', 'RLRVT')
        taskforce_id = _unique_registered_id(lines, 'TaskForces', 'RLRVF')
        script_id = _unique_registered_id(lines, 'ScriptTypes', 'RLRVS')
        marker_action = ['4', '1', team_id, '0', '0', '0', '0', 'A']

        if check.get('id') == 'victory':
            patched = insert_actions_before_codes(
                lines,
                action_id,
                [marker_action],
                before_codes=TERMINAL_END_ACTION_CODES,
            )
            if not patched:
                patched = append_action_to_action_id(
                    lines,
                    action_id,
                    marker_action,
                )
        else:
            patched = append_action_to_action_id(
                lines,
                action_id,
                marker_action,
            )
            if not patched:
                patched = append_parallel_global_hook(
                    lines,
                    action_id,
                    marker_action,
                    marker,
                )

        if not patched:
            failures.append((check, action_id))
            continue
        append_hook_team(
            lines,
            team_id,
            taskforce_id,
            script_id,
            marker,
            house,
        )
        markers[marker] = check.get('id')
    return markers, failures
