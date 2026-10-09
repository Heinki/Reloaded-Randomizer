"""Add bounded, faction-specific special-unit production to hostile AI bases.

Unlike DTA's reinforcement expansion, Reloaded needs normal factory queues.
Private TechnoTypes and single-member hunt teams preserve authored identities.
"""

from hashlib import sha256

from randomizer.config.static import load_static_config
from randomizer.rewards.enemy_scaling import enemy_effect_values

from .buff_values import _register_map_type
from .houses import (
    canonical_house_name, country_family, map_house_records,
    production_owner_countries,
)
from .ini import all_section_value_maps, section_value_map_preserve
from .ownership import unsafe_country_houses


_CONFIG = load_static_config('rewards/enemy_scaling.json')['powerhouse_rosters']
_YES = frozenset({'yes', 'true', '1'})
_REGISTRIES = {
    'infantry': 'InfantryTypes', 'vehicles': 'VehicleTypes',
    'aircraft': 'AircraftTypes',
}


def _fold(values):
    return {str(key).lower(): value for key, value in values.items()}


def enemy_powerhouse_rules(
    lines, hostile_houses, rewards, installed_sections, *, seed='', stage=1,
    difficulty=1, protected_mission=False, excluded_unit_ids=(),
):
    """Return additive rules, application receipts, and explicit skip reasons."""
    reward = next((item for item in rewards or () if item.get('enemy_reward')
                   and item.get('enemy_effect') == 'powerhouse'), None)
    if reward is None:
        return {}, [], []
    if protected_mission:
        return {}, [], ['fixed-force or protected scripted mission']

    sections = all_section_value_maps(lines)
    local = {name.lower(): values for name, values in sections.items()}
    installed = {name.lower(): values for name, values in installed_sections.items()}
    records = map_house_records(lines, sections=sections)
    excluded = {str(unit).upper() for unit in excluded_unit_ids}
    difficulty = max(0, min(2, int(difficulty)))
    occupied = set(local) | set(installed)
    occupied.update(str(key).lower() for key in local.get('aitriggertypes', {}))
    rules, applications, skipped = {}, [], []
    script_id = ''
    identity = f'{seed}|{stage}|{local.get("basic", {})}'
    enabled = _fold(local.get('aitriggertypesenable', {}))
    catalogue = load_static_config('rewards/reloaded_content_catalogue.json')['content']['units']
    unit_records = {
        str(record['id']).upper(): (category, record)
        for category, entries in catalogue.items() for record in entries
    }

    def unique(prefix, scope):
        stem = prefix + sha256(scope.encode('utf-8')).hexdigest()[:10].upper()
        candidate, suffix = stem, 2
        while candidate.lower() in occupied:
            candidate = f'{stem}{suffix}'
            suffix += 1
        occupied.add(candidate.lower())
        return candidate

    def register(registry, type_id):
        _register_map_type(rules, lines, installed_sections, registry, type_id)

    def effective(type_id):
        return {**_fold(installed.get(str(type_id).lower(), {})),
                **_fold(local.get(str(type_id).lower(), {}))}

    factories = {}

    def add_factory(owner, building):
        house = canonical_house_name(records, owner)
        if house not in hostile_houses:
            return
        values = effective(building)
        kind = str(values.get('factory', '')).lower()
        category = {'infantrytype': 'infantry', 'unittype': 'vehicles',
                    'aircrafttype': 'aircraft'}.get(kind)
        if category:
            naval = str(values.get('naval', '')).lower() in _YES
            factories.setdefault(house, {}).setdefault((category, naval), []).append(building)

    for raw in local.get('structures', {}).values():
        fields = str(raw).split(',')
        if len(fields) >= 2:
            add_factory(fields[0].strip(), fields[1].strip())
    for house in hostile_houses:
        for key, raw in local.get(house.lower(), {}).items():
            if str(key).isdigit():
                add_factory(house, str(raw).split(',')[0].strip())

    def source_team(house):
        for type_id in local.get('teamtypes', {}).values():
            values = local.get(str(type_id).lower(), {})
            # Transport, reinforcement and base-defense queues are not a
            # safe template for an independently built attacking specialist.
            if any(str(values.get(key, '')).lower() in _YES for key in (
                'reinforce', 'droppod', 'ontransonly', 'isontransonly', 'isbasedefense',
            )) or str(values.get('transportwaypoint', '-1')).strip() not in {'', '-1'}:
                continue
            for trigger_id, raw in local.get('aitriggertypes', {}).items():
                tokens = [token.strip() for token in str(raw).split(',')]
                if (len(tokens) < 18 or tokens[1].lower() != str(type_id).lower()
                    or str(enabled.get(str(trigger_id).lower(), 'yes')).lower() not in _YES
                    or tokens[15 + difficulty].lower() not in _YES):
                    continue
                owner = canonical_house_name(records, tokens[2])
                team_owner = canonical_house_name(records, values.get('house'))
                if owner == house or (tokens[2].lower() in {'<all>', 'all'} and team_owner == house):
                    return str(type_id), tokens
            if (canonical_house_name(records, values.get('house')) == house
                and str(values.get('autocreate', '')).lower() in _YES):
                # Existing campaign action 13 activates this parallel team.
                return str(type_id), None
        return '', None

    def production_path(source, classes):
        entry = unit_records.get(source)
        values = _fold(installed.get(source.lower(), {}))
        if not entry or source in excluded or not values:
            return ''
        category, record = entry
        if not any(values.get(key) and str(values[key]).lower() not in {'none', '<none>'}
                   for key in ('primary', 'secondary', 'weapon1')):
            return ''
        return next(iter(classes.get((category, bool(record.get('naval'))), ())), '')

    for house in hostile_houses:
        family = country_family(records.get(house, {}))
        roster = _CONFIG.get(family)
        if not roster:
            continue
        country = records[house]['country']
        if unsafe_country_houses(lines, country, hostile_houses, records=records, sections=sections):
            skipped.append(f'{house}: production country shared with non-hostile actors')
            continue
        classes = factories.get(house, {})
        source_id, trigger = source_team(house)
        if not classes or not source_id:
            skipped.append(f'{house}: no factory or active attack production template')
            continue

        def rank(pool, kind):
            return sorted((unit for unit in pool if production_path(unit, classes)),
                          key=lambda unit: sha256(f'{identity}|{house}|{kind}|{unit}'.encode()).digest())

        # Every configured specialist participates across seeds/stages. Bound
        # production to four definitions per house, with at most two heroes.
        heroes = rank(roster['heroes'], 'heroes')[:2]
        selected = heroes + rank(roster['specials'], 'specials')[:4 - len(heroes)]
        if not selected:
            skipped.append(f'{house}: no eligible special units for its factories')
        for source in selected:
            category, record = unit_records[source]
            factory = production_path(source, classes)
            actor = unique('RLREU', f'{house}|{source}')
            # Use installed rules, never cinematic map overrides. Clear
            # alternate tech, stolen-tech, transformation and grouping paths.
            values = {
                key: value for key, value in installed.get(source.lower(), {}).items()
                if not str(key).lower().startswith((
                    'prerequisite', 'requiresstolen', 'buildlimit', 'convert.',
                    'initialpayload.',
                )) and str(key).lower() not in {
                    '$inherits', 'basesection', 'owner', 'requiredhouses',
                    'forbiddenhouses', 'factoryowners', 'factoryowners.disallow',
                    'builtat', 'deploysinto', 'undeploysinto', 'reversedas', 'groupas',
                    'passengers.allowed',
                }
            }
            values.update({
                'Name': f'Enemy Powerhouse: {record["name"]}',
                'Image': _fold(installed[source.lower()]).get('image') or source,
                'Owner': ','.join(production_owner_countries(lines, [country])),
                'RequiredHouses': country,
                'ForbiddenHouses': ','.join(sorted({
                    record['country'] for name, record in records.items()
                    if name not in hostile_houses
                    and record['country'].lower() not in {
                        owner.lower() for owner in production_owner_countries(lines, [country])
                    }
                })) or 'none',
                'Prerequisite': factory, 'TechLevel': '1', 'BuildLimit': '1',
                'BuildTimeMultiplier': '1', 'BuildTime.MultipleFactory': '1',
                'CanPassiveAquire': 'yes', 'CanRetaliate': 'yes',
                'PreventAttackMove': 'no', 'IsSelectableCombatant': 'yes',
                'CanBeReversed': 'no', 'Cloneable': 'no',
                'AllowedToStartInMultiplayer': 'no', 'CrateGoodie': 'no',
            })
            register(_REGISTRIES[category], actor)
            rules[actor] = values
            if not script_id:
                script_id = unique('RLRESC', 'powerhouse-hunt')
                register('ScriptTypes', script_id)
                rules[script_id] = {'Name': 'Enemy Powerhouses Hunt', '0': '11,15'}
            taskforce = unique('RLRETF', f'{house}|{source}')
            team = unique('RLRETM', f'{house}|{source}')
            register('TaskForces', taskforce)
            register('TeamTypes', team)
            rules[taskforce] = {'Name': f'Enemy Powerhouse: {record["name"]}',
                                'Group': '-1', '0': f'1,{actor}'}
            team_values = dict(section_value_map_preserve(lines, source_id))
            # Remove template keys before replacing them case-insensitively.
            overrides = {
                'Name': f'Enemy Powerhouse: {record["name"]}', 'House': country,
                'TaskForce': taskforce, 'Script': script_id, 'Max': '1',
                'Full': 'yes', 'Reinforce': 'no', 'Autocreate': 'yes',
                'Prebuild': 'no', 'Recruiter': 'no', 'LooseRecruit': 'no',
                'AreTeamMembersRecruitable': 'no', 'Droppod': 'no',
                'OnTransOnly': 'no', 'IsOnTransOnly': 'no', 'IsBaseDefense': 'no',
                'TransportWaypoint': '-1', 'UseTransportOrigin': 'no',
                'VeteranLevel': '1', 'Priority': '1', 'Tag': '<none>', 'Group': '-1',
            }
            team_values = {key: value for key, value in team_values.items()
                           if str(key).lower() not in _fold(overrides)}
            rules[team] = {**team_values, **overrides}
            if trigger:
                trigger_id = unique('RLRETR', f'{house}|{source}')
                tokens = list(trigger)
                tokens[0:7] = [f'Enemy Powerhouse: {record["name"]}', team, country,
                               '1', '-1', '<none>', '0' * 64]
                tokens[7:10] = ['5.000000', '1.000000', '10.000000']
                tokens[14] = '<none>'
                rules.setdefault('AITriggerTypes', {})[trigger_id] = ','.join(tokens)
                rules.setdefault('AITriggerTypesEnable', {})[trigger_id] = 'yes'
            applications.append({
                **enemy_effect_values(reward), 'effect_id': reward['enemy_effect_id'],
                'category': 'Special unit production', 'house': house, 'country': country,
                'target': team, 'effect': f'Enemy Powerhouses production: {record["name"]}',
                'engine_field': 'AI production team', 'application_kind': 'production',
                'source_team_id': source_id, 'source_unit_ids': [source],
                'added_unit_ids': [actor], 'added_unit_count': 1, 'enemy_family': family,
                'factory': factory,
            })
    return rules, applications, skipped
