"""Validated access to Reloaded production topology review metadata."""

from randomizer.config.static import load_static_config
from randomizer.content.inventory import read_rules_sections, rules_fingerprint
from randomizer.maps.houses import country_family, map_house_records, player_house_from_map
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.missions.metadata import MISSION_METADATA


PRODUCTION_TOPOLOGY = load_static_config('production_topology.json')


def installed_production_topology_report():
    """Check source provenance and report pending five-faction review."""
    installed_sections, _source = read_rules_sections()
    actual_fingerprint = rules_fingerprint(installed_sections)
    configured_fingerprint = PRODUCTION_TOPOLOGY['rules_fingerprint_sha256']
    source_validation = PRODUCTION_TOPOLOGY['source_validation']
    review_status = {
        family: values['review']['status']
        for family, values in PRODUCTION_TOPOLOGY['families'].items()
    }
    mission_family_failures = []
    for mission in MISSION_METADATA:
        path = resolve_installed_scenario(mission['scenario'])
        lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()
        records = map_house_records(lines)
        player_house = player_house_from_map(lines, records=records)
        actual_family = country_family(records.get(player_house, {}))
        expected_family = str(mission['faction']).lower()
        if actual_family != expected_family:
            mission_family_failures.append({
                'code': mission['code'],
                'player_house': player_house,
                'expected': expected_family,
                'actual': actual_family,
            })
    valid = (
        actual_fingerprint == configured_fingerprint
        and source_validation['valid']
        and not source_validation['failures']
        and PRODUCTION_TOPOLOGY['active_families']
        == ['allies', 'soviets', 'yuri', 'gdi', 'nod']
        and PRODUCTION_TOPOLOGY['deferred_factions'] == ['CABAL']
        and not mission_family_failures
    )
    return {
        'rules_fingerprint_matches': actual_fingerprint == configured_fingerprint,
        'configured_rules_fingerprint_sha256': configured_fingerprint,
        'installed_rules_fingerprint_sha256': actual_fingerprint,
        'source_validation': dict(source_validation),
        'review_status': review_status,
        'review_complete': PRODUCTION_TOPOLOGY['review_complete'],
        'mission_family_checks': len(MISSION_METADATA),
        'mission_family_failures': mission_family_failures,
        'gameplay_ready': valid and PRODUCTION_TOPOLOGY['review_complete'],
        'valid': valid,
    }
