"""Read-only C&C Reloaded installation audit for port development."""

import json

from Archipelago.audit import archipelago_foundation_report
from randomizer.config.game_profile import (
    ENABLE_ADVANCED_GAMEPLAY,
    ENABLE_ARCHIPELAGO,
    ENABLE_SHOP_MODE,
    FOUNDATION_ONLY,
    GAMEPLAY_CATALOGUES_READY,
    OBJECTIVE_REWARDS_READY,
    SUPPORTED_GAME_VERSION,
)
from randomizer.content.inventory import inventory_report
from randomizer.content.review_catalogue import installed_content_review_report
from randomizer.content.production_topology import installed_production_topology_report
from randomizer.content.balance_catalogue import installed_balance_review_report
from randomizer.missions.installation import installation_catalogue_report
from randomizer.missions.identity_audit import installed_identity_report
from randomizer.missions.hook_audit import progress_hook_audit_report
from randomizer.missions.house_review import house_review_report
from randomizer.missions.difficulty_review import difficulty_review_report
from randomizer.missions.reward_review import reward_review_report
from randomizer.missions.metadata import installed_metadata_report
from randomizer.missions.objective_review import objective_review_report
from randomizer.missions.production_review import production_review_report
from randomizer.progression.audit import progression_audit_report
from randomizer.shop.self_check import validate_shop_domain
from randomizer.ui.reloaded_profile import installed_ui_profile_report
from randomizer.validation.release import release_validation_report


def installation_report():
    """Combine catalogue and rules inventory without changing game files."""
    missions = installation_catalogue_report()
    content = inventory_report()
    content_review = installed_content_review_report()
    production_topology = installed_production_topology_report()
    balance_review = installed_balance_review_report()
    identities = installed_identity_report()
    metadata = installed_metadata_report()
    house_review = house_review_report()
    difficulty_review = difficulty_review_report()
    reward_review = reward_review_report()
    objective_review = objective_review_report()
    production_review = production_review_report()
    progression = progression_audit_report()
    progress_hooks = progress_hook_audit_report()
    ui_profile = installed_ui_profile_report()
    archipelago = archipelago_foundation_report()
    shop = validate_shop_domain() if ENABLE_SHOP_MODE else {
        'valid': False,
        'enabled': False,
    }
    release_validation = release_validation_report()
    return {
        'supported_game_version': SUPPORTED_GAME_VERSION,
        'foundation_only': FOUNDATION_ONLY,
        'port_guard': {
            'gameplay_catalogues_ready': GAMEPLAY_CATALOGUES_READY,
            'objective_rewards_ready': OBJECTIVE_REWARDS_READY,
            'advanced_gameplay_enabled': ENABLE_ADVANCED_GAMEPLAY,
            'shop_mode_enabled': ENABLE_SHOP_MODE,
            'archipelago_enabled': ENABLE_ARCHIPELAGO,
        },
        'missions': missions,
        'content': content,
        'content_review': content_review,
        'production_topology': production_topology,
        'balance_review': balance_review,
        'identity_safety': identities,
        'mission_metadata': metadata,
        'mission_house_review': house_review,
        'mission_difficulty_review': difficulty_review,
        'mission_reward_review': reward_review,
        'mission_objective_review': objective_review,
        'mission_production_review': production_review,
        'progression': progression,
        'progress_hooks': progress_hooks,
        'ui_profile': ui_profile,
        'archipelago': archipelago,
        'shop': shop,
        'release_validation': release_validation,
        'passed': (
            missions['valid']
            and bool(content['registered_counts'])
            and content_review['valid']
            and production_topology['valid']
            and balance_review['valid']
            and identities['valid']
            and metadata['valid']
            and house_review['valid']
            and difficulty_review['valid']
            and reward_review['valid']
            and objective_review['valid']
            and production_review['valid']
            and progression['valid']
            and progress_hooks['valid']
            and ui_profile['valid']
            and (not ENABLE_ARCHIPELAGO or archipelago['valid'])
            and (not ENABLE_SHOP_MODE or shop['valid'])
            and release_validation['valid']
        ),
    }


def main():
    report = installation_report()
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
