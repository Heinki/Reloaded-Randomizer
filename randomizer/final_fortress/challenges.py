"""Grid enemy-buff definitions adapted to an isolated skirmish workspace."""

from copy import deepcopy

from randomizer.final_fortress.catalogue import SIDE_COUNTRIES
from randomizer.rewards.enemy_scaling import (
    ENEMY_BUFF_BY_ID, ENEMY_BUFF_DEFINITIONS, build_enemy_reward_pool,
    enemy_effect_text, enemy_effect_values,
)


OFFENSIVE_DEFINITION = {
    'id': 'faction_superweapons', 'name': 'Faction Offensive Superweapons',
    'effect': 'power_group', 'maximum_stacks': 1,
}
DROP_POD_DEFINITION = {
    'id': 'ai_drop_pods', 'name': 'AI Drop Pods', 'type': 'Support Power',
    'category': 'Support Powers', 'effect': 'power', 'superweapon': 'DropPodSpecial',
    'maximum_stacks': 1,
}


def definitions(*, include_retired=False):
    return tuple(entry for entry in ENEMY_BUFF_DEFINITIONS
                 if (entry['effect'] in {'armor', 'production', 'unit', 'powerhouse'}
                     or entry['id'] in {'ai_paratroopers'})
                 and (include_retired or (entry.get('country_suffix') != 'Defenses'
                      and entry.get('unit_buff_type') not in {'sight', 'sensors'}))) + (
                          DROP_POD_DEFINITION, OFFENSIVE_DEFINITION)


def definition(entry):
    key = entry['enemy_effect_id']
    if key == 'faction_superweapons':
        return OFFENSIVE_DEFINITION
    return DROP_POD_DEFINITION if key == 'ai_drop_pods' else ENEMY_BUFF_BY_ID[key]


def label(entry):
    if 'enemy_effect_id' not in entry:
        return entry['display_name']
    if entry['enemy_effect_id'] == 'ai_paratroopers':
        return 'Paradrop'
    return definition(entry)['name'].removeprefix('AI ')


def description(entry, stacks=1):
    if 'enemy_effect_id' not in entry:
        return entry['description']
    effect = entry['enemy_effect_id']
    if effect in {'ai_paratroopers', 'ai_drop_pods'}:
        payload = ('a Paradrop of its faction infantry' if effect == 'ai_paratroopers'
                   else 'GDI Drop Pods carrying 7–9 GDI infantry')
        return (f'Each enemy gains {payload}; {entry.get("shots", 3)} launches per enemy, '
                f'{entry.get("recharge_multiplier", 2)}x native recharge; not initially ready. '
                'Delivered troops receive applicable enemy Challenge buffs; outside wave caps.')
    if effect == 'powerhouse':
        return ('Each active scripted-wave side gains two rotating faction heavies and veteran units. '
                'Existing wave/living limits apply; at the ceiling heavies replace ordinary units.')
    if effect == 'faction_superweapons':
        return ('Each enemy gains its own offensive superweapon: Lightning Storm, Nuclear Missile, '
                'Psychic Dominator, Ion Cannon or Multi-Missile. Native recharge; AI-only private copies.')
    text = enemy_effect_text(definition(entry), stacks)
    if definition(entry)['effect'] == 'power':
        text += (f'; {entry.get("shots", 3)} launches per enemy, '
                 f'{entry.get("recharge_multiplier", 2)}x native/portable recharge; not initially ready')
    return text


def maximum(entry):
    if 'enemy_effect_id' not in entry:
        return 1
    return int(definition(entry)['maximum_stacks'])


def apply_country(row, challenges):
    for challenge in challenges:
        if 'enemy_effect_id' not in challenge:
            continue
        effect = definition(challenge)
        if effect['effect'] not in {'armor', 'production'}:
            continue
        field = ('Armor' if effect['effect'] == 'armor' else 'BuildTime') + effect['country_suffix'] + 'Mult'
        key = next((key for key in row if key.casefold() == field.casefold()), field)
        row[key] = str(enemy_effect_values(effect, challenge['stacks'], float(row.get(key, '1')))[
            'final_engine_value'])


def apply_units(writer, plan, rules, ai_rules, *, route_ai=True, aliases_out=None):
    """Reuse Grid calculations, then give the results only to private AI types.

    Native human types and weapons stay intact. AI task forces request the
    private counterparts; concrete country gates keep them out of human
    production, including when both sides chose the same native faction.
    """
    from randomizer.maps.buff_values import _register_map_type
    from randomizer.maps.enemy_scaling import enemy_native_unit_buff_rules
    from randomizer.maps.ini import IniLines, append_section_list_entry
    from randomizer.rewards.catalogue import BUFF_TARGETS
    from .buff_links import linked_types, rewrite_type_links

    selected = {entry['enemy_effect_id']: entry['stacks'] for entry in plan.get('challenges', [])
                if 'enemy_effect_id' in entry and definition(entry)['effect'] == 'unit'}
    if not selected:
        return {}
    pool = {entry['enemy_effect_id']: entry for entry in build_enemy_reward_pool(())}
    rewards = [deepcopy(pool[key]) for key, stacks in selected.items() for _ in range(stacks)]
    # This calculation-only map describes all native enemy countries. It is
    # never written to the game or routed through campaign progression.
    synthetic = IniLines(['[Countries]', *[f'{i}={country}' for i, country in enumerate(SIDE_COUNTRIES)],
                          '[Houses]', *[f'{i}=FFAI{i}' for i in range(len(SIDE_COUNTRIES))]])
    for i, country in enumerate(SIDE_COUNTRIES):
        synthetic.extend([f'[FFAI{i}]', f'Country={country}', 'PlayerControl=no'])
    categories = {value: category for category in ('InfantryTypes', 'VehicleTypes', 'AircraftTypes', 'BuildingTypes')
                  for value in rules[category].values()}
    linked_sources = {}
    for root in sorted(BUFF_TARGETS):
        if (root not in categories or categories[root] == 'BuildingTypes'
                or BUFF_TARGETS[root].get('linked_buff_source')):
            continue
        pending, visited = [root], {root}
        while pending:
            current = pending.pop()
            for _, target in linked_types(rules[current], categories):
                if target in visited:
                    continue
                visited.add(target)
                linked_sources.setdefault(target, root)
                pending.append(target)
    updates, _, _, _ = enemy_native_unit_buff_rules(
        synthetic, [f'FFAI{i}' for i in range(len(SIDE_COUNTRIES))], rewards, rules, {},
        linked_sources=linked_sources)
    overrides = {key: {**deepcopy(rules[key]), **values} for key, values in updates.items()
                 if key in categories}
    # Keep every outgoing form private even when this selection only affects
    # one form's weapon. Ownership and reverse links must stay inside the graph.
    pending = list(overrides)
    while pending:
        for _, target in linked_types(rules[pending.pop()], categories):
            if target not in overrides:
                overrides[target] = deepcopy(rules[target])
                pending.append(target)
    aliases = {key: writer.key() for key in overrides}
    if aliases_out is not None:
        aliases_out.update(aliases)
    for key, values in updates.items():
        if key in overrides or key == 'WeaponTypes':
            continue
        writer.sections[key] = deepcopy(values)
    for weapon in updates.get('WeaponTypes', {}).values():
        _register_map_type(writer.sections, writer.lines, rules, 'WeaponTypes', weapon)
    enemies = [f'FFENEMY{i + 1}' for i in range(3)]
    for original, base in overrides.items():
        row = deepcopy(base)
        owners = {part.strip() for part in rules[original].get('Owner', '').split(',')}
        required = {part.strip() for part in rules[original].get('RequiredHouses', '').split(',') if part.strip()}
        forbidden = {part.strip() for part in rules[original].get('ForbiddenHouses', '').split(',') if part.strip()}
        from .catalogue import eligible as native_eligible
        source = linked_sources.get(original, original)
        eligible = [alias for alias, country in zip(enemies, plan['enemy_countries'])
                    if native_eligible(source, country, rules[source])]
        # Native factory selection can consult the parent-country Owner mask;
        # RequiredHouses still gates production to the concrete enemy copies.
        owner_mask = owners | set(eligible)
        row.update(Image=row.get('Image', original), Owner=','.join(sorted(owner_mask)) or 'Neutral',
                   RequiredHouses=','.join(eligible) or 'Neutral', ForbiddenHouses='',
                   AllowedToStartInMultiplayer='no')
        rewrite_type_links(row, aliases)
        writer.sections[aliases[original]] = row
        from .native import register_scripted_weapons
        register_scripted_weapons(writer, original, row, rules)
        _register_map_type(writer.sections, writer.lines, rules, categories[original], aliases[original])
        writer.put(original, 'ForbiddenHouses', ','.join(sorted(forbidden | set(enemies))))
    for force in ai_rules.get('TaskForces', {}).values() if route_ai else ():
        row = deepcopy(ai_rules.get(force, {}))
        changed = False
        for key, value in tuple(row.items()):
            if not key.isdigit():
                continue
            count, sep, original = value.partition(',')
            if sep and original.strip() in aliases:
                row[key] = count + ',' + aliases[original.strip()]
                changed = True
        if changed:
            append_section_list_entry(writer.lines, 'TaskForces', force)
            writer.sections[force] = row
    for key, value in rules.get('General', {}).items() if route_ai else ():
        if key.lower().startswith('ai'):
            parts = value.split(',')
            if any(part.strip() in aliases for part in parts):
                writer.put('General', key, ','.join(aliases.get(part.strip(), part) for part in parts))
    for enemy in enemies:
        row = writer.sections[enemy]
        for key, value in tuple(row.items()):
            parts = str(value).split(',')
            if any(part.strip() in aliases for part in parts):
                row[key] = ','.join(aliases.get(part.strip(), part) for part in parts)
    return overrides


def load_ai_rules():
    from randomizer.core.paths import CAMEO_CACHE_DIR, GAME_ROOT
    from randomizer.ui.cameos import extract_mix_files_sync
    from randomizer.maps.ini import all_section_value_maps_preserve
    source = GAME_ROOT / 'aimd.ini'
    if source.is_file() and source.read_text(encoding='utf-8', errors='ignore').startswith(
            '; Generated by C&C Reloaded Randomizer Launcher Final Fortress'):
        source = CAMEO_CACHE_DIR / 'aimd.ini'
    if not source.is_file():
        source = CAMEO_CACHE_DIR / 'aimd.ini'
        if not extract_mix_files_sync([('AIMD.INI', source)]):
            raise ValueError('Installed AI task forces are unavailable for tier challenges.')
    return all_section_value_maps_preserve(source.read_text(encoding='utf-8', errors='ignore').splitlines())
