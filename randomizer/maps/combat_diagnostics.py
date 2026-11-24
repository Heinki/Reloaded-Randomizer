"""Read-only combat-rule snapshots for reported campaign issues."""

from .ini import all_section_value_maps_preserve
from .ownership import build_unit_usage_index


REPORTED_MISSION_CODES = frozenset({
    'GDI02A_FS', 'NOD02A_FS', 'GDI08A_FS', 'GDI06A_TS', 'SOV06',
})


def mission_combat_snapshot(source_lines, launch_lines, installed_sections):
    """Inspect actual authored/prepared maps; do not infer live engine damage."""
    installed = {name.casefold(): {key.casefold(): value for key, value in values.items()}
                 for name, values in installed_sections.items()}

    def snapshot(lines):
        local = {name.casefold(): {key.casefold(): value for key, value in values.items()}
                 for name, values in all_section_value_maps_preserve(lines).items()}

        def effective(section):
            name = str(section).casefold()
            return {**installed.get(name, {}), **local.get(name, {})}

        def country_values(country, seen=()):
            name = str(country).casefold()
            if not name or name in seen or len(seen) >= 20:
                return {}
            values = effective(name)
            return {**country_values(values.get('parentcountry', ''), (*seen, name)), **values}

        technos = []
        for type_id, owners in sorted(build_unit_usage_index(lines).items()):
            values = effective(type_id)
            weapons = {}
            for field, weapon_id in values.items():
                if field not in ('primary', 'secondary', 'eliteprimary', 'elitesecondary'):
                    continue
                weapon = effective(weapon_id)
                warhead_id = weapon.get('warhead', '')
                warhead = effective(warhead_id)
                weapons[field] = dict(
                    id=weapon_id,
                    values={key: value for key, value in weapon.items()
                            if key in ('damage', 'rof', 'range', 'warhead', 'projectile',
                                       'spawner', 'limpetmine', 'mindcontrol', 'temporal')},
                    warhead=dict(id=warhead_id, values={key: value for key, value in warhead.items()
                                 if key.startswith('versus.') or key in (
                                     'verses', 'pronedamage', 'affectsallies', 'affectsenemies',
                                     'cankill', 'allowzerodamage', 'effectsrequiredamage',
                                     'sonic', 'tiberium', 'cellspread', 'percentatmax',
                                     'webby')}))
            technos.append(dict(
                id=type_id, houses=sorted(owners),
                values={key: value for key, value in values.items()
                        if key.startswith('immune') or key in (
                            'strength', 'armor', 'invulnerable', 'insignificant',
                            'veteranabilities', 'eliteabilities', 'initialstrength')},
                weapons=weapons))
        houses = []
        for house_id in effective('Houses').values():
            house = effective(house_id)
            country = house.get('country', house_id)
            values = country_values(country)
            houses.append(dict(id=house_id, country=country,
                               values={key: value for key, value in house.items()
                                       if key in ('allies', 'playercontrol', 'iq', 'side', 'country')},
                               country_values={key: value for key, value in values.items()
                                               if key.startswith(('armor', 'firepower'))
                                               or key in ('parentcountry', 'side')}))
        return dict(
            technos=technos, houses=houses, armor_types=effective('ArmorTypes'),
            difficulty={name: effective(name) for name in ('Easy', 'Normal', 'Difficult')},
            veteran_values={key: value for key, value in effective('General').items()
                            if key.startswith(('veteran', 'elite'))})

    return dict(format='reloaded-combat-rules-v1',
                note='Effective rules only; live engine damage has not been measured.',
                authored=snapshot(source_lines),
                prepared=snapshot(launch_lines) if launch_lines is not None else None)
