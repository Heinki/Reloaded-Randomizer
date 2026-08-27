"""Validated access to Reloaded faction-content review metadata."""

from randomizer.config.static import load_static_config
from randomizer.content.inventory import read_rules_sections, rules_fingerprint


CONTENT_REVIEW = load_static_config(
    'rewards/reloaded_content_catalogue.json'
)


def _iter_reviews():
    content = CONTENT_REVIEW['content']
    groups = list(content['units'].values()) + [
        content['production'],
        content['defenses'],
        content['powers'],
    ]
    for records in groups:
        for record in records:
            for faction, review in record['reviews'].items():
                yield faction, record, review


def installed_content_review_report():
    """Verify catalogue provenance and summarize remaining manual review."""
    installed_sections, _source = read_rules_sections()
    actual_fingerprint = rules_fingerprint(installed_sections)
    configured_fingerprint = CONTENT_REVIEW['rules_fingerprint_sha256']
    approved_by_faction = {}
    for faction, _record, review in _iter_reviews():
        if review['status'] == 'approved':
            approved_by_faction[faction] = approved_by_faction.get(faction, 0) + 1
    return {
        'rules_fingerprint_matches': actual_fingerprint == configured_fingerprint,
        'configured_rules_fingerprint_sha256': configured_fingerprint,
        'installed_rules_fingerprint_sha256': actual_fingerprint,
        'review_summary': dict(CONTENT_REVIEW['review_summary']),
        'approved_by_faction': dict(sorted(approved_by_faction.items())),
        'review_complete': CONTENT_REVIEW['review_complete'],
        'gameplay_ready': (
            actual_fingerprint == configured_fingerprint
            and CONTENT_REVIEW['review_complete']
        ),
        'valid': actual_fingerprint == configured_fingerprint,
    }
