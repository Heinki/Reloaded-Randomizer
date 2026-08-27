"""Source-bound review of rewardable mission objective milestones.

Mental Omega can discover its custom ObjectiveComplete Actions. Reloaded uses
older EVA completion/archive voices instead, so only an explicit allowlist of
completion signatures is accepted. Objective statements, reminders, camera
changes, and arbitrary mission text are never sufficient evidence.
"""

import json
import re

from randomizer.config.static import load_static_config
from randomizer.maps.generated import file_sha256
from randomizer.maps.ini import (
    IniLines,
    all_section_value_maps,
    parse_action_groups,
    read_text,
)
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.missions.metadata import MISSION_METADATA


_MISSION_CONFIG = load_static_config('missions.json')
_ORDINAL_SIGNATURES = (
    ('primaryobjectiveachieved', 1),
    ('primaryobjectivearchive', 1),
    ('secondaryobjectiveachieved', 2),
    ('secondaryobjectivearchive', 2),
    ('tertiaryobjectiveachieved', 3),
    ('tertiaryobjectivearchive', 3),
    ('terciaryobjectivearchive', 3),
)
_GENERIC_SIGNATURES = frozenset({'eva_objectivecomplete'})
_BLOCKED_TRIGGER_TOKENS = ('debug', 'dead trigger', 'ignore this')


def _trigger_name(triggers, action_id):
    tokens = [
        token.strip()
        for token in str(triggers.get(action_id, '')).split(',')
    ]
    return tokens[2] if len(tokens) > 2 else ''


def _number_from_text(text):
    lowered = str(text or '').lower()
    patterns = (
        r'(?:objective|obj)[ _./-]*0?([1-9])',
        r'(?:complete|completed)[ _./-]*(?:objective|obj)[ _./-]*0?([1-9])',
    )
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return int(match.group(1))
    return None


def objective_completion_evidence(metadata):
    """Return conservative completion Actions normalized to reward checks."""
    source_path = resolve_installed_scenario(metadata['scenario'])
    lines = IniLines(read_text(source_path).splitlines())
    sections = all_section_value_maps(lines)
    triggers = sections.get('Triggers', {})
    terminal_ids = {
        str(action_id).lower()
        for action_id in metadata['verified_victory_action_ids']
    }
    candidates = []
    failures = []

    for action_id, value in sections.get('Actions', {}).items():
        declared, groups = parse_action_groups(str(value))
        if declared != len(groups):
            continue
        name = _trigger_name(triggers, action_id)
        name_lower = name.lower()
        if any(token in name_lower for token in _BLOCKED_TRIGGER_TOKENS):
            continue
        if str(action_id).lower() in terminal_ids:
            continue

        ordinals = set()
        generic = False
        signatures = []
        for group in groups:
            if len(group) < 3:
                continue
            parameter = str(group[2]).strip().lower()
            if group[0] == '21':
                for signature, ordinal in _ORDINAL_SIGNATURES:
                    if signature in parameter:
                        ordinals.add(ordinal)
                        signatures.append(parameter)
                if parameter in _GENERIC_SIGNATURES:
                    generic = True
                    signatures.append(parameter)
            if group[0] == '11':
                number = _number_from_text(parameter)
                if number is not None and any(
                    token in parameter for token in ('comp', 'complete')
                ):
                    ordinals.add(number)
                    signatures.append(parameter)

        if not ordinals and not generic:
            continue
        if len(ordinals) > 1:
            failures.append({
                'action_id': action_id,
                'error': 'completion Action has conflicting objective numbers',
                'ordinals': sorted(ordinals),
            })
            continue
        ordinal = next(iter(ordinals), None)
        if ordinal is None:
            ordinal = _number_from_text(name)
        candidates.append({
            'action_id': action_id,
            'trigger_name': name,
            'source_ordinal': ordinal,
            'signatures': sorted(set(signatures)),
        })

    numbered = sorted({
        candidate['source_ordinal']
        for candidate in candidates
        if candidate['source_ordinal'] is not None
    })
    group_order = [('numbered', number) for number in numbered]
    if any(
        candidate['source_ordinal'] is None for candidate in candidates
    ):
        # Unnumbered EVA_ObjectiveComplete Actions are one conservative
        # milestone. Multiple paths can announce the same completion.
        group_order.append(('generic', None))
    check_by_group = {
        group: f'objective_{index}'
        for index, group in enumerate(group_order, start=1)
    }
    action_checks = {}
    for candidate in candidates:
        group = (
            ('numbered', candidate['source_ordinal'])
            if candidate['source_ordinal'] is not None
            else ('generic', None)
        )
        action_checks[candidate['action_id']] = check_by_group[group]
        candidate['check_id'] = check_by_group[group]

    return {
        'expected_objective_count': len(group_order),
        'action_checks': action_checks,
        'completion_actions': candidates,
        'failures': failures,
    }


def objective_review_record(metadata):
    """Build one deterministic source-bound objective review record."""
    evidence = objective_completion_evidence(metadata)
    count = evidence['expected_objective_count']
    return {
        'source_sha256': metadata['source_sha256'],
        'expected_objective_count': count,
        'action_checks': evidence['action_checks'],
        'evidence': [
            (
                f'{len(evidence["action_checks"])} source-proven EVA '
                f'completion Action(s) form {count} rewardable milestone(s).'
                if count else
                'No source-proven independent completion Action exists; '
                'mission remains victory-only.'
            ),
            'Objective text, reminders, debug triggers, and terminal victory '
            'Actions are excluded.',
        ],
    }


def objective_review_report(config=None):
    """Validate objective records, metadata, and hook policy against maps."""
    config = config or _MISSION_CONFIG
    reviews = config.get('objective_reviews', {})
    configured_hooks = config.get('objective_hook_action_ids', {})
    expected_codes = {metadata['code'] for metadata in MISSION_METADATA}
    failures = []
    completion_action_count = 0
    milestone_count = 0
    reviewed_with_milestones = 0

    missing = sorted(expected_codes - set(reviews))
    extra = sorted(set(reviews) - expected_codes)
    if missing:
        failures.append({'error': 'missing objective reviews', 'codes': missing})
    if extra:
        failures.append({'error': 'unknown objective reviews', 'codes': extra})

    for metadata in MISSION_METADATA:
        code = metadata['code']
        actual = objective_completion_evidence(metadata)
        review = reviews.get(code)
        if actual['failures']:
            failures.extend(
                {'code': code, **failure} for failure in actual['failures']
            )
        if review is None:
            continue
        source_hash = file_sha256(
            resolve_installed_scenario(metadata['scenario'])
        )
        if review.get('source_sha256') != source_hash:
            failures.append({'code': code, 'error': 'source hash is stale'})
        if review.get('expected_objective_count') != actual[
            'expected_objective_count'
        ]:
            failures.append({'code': code, 'error': 'objective count is stale'})
        if review.get('action_checks') != actual['action_checks']:
            failures.append({'code': code, 'error': 'Action mapping is stale'})
        if configured_hooks.get(code, {}) != actual['action_checks']:
            failures.append({'code': code, 'error': 'hook policy is stale'})
        if metadata.get('expected_objective_count') != actual[
            'expected_objective_count'
        ] or metadata['review']['objectives'] != 'verified':
            failures.append({'code': code, 'error': 'metadata review is stale'})
        evidence_text = review.get('evidence')
        if (
            not isinstance(evidence_text, list)
            or not evidence_text
            or any(not isinstance(item, str) or not item for item in evidence_text)
        ):
            failures.append({'code': code, 'error': 'review evidence is missing'})
        completion_action_count += len(actual['action_checks'])
        milestone_count += actual['expected_objective_count']
        reviewed_with_milestones += bool(
            actual['expected_objective_count']
        )

    unexpected_hook_codes = sorted(set(configured_hooks) - expected_codes)
    if unexpected_hook_codes:
        failures.append({
            'error': 'unknown objective hook missions',
            'codes': unexpected_hook_codes,
        })
    return {
        'mission_count': len(MISSION_METADATA),
        'reviewed_mission_count': len(expected_codes.intersection(reviews)),
        'missions_with_rewardable_milestones': reviewed_with_milestones,
        'rewardable_milestone_count': milestone_count,
        'completion_action_count': completion_action_count,
        'failures': failures,
        'valid': len(reviews) == len(MISSION_METADATA) and not failures,
    }


def main():
    report = objective_review_report()
    print(json.dumps(report, indent=2))
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
