"""Promote only source-proven Reloaded mission metadata reviews.

Mental Omega stores completed mission judgments as explicit configuration.
Reloaded keeps that pattern, while this first pass automates only facts that
can be proven from unchanged Battle.ini entries, map hashes, authored map
records, standard ownership Actions, and explicit Reloaded-only reviewed build,
House-policy, objective-completion, progression-difficulty, and act/reward
evidence.
"""

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from randomizer.maps.generated import file_sha256
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.missions.production_review import (
    scripted_player_building_evidence,
    scripted_player_mcv_evidence,
    scripted_player_object_transfer_evidence,
    transferred_house_build_evidence,
)
from randomizer.content.inventory import read_rules_sections
from randomizer.missions.house_review import (
    house_policy_sha256,
    mission_house_policy,
    mission_house_policy_failures,
)
from randomizer.missions.difficulty_review import (
    campaign_finale_codes,
    difficulty_review_record,
)
from randomizer.missions.reward_review import (
    reward_review_record,
    reviewed_mission_reward_policy,
)
from randomizer.missions.objective_review import (
    objective_completion_evidence,
    objective_review_record,
)
from tools.build_mission_metadata import build_metadata


METADATA_PATH = REPOSITORY_ROOT / 'configs' / 'mission_catalogue.json'
MISSION_POLICY_PATH = REPOSITORY_ROOT / 'configs' / 'missions.json'


def _arguments():
    parser = argparse.ArgumentParser(
        description='Review source-proven C&C Reloaded mission metadata.',
    )
    parser.add_argument(
        '--write',
        action='store_true',
        help=(
            'Write verified promotions and synchronize completed build, '
            'House, objective, difficulty, and reward-tier policy.'
        ),
    )
    return parser.parse_args()


def _relationship_is_proven(record, records_by_code):
    relationship = record['relationship']
    kind = relationship['kind']
    related_codes = relationship['related_codes']
    peers = [records_by_code.get(code) for code in related_codes]
    if any(peer is None for peer in peers):
        return False
    if kind == 'standalone':
        return not related_codes
    group = [record, *peers]
    if any(
        peer['campaign'] != record['campaign']
        or peer['faction'] != record['faction']
        or peer['mission_number'] != record['mission_number']
        or peer['relationship']['series_key']
        != relationship['series_key']
        or record['code'] not in peer['relationship']['related_codes']
        for peer in peers
    ):
        return False
    if kind == 'sequential_parts':
        part_count = record['part_count']
        return (
            isinstance(part_count, int)
            and part_count == len(group)
            and {peer['part'] for peer in group}
            == set(range(1, part_count + 1))
            and all(peer['part_count'] == part_count for peer in group)
        )
    if kind == 'alternate_candidates':
        return (
            len(group) > 1
            and all(peer['part'] is None for peer in group)
            and len({peer['scenario'].lower() for peer in group}) == len(group)
            and all('location)' in peer['title'].lower() for peer in group)
        )
    return False


def reviewed_document():
    document = json.loads(METADATA_PATH.read_text(encoding='utf-8'))
    policy = json.loads(MISSION_POLICY_PATH.read_text(encoding='utf-8'))
    policy['sections']['reward_class_reviews'] = policy['sections'].pop(
        'act_reviews',
        policy['sections'].get('reward_class_reviews', {}),
    )
    manual_build_reviews = policy['sections'].get(
        'build_classification_reviews', {}
    )
    records = document['sections']['missions']
    for record in records:
        if 'reward_class' not in record:
            record['reward_class'] = record.pop('act_class', None)
        review = record.get('review', {})
        if 'reward_class' not in review:
            review['reward_class'] = review.pop(
                'act_class',
                'pending_review',
            )
    generated = build_metadata()['sections']['missions']
    installed_sections, _rules_source = read_rules_sections()
    generated_by_code = {record['code']: record for record in generated}
    records_by_code = {record['code']: record for record in records}
    failures = []
    promoted = {
        'relationships': [],
        'starting_force': [],
        'build_classification': [],
        'houses': [],
        'objectives': [],
        'difficulty_class': [],
        'reward_class': [],
    }

    finale_codes = campaign_finale_codes(records)
    policy['sections']['catalogue']['finale_mission_codes'] = [
        record['code'] for record in records
        if record['code'] in finale_codes
    ]
    policy['sections']['mission_reward_multipliers'] = (
        reviewed_mission_reward_policy(
            records,
            config=policy['sections'],
        )
    )

    for record in records:
        code = record['code']
        fresh = generated_by_code.get(code)
        if fresh is None:
            failures.append({'code': code, 'error': 'missing regenerated record'})
            continue
        source_path = resolve_installed_scenario(record['scenario'])
        source_hash = file_sha256(source_path)
        if source_hash != record['source_sha256'] or source_hash != fresh['source_sha256']:
            failures.append({'code': code, 'error': 'source hash changed'})
            continue

        source_fields = (
            'title',
            'faction',
            'campaign',
            'mission_number',
            'part',
            'part_count',
            'relationship',
            'player_house',
            'player_houses',
            'initial_allied_houses',
            'authored_houses',
            'starting_force',
        )
        if any(record[field] != fresh[field] for field in source_fields):
            failures.append({
                'code': code,
                'error': 'source-derived mission facts changed',
            })
            continue
        if not _relationship_is_proven(record, records_by_code):
            failures.append({'code': code, 'error': 'relationship is not proven'})
            continue

        if record['review']['relationships'] != 'verified':
            record['review']['relationships'] = 'verified'
            promoted['relationships'].append(code)
        if record['review']['starting_force'] != 'verified':
            record['review']['starting_force'] = 'verified'
            promoted['starting_force'].append(code)

        house_policy = mission_house_policy(code, config=policy['sections'])
        house_failures = mission_house_policy_failures(
            record,
            house_policy,
            installed_sections,
        )
        if house_failures:
            failures.extend(
                {'code': code, 'error': error} for error in house_failures
            )
        else:
            policy['sections']['house_policy_reviews'][code] = {
                'source_sha256': source_hash,
                'policy_sha256': house_policy_sha256(
                    code,
                    config=policy['sections'],
                ),
                'evidence': [
                    'Player Houses, initial alliances, and the authored House '
                    'registry were regenerated from the unchanged map source.',
                    'Optional helpers remain fail-closed; configured factory '
                    'and power exceptions passed Reloaded source checks.',
                ],
            }
            if record['review']['houses'] != 'verified':
                record['review']['houses'] = 'verified'
                promoted['houses'].append(code)

        objective_evidence = objective_completion_evidence(record)
        if objective_evidence['failures']:
            failures.extend(
                {'code': code, **failure}
                for failure in objective_evidence['failures']
            )
        else:
            objective_record = objective_review_record(record)
            policy['sections']['objective_reviews'][code] = objective_record
            record['expected_objective_count'] = objective_record[
                'expected_objective_count'
            ]
            if record['review']['objectives'] != 'verified':
                record['review']['objectives'] = 'verified'
                promoted['objectives'].append(code)

        difficulty_record = difficulty_review_record(
            record,
            config=policy['sections'],
        )
        policy['sections']['difficulty_reviews'][code] = difficulty_record
        record['difficulty_class'] = difficulty_record['difficulty_class']
        if record['review']['difficulty_class'] != 'verified':
            record['review']['difficulty_class'] = 'verified'
            promoted['difficulty_class'].append(code)

        reward_record = reward_review_record(
            record,
            config=policy['sections'],
        )
        policy['sections']['reward_class_reviews'][code] = reward_record
        record['reward_class'] = reward_record['reward_class']
        if record['review']['reward_class'] != 'verified':
            record['review']['reward_class'] = 'verified'
            promoted['reward_class'].append(code)

        evidence = record['starting_force']
        if (
            record['candidate_build_classification'] == 'base_build'
            and (
                evidence['has_initial_construction_yard']
                or evidence['has_initial_mobile_construction_unit']
            )
        ):
            record['build_classification'] = 'base_build'
            if record['review']['build_classification'] != 'verified':
                record['review']['build_classification'] = 'verified'
                promoted['build_classification'].append(code)
        elif (
            scripted_player_mcv_evidence(record, installed_sections)
            or any(
                evidence['construction_yard']
                for evidence in scripted_player_building_evidence(
                    record, installed_sections
                )
            )
            or any(
                evidence['construction_yard']
                or evidence['mobile_construction_unit']
                for evidence in scripted_player_object_transfer_evidence(
                    record, installed_sections
                )
            )
            or any(
                evidence['construction_yard']
                or evidence['mobile_construction_unit']
                for evidence in transferred_house_build_evidence(
                    record, installed_sections
                )
            )
        ):
            record['build_classification'] = 'base_build'
            if record['review']['build_classification'] != 'verified':
                record['review']['build_classification'] = 'verified'
                promoted['build_classification'].append(code)
        elif code in manual_build_reviews:
            record['build_classification'] = manual_build_reviews[code][
                'classification'
            ]
            if record['review']['build_classification'] != 'verified':
                record['review']['build_classification'] = 'verified'
                promoted['build_classification'].append(code)

    return document, {
        'mission_count': len(records),
        'promoted_counts': {
            key: len(values) for key, values in promoted.items()
        },
        'promoted_codes': promoted,
        'failures': failures,
        'valid': len(records) == 108 and not failures,
    }


def main():
    args = _arguments()
    document, report = reviewed_document()
    if args.write and report['valid']:
        policy = json.loads(
            MISSION_POLICY_PATH.read_text(encoding='utf-8')
        )
        policy['sections']['reward_class_reviews'] = policy['sections'].pop(
            'act_reviews',
            policy['sections'].get('reward_class_reviews', {}),
        )
        policy['sections']['house_policy_reviews'] = {
            record['code']: {
                'source_sha256': record['source_sha256'],
                'policy_sha256': house_policy_sha256(
                    record['code'],
                    config=policy['sections'],
                ),
                'evidence': [
                    'Player Houses, initial alliances, and the authored House '
                    'registry were regenerated from the unchanged map source.',
                    'Optional helpers remain fail-closed; configured factory '
                    'and power exceptions passed Reloaded source checks.',
                ],
            }
            for record in document['sections']['missions']
        }
        policy['sections']['objective_reviews'] = {
            record['code']: objective_review_record(record)
            for record in document['sections']['missions']
        }
        policy['sections']['objective_hook_action_ids'] = {
            code: review['action_checks']
            for code, review in policy['sections'][
                'objective_reviews'
            ].items()
            if review['action_checks']
        }
        finale_codes = campaign_finale_codes(
            document['sections']['missions']
        )
        policy['sections']['catalogue']['finale_mission_codes'] = [
            record['code'] for record in document['sections']['missions']
            if record['code'] in finale_codes
        ]
        policy['sections']['difficulty_reviews'] = {
            record['code']: difficulty_review_record(
                record,
                config=policy['sections'],
            )
            for record in document['sections']['missions']
        }
        policy['sections']['mission_reward_multipliers'] = (
            reviewed_mission_reward_policy(
                document['sections']['missions'],
                config=policy['sections'],
            )
        )
        policy['sections']['reward_class_reviews'] = {
            record['code']: reward_review_record(
                record,
                config=policy['sections'],
            )
            for record in document['sections']['missions']
        }
        METADATA_PATH.write_text(
            json.dumps(document, indent=2) + '\n',
            encoding='utf-8',
        )
        report['written'] = str(METADATA_PATH)
        if all(
            record['review']['build_classification'] == 'verified'
            for record in document['sections']['missions']
        ):
            policy['sections']['build_classifications'] = {
                record['code']: record['build_classification']
                for record in document['sections']['missions']
            }
            MISSION_POLICY_PATH.write_text(
                json.dumps(policy, indent=2) + '\n',
                encoding='utf-8',
            )
            report['mission_policy_written'] = str(MISSION_POLICY_PATH)
        else:
            report['mission_policy_written'] = None
    else:
        report['written'] = None
        report['mission_policy_written'] = None
    print(json.dumps(report, indent=2))
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
