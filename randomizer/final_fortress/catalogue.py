"""Reloaded country identities and reviewed production-path eligibility."""

from functools import lru_cache

from randomizer.config.game_profile import CAMPAIGN_FACTIONS
from randomizer.config.static import load_static_config
from randomizer.content.faction_paths import content_record_faction_path


_COUNTRIES = {'Allies': 'AlliesCountry', 'Soviets': 'SovietCountry',
              'Yuri': 'YuriCountry', 'GDI': 'GDICountry', 'Nod': 'NodCountry',
              'CABAL': 'RobotCountry'}
COUNTRY_LABELS = {_COUNTRIES[faction]: faction for faction in CAMPAIGN_FACTIONS}
SIDE_COUNTRIES = tuple(COUNTRY_LABELS)
SIDE_FAMILIES = tuple(label.lower() for label in COUNTRY_LABELS.values())
CONSTRUCTION_TYPES = {
    'AlliesCountry': ('AMCV', 'GACNST'), 'SovietCountry': ('SMCV', 'NACNST'),
    'YuriCountry': ('PCV', 'YACNST'), 'GDICountry': ('GDIMCV', 'TSGACNST'),
    'NodCountry': ('NODMCV', 'TSNACNST'),
}


@lru_cache(maxsize=1)
def production_scopes():
    """Resolve catalogue paths, never broad Owner masks alone."""
    content = load_static_config('rewards/reloaded_content_catalogue.json')['content']
    scopes = {}
    for category, records in [*content['units'].items(), ('defenses', content['defenses']),
                              ('special_buildings', content.get('special_buildings', []))]:
        for record in records:
            path = content_record_faction_path(record, category)
            reviewed = {faction for faction, review in record.get('reviews', {}).items()
                        if review.get('status') == 'approved'}
            scopes[record['id']] = reviewed & set(path['factions']) if path['complete'] else set()
    from randomizer.content.faction_paths import installed_faction_path_index
    for kind, factions in installed_faction_path_index()['scopes'].items():
        scopes.setdefault(kind, set(factions))
    return scopes


def eligible(kind, country, row):
    from randomizer.config.game_profile import ENABLE_CABAL
    from randomizer.content.inventory import is_cabal_content
    if not ENABLE_CABAL and is_cabal_content(kind, row):
        return False
    for owner, kinds in CONSTRUCTION_TYPES.items():
        if kind in kinds:
            return country == owner
    # A campaign family includes alternate skirmish countries. A Fortress
    # actor represents one concrete native country, including its lab branch.
    native = country.casefold()
    owners = {value.strip().casefold() for value in row.get('Owner', '').split(',') if value.strip()}
    required = {value.strip().casefold() for value in row.get('RequiredHouses', '').split(',') if value.strip()}
    forbidden = {value.strip().casefold() for value in row.get('ForbiddenHouses', '').split(',') if value.strip()}
    if native not in owners or native in forbidden or (required and native not in required):
        return False
    faction = COUNTRY_LABELS[country]
    scopes = production_scopes()
    if kind in scopes:
        return faction in scopes[kind]
    return True
