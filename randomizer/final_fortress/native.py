"""Reviewed Reloaded rules for private Fortress types and launch preparation."""

from copy import deepcopy
from math import ceil, floor


def installed_rules_registry():
    from randomizer.ui.cameos import installed_rules_registry as registry, extract_mix_files_sync
    from randomizer.core.paths import CAMEO_CACHE_DIR
    if not extract_mix_files_sync([('rulesmd.ini', CAMEO_CACHE_DIR / 'rulesmd.ini')]):
        raise ValueError('Installed Reloaded rules are unavailable.')
    powers, rules = registry()
    rules['_FortressNativeRegistries'] = {category: dict(rules[category]) for category in (
        'BuildingTypes', 'InfantryTypes', 'VehicleTypes', 'AircraftTypes')}
    # Installed lists contain obsolete aliases with no actual type section.
    for category in ('BuildingTypes', 'InfantryTypes', 'VehicleTypes', 'AircraftTypes'):
        rules[category] = {key: value for key, value in rules[category].items() if value in rules}
    inactive = {'RobotCountry', 'RobotCountry2', 'UnusedCountry', 'UnusedCountry2', 'NoPilotsCountry'}
    rules['Countries'] = {str(index): country for index, country in enumerate(
        country for country in rules['Countries'].values() if country not in inactive)}
    return powers, rules


def validate_production_houses(writer, plan, rules):
    """Reject a missing native war-factory choice before HouseClass can crash.

    Native 004F671D dereferences FirstBuildableFromArray(BuildWeapons) without
    checking for null. Validate the concrete country gates, parent ownership
    and AI planning side used by that selection for every active actor.
    """
    from .player_perks import coalition, needs_countries
    from .catalogue import CONSTRUCTION_TYPES
    actors = [(f'FFENEMY{i + 1}', country)
              for i, country in enumerate(plan['enemy_countries'])]
    actors.extend((actor, country) for actor, country, _ in coalition(plan)
                  if needs_countries(plan))
    if not needs_countries(plan):
        actors.append((plan['player_country'], plan['player_country']))
    sides = list(rules['Sides'])
    factories = writer.sections.get('AI', {}).get('BuildWeapons', rules['AI']['BuildWeapons']).split(',')
    for actor, country in actors:
        if actor.startswith('FF') and writer.sections[actor].get('ParentCountry') != actor:
            raise ValueError(f'Fortress {actor} must retain its own AI selector identity.')
        side = sides.index(rules[country]['Side'])

        def allowed(kind):
            row = {**rules.get(kind, {}), **writer.sections.get(kind, {})}
            owners = set(filter(None, row.get('Owner', '').split(',')))
            required = set(filter(None, row.get('RequiredHouses', '').split(',')))
            forbidden = set(filter(None, row.get('ForbiddenHouses', '').split(',')))
            planning_side = int(row.get('AIBasePlanningSide', '-1'))
            return (actor in owners
                    and (not required or actor in required)
                    and actor not in forbidden
                    and planning_side in (-1, side))

        if not any(allowed(kind) for kind in factories):
            raise ValueError(f'Fortress {actor} ({country}) has no buildable war factory; '
                             'native country/production gates are inconsistent.')
        with_yard = writer.sections.get(actor, {}).get('StartInMultiplayer.WithConst', '').lower() == 'yes'
        native = CONSTRUCTION_TYPES[country][1 if with_yard else 0]
        group, field = ('AI', 'BuildConst') if with_yard else ('General', 'BaseUnit')
        candidates = writer.sections.get(group, {}).get(field, rules[group][field]).split(',')
        chosen = next((kind for kind in candidates if allowed(kind)), None)
        actual = {**rules.get(chosen, {}), **writer.sections.get(chosen, {})}
        expected_image = rules[native].get('Image', native)
        if actual.get('Image', chosen) != expected_image:
            raise ValueError(f'Fortress {actor} would start with {chosen}, expected native {native}.')


def validate_player_roster(writer, plan, rules, aliases):
    """Reject missing native production or an ungated Secret Lab reward."""
    from .catalogue import eligible
    from .player_perks import coalition, needs_countries
    from .secret_labs import boon_types, allowed_boon, _items

    if not needs_countries(plan):
        return
    access = set(plan['effects'].get('special_access', []))
    units = {kind for category in ('InfantryTypes', 'VehicleTypes', 'AircraftTypes')
             for kind in rules[category].values()}
    for actor, country, _ in coalition(plan):
        for original in units:
            base = rules[original]
            if not eligible(original, country, base) or int(base.get('TechLevel', '-1')) < 0:
                continue
            target = aliases.get(original, original)
            row = {**rules.get(target, {}), **writer.sections.get(target, {})}
            if (int(row.get('TechLevel', '-1')) < 0
                    or actor not in _items(row.get('Owner', ''))
                    or actor in _items(row.get('ForbiddenHouses', ''))
                    or (row.get('RequiredHouses') and actor not in _items(row['RequiredHouses']))):
                raise ValueError(f'Fortress {actor} lost native {original} production ({target}).')
        for original in boon_types(rules):
            target = aliases.get(original)
            if target is None:
                continue
            row = writer.sections[target]
            if original not in access and row.get('TechLevel') != rules[original].get('TechLevel'):
                raise ValueError(f'Fortress {original} bypasses its native Secret Lab unlock.')
            if allowed_boon(row, actor) != allowed_boon(rules[original], country):
                raise ValueError(f'Fortress {original} changed its Secret Lab country gates.')


def register_scripted_weapons(writer, original, row, rules):
    """Translate private Venom bonuses onto its passenger-free scripted weapon.

    Ordinary production retains native weapons/passengers. Scripted waves use
    the installed automatic laser, preserving the same earned stat changes.
    Register these weapons before the native preload is frozen.
    """
    if original != 'VENOM':
        return
    from randomizer.maps.buff_values import _register_map_type
    if not hasattr(writer, 'scripted_weapons'):
        writer.scripted_weapons = {}
    for field, automatic in (('Primary', 'VenomAutoLaserFire'),
                             ('ElitePrimary', 'VenomAutoLaserFireE')):
        weapon = row.get(field)
        source = rules[original].get(field)
        if weapon == source or weapon not in writer.sections:
            continue
        key = (weapon, automatic)
        if key in writer.scripted_weapons:
            continue
        values = deepcopy(rules[automatic])
        for stat in ('Damage', 'ROF', 'Range'):
            before = float(rules[source].get(stat, '0'))
            after = float(writer.sections[weapon].get(stat, before))
            if before <= 0 or before == after:
                continue
            scaled = float(values.get(stat, '0')) * after / before
            values[stat] = (f'{scaled:g}' if stat == 'Range' else
                            str(max(1, ceil(scaled) if stat == 'ROF' else floor(scaled))))
        clone = writer.key()
        writer.sections[clone] = values
        _register_map_type(writer.sections, writer.lines, rules, 'WeaponTypes', clone)
        writer.scripted_weapons[key] = clone


def scripted_unit_row(original, row, scripted_weapons=None):
    """Keep native weapons while removing untracked scripted Venom passengers."""
    row = deepcopy(row)
    if original == 'VENOM':
        for field, automatic in (('Primary', 'VenomAutoLaserFire'),
                                 ('ElitePrimary', 'VenomAutoLaserFireE')):
            row[field] = (scripted_weapons or {}).get((row.get(field), automatic), automatic)
        row.update(Passengers='0', OpenTopped='no', Ammo='-1',
                   **{'InitialPayload.Types': 'none', 'InitialPayload.Nums': '0'})
    if original == 'TSJUMPJET':
        # Match the existing reviewed Reloaded reward template: an inline
        # projectile header in the source must not replace the infantry image.
        for key in ('AA', 'AG', 'Acceleration', 'Arm', 'Proximity', 'ROT', 'Ranged',
                    'SubjectToCliffs', 'SubjectToElevation', 'SubjectToWalls'):
            row.pop(key, None)
        row['Image'] = original
    return row
