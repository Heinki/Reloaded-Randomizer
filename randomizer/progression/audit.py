"""Read-only validation of Reloaded mission progression topology."""

import json
from collections import Counter

from randomizer.config.game_profile import (
    CAMPAIGN_FACTIONS,
    OBJECTIVE_REWARDS_READY,
)
from randomizer.config.static import static_config_section
from randomizer.core.paths import BATTLE_INI
from randomizer.missions.catalogue import (
    OPENING_MISSION_EXCLUSIONS,
    parse_missions,
)
from randomizer.missions.metadata import MISSION_METADATA
from randomizer.missions.overrides import MISSION_OBJECTIVE_HOOK_ACTION_IDS


EXPECTED_FACTION_COUNTS = dict(Counter(m['faction'] for m in MISSION_METADATA))


def _validate_relationships(missions):
    by_code = {mission['code']: mission for mission in missions}
    failures = []
    kind_counts = Counter()
    for mission in missions:
        code = mission['code']
        relationship = mission.get('relationship') or {}
        kind = relationship.get('kind')
        related = relationship.get('related_codes')
        if kind not in {
            'standalone', 'sequential_parts', 'alternate_candidates',
        } or not isinstance(related, list):
            failures.append(f'{code}: invalid relationship record')
            continue
        kind_counts[kind] += 1
        for related_code in related:
            peer = by_code.get(related_code)
            if peer is None:
                failures.append(f'{code}: missing related mission {related_code}')
                continue
            peer_relationship = peer.get('relationship') or {}
            if (
                code not in peer_relationship.get('related_codes', ())
                or peer_relationship.get('series_key')
                != relationship.get('series_key')
            ):
                failures.append(
                    f'{code}: non-reciprocal relationship with {related_code}'
                )
    return dict(sorted(kind_counts.items())), failures


def progression_audit_report():
    """Validate installed mission relationships and progression metadata."""
    missions = parse_missions(BATTLE_INI)
    failures = []
    codes = [mission['code'] for mission in missions]
    faction_counts = Counter(mission['faction'] for mission in missions)
    if dict(faction_counts) != EXPECTED_FACTION_COUNTS:
        failures.append({
            'scope': 'catalogue',
            'error': 'active faction counts differ from reviewed profile',
            'actual': dict(faction_counts),
        })
    if len(codes) != len(MISSION_METADATA) or len(codes) != len(set(codes)):
        failures.append({
            'scope': 'catalogue',
            'error': 'mission codes differ from reviewed metadata or contain duplicates',
        })

    relationship_counts, relationship_failures = _validate_relationships(
        missions
    )
    failures.extend(
        {'scope': 'relationships', 'error': error}
        for error in relationship_failures
    )

    pools = {'All Campaigns': missions}
    pools.update({
        faction: [
            mission for mission in missions if mission['faction'] == faction
        ]
        for faction in CAMPAIGN_FACTIONS
    })
    defaults = static_config_section(
        'default_player_config.json', 'defaults', dict
    )
    objective_reviewed = sum(
        1 for mission in MISSION_METADATA
        if mission['review']['objectives'] == 'verified'
    )
    difficulty_reviewed = sum(
        1 for mission in MISSION_METADATA
        if mission['review']['difficulty_class'] == 'verified'
    )
    reward_reviewed = sum(
        1 for mission in MISSION_METADATA
        if mission['review']['reward_class'] == 'verified'
    )
    objective_hook_count = sum(
        len(mapping) for mapping in MISSION_OBJECTIVE_HOOK_ACTION_IDS.values()
    )
    victory_only_enforced = (
        not OBJECTIVE_REWARDS_READY
        and defaults['rewards_on_victory_only'] is True
    )
    objective_rewards_enabled = (
        OBJECTIVE_REWARDS_READY
        and defaults['rewards_on_victory_only'] is False
    )
    if not (victory_only_enforced or objective_rewards_enabled):
        failures.append({
            'scope': 'reward granularity',
            'error': (
                'objective reward defaults do not match the runtime gate'
            ),
        })
    if objective_reviewed != len(MISSION_METADATA):
        failures.append({
            'scope': 'objective review',
            'error': 'objective metadata review is incomplete',
        })
    if difficulty_reviewed != len(MISSION_METADATA):
        failures.append({
            'scope': 'difficulty review',
            'error': 'difficulty metadata review is incomplete',
        })
    if reward_reviewed != len(MISSION_METADATA):
        failures.append({
            'scope': 'reward review',
            'error': 'reward-class metadata review is incomplete',
        })

    return {
        'mission_count': len(missions),
        'faction_counts': dict(faction_counts),
        'pool_count': len(pools),
        'relationship_kind_counts': relationship_counts,
        'objective_reviewed_missions': objective_reviewed,
        'objective_review_complete': (
            objective_reviewed == len(MISSION_METADATA)
        ),
        'difficulty_reviewed_missions': difficulty_reviewed,
        'difficulty_review_complete': (
            difficulty_reviewed == len(MISSION_METADATA)
        ),
        'reward_reviewed_missions': reward_reviewed,
        'reward_review_complete': reward_reviewed == len(MISSION_METADATA),
        'opening_exclusion_count': len(OPENING_MISSION_EXCLUSIONS),
        'objective_hook_count': objective_hook_count,
        'objective_rewards_ready': OBJECTIVE_REWARDS_READY,
        'objective_rewards_enabled': objective_rewards_enabled,
        'victory_only_enforced': victory_only_enforced,
        'failures': failures,
        'valid': not failures,
    }


def main():
    report = progression_audit_report()
    print(json.dumps(report, indent=2))
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
