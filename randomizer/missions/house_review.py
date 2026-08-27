"""Fail-closed review of authored campaign House policy.

Mental Omega keeps helper, capture-production, and multi-house power exceptions
as explicit mission configuration. Reloaded follows that design without
copying Mental Omega mission data: every decision is bound to the installed
map hash and to a hash of its Reloaded-only policy.
"""

from hashlib import sha256
import json

from randomizer.config.static import load_static_config
from randomizer.content.inventory import read_rules_sections
from randomizer.maps.generated import file_sha256
from randomizer.maps.houses import (
    canonical_house_name,
    country_family,
    is_buffable_helper_house,
    map_house_records,
    player_controlled_houses,
)
from randomizer.maps.ini import IniLines, all_section_value_maps, read_text
from randomizer.maps.ownership import (
    build_unit_usage_index,
    player_transfer_houses,
    scripted_enemy_house_pairs,
)
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.missions.metadata import MISSION_METADATA
from randomizer.missions.production_review import (
    scripted_player_object_transfer_evidence,
)


_MISSION_CONFIG = load_static_config('missions.json')
_ACTIVE_FAMILIES = frozenset({'allies', 'soviets', 'yuri', 'gdi', 'nod'})


def mission_house_policy(code, config=None):
    """Return the complete policy payload whose digest is reviewed."""
    config = config or _MISSION_CONFIG
    code = str(code or '').upper()
    house_config = config['house_config'].get(code, {})
    return {
        'allies': list(house_config.get('allies', ())),
        'enemies': list(house_config.get('enemies', ())),
        'helper_buff_excluded_houses': list(
            config['helper_buff_excluded_houses'].get(code, ())
        ),
        'player_production_houses': list(
            config['player_production_houses'].get(code, ())
        ),
        'player_production_house_reviews': dict(
            config['player_production_house_reviews'].get(code, {})
        ),
        'player_power_houses': list(
            config['player_power_houses'].get(code, ())
        ),
    }


def house_policy_sha256(code, config=None):
    """Hash one normalized mission policy for review invalidation."""
    payload = json.dumps(
        mission_house_policy(code, config=config),
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return sha256(payload).hexdigest()


def _canonical_set(records, values):
    return {
        canonical.lower()
        for value in values
        if (canonical := canonical_house_name(records, value))
    }


def _used_house_names(lines, records):
    used = set()
    for owners in build_unit_usage_index(lines).values():
        for owner in owners:
            canonical = canonical_house_name(records, owner)
            if canonical:
                used.add(canonical.lower())
    return used


def _effective_values(type_id, installed_sections, map_sections):
    wanted = str(type_id or '').lower()
    values = {}
    for sections in (installed_sections, map_sections):
        section_name = next(
            (name for name in sections if str(name).lower() == wanted),
            None,
        )
        if section_name:
            values.update(sections[section_name])
    return {str(key).lower(): value for key, value in values.items()}


def _is_production_structure(type_id, installed_sections, map_sections):
    values = _effective_values(type_id, installed_sections, map_sections)
    return (
        str(values.get('constructionyard') or '').lower() == 'yes'
        or str(values.get('factory') or '').lower()
        not in {'', 'none', '<none>'}
    )


def mission_house_policy_failures(metadata, policy, installed_sections):
    source_path = resolve_installed_scenario(metadata['scenario'])
    lines = IniLines(read_text(source_path).splitlines())
    sections = all_section_value_maps(lines)
    records = map_house_records(lines, sections=sections)
    authored = {name.lower() for name in records}
    players = {
        name.lower()
        for name in player_controlled_houses(lines, records=records)
    }
    initial_allies = {
        name.lower() for name in metadata['initial_allied_houses']
    }
    used = _used_house_names(lines, records)
    hostile_pairs = scripted_enemy_house_pairs(lines, records=records)
    transferred = {
        name.lower()
        for name in player_transfer_houses(
            lines,
            records=records,
            scripted_enemies=hostile_pairs,
        )
    }
    action14_sources = {
        evidence['source_house'].lower()
        for evidence in scripted_player_object_transfer_evidence(
            metadata, installed_sections
        )
        if evidence.get('source_house')
    }
    failures = []

    for category in (
        'allies',
        'enemies',
        'helper_buff_excluded_houses',
        'player_production_houses',
        'player_power_houses',
    ):
        values = policy[category]
        if len(values) != len({str(value).lower() for value in values}):
            failures.append(f'{category} contains duplicates')
        missing = [
            value for value in values
            if not canonical_house_name(records, value)
        ]
        if missing:
            failures.append(
                f'{category} contains missing Houses: {", ".join(missing)}'
            )

    allies = _canonical_set(records, policy['allies'])
    enemies = _canonical_set(records, policy['enemies'])
    exclusions = _canonical_set(
        records, policy['helper_buff_excluded_houses']
    )
    production = _canonical_set(
        records, policy['player_production_houses']
    )
    direct_capture_reviews = policy['player_production_house_reviews']
    power = _canonical_set(records, policy['player_power_houses'])

    for house in sorted(allies):
        name = next(name for name in records if name.lower() == house)
        record = records[name]
        if house in players:
            failures.append(f'allied helper {name} is player-controlled')
        if house not in initial_allies:
            failures.append(f'allied helper {name} is not initially allied')
        if house not in used:
            failures.append(f'allied helper {name} has no authored usage')
        if not is_buffable_helper_house(record):
            failures.append(f'allied helper {name} is neutral/cinematic')
        if country_family(record) not in _ACTIVE_FAMILIES:
            failures.append(f'allied helper {name} is outside active factions')
        if house in transferred:
            failures.append(f'allied helper {name} transfers to the player')
        if any(
            frozenset((house, player)) in hostile_pairs
            for player in players
        ):
            failures.append(f'allied helper {name} becomes player-hostile')
        if house in enemies:
            failures.append(f'{name} is both allied helper and enemy')

    if not exclusions.issubset(allies):
        failures.append('helper exclusions are not a subset of allied helpers')
    for house in sorted(production):
        name = next(name for name in records if name.lower() == house)
        if house in players:
            failures.append(f'production source {name} is player-controlled')
        direct_review = direct_capture_reviews.get(name)
        if house not in action14_sources and not direct_review:
            failures.append(
                f'production source {name} lacks transfer/capture proof'
            )
        if direct_review:
            reviewed_types = {
                str(type_id).upper()
                for type_id in direct_review.get('structure_ids', ())
            }
            authored_types = {
                tokens[1].upper()
                for value in sections.get('Structures', {}).values()
                if len(tokens := [
                    token.strip() for token in str(value).split(',')
                ]) >= 2
                and canonical_house_name(records, tokens[0]).lower() == house
            }
            if not reviewed_types or not reviewed_types.issubset(authored_types):
                failures.append(
                    f'direct-capture assets for {name} are not authored'
                )
            elif any(
                not _is_production_structure(
                    type_id, installed_sections, sections
                )
                for type_id in reviewed_types
            ):
                failures.append(
                    f'direct-capture assets for {name} are not factories'
                )
        if house in allies:
            failures.append(f'production source {name} is a reward helper')
    for house in sorted(power):
        name = next(name for name in records if name.lower() == house)
        if house not in players:
            failures.append(f'power recipient {name} is not PlayerControl')
    reviewed_production_names = {
        canonical.lower()
        for value in direct_capture_reviews
        if (canonical := canonical_house_name(records, value))
    }
    if not reviewed_production_names.issubset(production):
        failures.append('direct-capture review is outside production sources')
    for house in sorted(enemies):
        name = next(name for name in records if name.lower() == house)
        if house in players:
            failures.append(f'enemy {name} is player-controlled')
    if not players:
        failures.append('map has no source-derived player House')
    if not players.issubset(authored):
        failures.append('source-derived player House is absent from registry')
    return failures


def house_review_report(config=None):
    """Validate all reviewed Reloaded House decisions against source maps."""
    config = config or _MISSION_CONFIG
    installed_sections, rules_source = read_rules_sections()
    reviews = config.get('house_policy_reviews', {})
    expected_codes = {metadata['code'] for metadata in MISSION_METADATA}
    failures = []
    details = []

    missing_reviews = sorted(expected_codes - set(reviews))
    extra_reviews = sorted(set(reviews) - expected_codes)
    if missing_reviews:
        failures.append({
            'error': 'missing house-policy reviews',
            'codes': missing_reviews,
        })
    if extra_reviews:
        failures.append({
            'error': 'unknown house-policy reviews',
            'codes': extra_reviews,
        })

    for metadata in MISSION_METADATA:
        code = metadata['code']
        review = reviews.get(code)
        if review is None:
            continue
        source_path = resolve_installed_scenario(metadata['scenario'])
        actual_source_hash = file_sha256(source_path)
        actual_policy_hash = house_policy_sha256(code, config=config)
        errors = []
        if review.get('source_sha256') != actual_source_hash:
            errors.append('review source hash does not match installed map')
        if review.get('policy_sha256') != actual_policy_hash:
            errors.append('review policy hash is stale')
        evidence = review.get('evidence')
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(not isinstance(item, str) or not item for item in evidence)
        ):
            errors.append('review evidence is missing')
        errors.extend(
            mission_house_policy_failures(
                metadata,
                mission_house_policy(code, config=config),
                installed_sections,
            )
        )
        details.append({
            'code': code,
            'policy': mission_house_policy(code, config=config),
            'errors': errors,
        })
        failures.extend(
            {'code': code, 'error': error} for error in errors
        )

    return {
        'mission_count': len(MISSION_METADATA),
        'reviewed_mission_count': len(expected_codes.intersection(reviews)),
        'rules_source': str(rules_source),
        'configured_helper_mission_count': sum(
            bool(detail['policy']['allies']) for detail in details
        ),
        'configured_production_mission_count': sum(
            bool(detail['policy']['player_production_houses'])
            for detail in details
        ),
        'configured_power_mission_count': sum(
            bool(detail['policy']['player_power_houses'])
            for detail in details
        ),
        'details': details,
        'failures': failures,
        'valid': len(details) == len(MISSION_METADATA) and not failures,
    }


def main():
    report = house_review_report()
    print(json.dumps(report, indent=2))
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
