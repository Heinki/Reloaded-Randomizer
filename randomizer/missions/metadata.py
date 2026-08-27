"""Validated access to Reloaded-native mission metadata."""

from randomizer.config.static import load_static_config
from randomizer.maps.generated import file_sha256
from randomizer.missions.installation import (
    installed_mission_catalogue,
    resolve_installed_scenario,
)


_CONFIG = load_static_config('mission_catalogue.json')
MISSION_METADATA = tuple(_CONFIG['missions'])
MISSION_METADATA_BY_CODE = {
    str(mission['code']).upper(): mission for mission in MISSION_METADATA
}
REVIEW_FIELDS = (
    'houses',
    'starting_force',
    'relationships',
    'build_classification',
    'objectives',
    'difficulty_class',
    'reward_class',
)


def installed_metadata_report():
    """Compare bundled metadata with current Battle.ini and source hashes."""
    installed = installed_mission_catalogue()
    failures = []
    for mission in installed:
        metadata = MISSION_METADATA_BY_CODE.get(mission['code'].upper())
        if metadata is None:
            failures.append({'code': mission['code'], 'error': 'missing metadata'})
            continue
        if metadata['scenario'].lower() != mission['scenario'].lower():
            failures.append({
                'code': mission['code'],
                'error': 'scenario mismatch',
                'expected': metadata['scenario'],
                'actual': mission['scenario'],
            })
            continue
        source_path = resolve_installed_scenario(mission['scenario'])
        actual_hash = file_sha256(source_path)
        if actual_hash != metadata['source_sha256']:
            failures.append({
                'code': mission['code'],
                'error': 'source hash mismatch',
                'expected': metadata['source_sha256'],
                'actual': actual_hash,
            })
    installed_codes = {mission['code'].upper() for mission in installed}
    for code in sorted(set(MISSION_METADATA_BY_CODE) - installed_codes):
        failures.append({'code': code, 'error': 'not active in Battle.ini'})
    pending_counts = {}
    review_status_counts = {}
    for mission in MISSION_METADATA:
        for field, status in mission['review'].items():
            review_status_counts.setdefault(field, {})
            review_status_counts[field][status] = (
                review_status_counts[field].get(status, 0) + 1
            )
            if status == 'verified':
                continue
            pending_counts[field] = pending_counts.get(field, 0) + 1
    remaining_review_counts = {
        field: pending_counts.get(field, 0) for field in REVIEW_FIELDS
        if pending_counts.get(field, 0)
    }
    total_review_parts = len(MISSION_METADATA) * len(REVIEW_FIELDS)
    remaining_review_parts = sum(remaining_review_counts.values())
    hash_failures = {
        'source hash mismatch', 'scenario mismatch', 'missing metadata'
    }
    return {
        'metadata_mission_count': len(MISSION_METADATA),
        'installed_mission_count': len(installed),
        'hash_verified_missions': len(installed) - len([
            failure for failure in failures
            if failure.get('error') in hash_failures
        ]),
        'pending_review_counts': dict(sorted(pending_counts.items())),
        'review_status_counts': dict(sorted(review_status_counts.items())),
        'review_categories': list(REVIEW_FIELDS),
        'total_review_parts': total_review_parts,
        'completed_review_parts': total_review_parts - remaining_review_parts,
        'remaining_review_parts': remaining_review_parts,
        'remaining_review_counts': remaining_review_counts,
        'failures': failures,
        'valid': len(installed) == len(MISSION_METADATA) and not failures,
    }
