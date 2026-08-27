"""Read-only validation of Reloaded mission progression topology."""

import json
import random
from collections import Counter

from randomizer.config.game_profile import (
    CAMPAIGN_FACTIONS,
    OBJECTIVE_REWARDS_READY,
)
from randomizer.config.static import static_config_section
from randomizer.core.paths import BATTLE_INI
from randomizer.missions.catalogue import (
    LOW_LEVEL_MISSION_COUNT,
    OPENING_MISSION_EXCLUSIONS,
    classic_mission_order,
    parse_missions,
    seed_mission_order,
)
from randomizer.missions.metadata import MISSION_METADATA
from randomizer.missions.overrides import MISSION_OBJECTIVE_HOOK_ACTION_IDS
from randomizer.progression.grid import (
    COMPLETED,
    UNLOCKED,
    create_grid,
    is_complete,
    refresh_states,
    starting_nodes,
)


EXPECTED_FACTION_COUNTS = {
    'Allies': 19,
    'Soviets': 19,
    'Yuri': 13,
    'GDI': 30,
    'Nod': 27,
}
AUDIT_SEEDS = ('RLR-PROGRESSION-0', 'RLR-PROGRESSION-1')


def _simulate_grid(grid):
    completed = []
    while len(completed) < len(grid['nodes']):
        states = refresh_states(grid, completed)
        available = sorted(
            code for code, state in states.items()
            if state == UNLOCKED and code not in completed
        )
        if not available:
            break
        completed.append(available[0])
    states = refresh_states(grid, completed)
    return completed, states


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
    """Validate Classic, Mission List, and Grid over every active pool."""
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
    if len(codes) != 108 or len(codes) != len(set(codes)):
        failures.append({
            'scope': 'catalogue',
            'error': 'mission codes are not 108 unique entries',
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
    mode_checks = 0
    grid_checks = 0
    for pool_name, pool in pools.items():
        pool_codes = [mission['code'] for mission in pool]
        if classic_mission_order(pool, len(pool)) != pool_codes:
            failures.append({
                'scope': pool_name,
                'error': 'Classic order differs from installed catalogue',
            })
        else:
            mode_checks += 1

        for seed in AUDIT_SEEDS:
            first = seed_mission_order(
                pool,
                random.Random(seed),
                len(pool),
                excluded_opening_codes=OPENING_MISSION_EXCLUSIONS,
            )
            second = seed_mission_order(
                pool,
                random.Random(seed),
                len(pool),
                excluded_opening_codes=OPENING_MISSION_EXCLUSIONS,
            )
            if first != second or set(first) != set(pool_codes):
                failures.append({
                    'scope': pool_name,
                    'seed': seed,
                    'error': 'Mission List order is not deterministic and complete',
                })
                continue
            mode_checks += 1
            opening_codes = set(first[:min(LOW_LEVEL_MISSION_COUNT, len(first))])
            unsafe_openings = sorted(
                opening_codes.intersection(OPENING_MISSION_EXCLUSIONS)
            )
            if unsafe_openings:
                failures.append({
                    'scope': pool_name,
                    'seed': seed,
                    'error': 'protected opening contains reviewed later mission',
                    'codes': unsafe_openings,
                })

            for two_starts in (False, True):
                try:
                    grid = create_grid(
                        first,
                        two_start_positions=two_starts,
                        protect_opening=True,
                    )
                    completed, states = _simulate_grid(grid)
                except Exception as exc:
                    failures.append({
                        'scope': pool_name,
                        'seed': seed,
                        'two_starts': two_starts,
                        'error': str(exc),
                    })
                    continue
                expected_starts = 2 if two_starts else 1
                if (
                    len(starting_nodes(grid)) != expected_starts
                    or len(completed) != len(first)
                    or set(grid['nodes']) != set(first)
                    or any(state != COMPLETED for state in states.values())
                    or not is_complete(grid)
                ):
                    failures.append({
                        'scope': pool_name,
                        'seed': seed,
                        'two_starts': two_starts,
                        'error': 'Grid is incomplete, unreachable, or has bad starts',
                    })
                    continue
                grid_checks += 1

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
        'classic_and_mission_list_checks': mode_checks,
        'grid_checks': grid_checks,
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
