"""Source-bound mission reward-tier review for C&C Reloaded.

C&C Reloaded campaigns do not use Mental Omega's Act 1/Act 2 structure.
Every non-finale mission therefore uses the standard reward multiplier. Only
explicit, reviewed Reloaded campaign finales receive the higher multiplier.
"""

from collections import Counter
from hashlib import sha256
import json

from randomizer.config.static import load_static_config
from randomizer.missions.metadata import MISSION_METADATA


_MISSION_CONFIG = load_static_config('missions.json')
REWARD_CLASSES = ('standard', 'finale')
REWARD_CLASS_MULTIPLIERS = {'standard': 1, 'finale': 3}


def reward_class_for_mission(metadata, config=None):
    """Return ``finale`` only for an explicit reviewed Reloaded finale."""
    config = config or _MISSION_CONFIG
    code = str(metadata['code']).upper()
    return (
        'finale'
        if code in set(config['catalogue']['finale_mission_codes'])
        else 'standard'
    )


def reviewed_mission_reward_policy(records=None, config=None):
    """Return complete standard/finale policy in catalogue order."""
    records = records or MISSION_METADATA
    config = config or _MISSION_CONFIG
    mission_classes = {class_name: [] for class_name in REWARD_CLASSES}
    for record in records:
        mission_classes[
            reward_class_for_mission(record, config=config)
        ].append(record['code'])
    return {
        'default_multiplier': 1,
        'class_multipliers': dict(REWARD_CLASS_MULTIPLIERS),
        'mission_classes': mission_classes,
        'mission_overrides': {},
    }


def reward_policy_sha256(metadata, config=None):
    """Fingerprint exact finale and multiplier policy for one mission."""
    config = config or _MISSION_CONFIG
    code = str(metadata['code']).upper()
    reward_class = reward_class_for_mission(metadata, config=config)
    reward_config = config['mission_reward_multipliers']
    payload = {
        'code': code,
        'is_finale': code in set(config['catalogue']['finale_mission_codes']),
        'reward_class': reward_class,
        'class_multiplier': reward_config['class_multipliers'][reward_class],
        'mission_override': reward_config['mission_overrides'].get(code),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return sha256(encoded).hexdigest()


def reward_review_record(metadata, config=None):
    """Build one deterministic source- and policy-bound reward review."""
    config = config or _MISSION_CONFIG
    reward_class = reward_class_for_mission(metadata, config=config)
    multiplier = config['mission_reward_multipliers'][
        'class_multipliers'
    ][reward_class]
    return {
        'source_sha256': metadata['source_sha256'],
        'policy_sha256': reward_policy_sha256(metadata, config=config),
        'reward_class': reward_class,
        'evidence': [
            (
                'Explicit reviewed Reloaded campaign finale receives the '
                'higher reward multiplier.'
                if reward_class == 'finale' else
                'Reloaded uses the standard reward multiplier for every '
                'non-finale mission.'
            ),
            f'Reward multiplier is {multiplier}; no Mental Omega mission '
            'identity or progression judgment is used.',
        ],
    }


def reward_review_report(config=None):
    """Validate reward reviews, metadata, and complete multiplier policy."""
    config = config or _MISSION_CONFIG
    reviews = config.get('reward_class_reviews', {})
    expected_codes = {metadata['code'] for metadata in MISSION_METADATA}
    expected_policy = reviewed_mission_reward_policy(
        MISSION_METADATA,
        config=config,
    )
    failures = []
    counts = Counter()

    if config['mission_reward_multipliers'] != expected_policy:
        failures.append({'error': 'mission reward class policy is stale'})
    missing = sorted(expected_codes - set(reviews))
    extra = sorted(set(reviews) - expected_codes)
    if missing:
        failures.append({'error': 'missing reward reviews', 'codes': missing})
    if extra:
        failures.append({'error': 'unknown reward reviews', 'codes': extra})

    for metadata in MISSION_METADATA:
        code = metadata['code']
        expected = reward_review_record(metadata, config=config)
        review = reviews.get(code)
        if review is None:
            continue
        if review != expected:
            failures.append({'code': code, 'error': 'reward review is stale'})
        if (
            metadata.get('reward_class') != expected['reward_class']
            or metadata['review'].get('reward_class') != 'verified'
        ):
            failures.append({'code': code, 'error': 'metadata review is stale'})
        counts[expected['reward_class']] += 1

    return {
        'mission_count': len(MISSION_METADATA),
        'reviewed_mission_count': len(expected_codes.intersection(reviews)),
        'reward_class_counts': {
            name: counts.get(name, 0) for name in REWARD_CLASSES
        },
        'class_multipliers': dict(REWARD_CLASS_MULTIPLIERS),
        'failures': failures,
        'valid': len(reviews) == len(MISSION_METADATA) and not failures,
    }


def main():
    report = reward_review_report()
    print(json.dumps(report, indent=2))
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
