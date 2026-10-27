"""Final Fortress multiplayer map and solo spawner adapter.

Only this adapter owns survival triggers. Normal global skirmish AI remains
enabled. Native Player-at-start-location team owners avoid country collisions.
"""

from copy import deepcopy
import hashlib
from itertools import combinations
from pathlib import Path
import re

from randomizer.final_fortress.catalogue import SIDE_COUNTRIES
from randomizer.core.storage import atomic_write_text
from randomizer.core.paths import CAMEO_CACHE_DIR
from randomizer.maps.hooks import append_hook_team
from randomizer.maps.buff_values import _register_map_type
from randomizer.maps.ini import (
    IniLines, append_section_list_entry, merge_ini_section_values,
    next_numeric_section_index, section_value_map,
)

from .maps import inspect_map, source_lines


MAX_SCRIPTED_WAVES = 11


def marker_names(run_id, plan=None):
    if not re.fullmatch('[0-9a-f]{32}', run_id):
        raise ValueError('Invalid Final Fortress run ID.')
    prefix = 'RFF_' + hashlib.sha256(run_id.encode('ascii')).hexdigest()[:16]
    names = {event: prefix + suffix for event, suffix in (
        ('started', '_START'), ('victory', '_WIN'), ('defeat', '_LOSS'))}
    wave_count = len(plan['wave_schedule']) if plan is not None else MAX_SCRIPTED_WAVES
    names.update({f'wave:{index}': f'{prefix}_W{index:02d}' for index in range(1, wave_count + 1)})
    if plan is not None:
        for event in plan['gem_rewards']:
            if event not in names and not event.startswith('kills:'):
                names[event] = prefix + '_E' + hashlib.sha256(event.encode()).hexdigest()[:8]
    return names


def _waypoint(number):
    if type(number) is not int or not 0 <= number < 26:
        raise ValueError('Final Fortress currently requires waypoints 0–25.')
    return chr(65 + number)


def _owner(number):
    # These native names resolve Scenario.HouseIndices[starting_position].
    # They do not refer to MultiN or a country ID.
    if not 0 <= number < 8:
        raise ValueError('Final Fortress requires native start positions 0–7.')
    return f'<Player @ {_waypoint(number)}>'


def _action(code, value=0, *, team='0', trigger='0', waypoint='A'):
    kind, parameter = ('1', team) if team != '0' else (
        ('2', trigger) if trigger != '0' else ('0', value))
    return [str(code), kind, str(parameter), '0', '0', '0', '0', waypoint]


class _MapWriter:
    def __init__(self, lines, player_waypoint=0):
        self.lines = lines
        self.player_waypoint = player_waypoint
        self.sections = {}
        self.counter = 0
        self.variable_counter = 0
        self._task_force_cache = {}
        self._script_cache = {}

    def key(self):
        self.counter += 1
        return f'FF{self.counter:06X}'

    def put(self, section, key, value):
        self.sections.setdefault(section, {})[str(key)] = str(value)

    def flag(self, name):
        index = self.variable_counter
        self.variable_counter += 1
        if index >= 100:
            raise ValueError('Final Fortress exhausted native local variables.')
        self.put('VariableNames', index, name + ',0')
        return index

    def trigger(self, name, events, actions, *, disabled=False, persistence=0,
                owner='<none>'):
        if not 1 <= len(events) <= 32:
            raise ValueError('Native triggers require 1–32 events.')
        key, tag = self.key(), self.key()
        self.put('Triggers', key, f'{owner},<none>,{name},{int(disabled)},1,1,1,0')
        self.put('Tags', tag, f'{persistence},{name},{key}')
        self.put('Events', key, ','.join(map(str, [len(events), *(
            token for event in events for token in event)])))
        value = ','.join([str(len(actions)), *(token for action in actions for token in action)])
        if len((key + '=' + value).encode('cp1252', errors='replace')) > 511:
            raise ValueError('Final Fortress action exceeds the native INI parser limit.')
        self.put('Actions', key, value)
        return key, tag

    def team(self, name, units, owner_waypoint, *, attack=True, owner=None):
        # Native recruitment matches only the first TaskForce row of a type.
        # A repeated row can leave the last spawned FootClass without a team;
        # Reinforce dereferences that null Team pointer at native 0065D99F.
        counts = {}
        for unit in units:
            count = unit['count']
            if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
                raise ValueError('A native TaskForce requires positive integer unit counts.')
            counts[unit['type']] = counts.get(unit['type'], 0) + count
        units = [{'type': kind, 'count': count} for kind, count in counts.items()]
        if not 1 <= len(units) <= 6:
            raise ValueError('A native TaskForce supports 1–6 different unit types.')
        team = self.key()
        append_section_list_entry(self.lines, 'TeamTypes', team)
        composition = tuple((unit['type'], unit['count']) for unit in units)
        force = self._task_force_cache.get(composition)
        if force is None:
            force = self._task_force_cache[composition] = self.key()
            append_section_list_entry(self.lines, 'TaskForces', force)
            self.put(force, 'Name', name)
            self.put(force, 'Group', -1)
            for index, unit in enumerate(units):
                self.put(force, index, f'{unit["count"]},{unit["type"]}')
        # Attack immediately. Moving onto the original MCV waypoint first can
        # wait forever after the construction yard occupies that destination.
        script = self._script_cache.get(attack)
        if script is None:
            script = self._script_cache[attack] = self.key()
            append_section_list_entry(self.lines, 'ScriptTypes', script)
            self.put(script, 'Name', 'Fortress attack orders' if attack else 'Fortress guard orders')
            if attack:
                self.put(script, 0, '0,1')
                self.put(script, 1, '6,1')
            else:
                self.put(script, 0, '11,5')
        values = {
            'Name': name, 'House': owner or _owner(owner_waypoint), 'TaskForce': force,
            'Script': script, 'Waypoint': _waypoint(owner_waypoint),
            'Max': '1', 'Priority': '50', 'Group': '-1', 'TechLevel': '0',
            'Autocreate': 'no', 'Prebuild': 'no', 'Recruiter': 'no',
            'AreTeamMembersRecruitable': 'no', 'Reinforce': 'no',
            # Full=yes packs reinforcement teammates into transports before
            # placement, bypassing normal passenger size/capacity checks.
            # Loadable=no only blocks later boarding; Full=no keeps every
            # scripted arrival outside transports, including tanks beside IFVs.
            'LooseRecruit': 'no', 'Full': 'no', 'Whiner': 'no',
            'Suicide': 'yes' if attack else 'no', 'Aggressive': 'yes',
            # Scripted gifts must consider all hostile houses, just like the
            # installed AI teams. A helper's primary-enemy selection can be
            # unset or unsuitable while its initial army is being assigned.
            'AvoidThreats': 'no', 'OnlyTargetHouseEnemy': 'no',
            'VeteranLevel': '1', 'Loadable': 'no', 'OnTransOnly': 'no',
        }
        for key, value in values.items():
            self.put(team, key, value)
        return team

    def wave_types(self, groups, rules, overrides=None, *, aliases=None):
        """Private native copies let absence checks survive AI team disbanding.

        Native AI team removal strips member tags before some death callbacks.
        Type identities remain observable after capture or team replacement.
        Deployment conversions stay within the same tracked wave identities.
        """
        infantry = set(rules['InfantryTypes'].values())
        vehicles = set(rules['VehicleTypes'].values())
        aliases = {} if aliases is None else aliases
        visited = set()

        def register(original):
            if original in visited:
                return aliases[original]
            category = ('InfantryTypes' if original in infantry else
                        'VehicleTypes' if original in vehicles else None)
            if category is None:
                raise ValueError(f'Wave type {original} must be installed ground infantry or vehicle.')
            from .native import scripted_unit_row
            row = scripted_unit_row(original, (overrides or {}).get(original, rules[original]),
                                    getattr(self, 'scripted_weapons', {}))
            payload = row.get('InitialPayload.Types', '').strip()
            if payload and payload.lower() != 'none':
                raise ValueError(f'Wave type {original} creates unbudgeted passengers; choose another unit.')
            spawn = row.get('Spawns', '').strip()
            # Perks/Challenges redirect Spawns to private missile copies. Read
            # their generated definitions too; the installed registry only
            # knows native IDs such as V3ROCKET.
            spawn_row = {**rules.get(spawn, {}), **self.sections.get(spawn, {})}
            if spawn and spawn.lower() != 'none' and str(
                    spawn_row.get('MissileSpawn', 'no')).strip().lower() not in {'yes', 'true', '1'}:
                raise ValueError(f'Wave type {original} creates unbudgeted aircraft; choose another unit.')
            if row.get('DeploysInto', '').lower() not in ('', 'none'):
                raise ValueError(f'Wave type {original} deploys into a building; tracking is not configured.')
            alias = aliases.get(original) or self.key()
            aliases[original] = alias
            visited.add(original)
            _register_map_type(self.sections, self.lines, rules, category, alias)
            native = rules.get('_FortressNativeRegistries', {}).get(category, rules[category])
            registered = list(dict.fromkeys([
                *native.values(), *section_value_map(self.lines, category).values(),
                *self.sections.get(category, {}).values()]))
            if registered.index(alias) >= 512:
                raise ValueError(f'Fortress {category} survivor counter exceeds the native 512-type limit.')
            row.update({'Image': row.get('Image', original), 'TechLevel': '-1',
                        'BuildLimit': '0', 'Crewed': 'no',
                        'AllowedToStartInMultiplayer': 'no',
                        'Insignificant': 'no', 'DontScore': 'no'})
            for field in ('Convert.Deploy', 'Convert.Land', 'Convert.Water'):
                target = row.get(field, '').strip()
                if target and target.lower() != 'none':
                    row[field] = register(target)
            self.sections[alias] = row
            return alias

        for group in groups:
            for unit in group['units']:
                register(unit['type'])
        return aliases

    def reinforce(self, team):
        """Use the native explicit-waypoint action for scripted arrivals.

        Action 7 passes -1 as the placement override. Action 80 passes the
        actual waypoint and enables native placement around that cell. Keep
        both the action and TeamType anchored to the same arrival location.
        """
        return _action(80, team=team, waypoint=self.sections[team]['Waypoint'])

    def finish(self, *, replace_sections=()):
        from randomizer.maps.ini import find_section_bounds
        for section in replace_sections:
            start, end = find_section_bounds(self.lines, section)
            if start is not None:
                self.lines[start + 1:end] = []
        if 'Countries' in self.sections:
            from randomizer.maps.ini import find_section_bounds
            start, end = find_section_bounds(self.lines, 'Countries')
            if start is not None:
                self.lines[start + 1:end] = []
            if len(self.sections['Countries']) > 32:
                raise ValueError('Fortress exceeded the native 32-country limit.')
        for key, value in self.sections.get('Actions', {}).items():
            if len((key + '=' + value).encode('cp1252', errors='replace')) > 511:
                raise ValueError('Final Fortress action exceeds the native INI parser limit.')
        merge_ini_section_values(self.lines, self.sections)
        if 'Countries' in self.sections:
            # Country indices are assigned by entry order, not INI key value.
            # The general merger sorts new keys lexically (0,1,10,...,2),
            # which makes spawner Side=26 select YuriCountry2 instead of our
            # Soviet FFPLAYER. Emit the complete country table numerically in
            # both the map and the global preload, before houses are allocated.
            start, end = find_section_bounds(self.lines, 'Countries')
            ordered = sorted(self.sections['Countries'].items(), key=lambda item: int(item[0]))
            if [int(key) for key, _ in ordered] != list(range(len(ordered))):
                raise ValueError('Fortress country indices must be consecutive from zero.')
            self.lines[start + 1:end] = [f'{key}={value}' for key, value in ordered]
        return ('\r\n'.join(self.lines) + '\r\n').encode('cp1252', errors='replace')


def _capacity_subsets(previous_counts, incoming, limit):
    """Minimal sets of completed waves that make room for the next wave.

    Completion flags only move from false to true. Keeping a whole wave reserved
    until all its private unit identities disappear bounds the real population.
    Eleven scheduled waves bound candidate subsets to 1,024 for the last wave.
    """
    required = sum(previous_counts) + incoming - limit
    if required <= 0:
        return [()]
    accepted = []
    for length in range(1, len(previous_counts) + 1):
        for subset in combinations(range(len(previous_counts)), length):
            if any(set(earlier).issubset(subset) for earlier in accepted):
                continue
            if sum(previous_counts[index] for index in subset) >= required:
                accepted.append(subset)
    return accepted


def _transfer_tag(writer, waypoint, name):
    trigger, tag = writer.trigger(name, [(13, 0, 0)],
                                  [_action(14, 4475 + waypoint)], persistence=2)
    writer.trigger(name + ' stop', [(13, 0, 1)], [_action(54, trigger=trigger)])
    return tag


def _place(writer, section, value):
    index = next_numeric_section_index(writer.lines, section)
    while str(index) in writer.sections.get(section, {}):
        index += 1
    writer.put(section, index, value)


def _starting_perks(writer, plan, rules, aliases=None):
    """Place faction-native grants for the human and each enabled helper."""
    from .maps import perk_layout
    from .player_perks import coalition, human_actor
    effects = plan['effects']
    aliases = aliases or {}
    if not any(effects.get(key) for key in ('starting_units', 'starting_defenses',
                                          'starting_buildings', 'defense_types', 'starting_harvesters',
                                          'starting_power_buildings')):
        return
    points = section_value_map(writer.lines, 'Waypoints')
    refinery_copies = {}

    def refinery_copy(original):
        if original in refinery_copies:
            return refinery_copies[original]
        alias = writer.key()
        effective = aliases.get(original, original)
        row = deepcopy({**rules[original], **writer.sections.get(effective, {})})
        row.update(Image=row.get('Image', original), FreeUnit='none', TechLevel='-1', BuildLimit='0')
        writer.sections[alias] = row
        _register_map_type(writer.sections, writer.lines, rules, 'BuildingTypes', alias)
        refinery_copies[original] = alias
        from .player_perks import register_building_equivalent
        register_building_equivalent(writer, rules, original, alias, aliases,
                                     preserve_native=True)
        return alias

    for name, country, waypoint in coalition(plan):
        tag = _transfer_tag(writer, waypoint, 'Starting perks ' + name)
        cell = int(points[str(waypoint)])
        start = {'x': cell % 1000, 'y': cell // 1000}
        layout = perk_layout(plan['map'], waypoint, country)
        if (effects.get('starting_buildings') or effects.get('defense_types')
                or effects.get('starting_power_buildings')) and not layout:
            raise ValueError('Configure safe starting-building and defense positions for this map.')
        staging = layout['units'] if layout else {'x': start['x'] - 4, 'y': start['y'] - 6}
        infantry = set(rules['InfantryTypes'].values())
        vehicles = set(rules['VehicleTypes'].values())
        ordinal = 0
        units = [*effects['starting_units'], *effects.get('starting_harvesters', [])]
        for unit in units:
            original = unit['type']
            kind = 'Infantry' if original in infantry else 'Units'
            if original not in infantry | vehicles:
                raise ValueError('Starting perk units must be installed infantry or vehicles.')
            for _ in range(unit['count']):
                # The 15 army slots are an audited 5x3 rectangle. Harvesters
                # arrive on the refinery's loading apron, not a sixteenth slot.
                is_harvester = unit in effects.get('starting_harvesters', [])
                if is_harvester:
                    position = layout['buildings'][2]
                    x, y = position['x'] + 1, position['y'] + 3
                else:
                    x, y = staging['x'] + ordinal % 5, staging['y'] + ordinal // 5
                experience = effects['veterancy'] if not is_harvester else 0
                # Map object experience is a percentage, unlike the
                # one-based TeamType.VeteranLevel enumeration.
                experience *= 100
                alias = aliases.get(original, original)
                mission = 'Harvest' if is_harvester else 'Guard'
                if kind == 'Infantry':
                    value = f'Neutral,{alias},256,{x},{y},0,{mission},64,{tag},{experience},-1,0,0,0'
                else:
                    value = f'Neutral,{alias},256,{x},{y},64,{mission},{tag},{experience},-1,0,-1,0,0'
                _place(writer, kind, value)
                if not is_harvester:
                    ordinal += 1
        if not human_actor(plan, name):
            army = effects['starting_units']
            for index in range(0, len(army), 6):
                team = writer.team(f'Fortress helper starting army {name} {index // 6 + 1}',
                                   [{'type': aliases.get(unit['type'], unit['type']), 'count': unit['count']}
                                    for unit in army[index:index + 6]], waypoint, owner=name)
                writer.put(team, 'Recruiter', 'yes')
                writer.put(team, 'Full', 'no')
                writer.put(team, 'VeteranLevel', effects['veterancy'] + 1)
                writer.trigger(f'Fortress helper starting orders {name} {index // 6 + 1}',
                               [(13, 0, 2)], [_action(4, team=team)], owner=name)
        defenses = list(effects['starting_defenses'])
        if len(effects.get('defense_types', [])) > len((layout or {}).get('defenses', [])):
            raise ValueError('Configure enough perimeter defense positions for this loadout.')
        defenses.extend({'type': kind, 'position': layout['defenses'][index]}
                        for index, kind in enumerate(effects.get('defense_types', [])))
        buildings = [{'type': kind, 'position': layout['buildings'][index]}
                     for index, kind in enumerate(effects.get('starting_buildings', []))]
        power = effects.get('starting_power_buildings', [])
        if len(power) > len((layout or {}).get('power', [])):
            raise ValueError('Configure enough starting power plant positions for this loadout.')
        buildings.extend({'type': kind, 'position': layout['power'][index]}
                         for index, kind in enumerate(power))
        for building in [*buildings, *defenses]:
            original = building['type']
            if original not in rules['BuildingTypes'].values():
                raise ValueError('Starting perk building must be installed.')
            alias = refinery_copy(original) if rules[original].get('FreeUnit', 'none').lower() != 'none' else aliases.get(original, original)
            position = building['position']
            _place(writer, 'Structures', f'Neutral,{alias},256,{position["x"]},'
                   f'{position["y"]},64,{tag},1,0,1,0,0,None,None,None,0,0')


def _enemy_challenges(writer, plan, rules):
    """Private country derivatives preserve the human's original country stats.

    Copy native faction fields, but retain an independent country identity for
    the installed Phobos AI selector. Explicit production masks handle access.
    The native armor, speed and build-time country multipliers affect normal
    AI production as well as scripted reinforcements from the opening frame.
    """
    start_index = max(map(int, rules['Countries'])) + 1
    fields = {
        'armor': ('ArmorInfantryMult', 'ArmorUnitsMult', 'ArmorAircraftMult',
                  'ArmorBuildingsMult', 'ArmorDefensesMult'),
        'speed': ('SpeedInfantryMult', 'SpeedUnitsMult'),
        'production': ('BuildTimeInfantryMult', 'BuildTimeUnitsMult',
                       'BuildTimeAircraftMult', 'BuildTimeBuildingsMult', 'BuildTimeDefensesMult'),
    }
    for index, country in enumerate(plan['enemy_countries']):
        alias = f'FFENEMY{index + 1}'
        row = deepcopy(rules[country])
        row.update(ParentCountry=alias, Multiplay='no')
        writer.put('FFCountryOrigins', alias, country)
        for challenge in plan.get('challenges', []):
            if 'enemy_effect_id' in challenge:
                continue
            factor = (1 - challenge['percent'] / 100 if challenge['effect'] == 'production'
                      else 1 + challenge['percent'] / 100)
            for field in fields[challenge['effect']]:
                key = next((key for key in row if key.casefold() == field.casefold()), field)
                row[key] = str(float(row.get(key, '1')) * factor)
        from .challenges import apply_country
        apply_country(row, plan.get('challenges', []))
        writer.put('Countries', start_index + index, alias)
        writer.sections[alias] = row


def _camps(writer, plan, rules, marker_teams, finished, overrides=None, player_aliases=None,
           guard_types=None):
    infantry = set(rules['InfantryTypes'].values())
    pickup = True
    if plan['map']['camps']:
        # Scripted claims deliver the frozen reward to the human recipient.
        # Suppress native crate money so collecting it cannot pay twice.
        writer.put('CrateRules', 'SoloCrateMoney', 0)
        writer.put('CrateRules', 'RandomCrateMoney', 0)
        writer.put('Powerups', 'Money', '0,MONEY,yes,0')
    for index, camp in enumerate(plan['map']['camps']):
        from .camps import guard_positions
        if 'position' not in camp:
            raise ValueError('Camp position and guards must be configured before launch.')
        position = camp['position']
        waypoint = 20 + index
        _waypoint(waypoint)
        writer.put('Waypoints', waypoint, position['y'] * 1000 + position['x'])
        if camp.get('starter_camp') and any(
                unit['type'] not in infantry or str(rules[unit['type']].get('TechLevel')) != '1'
                for unit in camp['guards']):
            raise ValueError('Starter camps require installed basic Tier 1 infantry.')
        aliases = writer.wave_types([{'units': camp['guards']}], rules, overrides,
                                    aliases=guard_types[index] if guard_types is not None else None)
        owner_waypoint = plan['map']['enemy_waypoints'][camp['enemy_index']]
        country = f'FFENEMY{camp["enemy_index"] + 1}'
        cleared = writer.flag('Camp ' + camp['id'] + (' ready' if pickup else ' cleared'))
        if pickup:
            # Crates and claims become available at startup. Guard death events
            # have fired prematurely in live games; collection alone pays out.
            clear, _ = writer.trigger('Camp ' + camp['id'] + ' ready', [(13, 0, 0)], [])
            tag = _transfer_tag(writer, owner_waypoint, 'Camp ' + camp['id'] + ' ownership')
            transfer = writer.sections['Tags'][tag].split(',')[2]
        else:
            clear, tag = writer.trigger('Camp ' + camp['id'] + ' cleared',
                                       [(37, 0, finished), (48, 0, 0)], [],
                                       owner=country, persistence=1)
            # Preserve death-based receipts for frozen plans through version 24.
            transfer, _ = writer.trigger('Camp ' + camp['id'] + ' ownership',
                                        [(0, 0, 0)], [_action(14, 4475 + owner_waypoint)])
            # Action 14 visits every object whose tag contains this linked trigger.
            writer.trigger('Camp ' + camp['id'] + ' ownership start',
                           [(13, 0, 0)], [_action(22, trigger=transfer)])
            writer.put('Triggers', clear,
                       f'{country},{transfer},Camp {camp["id"]} cleared,0,1,1,1,0')
        writer.put('FFCampTracking', camp['id'],
                   f'{clear},{tag},{transfer},{sum(unit["count"] for unit in camp["guards"])}')
        for alias in aliases.values():
            writer.sections[alias].update({
                'CanPassiveAquire': 'yes', 'CanRetaliate': 'yes',
                'OpportunityFire': 'no', 'GuardRange': '6', 'DefaultToGuardArea': 'yes',
                'ImmuneToPsionics': 'yes', 'ImmuneToAbduction': 'yes', 'CanBeReversed': 'no',
                'VehicleThief.Allowed': 'no',
                'Convert.Deploy': 'none', 'Convert.Land': 'none', 'Convert.Water': 'none'})
        ordinal = 0
        positions = guard_positions(camp)
        for unit in camp['guards']:
            alias = aliases[unit['type']]
            for _ in range(unit['count']):
                # Leave the center cell free for the reward crate and claim.
                x, y = positions[ordinal]['x'], positions[ordinal]['y']
                mission = 'Area Guard'
                if unit['type'] in infantry:
                    value = f'Neutral,{alias},256,{x},{y},0,{mission},64,{tag},0,-1,0,0,0'
                    section = 'Infantry'
                else:
                    value = f'Neutral,{alias},256,{x},{y},64,{mission},{tag},0,-1,0,-1,0,0'
                    section = 'Units'
                _place(writer, section, value)
                ordinal += 1
        from .coop_map import camp_claims
        camp_claims(writer, plan, rules, camp, index, waypoint, cleared,
                    marker_teams, finished, clear, player_aliases or {})


def _camp_squad(writer, plan, camp, waypoint, start, owner, aliases):
    """Deliver every frozen reward type with explicit native cell placement."""
    units = [{'type': aliases.get(unit['type'], unit['type']), 'count': unit['count']}
             for unit in camp['crate_reward']['units']]
    pickup = True
    groups = [[unit] for unit in units] if pickup else [units]
    actions = []
    for index, group in enumerate(groups):
        name = 'Player camp reward ' + camp['id']
        if plan.get('coop_players'):
            name += ' ' + owner
        if pickup:
            name += f' group {index + 1}'
        team = writer.team(name, group, start, attack=False, owner=owner)
        writer.put(team, 'Waypoint', _waypoint(waypoint))
        actions.append(writer.reinforce(team) if pickup else _action(7, team=team))
    return actions


def _cash_reward(writer, plan, rules, camp, claimed, index, *, waypoint=None):
    """Player-gated cash without allowing native AI crate pickups to profit."""
    alias = writer.key()
    row = deepcopy(rules['CABHUT'])
    row.update({'Image': 'CABHUT', 'Name': 'Final Fortress reward escrow',
                'InvisibleInGame': 'yes', 'IsPassable': 'yes', 'Immune': 'yes',
                'LegalTarget': 'no', 'Selectable': 'no', 'Capturable': 'no',
                'Insignificant': 'no', 'DontScore': 'no', 'KeepAlive': 'no', 'RadarInvisible': 'yes',
                'ProduceCashStartup': str(camp['crate_reward']['credits']),
                'ProduceCashAmount': '0', 'ProduceCashDelay': '0',
                'Unsellable': 'yes', 'CanBeOccupied': 'no', 'TechLevel': '-1'})
    writer.sections[alias] = row
    _register_map_type(writer.sections, writer.lines, rules, 'BuildingTypes', alias)
    _, tag = writer.trigger('Cash reward ' + camp['id'], [(36, 0, claimed)],
                            [_action(14, 4475 + (plan['map']['player_waypoint']
                                                if waypoint is None else waypoint))])
    # A persistent tag with a latched Local Set event can keep the native
    # TeamLeavesMap cleanup loop on this same tag forever after payment.
    # Consume the default one-shot tag after its single ownership transfer.
    # An unused skirmish start keeps the passable escrow away from the fight.
    points = section_value_map(writer.lines, 'Waypoints')
    unused = next(number for number in range(8) if number not in {
        plan['map']['player_waypoint'], *plan['map']['enemy_waypoints'],
        *plan.get('allied_waypoints', [])})
    cell = int(points[str(unused)])
    x, y = cell % 1000 + index, cell // 1000
    from .coop_map import escrow_cell
    x, y = escrow_cell(writer, plan, rules, cell)
    _place(writer, 'Structures', f'Neutral,{alias},256,{x},{y},'
           f'64,{tag},1,0,1,0,0,None,None,None,0,0')


def build_map(game_root, run, rules, *, preloads=None):
    """Generate bytes only; never modify the original installed map."""
    # The installed registries retain inactive IDs (for example YADEPT)
    # without corresponding definitions. Clone only defined types, retaining
    # the original registry indices and every authored definition unchanged.
    rules = dict(rules)
    for category in ('BuildingTypes', 'VehicleTypes', 'InfantryTypes', 'AircraftTypes'):
        rules[category] = {index: kind for index, kind in rules[category].items()
                           if kind in rules}
    plan = run['plan']
    definition = plan['map']
    inspect_map(game_root, definition)
    if len(plan['wave_schedule']) > MAX_SCRIPTED_WAVES:
        raise ValueError(f'The engine adapter supports at most {MAX_SCRIPTED_WAVES} waves.')
    lines = source_lines(game_root, definition)
    if any(section_value_map(lines, section) for section in ('Triggers', 'VariableNames')):
        raise ValueError('Final Fortress requires a source without authored triggers or variables.')
    writer = _MapWriter(lines, definition['player_waypoint'])
    finished = writer.flag('Final Fortress finished')
    marker_teams = {}
    for event, name in marker_names(run['id'], plan).items():
        team, force, script = writer.key(), writer.key(), writer.key()
        # Neutral remains available even when destruction defeats the human in
        # the same frame. Empty marker teams never affect combat or economy.
        append_hook_team(lines, team, force, script, name, 'Neutral')
        marker_teams[event] = team

    # Each AI receives one inert, untargetable controller. It keeps skirmish
    # elimination from awarding victory before the survival timer expires.
    # These three fixed controllers never produce units or enter wave counts.
    controller_type = 'FFCONTROLLER'
    controller = deepcopy(rules['E1'])
    controller.update({
        'Image': controller.get('Image', 'E1'), 'Name': 'Final Fortress controller', 'TechLevel': '-1',
        'Primary': 'none', 'Secondary': 'none', 'ElitePrimary': 'none',
        'EliteSecondary': 'none', 'Speed': '0', 'Invisible': 'yes',
        'Immune': 'yes', 'LegalTarget': 'no', 'Selectable': 'no',
        'RadarInvisible': 'yes', 'Insignificant': 'no', 'DontScore': 'no',
        'AllowedToStartInMultiplayer': 'no', 'ImmuneToPsionics': 'yes',
        'ImmuneToRadiation': 'yes', 'ImmuneToPoison': 'yes',
        'Crushable': 'no', 'CanBeReversed': 'no', 'BuildLimit': '0',
        'DeploysInto': 'none', 'Deployer': 'no', 'DeathWeapon': 'none',
    })
    writer.sections[controller_type] = controller
    _register_map_type(writer.sections, lines, rules, 'InfantryTypes', controller_type)
    startup = [_action(4, team=marker_teams['started'])]
    # Timer Set (27) clears the native caption as well as setting the duration.
    # Apply Timer Text last, after both setting and starting the countdown.
    # Values are simulation seconds, like the elapsed-time victory gate.
    writer.trigger('Final Fortress countdown', [(13, 0, 0)], [
        _action(27, plan['survival_seconds']), _action(23),
        ['103', '4', 'NOSTR:Until Victory', '0', '0', '0', '0', 'A']])
    for enemy_index, waypoint in enumerate(definition['enemy_waypoints']):
        team = writer.team('Final Fortress AI controller',
                           [{'type': controller_type, 'count': 1}], waypoint, attack=False,
                           owner=f'FFENEMY{enemy_index + 1}')
        startup.append(writer.reinforce(team))
    writer.trigger('Final Fortress start', [(13, 0, 1)], startup)

    # Use a private copy so other installed buildings retain native behavior.
    building_type = 'FFOBJECTIVE'
    building = definition['protected_building']
    objective = deepcopy(rules[building['type']])
    if plan['effects'].get('lab_health_percent'):
        # Change only this private objective. Its initial health stays full;
        # native damage thresholds and emergency repair use the new Strength.
        objective['Strength'] = str(int(objective['Strength']) * (100 + plan['effects']['lab_health_percent']) // 100)
    objective.update({'Image': objective.get('Image', building['type']), 'Name': 'Final Fortress',
                      'Insignificant': 'no', 'Selectable': 'yes',
                      'Capturable': 'no', 'CanBeOccupied': 'no', 'Unsellable': 'yes',
                      'ImmuneToPsionics': 'yes', 'Chronoshift.Allow': 'no',
                      'UndeploysInto': 'none', 'LeaveRubble': 'no', 'Warpable': 'no',
                      'ImmuneToAbduction': 'yes', 'ImmuneToTemporal': 'yes'})
    objective.update({'ProduceCashStartup': str(plan['effects']['starting_credits']),
                      'ProduceCashAmount': '0', 'ProduceCashDelay': '0'})
    writer.sections[building_type] = objective
    _register_map_type(writer.sections, lines, rules, 'BuildingTypes', building_type)
    loss_trigger, loss_tag = writer.trigger('Final Fortress objective destroyed', [(48, 0, 0)], [
        _action(56, finished), _action(4, team=marker_teams['defeat']), _action(68)], persistence=2)
    writer.put('Actions', loss_trigger, '4,' + ','.join(
        _action(56, finished) + _action(54, trigger=loss_trigger)
        + _action(4, team=marker_teams['defeat']) + _action(68)))
    transfer, _ = writer.trigger('Final Fortress objective ownership', [(13, 0, 0)], [
        _action(14, 4475 + definition['player_waypoint'])])
    writer.put('Triggers', loss_trigger,
               f'<none>,{transfer},Final Fortress objective destroyed,0,1,1,1,0')
    writer.put('Actions', transfer, '2,' + ','.join(
        _action(14, 4475 + definition['player_waypoint'])
        + _action(54, trigger=transfer)))
    position = building['position']
    # Native skirmish objects start Neutral. The linked ownership action uses
    # the installed cooperative maps' Player-at-location transfer mechanism.
    key = next_numeric_section_index(lines, 'Structures')
    writer.put('Structures', key,
               f'Neutral,{building_type},256,{position["x"]},'
               f'{position["y"]},64,{loss_tag},1,0,1,0,0,None,None,None,0,0')
    writer.trigger('Final Fortress survival victory',
                   [(13, 0, plan['survival_seconds']), (37, 0, finished)], [
                       _action(56, finished), _action(4, team=marker_teams['victory']), _action(67)])

    for milestone in plan['milestones']:
        writer.trigger('Survival ' + milestone['id'],
                       [(13, 0, milestone['seconds']), (37, 0, finished)],
                       [_action(4, team=marker_teams['milestone:' + milestone['id']])])

    from .challenges import apply_units, load_ai_rules
    from .player_perks import apply_player_types, gate_prerequisite_overrides, route_ai, support_powers
    before_perk_rules = deepcopy(writer.sections)
    writer.sections['Countries'] = dict(rules['Countries'])
    _enemy_challenges(writer, plan, rules)
    has_unit_challenges = any('enemy_effect_id' in entry and entry['enemy_effect_id'].startswith('tier')
                              for entry in plan.get('challenges', []))
    ai_rules = load_ai_rules()
    reserved_player_types = {}
    # Native house ownership counters hold only 512 entries per category.
    # Reserve camps before the large player/challenge/pool registries so their
    # Event 61 checks never read an untracked high-index vehicle. Preload these
    # identities before houses are constructed, then refresh challenge stats.
    guard_types = [writer.wave_types([{'units': camp['guards']}], rules)
                   for camp in definition['camps']]
    reserved_friendly_types = None
    if plan.get('reinforcement_schedule'):
        from .friendly_pool import reserve_pool_types
        reserved_friendly_types = reserve_pool_types(writer, plan, rules)
    from .wave_pool import reserve_pool_types as reserve_enemy_pool_types
    reserved_enemy_types = reserve_enemy_pool_types(writer, plan, rules)
    enemy_aliases = {}
    overrides = apply_units(writer, plan, rules, ai_rules, route_ai=False,
                            aliases_out=enemy_aliases) if has_unit_challenges else {}
    from .enemy_bases import protect_enemy_buildings, place_fortifications
    protect_enemy_buildings(writer, plan, rules, enemy_aliases)
    for field in ('BaseUnit', 'HarvesterUnit'):
        native = writer.sections.get('General', {}).get(field, rules['General'].get(field, '')).split(',')
        additions = [enemy_aliases[unit] for unit in native if unit in enemy_aliases]
        if additions:
            writer.put('General', field, ','.join(dict.fromkeys([*native, *additions])))
    player_aliases = apply_player_types(writer, plan, rules, reserved_aliases=reserved_player_types)
    from .secret_labs import apply_secret_labs
    apply_secret_labs(writer, plan, rules, player_aliases, enemy_aliases)
    from .reinforcements import reserve_staging
    reserve_staging(writer, plan, rules)
    place_fortifications(writer, plan, rules, enemy_aliases)
    _starting_perks(writer, plan, rules, player_aliases)
    support_powers(writer, plan, rules, player_aliases)
    from .economy import apply_fundraising
    apply_fundraising(writer, plan, rules, finished)
    from .lab_support import apply_lab_support
    apply_lab_support(writer, plan, rules, player_aliases, finished, loss_trigger)
    from .enemy_powers import apply_enemy_powers
    apply_enemy_powers(writer, plan, rules, enemy_aliases)
    from .wave_clock import create_wave_clock, create_friendly_clocks
    wave_clock = create_wave_clock(writer, plan, rules, finished)
    friendly_clocks = create_friendly_clocks(writer, plan, rules, finished)
    if plan['effects'].get('reveal_map') and not plan.get('coop_players'):
        writer.trigger('Final Fortress satellite intelligence', [(13, 0, 1)], [_action(16)])
    ai_sections = route_ai(writer, plan, rules, ai_rules, enemy_aliases, player_aliases)
    _camps(writer, plan, rules, marker_teams, finished, overrides, player_aliases,
           guard_types=guard_types)
    gate_prerequisite_overrides(writer, plan, rules)
    from .native import validate_production_houses, validate_player_roster
    validate_production_houses(writer, plan, rules)
    validate_player_roster(writer, plan, rules, player_aliases)
    if reserved_friendly_types:
        from .reinforcements import reinforcement_overrides
        friendly_overrides = reinforcement_overrides(writer, player_aliases)
        for aliases in reserved_friendly_types:
            writer.wave_types([{'units': plan['effects']['reinforcements']['units']}],
                               rules, friendly_overrides, aliases=aliases)
    if preloads is not None:
        map_only = {'Structures', 'Units', 'Infantry', 'Aircraft', 'Triggers', 'Tags', 'Events',
                    'Actions', 'VariableNames', 'CellTags', 'Waypoints', 'TaskForces', 'TeamTypes',
                    'ScriptTypes', 'AITriggerTypes', 'AITriggerTypesEnable', 'FFSpecialAccess', 'FFEnemyPowers',
                    'FFPlayerTypes', 'FFEnemyBuildings', 'FFEnemyBaseUnits', 'FFEnemyFortifications',
                    'FFEnemyStartingYards', 'Smudge',
                    'FFCountryOrigins',
                    'FFReinforcementPads', 'FFEnemyWavePads', 'FFWaveClock',
                    'FFCampTracking', 'FFLabSupport', 'FFFundraising'}
        changed = {section: {key: value for key, value in values.items()
                            if before_perk_rules.get(section, {}).get(key) != value}
                   for section, values in writer.sections.items() if section not in map_only
                   and not section.startswith('FFAlliedClock') and section not in ai_sections}
        preloads['rules'] = {key: row for key, row in changed.items() if row}
        preloads['ai'] = ai_sections
    from .reinforcements import apply_reinforcements
    apply_reinforcements(writer, plan, rules, player_aliases, finished, friendly_clocks=friendly_clocks,
                         reserved_types=reserved_friendly_types)

    from .wave_pool import apply_wave_pool
    apply_wave_pool(writer, plan, rules, overrides, marker_teams, finished, wave_clock=wave_clock,
                    reserved_types=reserved_enemy_types)
    writer.put('Basic', 'Name', 'Final Fortress - ' + definition['display_name'])
    writer.put('Basic', 'IgnoreGlobalAITriggers', 'no')
    writer.put('SpecialFlags', 'FixedAlliance', 'yes')
    from .placement import validate_camp_access, validate_enemy_arrivals
    validate_enemy_arrivals(writer, plan)
    validate_camp_access(writer, plan)
    from .placement import validate_placements
    validate_placements(writer, rules, plan)
    return writer.finish()


def spawn_data(plan, map_data, *, game_speed=2):
    """One human, three hostile AIs, and up to two friendly skirmish AIs."""
    from .player_perks import needs_countries
    if type(game_speed) is not int or not 0 <= game_speed <= 6:
        raise ValueError('Invalid game speed.')
    game_id = int(hashlib.sha256(plan['seed'].encode('utf-8')).hexdigest()[:8], 16) % (2**31 - 1) + 1
    sections = {'Settings': {
        'Name': 'Commander', 'Scenario': 'spawnmap.ini', 'UIGameMode': 'Final Fortress',
        'UIMapName': plan['map']['display_name'], 'PlayerCount': '1',
        'AIPlayers': str(3 + len(plan.get('allied_countries', []))),
        'Seed': str(game_id), 'GameID': str(game_id), 'Host': 'Yes', 'IsSinglePlayer': 'No',
        'Side': str(SIDE_COUNTRIES.index(plan['player_country'])), 'Color': '0',
        'IsSpectator': 'No', 'GameSpeed': str(game_speed), 'ShortGame': 'No',
        'AutoSurrender': 'No', 'BuildOffAlly': 'No', 'FrameSendRate': '7', 'Protocol': '2',
        'FogOfWar': 'No', 'MultiEngineer': 'Yes', 'UnitCount': '0', 'Credits': '10000',
        'TechLevel': '10', 'Bases': 'Yes', 'Crates': 'No',
        'MapSHA1': hashlib.sha1(map_data).hexdigest(),
    }, 'SpawnLocations': {'Multi1': str(plan['map']['player_waypoint'])}}
    countries = section_value_map(IniLines(map_data.decode('latin-1').splitlines()), 'Countries')
    # The native registry assigns indices by physical entry order. INI keys
    # are labels, so never infer a spawner index from their numeric spelling.
    indices = {country: index for index, country in enumerate(countries.values())}
    private_player = needs_countries(plan)
    def private_country_index(alias):
        return indices[alias]
    sections['Settings']['Side'] = str(indices['FFPLAYER' if private_player else plan['player_country']])
    friends = [0, *range(4, 4 + len(plan.get('allied_countries', [])))]
    ordinals = ('One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven')
    for actor in friends:
        sections[f'Multi{actor + 1}_Alliances'] = {
            f'HouseAlly{ordinal}': str(other)
            for ordinal, other in zip(ordinals, (other for other in friends if other != actor))}
    for index, country in enumerate(plan['enemy_countries'], 2):
        house = f'Multi{index}'
        country_index = indices.get(f'FFENEMY{index - 1}', indices[country])
        sections.setdefault('HouseCountries', {})[house] = str(country_index)
        sections.setdefault('HouseColors', {})[house] = str(index - 1)
        sections.setdefault('HouseHandicaps', {})[house] = str(2 - plan['engine_difficulty'])
        sections['SpawnLocations'][house] = str(plan['map']['enemy_waypoints'][index - 2])
        sections[house + '_Alliances'] = {
            f'HouseAlly{ordinal}': str(other - 1)
            for ordinal, other in zip(('One', 'Two'), (other for other in range(2, 5) if other != index))}
    for index, waypoint in enumerate(plan.get('allied_waypoints', []), 1):
        house = f'Multi{index + 4}'
        sections.setdefault('HouseCountries', {})[house] = str(private_country_index(f'FFALLY{index}'))
        sections.setdefault('HouseColors', {})[house] = str((4, 6)[index - 1])
        sections.setdefault('HouseHandicaps', {})[house] = str(2 - plan['engine_difficulty'])
        sections['SpawnLocations'][house] = str(waypoint)
    from .colors import remap_colors
    remap_colors(sections, plan)
    return '\r\n'.join(line for section, values in sections.items()
                       for line in (f'[{section}]', *(f'{key}={value}' for key, value in values.items()), '')).encode('cp1252', errors='replace')


def prepare_game(game_root, run, rules, *, game_speed=2, coop_slot=None, endpoints=None):
    """Write leased runtime files only after the player requests launch."""
    preloads = {}
    map_data = build_map(game_root, run, rules, preloads=preloads)
    if coop_slot is None:
        spawn = spawn_data(run['plan'], map_data, game_speed=game_speed)
    else:
        from .coop import spawn_data as coop_spawn_data
        spawn = coop_spawn_data(run['plan'], map_data, slot=coop_slot,
                                endpoints=endpoints, game_speed=game_speed)
    root = Path(game_root)
    atomic_write_text(root / 'spawnmap.ini', map_data.decode('latin-1'), encoding='latin-1')
    if preloads['rules']:
        # Multiplayer houses are allocated before map-local countries load.
        # Preload private countries and perk types using the complete installed
        # rules cache, under the existing runtime lease/cleanup.
        target = root / 'rulesmd.ini'
        marker = '; Generated by C&C Reloaded Randomizer Launcher'
        if target.exists() and not target.read_text(
                encoding='utf-8', errors='ignore').startswith(marker):
            raise ValueError('Cannot replace an existing custom rulesmd.ini for enemy challenges.')
        source = target if target.is_file() else CAMEO_CACHE_DIR / 'rulesmd.ini'
        preload = _MapWriter(IniLines(source.read_text(
            encoding='utf-8', errors='ignore').splitlines()))
        preload.sections.update(preloads['rules'])
        text = preload.finish().decode('latin-1')
        atomic_write_text(target, marker + ' Final Fortress country preload\r\n' + text,
                          encoding='latin-1')
    if preloads['ai']:
        target = root / 'aimd.ini'
        marker = '; Generated by C&C Reloaded Randomizer Launcher Final Fortress AI preload'
        if target.exists() and not target.read_text(
                encoding='utf-8', errors='ignore').startswith(marker):
            raise ValueError('Cannot replace an existing custom aimd.ini for enemy tier challenges.')
        preload = _MapWriter(IniLines((CAMEO_CACHE_DIR / 'aimd.ini').read_text(
            encoding='utf-8', errors='ignore').splitlines()))
        preload.sections.update(preloads['ai'])
        atomic_write_text(target, marker + '\r\n' + preload.finish(
            replace_sections=('AITriggerTypes', 'AITriggerTypesEnable')).decode('latin-1'), encoding='latin-1')
    atomic_write_text(root / 'spawn.ini', spawn.decode('latin-1'), encoding='latin-1')
    return hashlib.sha256(map_data).hexdigest()


def cleanup_ai_preload(game_root):
    path = Path(game_root) / 'aimd.ini'
    if path.is_file() and path.read_text(encoding='utf-8', errors='ignore').startswith(
            '; Generated by C&C Reloaded Randomizer Launcher Final Fortress AI preload'):
        path.unlink()
