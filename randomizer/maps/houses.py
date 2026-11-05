"""House/country discovery for campaign maps.

Functions here only interpret map ownership. Buff planning and clone mutation
belong in their respective modules.
"""

from randomizer.config.game_profile import ENABLE_CABAL
from randomizer.core.collections import comma_items, unique_in_order
from randomizer.maps.ini import all_section_value_maps, ini_value_text, section_value_map


def map_house_records(lines, sections=None):
    """Return map house metadata after one case-insensitive INI parse."""
    sections = sections if sections is not None else all_section_value_maps(lines)
    by_lower = {name.lower(): values for name, values in sections.items()}
    houses = by_lower.get('houses', {})
    records = {}
    for name in houses.values():
        name = ini_value_text(name)
        if not name:
            continue
        values = by_lower.get(name.lower(), {})
        # Country/ParentCountry comments are not part of their IDs. GDI05A_TS
        # has Country=NodCountry ;Russians. Copying that raw value into a
        # TriggerType comments out every remaining CSV field and crashes the
        # engine's trigger loader in its null-argument string comparison.
        country = ini_value_text(values.get('country')) or name.replace(' House', '')
        country_values = by_lower.get(country.lower(), {})
        records[name] = {
            'name': name,
            'country': country,
            'parent_country': ini_value_text(country_values.get('parentcountry')),
            'side': ini_value_text(country_values.get('side')),
            'allies': comma_items(ini_value_text(values.get('allies'))),
            'player': ini_value_text(values.get('playercontrol')).lower() == 'yes',
        }
    return records


def canonical_house_name(records, value):
    """Resolve FinalAlert House/Country aliases without guessing."""
    wanted = ini_value_text(value).lower()
    if not wanted or wanted in {'<none>', 'none', 'neutral'}:
        return ''

    for name in records:
        if wanted in {name.lower(), name.removesuffix(' House').lower()}:
            return name

    country_matches = [
        name
        for name, record in records.items()
        if wanted == (record.get('country') or '').strip().lower()
    ]
    return country_matches[0] if len(country_matches) == 1 else ''


def player_house_from_map(lines, records=None):
    """Return authoritative human house, preferring ``[Basic] Player``."""
    records = records if records is not None else map_house_records(lines)
    basic_player = section_value_map(lines, 'Basic').get('player', '')
    primary_house = canonical_house_name(records, basic_player)
    if primary_house:
        return primary_house
    for name, record in records.items():
        if record.get('player'):
            return name
    return ''


def player_country_from_map(lines):
    """Return authoritative human country with vanilla fallback."""
    records = map_house_records(lines)
    house = player_house_from_map(lines, records=records)
    if house:
        return records.get(house, {}).get('country') or house.replace(' House', '')
    return 'UnitedStates'


def player_controlled_houses(lines, records=None):
    """Return authoritative then secondary player-controlled map houses."""
    records = records if records is not None else map_house_records(lines)
    primary_house = player_house_from_map(lines, records=records)
    return unique_in_order(
        ([primary_house] if primary_house else [])
        + [name for name, record in records.items() if record.get('player')]
    )


def country_inherits_from(lines, country, ancestor, sections=None):
    """Return whether country equals/inherits one ancestor."""
    wanted = ini_value_text(ancestor).lower()
    current = ini_value_text(country)
    visited = set()
    sections = sections if sections is not None else all_section_value_maps(lines)
    by_lower = {name.lower(): values for name, values in sections.items()}
    while current and current.lower() not in visited:
        current_lower = current.lower()
        if current_lower == wanted:
            return True
        visited.add(current_lower)
        values = by_lower.get(current_lower, {})
        parent = ini_value_text(values.get('parentcountry'))
        if not parent or parent.lower() == current_lower:
            break
        current = parent
    return False


def production_owner_countries(lines, countries, sections=None):
    """Return concrete countries plus each ParentCountry chain."""
    sections = sections if sections is not None else all_section_value_maps(lines)
    by_lower = {
        str(name).lower(): (str(name), values)
        for name, values in sections.items()
    }
    result = []
    seen = set()
    for country in countries or ():
        current = ini_value_text(country)
        chain_seen = set()
        while current and current.lower() not in chain_seen:
            current_lower = current.lower()
            chain_seen.add(current_lower)
            if current_lower not in seen:
                seen.add(current_lower)
                result.append(current)
            _section_name, values = by_lower.get(current_lower, ('', {}))
            parent = ini_value_text(values.get('parentcountry'))
            if not parent or parent.lower() == current_lower:
                break
            current = parent
    return result


def player_factory_owner_countries(lines, countries, records=None):
    """Exclude active AI factory ancestry from player production restrictions.

    Red Revolution's human SovietCountry inherits Russians, which is also
    BadGuy1's country. Banning that ancestor on shared native units disables
    the enemy's factories as well as the player's duplicate cameos.
    """
    records = records if records is not None else map_house_records(lines)
    # Concrete player/transfer owners are reviewed separately. Expand their
    # ancestry only when the added country cannot also be an AI factory owner.
    countries = unique_in_order(countries or ())
    concrete = {country.casefold() for country in countries}
    controlled = {
        name.casefold() for name in player_controlled_houses(lines, records)
    }
    # Empty cinematic Houses can share the player's ParentCountry. They have
    # no factory plans to protect. Treating them as producers removed Americans
    # and Germans from ALL11_RA2's native gates and exposed duplicate Harriers,
    # Rocketeers and Aegis Cruisers through the player's own factories.
    from randomizer.maps.ownership import build_unit_usage_index
    from randomizer.missions.access import (
        CONYARD_BY_MCV, MOBILE_FACTORY_BY_UNIT, PRODUCTION_LOOKUP,
    )

    factory_types = set(PRODUCTION_LOOKUP) | set(CONYARD_BY_MCV) | set(MOBILE_FACTORY_BY_UNIT)
    usage = build_unit_usage_index(lines)
    producers = {
        str(owner).casefold()
        for type_id in factory_types
        for owner in usage.get(type_id, ())
    }
    sections = {name.casefold(): values for name, values in all_section_value_maps(lines).items()}
    for name in records:
        if any(
            str(value).split(',', 1)[0].strip().upper() in factory_types
            for key, value in sections.get(name.casefold(), {}).items()
            if str(key).isdigit()
        ):
            producers.add(name.casefold())
    non_player_countries = {
        country.casefold()
        for country in production_owner_countries(
            lines,
            [record['country'] for name, record in records.items()
             if name.casefold() not in controlled and producers.intersection({
                 name.casefold(), name.removesuffix(' House').casefold(),
                 record['country'].casefold(),
             })],
        )
    }
    return [
        country for country in production_owner_countries(lines, countries)
        if country.casefold() in concrete
        or country.casefold() not in non_player_countries
    ]


def resolve_configured_helper_houses(records, configured_houses, player_houses=()):
    """Resolve reviewed helper names; reject missing/ambiguous entries."""
    player_names = {str(name or '').lower() for name in player_houses}
    resolved = []
    rejected = []
    for value in configured_houses or ():
        house = canonical_house_name(records, value)
        if not house:
            rejected.append(str(value))
            continue
        if house.lower() in player_names:
            continue
        resolved.append(house)
    return (unique_in_order(resolved), unique_in_order(rejected))


def is_buffable_helper_house(record):
    """Reject neutral/cinematic placeholders as helper armies."""
    name = (record.get('name') or '').lower()
    country = (record.get('country') or '').lower()
    parent = (record.get('parent_country') or '').lower()
    blocked = ('neutral', 'civilian', 'special', 'placeholder', 'cinematic')
    if parent in blocked:
        return False
    return not any(token in name or token in country for token in blocked)


def country_family(record):
    """Classify one map house record into playable production family."""
    text = ' '.join([
        record.get('name') or '',
        record.get('country') or '',
        record.get('parent_country') or '',
        record.get('side') or '',
    ]).lower()
    country_text = ' '.join([
        record.get('name') or '',
        record.get('country') or '',
        record.get('parent_country') or '',
    ]).lower()

    # Never let a disabled CABAL country fall through to another faction.
    if any(token in text for token in ('robotcountry', 'robotside', 'cabal')):
        return 'cabal' if ENABLE_CABAL else ''
    if any(token in country_text for token in (
        'yuricountry', 'yuri'
    )):
        return 'yuri'
    if any(token in country_text for token in ('gdicountry', 'gdi')):
        return 'gdi'
    if any(token in country_text for token in ('nodcountry', 'nod')):
        return 'nod'
    if any(token in country_text for token in (
        'sovietcountry', 'soviet', 'russia', 'russians', 'confederation',
        'africans', 'arabs', 'iraq', 'cuba', 'libya'
    )):
        return 'soviets'
    if any(token in country_text for token in (
        'alliescountry', 'allies', 'americans', 'british', 'french',
        'germans', 'alliance', 'unitedstates'
    )):
        return 'allies'
    if 'thirdside' in text:
        return 'yuri'
    if 'secondside' in text:
        return 'soviets'
    if 'firstside' in text:
        return 'allies'
    return ''
