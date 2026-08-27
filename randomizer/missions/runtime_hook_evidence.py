"""Validate persisted real-game victory-hook evidence.

Evidence is written only by ``tools/runtime_victory_hook_check.py`` after a
reviewed generated map reaches its victory marker, restores ``spawn.ini``,
removes owned generated maps, and proves the authored source hash unchanged.
"""

import json

from randomizer.core.paths import LOG_DIR
from randomizer.maps.hooks import hook_marker_name
from randomizer.missions.metadata import MISSION_METADATA_BY_CODE


RUNTIME_HOOK_EVIDENCE_DIR = LOG_DIR / 'runtime_victory_hooks'


def runtime_hook_evidence_path(mission_code):
    """Return canonical evidence path for one mission code."""
    code = str(mission_code or '').strip().upper()
    if not code or not code.replace('_', '').isalnum():
        raise ValueError(f'Invalid mission code for runtime evidence: {mission_code!r}')
    return RUNTIME_HOOK_EVIDENCE_DIR / f'{code}.json'


def runtime_hook_evidence_report():
    """Return source-bound accepted and rejected runtime victory evidence."""
    accepted = []
    rejected = []
    if not RUNTIME_HOOK_EVIDENCE_DIR.is_dir():
        return {
            'verified_mission_count': 0,
            'verified_mission_codes': [],
            'remaining_mission_count': len(MISSION_METADATA_BY_CODE),
            'rejected_evidence': [],
        }

    for path in sorted(RUNTIME_HOOK_EVIDENCE_DIR.glob('*.json')):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            rejected.append({'file': str(path), 'reason': str(exc)})
            continue
        code = str(record.get('mission_code') or '').upper()
        metadata = MISSION_METADATA_BY_CODE.get(code)
        reasons = []
        if metadata is None:
            reasons.append('unknown mission code')
        elif record.get('source_sha256') != metadata['source_sha256']:
            reasons.append('source hash differs from reviewed metadata')
        if record.get('victory_marker') != hook_marker_name(code, 'victory'):
            reasons.append('victory marker differs from reviewed identity')
        if metadata is not None and tuple(
            str(value).lower()
            for value in record.get('victory_action_ids', ())
        ) != tuple(
            str(value).lower()
            for value in metadata['verified_victory_action_ids']
        ):
            reasons.append('victory Actions differ from reviewed metadata')
        if not record.get('passed'):
            reasons.append('runtime check did not pass')
        if not record.get('generated_scenario_confirmed'):
            reasons.append('generated scenario was not confirmed')
        if not record.get('victory_marker_seen'):
            reasons.append('victory marker was not seen')
        if not record.get('source_unchanged'):
            reasons.append('authored source integrity was not confirmed')
        if not record.get('spawn_restored'):
            reasons.append('spawn.ini restoration was not confirmed')
        if not record.get('generated_maps_removed'):
            reasons.append('generated map cleanup was not confirmed')
        if reasons:
            rejected.append({
                'file': str(path),
                'mission_code': code,
                'reasons': reasons,
            })
            continue
        accepted.append(code)

    accepted = sorted(set(accepted))
    return {
        'verified_mission_count': len(accepted),
        'verified_mission_codes': accepted,
        'remaining_mission_count': len(MISSION_METADATA_BY_CODE) - len(accepted),
        'rejected_evidence': rejected,
    }
