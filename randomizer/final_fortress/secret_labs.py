"""Retain native Secret Lab selection across isolated Fortress countries."""


def _items(value):
    return [item.strip() for item in value.split(',')
            if item.strip() and item.strip().lower() not in ('none', '<none>')]


def boon_types(rules):
    values = []
    for field in ('SecretInfantry', 'SecretUnits', 'SecretBuildings'):
        values.extend(_items(rules.get('General', {}).get(field, '')))
    for row in rules.values():
        values.extend(_items(row.get('SecretLab.PossibleBoons', '')))
    registered = {kind for category in ('BuildingTypes', 'InfantryTypes', 'VehicleTypes', 'AircraftTypes')
                  for kind in rules[category].values()}
    return set(values) & registered


def allowed_boon(row, country):
    required = {item.casefold() for item in _items(row.get('SecretLab.RequiredHouses', ''))}
    forbidden = {item.casefold() for item in _items(row.get('SecretLab.ForbiddenHouses', ''))}
    country = country.casefold()
    return country not in forbidden and (not required or country in required)


def apply_secret_labs(writer, plan, rules, aliases, enemy_aliases):
    """Offer each actor its own boon identity, keeping native capture behavior.

    Ares tests SecretLab house masks separately from normal production gates.
    Original and private identities therefore need separate boon masks too.
    A lab offers only the identity whose buffs and country gates match its
    captor; it must not choose a now-forbidden original behind a player clone.
    """
    from .player_perks import coalition, needs_countries
    from randomizer.config.game_profile import ENABLE_CABAL
    from randomizer.content.inventory import is_cabal_content

    friends = [(name, country) for name, country, _ in coalition(plan)] if needs_countries(plan) else []
    enemies = [(f'FFENEMY{index + 1}', country)
               for index, country in enumerate(plan['enemy_countries'])]
    actors = [*friends, *enemies]
    boons = boon_types(rules)
    replacements = {}
    for original in boons:
        base = rules[original]
        if not ENABLE_CABAL and is_cabal_content(original, base):
            replacements[original] = []
            continue
        private = [(mapping[original], owners) for mapping, owners in (
            (aliases, friends), (enemy_aliases, enemies)) if original in mapping]
        owners = [name for name, country in actors if allowed_boon(base, country)]
        required = _items(base.get('SecretLab.RequiredHouses', ''))
        forbidden = _items(base.get('SecretLab.ForbiddenHouses', ''))
        if required:
            writer.put(original, 'SecretLab.RequiredHouses', ','.join(dict.fromkeys([*required, *owners])))
        forbidden.extend(name for name, country in actors if not allowed_boon(base, country))
        for alias, group in private:
            permitted = [name for name, country in group if allowed_boon(base, country)]
            writer.put(alias, 'SecretLab.RequiredHouses', ','.join(permitted) or 'Neutral')
            writer.put(alias, 'SecretLab.ForbiddenHouses', '')
            forbidden.extend(name for name, _ in group)
        writer.put(original, 'SecretLab.ForbiddenHouses', ','.join(dict.fromkeys(forbidden)))
        replacements[original] = [original, *(alias for alias, _ in private)]

    fallback = [kind for field in ('SecretInfantry', 'SecretUnits', 'SecretBuildings')
                for kind in _items(rules.get('General', {}).get(field, ''))]
    for kind in rules['BuildingTypes'].values():
        base = rules[kind]
        if base.get('SecretLab', '').lower() != 'yes':
            continue
        pool = _items(base.get('SecretLab.PossibleBoons', '')) or fallback
        expanded = list(dict.fromkeys(value for original in pool
                                     for value in replacements.get(original, [original])))
        for target in (kind, aliases.get(kind), enemy_aliases.get(kind)):
            if target:
                writer.put(target, 'SecretLab.PossibleBoons', ','.join(expanded))
