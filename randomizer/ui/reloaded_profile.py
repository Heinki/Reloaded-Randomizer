"""Read-only validation for the C&C Reloaded launcher UI profile."""

from randomizer.config.game_profile import (
    ACTIVE_SIDE_SECTIONS,
    CAMPAIGN_FILTER_SPECS,
    ENABLE_ADVANCED_UI,
    ENABLE_ADVANCED_GAMEPLAY,
    ENABLE_SHOP_MODE,
    EVA_SIDE_SECTION_BY_FACTION,
    EVA_TAG_FALLBACK_BY_FACTION,
    FACTION_ORDER,
)
from randomizer.config.player import DEFAULT_CONFIG
from randomizer.content.inventory import read_rules_sections
from randomizer.maps.settings import validate_eva_voice_profiles
from randomizer.ui.config import (
    CAMPAIGN_FILTERS,
    EVA_APPEARANCE_PROFILES,
    EVA_VOICE_TAGS,
    FACTION_TILE_COLORS,
    UNLOCK_DASHBOARD_FACTIONS,
)


def installed_ui_profile_report():
    """Verify five-faction UI choices against the installed Reloaded sides."""
    factions = list(FACTION_ORDER)
    sections, source = read_rules_sections()
    installed_voice_tags = {}
    missing_side_sections = []
    for faction, side in EVA_SIDE_SECTION_BY_FACTION.items():
        if side not in sections:
            missing_side_sections.append(side)
        installed_voice_tags[faction] = (
            sections.get(side, {}).get('EVA.Tag')
            or EVA_TAG_FALLBACK_BY_FACTION.get(faction, '')
        )

    eva_profiles = validate_eva_voice_profiles(
        EVA_VOICE_TAGS,
        EVA_APPEARANCE_PROFILES,
    )
    campaign_filters_match = CAMPAIGN_FILTERS == [
        'All Campaigns', *(label for label, _faction, _campaign in CAMPAIGN_FILTER_SPECS),
    ]
    faction_colors_match = list(FACTION_TILE_COLORS) == factions
    dashboard_factions_match = list(UNLOCK_DASHBOARD_FACTIONS) == factions
    default_arsenal_factions = list(
        DEFAULT_CONFIG['generation']['arsenal']['factions']
    )
    default_arsenal_factions_match = default_arsenal_factions == factions
    eva_tags_match = installed_voice_tags == EVA_VOICE_TAGS
    side_sections_match = list(EVA_SIDE_SECTION_BY_FACTION.values()) == list(
        ACTIVE_SIDE_SECTIONS
    )
    valid = all((
        campaign_filters_match,
        faction_colors_match,
        dashboard_factions_match,
        default_arsenal_factions_match,
        eva_tags_match,
        side_sections_match,
        not missing_side_sections,
        eva_profiles['valid'],
    ))
    return {
        'rules_source': source,
        'active_factions': factions,
        'campaign_filters_match': campaign_filters_match,
        'faction_colors_match': faction_colors_match,
        'unlock_dashboard_factions': list(UNLOCK_DASHBOARD_FACTIONS),
        'dashboard_factions_match': dashboard_factions_match,
        'default_arsenal_factions': default_arsenal_factions,
        'default_arsenal_factions_match': default_arsenal_factions_match,
        'installed_voice_tags': installed_voice_tags,
        'configured_voice_tags': dict(EVA_VOICE_TAGS),
        'eva_tags_match': eva_tags_match,
        'eva_profiles': eva_profiles,
        'active_side_sections': list(ACTIVE_SIDE_SECTIONS),
        'missing_side_sections': missing_side_sections,
        'advanced_ui_enabled': ENABLE_ADVANCED_UI,
        'advanced_modes_enabled': ENABLE_ADVANCED_GAMEPLAY,
        'shop_mode_enabled': ENABLE_SHOP_MODE,
        'valid': valid,
    }
