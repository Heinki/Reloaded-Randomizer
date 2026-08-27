"""Read-only authored-identity audit for every active Reloaded mission."""

from collections import Counter

from randomizer.content.inventory import read_rules_sections
from randomizer.maps.identity_safety import (
    capture_authored_identity_contract,
    validate_authored_identity_contract,
)
from randomizer.maps.ini import IniLines, read_text
from randomizer.missions.installation import (
    installed_mission_catalogue,
    resolve_installed_scenario,
)


def installed_identity_report():
    """Capture and self-validate identity contracts for active missions."""
    installed_sections, rules_source = read_rules_sections()
    missions = installed_mission_catalogue()
    failures = []
    protected_counts = Counter()
    positioned_total = 0
    record_total = 0
    maps_with_positioned_references = 0
    details = []

    for mission in missions:
        path = resolve_installed_scenario(mission['scenario'])
        try:
            lines = IniLines(read_text(path).splitlines())
            contract = capture_authored_identity_contract(
                lines, installed_sections
            )
            validation = validate_authored_identity_contract(contract, lines)
        except Exception as exc:
            failures.append({
                'code': mission['code'],
                'scenario': mission['scenario'],
                'error': str(exc),
            })
            continue

        protected_counts.update(contract.protected_type_ids)
        positioned_total += validation['positioned_reference_count']
        record_total += validation['record_reference_count']
        if validation['positioned_reference_count']:
            maps_with_positioned_references += 1
        details.append({
            'code': mission['code'],
            'protected_types': validation['protected_type_count'],
            'positioned_references': validation[
                'positioned_reference_count'
            ],
            'authored_records': validation['record_reference_count'],
        })

    return {
        'rules_source': rules_source,
        'mission_count': len(missions),
        'audited_missions': len(details),
        'maps_with_positioned_references': maps_with_positioned_references,
        'unique_protected_types': len(protected_counts),
        'positioned_references': positioned_total,
        'authored_records': record_total,
        'failures': failures,
        'valid': len(details) == len(missions) and not failures,
    }
