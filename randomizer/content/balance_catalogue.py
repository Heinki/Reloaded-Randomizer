"""Validated access to Reloaded buff-target and superweapon review facts."""

from collections import Counter

from randomizer.config.static import load_static_config
from randomizer.content.inventory import read_rules_sections, rules_fingerprint


BALANCE_REVIEW = load_static_config('rewards/reloaded_balance_catalogue.json')


def installed_balance_review_report():
    """Verify balance catalogue provenance and summarize review hazards."""
    installed_sections, _source = read_rules_sections()
    actual_fingerprint = rules_fingerprint(installed_sections)
    configured_fingerprint = BALANCE_REVIEW['rules_fingerprint_sha256']
    registered_powers = [
        value for value in installed_sections.get('SuperWeaponTypes', {}).values()
        if value
    ]
    reviewed_power_total = (
        len(BALANCE_REVIEW['powers']) + BALANCE_REVIEW['deferred_power_count']
    )
    target_flags = Counter(
        flag
        for record in BALANCE_REVIEW['buff_targets']
        for flag in record['review']['flags']
    )
    power_flags = Counter(
        flag
        for record in BALANCE_REVIEW['powers']
        for flag in record['review']['flags']
    )
    missing_target_sections = [
        record['id']
        for record in BALANCE_REVIEW['buff_targets']
        if record['id'] not in installed_sections
    ]
    valid = (
        actual_fingerprint == configured_fingerprint
        and BALANCE_REVIEW['active_factions']
        == ['Allies', 'Soviets', 'Yuri', 'GDI', 'Nod']
        and BALANCE_REVIEW['deferred_factions'] == ['CABAL']
        and reviewed_power_total == len(registered_powers)
        and not missing_target_sections
    )
    return {
        'rules_fingerprint_matches': actual_fingerprint == configured_fingerprint,
        'buff_target_count': len(BALANCE_REVIEW['buff_targets']),
        'registered_power_count': len(registered_powers),
        'reviewed_power_count': len(BALANCE_REVIEW['powers']),
        'deferred_power_count': BALANCE_REVIEW['deferred_power_count'],
        'shared_weapon_target_count': target_flags.get(
            'shared_weapon_requires_clone', 0
        ),
        'missing_weapon_section_target_count': target_flags.get(
            'missing_weapon_section', 0
        ),
        'power_flag_counts': dict(sorted(power_flags.items())),
        'missing_target_sections': missing_target_sections,
        'review_summary': dict(BALANCE_REVIEW['review_summary']),
        'review_complete': BALANCE_REVIEW['review_complete'],
        'gameplay_ready': valid and BALANCE_REVIEW['review_complete'],
        'valid': valid,
    }
