"""Source-bound progression difficulty review for Reloaded missions.

Mental Omega protects its opening with four deterministic stage buckets and
explicit late/finale mission lists. Reloaded retains that engine-generic
mechanism, but derives scores from reviewed campaign mission numbers and uses
only Reloaded campaign finales. This is a progression-safety classification;
it does not change the in-game difficulty selected by the player.
"""

from collections import Counter, defaultdict
from hashlib import sha256
import json

from randomizer.config.static import load_static_config
from randomizer.missions.metadata import MISSION_METADATA


_MISSION_CONFIG = load_static_config('missions.json')
DIFFICULTY_CLASSES = ('opening', 'mid', 'late', 'finale')
MID_STAGE_MAX = 16


def campaign_finale_codes(records):
    """Return every part/candidate at each campaign/faction's final number."""
    groups = defaultdict(list)
    for record in records:
        groups[(record['campaign'], record['faction'])].append(record)

    finales = set()
    for group in groups.values():
        numbered = [
            record for record in group
            if isinstance(record.get('mission_number'), int)
            and not isinstance(record.get('mission_number'), bool)
        ]
        if not numbered:
            continue
        last_number = max(record['mission_number'] for record in numbered)
        finales.update(
            record['code'] for record in numbered
            if record['mission_number'] == last_number
        )
    return frozenset(finales)


def progression_stage_score(metadata, config=None):
    """Return the Mental Omega-compatible stage score for one mission."""
    config = config or _MISSION_CONFIG
    catalogue = config['catalogue']
    code = str(metadata['code']).upper()
    if code in set(catalogue['finale_mission_codes']):
        return int(catalogue['finale_stage_score'])
    if code in set(catalogue['operation_mission_codes']):
        return int(catalogue['operation_stage_score'])
    mission_number = metadata.get('mission_number')
    if isinstance(mission_number, int) and not isinstance(mission_number, bool):
        return mission_number
    campaign_order = metadata.get('campaign_order')
    if isinstance(campaign_order, int) and not isinstance(campaign_order, bool):
        return campaign_order
    return int(catalogue['fallback_stage_score'])


def difficulty_class_for_score(score, config=None):
    """Map one stage score to the four retained progression buckets."""
    config = config or _MISSION_CONFIG
    catalogue = config['catalogue']
    if score <= int(catalogue['low_level_stage_max']):
        return 'opening'
    if score <= MID_STAGE_MAX:
        return 'mid'
    if score < int(catalogue['finale_stage_score']):
        return 'late'
    return 'finale'


def difficulty_policy_sha256(metadata, config=None):
    """Fingerprint the exact policy inputs used for one classification."""
    config = config or _MISSION_CONFIG
    catalogue = config['catalogue']
    code = str(metadata['code']).upper()
    payload = {
        'code': code,
        'mission_number': metadata.get('mission_number'),
        'campaign_order': metadata.get('campaign_order'),
        'low_level_stage_max': int(catalogue['low_level_stage_max']),
        'mid_stage_max': MID_STAGE_MAX,
        'operation_stage_score': int(catalogue['operation_stage_score']),
        'fallback_stage_score': int(catalogue['fallback_stage_score']),
        'finale_stage_score': int(catalogue['finale_stage_score']),
        'is_operation': code in set(catalogue['operation_mission_codes']),
        'is_finale': code in set(catalogue['finale_mission_codes']),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return sha256(encoded).hexdigest()


def difficulty_review_record(metadata, config=None):
    """Build one deterministic source- and policy-bound review record."""
    config = config or _MISSION_CONFIG
    score = progression_stage_score(metadata, config=config)
    difficulty_class = difficulty_class_for_score(score, config=config)
    if difficulty_class == 'finale':
        source = (
            'This is the final authored mission number for its Reloaded '
            'campaign and faction; every sequential part shares the finale.'
        )
    else:
        source = (
            f'Reviewed authored mission number {metadata["mission_number"]} '
            f'produces stage score {score}.'
        )
    return {
        'source_sha256': metadata['source_sha256'],
        'policy_sha256': difficulty_policy_sha256(metadata, config=config),
        'stage_score': score,
        'difficulty_class': difficulty_class,
        'evidence': [
            source,
            'Mental Omega progression bucket thresholds are retained; only '
            'Reloaded campaign metadata and finale identities are used.',
        ],
    }


def difficulty_review_report(config=None):
    """Validate all classifications, finale policy, and metadata bindings."""
    config = config or _MISSION_CONFIG
    reviews = config.get('difficulty_reviews', {})
    expected_codes = {metadata['code'] for metadata in MISSION_METADATA}
    configured_finales = set(config['catalogue']['finale_mission_codes'])
    expected_finales = set(campaign_finale_codes(MISSION_METADATA))
    failures = []
    counts = Counter()

    if configured_finales != expected_finales:
        failures.append({
            'error': 'Reloaded finale mission policy is stale',
            'missing': sorted(expected_finales - configured_finales),
            'extra': sorted(configured_finales - expected_finales),
        })
    missing = sorted(expected_codes - set(reviews))
    extra = sorted(set(reviews) - expected_codes)
    if missing:
        failures.append({'error': 'missing difficulty reviews', 'codes': missing})
    if extra:
        failures.append({'error': 'unknown difficulty reviews', 'codes': extra})

    for metadata in MISSION_METADATA:
        code = metadata['code']
        expected = difficulty_review_record(metadata, config=config)
        review = reviews.get(code)
        if review is None:
            continue
        if review != expected:
            failures.append({'code': code, 'error': 'difficulty review is stale'})
        if (
            metadata.get('difficulty_class') != expected['difficulty_class']
            or metadata['review']['difficulty_class'] != 'verified'
        ):
            failures.append({'code': code, 'error': 'metadata review is stale'})
        counts[expected['difficulty_class']] += 1

    return {
        'mission_count': len(MISSION_METADATA),
        'reviewed_mission_count': len(expected_codes.intersection(reviews)),
        'difficulty_class_counts': {
            name: counts.get(name, 0) for name in DIFFICULTY_CLASSES
        },
        'finale_mission_codes': sorted(configured_finales),
        'opening_exclusion_count': len(MISSION_METADATA) - counts['opening'],
        'failures': failures,
        'valid': len(reviews) == len(MISSION_METADATA) and not failures,
    }


def main():
    report = difficulty_review_report()
    print(json.dumps(report, indent=2))
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
