"""Approve conservative Reloaded buff types for reviewed runtime targets.

This review promotes only TechnoTypes already approved by the independent
Reloaded content-path catalogue. SuperWeapon reviews are intentionally left
untouched; powers require a separate dependency and provider pass.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.config.static import load_static_config


CATALOGUE_PATH = (
    PROJECT_ROOT / 'configs' / 'rewards' / 'reloaded_balance_catalogue.json'
)
ACTIVE_BUFF_TYPES = {
    'production',
    'cost',
    'speed',
    'armor',
    'health',
    'sight',
    'damage',
    'reload',
    'range',
    'ammo',
    'passenger_capacity',
    'cloak',
    'sensors',
    'veteran',
}


def _approved_content_ids():
    content = load_static_config(
        'rewards/reloaded_content_catalogue.json'
    )['content']
    records = [
        record
        for category in content['units'].values()
        for record in category
    ] + list(content['defenses'])
    return {
        str(record['id']).upper()
        for record in records
        if not str(record['id']).upper().endswith('_AI')
        and any(
            review.get('status') == 'approved'
            for review in record.get('reviews', {}).values()
        )
    }


def review_document(document):
    sections = document['sections']
    approved_ids = _approved_content_ids()
    approved_targets = 0
    approved_effects = 0
    for target in sections['buff_targets']:
        unit_id = str(target['id']).upper()
        if unit_id not in approved_ids:
            continue
        candidates = set(target.get('candidate_buff_types') or ())
        approved = candidates.intersection(ACTIVE_BUFF_TYPES)
        stats = target.get('stats') or {}
        if stats.get('cloakable'):
            approved.discard('cloak')
        if stats.get('sensors'):
            approved.discard('sensors')
        excluded = candidates.difference(approved)
        target['review'] = {
            'status': 'approved',
            'approved_buff_types': sorted(approved),
            'excluded_buff_types': sorted(excluded),
            'flags': list((target.get('review') or {}).get('flags') or ()),
            'notes': (
                'Approved for isolated player-production clones after the '
                'Reloaded content-path review. Native starting-unit edits '
                'remain guarded by opponent ownership and shared-weapon '
                'safety checks.'
            ),
        }
        approved_targets += 1
        approved_effects += len(approved)

    buff_statuses = Counter(
        target.get('review', {}).get('status', 'pending_review')
        for target in sections['buff_targets']
    )
    power_statuses = Counter(
        power.get('review', {}).get('status', 'pending_review')
        for power in sections['powers']
    )
    sections['review_summary'] = {
        'buff_targets': dict(sorted(buff_statuses.items())),
        'powers': dict(sorted(power_statuses.items())),
    }
    sections['review_complete'] = (
        all(status in {'approved', 'excluded'} for status in buff_statuses)
        and all(status in {'approved', 'excluded'} for status in power_statuses)
    )
    document['description'] = (
        'Installed Reloaded buff-target and superweapon review facts. '
        'Approved buff effects are clone-isolated; powers remain gated.'
    )
    return {
        'approved_target_count': approved_targets,
        'approved_effect_count': approved_effects,
        'review_summary': sections['review_summary'],
        'review_complete': sections['review_complete'],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    document = json.loads(CATALOGUE_PATH.read_text(encoding='utf-8'))
    report = review_document(document)
    if args.write:
        CATALOGUE_PATH.write_text(
            json.dumps(document, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8',
        )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
