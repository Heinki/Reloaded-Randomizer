"""Promote only source-proven C&C Reloaded content-review candidates.

Mental Omega uses explicit reviewed rosters. C&C Reloaded keeps that pattern,
but decisions come only from its installed 2.7.0 rules. This pass combines
house gates with resolved prerequisites, factories, and provider buildings;
it approves only source-proven active-faction paths without unresolved hazards.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.config.static import validate_sections
from randomizer.content.faction_paths import content_record_faction_path
from randomizer.content.inventory import read_rules_sections, rules_fingerprint


CATALOGUE_PATH = (
    PROJECT_ROOT / 'configs' / 'rewards' / 'reloaded_content_catalogue.json'
)
APPROVAL_NOTE = (
    'Approved from installed C&C Reloaded 2.7.0 rules: exactly one active '
    'canonical faction, explicit production path, buildable TechLevel, and '
    'no review hazard flags.'
)
PENDING_NOTE = (
    'Automatic approval withheld because source-derived review hazard flags '
    'require an explicit Reloaded gameplay decision.'
)
SCOPED_OWNER_NOTE = (
    'Approved from installed C&C Reloaded 2.7.0 rules: broad Owner list is '
    'reduced to exactly one active canonical faction by RequiredHouses or '
    'ForbiddenHouses, with an explicit production path and no other hazard.'
)
PATH_APPROVAL_NOTE = (
    'Approved from installed C&C Reloaded 2.7.0 production-path evidence: '
    '{path}; resolved active faction scope is {scope}. No unresolved review '
    'hazard remains beyond broad Owner/provider ownership.'
)
PATH_EXCLUSION_NOTE = (
    'Excluded from {faction}: installed C&C Reloaded 2.7.0 production-path '
    'evidence ({path}) resolves to {scope}, so this faction cannot build or '
    'provide the entry through that path.'
)
SAFE_SCOPING_FLAGS = {'broad_owner_list', 'broad_provider_owner_list'}


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Review source-proven Reloaded content paths.',
    )
    parser.add_argument('--write', action='store_true')
    return parser.parse_args()


def _iter_reviews(document):
    content = document['sections']['content']
    groups = [
        *(('units', category, records)
          for category, records in content['units'].items()),
        ('production', 'production', content['production']),
        ('defenses', 'defenses', content['defenses']),
        ('powers', 'powers', content['powers']),
    ]
    for section, category, records in groups:
        for record in records:
            for faction, review in record['reviews'].items():
                yield section, category, faction, record, review


def _path_description(path):
    parts = []
    if path['prerequisites']:
        parts.append('Prerequisite=' + ','.join(path['prerequisites']))
    if path['built_at']:
        parts.append('BuiltAt=' + ','.join(path['built_at']))
    return '; '.join(parts) or 'no explicit path'


def _scope_description(factions):
    return ', '.join(sorted(factions)) if factions else 'no active faction'


def review_catalogue(document):
    """Apply deterministic conservative decisions and refresh summary."""
    installed_sections, _source = read_rules_sections()
    installed_fingerprint = rules_fingerprint(installed_sections)
    configured_fingerprint = document['sections'][
        'rules_fingerprint_sha256'
    ]
    if installed_fingerprint != configured_fingerprint:
        raise ValueError(
            'Installed rules fingerprint differs from content catalogue. '
            'Rebuild catalogue before reviewing it.'
        )

    promoted = Counter()
    path_promoted = Counter()
    path_excluded = Counter()
    deferred = Counter()
    for section, category, faction, record, review in _iter_reviews(document):
        if review['status'] not in {'candidate', 'pending_review'}:
            continue
        key = f'{section}/{category}'
        flags = set(review['flags'])
        exact_faction = record['eligible_factions'] == [faction]
        path = content_record_faction_path(record, section)
        if path['complete'] and path.get('specific'):
            description = _path_description(path)
            scope = _scope_description(path['factions'])
            if faction not in path['factions']:
                review['status'] = 'excluded'
                review['notes'] = PATH_EXCLUSION_NOTE.format(
                    faction=faction,
                    path=description,
                    scope=scope,
                )
                path_excluded[(faction, key)] += 1
                continue
            if flags.issubset(SAFE_SCOPING_FLAGS):
                review['status'] = 'approved'
                review['notes'] = PATH_APPROVAL_NOTE.format(
                    path=description,
                    scope=scope,
                )
                promoted[(faction, key)] += 1
                path_promoted[(faction, key)] += 1
                continue
        if flags and flags.issubset(SAFE_SCOPING_FLAGS) and exact_faction:
            review['status'] = 'approved'
            review['notes'] = SCOPED_OWNER_NOTE
            promoted[(faction, key)] += 1
            continue
        if review['status'] == 'pending_review':
            continue
        if flags:
            review['status'] = 'pending_review'
            review['notes'] = PENDING_NOTE
            deferred[(faction, key)] += 1
            continue
        if not exact_faction:
            raise ValueError(
                f'Candidate {record["id"]} does not have one exact faction.'
            )
        review['status'] = 'approved'
        review['notes'] = APPROVAL_NOTE
        promoted[(faction, key)] += 1

    status_counts = Counter(
        review['status']
        for _section, _category, _faction, _record, review
        in _iter_reviews(document)
    )
    document['sections']['review_summary'] = dict(sorted(status_counts.items()))
    document['sections']['review_complete'] = not bool(
        status_counts.get('candidate') or status_counts.get('pending_review')
    )
    return {
        'promoted_count': sum(promoted.values()),
        'path_promoted_count': sum(path_promoted.values()),
        'path_excluded_count': sum(path_excluded.values()),
        'deferred_flagged_candidate_count': sum(deferred.values()),
        'promoted_by_faction': {
            faction: sum(
                count for (current, _group), count in promoted.items()
                if current == faction
            )
            for faction in ('Allies', 'Soviets', 'Yuri', 'GDI', 'Nod')
        },
        'review_summary': document['sections']['review_summary'],
        'review_complete': document['sections']['review_complete'],
    }


def main():
    args = _parse_args()
    document = json.loads(CATALOGUE_PATH.read_text(encoding='utf-8'))
    report = review_catalogue(document)
    validate_sections(
        'rewards/reloaded_content_catalogue.json',
        document['sections'],
        CATALOGUE_PATH,
    )
    if args.write:
        CATALOGUE_PATH.write_text(
            json.dumps(document, indent=2) + '\n',
            encoding='utf-8',
        )
        report['written'] = str(CATALOGUE_PATH)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
