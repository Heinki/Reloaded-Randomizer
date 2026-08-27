"""Mission catalogue parsing and deterministic seed-order construction.

This module deliberately contains no Tk state.  Keeping mission discovery and
ordering pure makes seed compatibility testable without starting the launcher.
"""

import re

from randomizer.config.game_profile import (
    CAMPAIGN_FILTER_BY_LABEL,
    CAMPAIGN_FACTIONS_BY_NAME,
    FACTION_ALIASES,
    FACTION_ORDER as PROFILE_FACTION_ORDER,
)
from randomizer.config.static import load_static_config
from randomizer.missions.metadata import MISSION_METADATA_BY_CODE


_MISSION_CONFIG = load_static_config('missions.json')
_MISSION_CATALOGUE = _MISSION_CONFIG['catalogue']
_MISSION_REWARD_CONFIG = _MISSION_CONFIG['mission_reward_multipliers']


FACTION_ORDER = tuple(PROFILE_FACTION_ORDER)
MISSION_CAMPAIGN_PREFIXES = {
    'Red Alert 2': 'RA2',
    "Yuri's Revenge": 'YR',
    'Tiberian Sun': 'TIB',
    'Firestorm': 'FIRE',
}
FALLBACK_OBJECTIVE_COUNT = int(_MISSION_CATALOGUE['fallback_objective_count'])
STARTING_UNLOCKED_MISSIONS = int(_MISSION_CATALOGUE['starting_unlocked_missions'])
LOW_LEVEL_MISSION_COUNT = int(_MISSION_CATALOGUE['low_level_mission_count'])
LOW_LEVEL_STAGE_MAX = int(_MISSION_CATALOGUE['low_level_stage_max'])
OPERATION_STAGE_SCORE = int(_MISSION_CATALOGUE['operation_stage_score'])
FALLBACK_STAGE_SCORE = int(_MISSION_CATALOGUE['fallback_stage_score'])
FINALE_STAGE_SCORE = int(_MISSION_CATALOGUE['finale_stage_score'])
FINALE_MISSION_CODES = frozenset(_MISSION_CATALOGUE['finale_mission_codes'])
OPERATION_MISSION_CODES = frozenset(_MISSION_CATALOGUE['operation_mission_codes'])

MISSION_REWARD_CLASS_MULTIPLIERS = {
    str(class_name): int(multiplier)
    for class_name, multiplier in _MISSION_REWARD_CONFIG[
        'class_multipliers'
    ].items()
}
MISSION_REWARD_CLASS_BY_CODE = {
    str(code).upper(): str(class_name)
    for class_name, codes in _MISSION_REWARD_CONFIG['mission_classes'].items()
    for code in codes
}
MISSION_REWARD_MULTIPLIER_OVERRIDES = {
    str(code).upper(): int(multiplier)
    for code, multiplier in _MISSION_REWARD_CONFIG.get(
        'mission_overrides', {}
    ).items()
}
DEFAULT_MISSION_REWARD_MULTIPLIER = int(
    _MISSION_REWARD_CONFIG['default_multiplier']
)

BASE_BUILD = 'base_build'
TRUE_NO_BUILD = 'true_no_build'
NO_BUILD_PRODUCTION = 'no_build_production'

# All C&C Reloaded classifications are source-hash-bound reviewed policy.
MISSION_BUILD_CLASSIFICATIONS = dict(_MISSION_CONFIG['build_classifications'])

TRUE_NO_BUILD_MISSION_CODES = frozenset(
    code for code, classification in MISSION_BUILD_CLASSIFICATIONS.items()
    if classification == TRUE_NO_BUILD
)
NO_BUILD_PRODUCTION_MISSION_CODES = frozenset(
    code for code, classification in MISSION_BUILD_CLASSIFICATIONS.items()
    if classification == NO_BUILD_PRODUCTION
)
NO_BUILD_MISSION_CODES = frozenset(
    TRUE_NO_BUILD_MISSION_CODES | NO_BUILD_PRODUCTION_MISSION_CODES
)

# Backward-compatible boolean view for older integrations. ``True`` means the
# mission belongs to either non-base-building category.
NO_BUILD_MISSION_FLAGS = {
    code: classification != BASE_BUILD
    for code, classification in MISSION_BUILD_CLASSIFICATIONS.items()
}

# Only source-bound Reloaded ``opening`` classifications may occupy protected
# opening slots. Narrow custom pools can still use the existing fallback.
OPENING_MISSION_EXCLUSIONS = frozenset(
    mission['code'] for mission in MISSION_METADATA_BY_CODE.values()
    if mission.get('difficulty_class') != 'opening'
)


def mission_reward_class(code):
    return MISSION_REWARD_CLASS_BY_CODE.get(str(code or '').upper(), '')


def mission_reward_multiplier(code):
    code = str(code or '').upper()
    if code in MISSION_REWARD_MULTIPLIER_OVERRIDES:
        return MISSION_REWARD_MULTIPLIER_OVERRIDES[code]
    class_name = MISSION_REWARD_CLASS_BY_CODE.get(code)
    return MISSION_REWARD_CLASS_MULTIPLIERS.get(
        class_name,
        DEFAULT_MISSION_REWARD_MULTIPLIER,
    )


def normalize_faction(side):
    side = (side or '').strip().lower()
    direct = FACTION_ALIASES.get(side)
    if direct:
        return direct
    for alias, faction in FACTION_ALIASES.items():
        if alias in side:
            return faction
    return ''


def mission_display_title(mission):
    """Return a mission title prefixed by its original campaign."""
    title = str(
        mission.get('title') or mission.get('code') or 'Mission'
    ).strip()
    prefix = MISSION_CAMPAIGN_PREFIXES.get(
        str(mission.get('campaign') or '').strip()
    )
    return f'[{prefix}] {title}' if prefix else title


def campaign_filter_factions(selected):
    """Return active faction represented by one exact campaign choice."""
    selected = str(selected or '')
    if selected == 'All Campaigns':
        return frozenset(FACTION_ORDER)
    spec = CAMPAIGN_FILTER_BY_LABEL.get(selected)
    if spec:
        return frozenset({spec['faction']})
    # Legacy values remain readable for old settings files. They are no
    # longer presented by the launcher because their campaign is ambiguous.
    if selected in FACTION_ORDER:
        return frozenset({selected})
    return frozenset(CAMPAIGN_FACTIONS_BY_NAME.get(selected, ()))


def mission_matches_campaign_filter(mission, selected):
    """Match one exact faction/campaign pair or every active mission."""
    selected = str(selected or '')
    if selected == 'All Campaigns':
        return True
    spec = CAMPAIGN_FILTER_BY_LABEL.get(selected)
    if spec:
        return (
            mission.get('campaign') == spec['campaign']
            and mission.get('faction') == spec['faction']
        )
    # Backward compatibility for imported settings created before exact
    # faction/campaign labels were introduced.
    if selected in CAMPAIGN_FACTIONS_BY_NAME:
        return mission.get('campaign') == selected
    return (
        mission.get('faction') == selected
        or normalize_faction(mission.get('side', '')) == selected
    )


def filter_missions_by_build_settings(
    missions,
    include_true_no_build=True,
    include_no_build_production=True,
    include_operation_missions=True,
):
    """Apply independent no-build and optional-operation pool settings."""
    excluded = set()
    if not include_true_no_build:
        excluded.add(TRUE_NO_BUILD)
    if not include_no_build_production:
        excluded.add(NO_BUILD_PRODUCTION)
    return [
        mission for mission in missions
        if mission.get('build_classification', BASE_BUILD) not in excluded
        and (
            include_operation_missions
            or mission.get('code', '').upper() not in OPERATION_MISSION_CODES
        )
    ]


def parse_long_description_objectives(text):
    if not text:
        return []
    objectives = []
    for part in text.split('@'):
        match = re.match(r'\s*Objective\s+(\d+)\s*:\s*(.+?)\s*$', part, flags=re.IGNORECASE)
        if match:
            objectives.append(match.group(2).strip())
    return objectives


def parse_missions(path, fallback_objective_count=FALLBACK_OBJECTIVE_COUNT):
    """Read the ordered campaign catalogue from C&C Reloaded ``Battle.ini``."""
    if not path.exists():
        return []

    lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()
    mission_codes = []
    seen_codes = set()
    sections = {}
    current_section = None
    in_battles = False

    for line in lines:
        no_comment = line.split(';', 1)[0].strip()
        if not no_comment:
            continue
        if no_comment.startswith('[') and no_comment.endswith(']'):
            current_section = no_comment[1:-1].strip()
            in_battles = current_section == 'Battles'
            sections.setdefault(current_section, {})
            continue
        if in_battles and '=' in no_comment:
            _, value = no_comment.split('=', 1)
            code = value.strip()
            if code and code not in seen_codes:
                mission_codes.append(code)
                seen_codes.add(code)
            continue
        if current_section and '=' in no_comment:
            key, value = no_comment.split('=', 1)
            sections.setdefault(current_section, {})[key.strip()] = value.strip()

    missions = []
    for code in mission_codes:
        section = sections.get(code, {})
        scenario = section.get('Scenario') or section.get('SCENARIO')
        if not scenario:
            continue
        position = len(missions) + 1
        metadata = MISSION_METADATA_BY_CODE.get(code.upper(), {})
        objectives = parse_long_description_objectives(section.get('LongDescription', ''))
        reviewed_build_classification = metadata.get('build_classification')
        build_classification = (
            reviewed_build_classification
            if reviewed_build_classification in {
                BASE_BUILD, TRUE_NO_BUILD, NO_BUILD_PRODUCTION,
            }
            else MISSION_BUILD_CLASSIFICATIONS.get(code, BASE_BUILD)
        )
        expected_objective_count = metadata.get('expected_objective_count')
        missions.append({
            'index': position,
            'code': code,
            'scenario': scenario,
            'title': section.get('Description') or section.get('description') or code,
            'side': section.get('SideName') or section.get('Side') or '',
            'faction': metadata.get('faction') or normalize_faction(
                section.get('SideName') or section.get('Side') or ''
            ),
            'campaign': metadata.get('campaign', ''),
            'campaign_order': metadata.get('campaign_order', position),
            'mission_number': metadata.get('mission_number'),
            'part': metadata.get('part'),
            'part_count': metadata.get('part_count'),
            'difficulty_class': metadata.get('difficulty_class'),
            'reward_class': metadata.get('reward_class'),
            'relationship': dict(metadata.get('relationship', {})),
            'metadata_review': dict(metadata.get('review', {})),
            'source_sha256': metadata.get('source_sha256', ''),
            'player_house': metadata.get('player_house', ''),
            'player_houses': list(metadata.get('player_houses', ())),
            'candidate_terminal_actions': list(
                metadata.get('candidate_terminal_actions', ())
            ),
            'verified_victory_action_ids': list(
                metadata.get('verified_victory_action_ids', ())
            ),
            'objectives': objectives,
            'objective_count': (
                expected_objective_count
                if isinstance(expected_objective_count, int)
                else len(objectives) or fallback_objective_count
            ),
            'build_classification': build_classification,
            'candidate_build_classification': metadata.get(
                'candidate_build_classification'
            ),
            'build_classification_reviewed': (
                reviewed_build_classification is not None
            ),
            'no_build': build_classification != BASE_BUILD,
            'true_no_build': build_classification == TRUE_NO_BUILD,
            'no_build_production': (
                build_classification == NO_BUILD_PRODUCTION
            ),
            'operation': code in OPERATION_MISSION_CODES,
            'reward_class': mission_reward_class(code),
            'reward_multiplier': mission_reward_multiplier(code),
        })
    return missions


def mission_stage_score(mission):
    code = str(mission.get('code', '') or '').upper()
    mission_number = mission.get('mission_number')
    if code in OPERATION_MISSION_CODES:
        score = OPERATION_STAGE_SCORE
    elif (
        isinstance(mission_number, int)
        and not isinstance(mission_number, bool)
    ):
        score = mission_number
    elif (
        isinstance(mission.get('campaign_order'), int)
        and not isinstance(mission.get('campaign_order'), bool)
    ):
        score = mission['campaign_order']
    else:
        score = int(mission.get('index') or FALLBACK_STAGE_SCORE)
    if code in FINALE_MISSION_CODES:
        score = max(score, FINALE_STAGE_SCORE)
    return score


def campaign_mission_counts(missions):
    counts = {faction: 0 for faction in FACTION_ORDER}
    for mission in missions:
        faction = normalize_faction(mission.get('side', ''))
        if faction in counts:
            counts[faction] += 1
    return {faction: count for faction, count in counts.items() if count}


def seed_campaign_limits(missions, mission_goal):
    """Return installed per-faction capacities for mixed Reloaded seeds."""
    return dict(campaign_mission_counts(missions))


def classic_mission_order(missions, mission_goal):
    """Return the requested missions in installed campaign-catalogue order."""
    missions = list(missions)
    if not missions:
        return []
    mission_goal = max(1, min(mission_goal, len(missions)))
    return [mission['code'] for mission in missions[:mission_goal]]


def seed_mission_order(
    missions,
    rng,
    mission_goal,
    low_level_count=LOW_LEVEL_MISSION_COUNT,
    preferred_opening_codes=None,
    excluded_opening_codes=None,
):
    """Return the requested low-level opening, then an unrestricted shuffle."""
    missions = list(missions)
    if not missions:
        return []
    mission_goal = max(1, min(mission_goal, len(missions)))
    campaign_limits = seed_campaign_limits(missions, mission_goal)
    picked_by_faction = {faction: 0 for faction in campaign_limits}

    def bucket(mission):
        score = mission_stage_score(mission)
        return 0 if score <= LOW_LEVEL_STAGE_MAX else 1 if score <= 16 else 2 if score < 24 else 3

    def shuffled(items):
        items = list(items)
        rng.shuffle(items)
        return items

    opening_count = min(max(0, int(low_level_count)), mission_goal)
    preferred_opening_codes = set(preferred_opening_codes or ())
    excluded_opening_codes = set(excluded_opening_codes or ())

    picked_codes = set()
    ordered = []

    def add_mission(mission):
        faction = normalize_faction(mission.get('side', ''))
        if (
            mission['code'] in picked_codes
            or picked_by_faction.get(faction, 0) >= campaign_limits.get(faction, len(missions))
        ):
            return False
        ordered.append(mission)
        picked_codes.add(mission['code'])
        picked_by_faction[faction] = picked_by_faction.get(faction, 0) + 1
        return True

    # Optional no-build preference still respects stage buckets: easier fixed-
    # unit missions win before late/finale no-build missions. Reviewed opening
    # exclusions remain authoritative.
    if preferred_opening_codes and opening_count:
        for bucket_index in range(4):
            bucket_missions = (
                mission for mission in missions
                if mission['code'] in preferred_opening_codes
                and mission['code'] not in excluded_opening_codes
                and bucket(mission) == bucket_index
            )
            for mission in shuffled(bucket_missions):
                if add_mission(mission) and len(ordered) >= opening_count:
                    break
            if len(ordered) >= opening_count:
                break

    # Keep only the opening approachable. The installed catalogue has enough
    # missions 1-6 for all campaign filters; later buckets are a defensive
    # fallback for custom or incomplete catalogues.
    for bucket_index in range(4) if len(ordered) < opening_count else ():
        bucket_missions = (
            mission for mission in missions
            if mission['code'] not in excluded_opening_codes
            and bucket(mission) == bucket_index
        )
        for mission in shuffled(bucket_missions):
            if add_mission(mission) and len(ordered) >= opening_count:
                break
        if len(ordered) >= opening_count:
            break

    # A narrow custom/campaign-only pool may contain too few safe opening maps.
    # Fill from excluded maps only when otherwise impossible to reach requested
    # opening size; mixed installed campaigns never need this fallback.
    if len(ordered) < opening_count:
        for bucket_index in range(4):
            bucket_missions = (
                mission for mission in missions
                if mission['code'] in excluded_opening_codes
                and bucket(mission) == bucket_index
            )
            for mission in shuffled(bucket_missions):
                if add_mission(mission) and len(ordered) >= opening_count:
                    break
            if len(ordered) >= opening_count:
                break
    if len(ordered) >= mission_goal:
        return [item['code'] for item in ordered]

    # Everything after the protected opening is equally eligible. Finales can
    # therefore appear in the first unprotected slot.
    for mission in shuffled(missions):
        if add_mission(mission) and len(ordered) >= mission_goal:
            break
    return [item['code'] for item in ordered]
