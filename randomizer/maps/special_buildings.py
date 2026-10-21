"""Map-local engine hooks required by player-owned special buildings."""

from math import floor

from randomizer.config.tuning import stacking_amount
from randomizer.core.collections import comma_items, unique_in_order
from randomizer.maps.base import _collision_safe_type_id
from randomizer.maps.buff_values import _register_map_type
from randomizer.maps.ini import (
    all_section_value_maps, section_value_map_preserve,
)
from randomizer.maps.production import PLAYER_ORIGINAL_PRODUCTION_GATE_ID
from randomizer.rewards.catalogue import (
    BUFF_TARGETS, canonical_rewards, effective_buff_count,
)


REPROCESSOR_SOURCE_ID = 'FAREPR'
REPROCESSOR_BOUNTY_SECTION = 'General'
REPROCESSOR_BOUNTY_KEY = 'BountyEnablers'
REPROCESSOR_BOUNTY_CATEGORIES = frozenset({
    'infantry', 'units', 'aircraft',
})
ORE_PURIFIER_SOURCE_ID = 'GAOREP'
DEFAULT_REFINERY_MINER_IDS = {
    'GAREFN': 'CMIN',
    'NAREFN': 'HARV',
    'TSPROC': 'TSHARV',
    'TSPROC2': 'TSNHARV',
}


def _section_values(sections, section):
    wanted = str(section).lower()
    return next(
        (
            {
                str(key).lower(): str(value)
                for key, value in values.items()
            }
            for name, values in (sections or {}).items()
            if str(name).lower() == wanted
        ),
        {},
    )


def _effective_section_values(map_sections, installed_sections, section):
    values = _section_values(installed_sections, section)
    values.update(_section_values(map_sections, section))
    return values


def power_plant_bonus_rules(lines, rewards, installed_sections):
    """Enhance actual native and cloned plants without changing mission IDs.

    Basic power plants retain their native BuildingType so authored build,
    existence, and destruction checks still recognize them. Registered reward
    clones are included by their actual runtime IDs as well; GroupAs only
    provides selection grouping, not an alias for exact-type mission checks.
    """
    active = [reward for reward in canonical_rewards(rewards)
              if reward.get('buff_type') == 'power_output']
    if not active:
        return {}, (), {}
    stacks = effective_buff_count(active[0], len(active))
    bonus = int(stacking_amount('power_output', stacks))
    if not bonus:
        return {}, (), {}
    sections = all_section_value_maps(lines)
    registered = unique_in_order([
        *(_section_values(installed_sections, 'BuildingTypes').values()),
        *(_section_values(sections, 'BuildingTypes').values()),
    ])
    buildings = {
        building: _effective_section_values(sections, installed_sections, building)
        for building in registered
    }
    upgrade_power = {}
    for values in buildings.values():
        power = int(values.get('power', '0'))
        hosts = comma_items(values.get('powersupbuilding', ''))
        hosts.extend(comma_items(values.get('powersup.buildings', '')))
        if power > 0:
            for host in hosts:
                upgrade_power.setdefault(host.casefold(), set()).add(power)
    groups, targets = {}, {}
    for building, values in buildings.items():
        power = int(values.get('power', '0'))
        if power <= 0 or values.get('powersupbuilding') or values.get('powersup.buildings'):
            continue
        upgrades = upgrade_power.get(building.casefold(), set())
        if len(upgrades) > 1:
            raise ValueError(f'{building}: mixed turbine outputs cannot share a power bonus')
        factor = 1.0 + bonus / next(iter(upgrades)) if upgrades else 1.0
        amount = power + bonus - floor(power * factor + 0.5)
        if amount < 0:
            raise ValueError(f'{building}: turbine output is too low for a safe power bonus')
        groups.setdefault((factor, amount), []).append(building)
        targets[building] = {'base': power, 'factor': factor, 'amount': amount}
    # Lookup maps lowercase every key. Never emit those normalized mappings as
    # standalone clones: the engine requires the original rules-key spelling,
    # including Strength, Image, InvisibleInGame, Power, and the enhancer tags.
    template = section_value_map_preserve(
        lines, PLAYER_ORIGINAL_PRODUCTION_GATE_ID
    )
    if not template:
        raise ValueError('Player power bonus requires the isolated startup building template')
    reserved = {name.casefold() for name in (*installed_sections, *sections)}
    rules, providers = {}, []
    for (factor, amount), plants in groups.items():
        for offset in range(0, len(plants), 20):
            provider = _collision_safe_type_id(
                f'RLRPPower{len(providers) + 1}',
                f'power-output:{len(providers) + 1}', reserved,
            )
            values = dict(template)
            values.update({
                'Name': 'Randomizer Power Plant Output',
                'UIName': 'NOSTR:Randomizer Power Plant Output',
                'PowerPlantEnhancer.PowerPlants': ','.join(plants[offset:offset + 20]),
                'PowerPlantEnhancer.Amount': str(amount),
                'PowerPlantEnhancer.Factor': format(factor, '.12g'),
            })
            rules[provider] = values
            _register_map_type(rules, lines, installed_sections, 'BuildingTypes', provider)
            providers.append(provider)
    return rules, tuple(providers), {'stacks': stacks, 'bonus': bonus, 'targets': targets}


def building_upgrade_clone_rules(lines, installed_sections, clone_handled):
    """Let native and cloned attachments upgrade every actual host identity.

    PowersUpBuilding compares exact BuildingTypes, so copying it unchanged
    leaves an attachment unable to upgrade a cloned host. Phobos supports
    multiple hosts through PowersUp.Buildings. Keep the native host available
    and add only registered production/reference clones from this launch.
    A cloned attachment uses its production host as PowersUpBuilding too,
    retaining Ares prerequisite counting on the normal player build path.
    """
    map_sections = all_section_value_maps(lines)
    registered = {
        str(identifier).upper(): str(identifier)
        for identifier in _effective_section_values(
            map_sections, installed_sections, 'BuildingTypes'
        ).values()
        if str(identifier).strip()
    }
    families = {}
    source_by_clone = {}
    primary_host_by_source = {}
    for source_id, details in (clone_handled or {}).items():
        source_id = str(source_id).upper()
        clone_ids = unique_in_order(
            str(details.get(key) or '').strip()
            for key in ('clone_id', 'reference_clone_id')
            if str(details.get(key) or '').upper() in registered
        )
        if not clone_ids:
            continue
        families[source_id] = clone_ids
        for clone_id in clone_ids:
            source_by_clone[clone_id.upper()] = source_id
        primary_id = str(details.get('clone_id') or '')
        if primary_id.upper() in registered:
            primary_host_by_source[source_id] = primary_id

    rules = {}
    for building_upper, building_id in registered.items():
        values = _effective_section_values(
            map_sections, installed_sections, building_id
        )
        primary_host = values.get('powersupbuilding', '').strip()
        authored_hosts = comma_items(values.get('powersup.buildings', ''))
        hosts = unique_in_order([
            host for host in [primary_host, *authored_hosts]
            if host and host.lower() not in {'none', '<none>'}
        ])
        expanded_hosts = list(hosts)
        for host in hosts:
            host_source = source_by_clone.get(host.upper(), host.upper())
            if host_source not in families:
                continue
            if host_source in registered:
                expanded_hosts.append(registered[host_source])
            expanded_hosts.extend(families[host_source])
        seen = set()
        unique_hosts = []
        for host in expanded_hosts:
            if host.upper() not in seen:
                seen.add(host.upper())
                unique_hosts.append(host)
        expanded_hosts = unique_hosts
        changes = {}
        if {host.upper() for host in expanded_hosts} != {
            host.upper() for host in hosts
        }:
            changes['PowersUp.Buildings'] = ','.join(expanded_hosts)
        if building_upper in source_by_clone and primary_host:
            host_source = source_by_clone.get(
                primary_host.upper(), primary_host.upper()
            )
            runtime_host = primary_host_by_source.get(host_source)
            if runtime_host and runtime_host.upper() != primary_host.upper():
                changes['PowersUpBuilding'] = runtime_host
        if changes:
            rules[building_id] = changes
    return rules


def refinery_free_unit_pairs(map_sections, installed_sections):
    """Resolve actual refinery spawn types, including map-local overrides.

    Refinery=yes alone also identifies economic support buildings. Only
    refineries with a FreeUnit participate in the native miner contract.
    Reviewed faction pairs provide fallbacks for incomplete rules registries;
    explicit map overrides such as FreeUnit=none still take precedence.
    """
    building_ids = set(DEFAULT_REFINERY_MINER_IDS)
    for sections in (installed_sections, map_sections):
        building_ids.update(
            str(value).strip().upper()
            for value in _section_values(sections, 'BuildingTypes').values()
            if str(value).strip()
        )
    pairs = {}
    for building_id in sorted(building_ids):
        values = _effective_section_values(
            map_sections, installed_sections, building_id
        )
        fallback = DEFAULT_REFINERY_MINER_IDS.get(building_id, '')
        if values.get('refinery', 'yes' if fallback else '').strip().lower() != 'yes':
            continue
        free_units = [
            item.upper()
            for item in comma_items(values.get('freeunit', fallback))
            if item.lower() not in {'none', '<none>'}
        ]
        if free_units:
            pairs[building_id] = free_units[0]
    return pairs


def validate_original_refinery_contract():
    """Self-check installed refinery IDs and their untouched FreeUnit pairs."""
    from randomizer.ui.cameos import installed_rules_registry

    _superweapons, installed_sections = installed_rules_registry()
    registered = {
        str(value).strip().upper()
        for value in installed_sections.get('BuildingTypes', {}).values()
        if str(value).strip()
    }
    pairs = {}
    issues = []
    for refinery_id, fallback_miner_id in DEFAULT_REFINERY_MINER_IDS.items():
        values = _section_values(installed_sections, refinery_id)
        free_units = [
            item.upper()
            for key in ('freeunit', 'freeunit2')
            for item in comma_items(values.get(key, ''))
            if item.lower() not in {'none', '<none>'}
        ]
        miner_id = free_units[0] if free_units else fallback_miner_id
        pairs[refinery_id] = {'miner': miner_id, 'free_unit_count': len(free_units)}
        if refinery_id not in registered:
            issues.append(f'{refinery_id} is unregistered')
        if len(free_units) != 1:
            issues.append(f'{refinery_id} has {len(free_units)} free units')
        miner_docks = {
            dock.upper()
            for dock in comma_items(
                _section_values(installed_sections, miner_id).get('dock', '')
            )
        }
        if refinery_id not in miner_docks:
            issues.append(f'{miner_id} cannot dock at {refinery_id}')
    return {'pairs': pairs, 'issues': issues}


def ore_purifier_miner_dock_rules(lines, clone_handled):
    """Allow every isolated ore miner to dock at isolated Ore Purifier."""
    purifier_id = str(
        (clone_handled or {}).get(ORE_PURIFIER_SOURCE_ID, {}).get('clone_id')
        or ''
    ).strip()
    report = {
        'purifier_id': purifier_id,
        'miner_ids': (),
        'issues': (),
    }
    if not purifier_id:
        return {}, report

    sections = all_section_value_maps(lines)
    rules = {}
    miner_ids = []
    for details in (clone_handled or {}).values():
        clone_id = str((details or {}).get('clone_id') or '').strip()
        if not clone_id or clone_id.upper() == purifier_id.upper():
            continue
        values = _section_values(sections, clone_id)
        if values.get('harvester', '').strip().lower() != 'yes':
            continue
        docks = comma_items(values.get('dock', ''))
        rules[clone_id] = {
            'Dock': ','.join(unique_in_order(docks + [purifier_id])),
        }
        miner_ids.append(clone_id)

    issues = () if miner_ids else ('no cloned Harvester=yes miners found',)
    report.update({
        'miner_ids': tuple(unique_in_order(miner_ids)),
        'issues': issues,
    })
    return rules, report


def validate_ore_purifier_miner_docks():
    """Self-check static and runtime Ore Purifier docking identities."""
    from randomizer.rewards.reloaded_roster import randomizer_unit_roster

    _paths, clone_ids, templates = randomizer_unit_roster()
    purifier_id = clone_ids[ORE_PURIFIER_SOURCE_ID]
    miner_source_ids = sorted(
        source_id
        for source_id, values in templates.items()
        if str(_section_values({'template': values}, 'template').get(
            'harvester', ''
        )).lower() == 'yes'
    )
    clone_handled = {
        source_id: {'clone_id': clone_ids[source_id]}
        for source_id in miner_source_ids + [ORE_PURIFIER_SOURCE_ID]
    }
    lines = []
    static_missing = []
    for source_id in miner_source_ids:
        clone_id = clone_ids[source_id]
        values = _section_values({'template': templates[source_id]}, 'template')
        docks = comma_items(values.get('dock', ''))
        if purifier_id.upper() not in {dock.upper() for dock in docks}:
            static_missing.append(clone_id)
        lines.extend([
            f'[{clone_id}]',
            'Harvester=yes',
            f'Dock={",".join(docks)}',
            '',
        ])
    runtime_rules, runtime_report = ore_purifier_miner_dock_rules(
        lines,
        clone_handled,
    )
    runtime_missing = [
        clone_ids[source_id]
        for source_id in miner_source_ids
        if purifier_id.upper() not in {
            dock.upper()
            for dock in comma_items(
                runtime_rules.get(clone_ids[source_id], {}).get('Dock', '')
            )
        }
    ]
    return {
        'purifier_id': purifier_id,
        'miner_ids': [clone_ids[source_id] for source_id in miner_source_ids],
        'static_missing': static_missing,
        'runtime_missing': runtime_missing,
        'runtime_issues': list(runtime_report['issues']),
    }


def reprocessor_bounty_rules(
    lines,
    installed_sections,
    clone_handled,
    buildable_tech_ids=(),
):
    """Bind Ares bounty activation to the actual player Reprocessor clone.

    Ares checks ``[General]BountyEnablers`` by exact BuildingType. Native
    Mental Omega lists only ``FAREPR``. Randomizer production uses an isolated
    player clone, so owning it cannot activate bounty until its runtime ID is
    appended here.
    """
    reprocessor = (clone_handled or {}).get(REPROCESSOR_SOURCE_ID, {})
    clone_id = str(reprocessor.get('clone_id') or '').strip()
    report = {
        'clone_id': clone_id,
        'trigger_enabled': False,
        'trigger_mode': 'absent',
        'registered': False,
        'enablers': (),
        'eligible_by_faction': {},
        'eligible_unit_ids': (),
        'excluded_unit_ids': (),
        'issues': (),
    }
    if not clone_id:
        return {}, report

    map_sections = all_section_value_maps(lines)
    map_general = _section_values(map_sections, REPROCESSOR_BOUNTY_SECTION)
    installed_general = _section_values(
        installed_sections, REPROCESSOR_BOUNTY_SECTION
    )
    bounty_key = REPROCESSOR_BOUNTY_KEY.lower()
    explicit_map_enablers = bounty_key in map_general
    raw_enablers = (
        map_general.get(bounty_key, '')
        if explicit_map_enablers
        else installed_general.get(bounty_key, '')
    )
    enablers = unique_in_order(comma_items(raw_enablers))

    registered_buildings = {
        str(value).upper()
        for value in _effective_section_values(
            map_sections, installed_sections, 'BuildingTypes'
        ).values()
        if str(value).strip()
    }
    registered = clone_id.upper() in registered_buildings
    rules = {}
    if explicit_map_enablers and not str(raw_enablers).strip():
        # Empty list means bounty is globally enabled. Preserve authored map
        # behavior instead of changing it into a Reprocessor-only gate.
        effective_enablers = ()
        trigger_mode = 'always'
        trigger_enabled = True
    else:
        effective_enablers = tuple(unique_in_order(enablers + [clone_id]))
        trigger_mode = 'building'
        trigger_enabled = registered and clone_id.upper() in {
            item.upper() for item in effective_enablers
        }
        rules = {
            REPROCESSOR_BOUNTY_SECTION: {
                REPROCESSOR_BOUNTY_KEY: ','.join(effective_enablers),
            }
        }

    eligible_by_faction = {}
    eligible_ids = []
    excluded_ids = []
    candidate_ids = {
        str(unit_id).upper()
        for unit_id in buildable_tech_ids
        if str(unit_id).strip()
    }
    for unit_id in sorted(candidate_ids):
        target = BUFF_TARGETS.get(unit_id, {})
        if target.get('category') not in REPROCESSOR_BOUNTY_CATEGORIES:
            continue
        actual_id = str(
            (clone_handled or {}).get(unit_id, {}).get('clone_id') or unit_id
        )
        values = _effective_section_values(
            map_sections, installed_sections, actual_id
        )
        if str(values.get('bounty', '')).strip().lower() == 'yes':
            eligible_ids.append(actual_id)
            for faction in target.get('factions', ()):
                eligible_by_faction.setdefault(str(faction), []).append(
                    actual_id
                )
        else:
            excluded_ids.append(actual_id)

    issues = []
    if not registered:
        issues.append(f'{clone_id} is absent from BuildingTypes')
    if not trigger_enabled:
        issues.append(f'{clone_id} is absent from effective BountyEnablers')
    if not eligible_ids:
        issues.append('no buildable player units have Bounty=yes')

    report.update({
        'trigger_enabled': trigger_enabled,
        'trigger_mode': trigger_mode,
        'registered': registered,
        'enablers': effective_enablers,
        'eligible_by_faction': {
            faction: tuple(unit_ids)
            for faction, unit_ids in sorted(eligible_by_faction.items())
        },
        'eligible_unit_ids': tuple(eligible_ids),
        'excluded_unit_ids': tuple(excluded_ids),
        'issues': tuple(issues),
    })
    return rules, report


def validate_reprocessor_bounty_support():
    """Self-check native parity plus four-faction player-clone eligibility."""
    from randomizer.rewards.reloaded_roster import randomizer_unit_roster

    _paths, clone_ids, templates = randomizer_unit_roster()
    representatives = {
        'Allies': 'E1',
        'Soviets': 'E2',
        'Yuri': 'INIT',
        'GDI': 'TSE1',
        'Nod': 'TSNE1',
    }

    def value(values, key, default=''):
        wanted = str(key).lower()
        return next(
            (
                str(raw_value)
                for raw_key, raw_value in values.items()
                if str(raw_key).lower() == wanted
            ),
            default,
        )

    eligible_by_faction = {}
    excluded_by_faction = {}
    for faction in representatives:
        faction_ids = sorted(
            unit_id
            for unit_id, target in BUFF_TARGETS.items()
            if faction in target.get('factions', ())
            and target.get('category') in REPROCESSOR_BOUNTY_CATEGORIES
        )
        eligible_by_faction[faction] = [
            unit_id
            for unit_id in faction_ids
            if value(templates.get(unit_id, {}), 'Bounty').lower() == 'yes'
        ]
        excluded_by_faction[faction] = [
            unit_id
            for unit_id in faction_ids
            if value(templates.get(unit_id, {}), 'Bounty').lower() != 'yes'
        ]

    reprocessor_template = templates.get(REPROCESSOR_SOURCE_ID, {})
    native_parity = {
        'powered': value(reprocessor_template, 'Powered').lower() == 'true',
        'power': value(reprocessor_template, 'Power') == '-200',
        'superweapon': (
            value(reprocessor_template, 'SuperWeapon') == 'DevourerSpecial'
        ),
        'empulse_cannon': (
            value(reprocessor_template, 'EMPulseCannon').lower() == 'yes'
        ),
        'native_prerequisite': (
            value(reprocessor_template, 'Prerequisite') == 'FACNST,FOETECH'
        ),
    }

    lines = [
        '[BuildingTypes]',
        f'0={clone_ids[REPROCESSOR_SOURCE_ID]}',
        '',
        f'[{clone_ids[REPROCESSOR_SOURCE_ID]}]',
        'Bounty=no',
    ]
    clone_handled = {
        REPROCESSOR_SOURCE_ID: {
            'clone_id': clone_ids[REPROCESSOR_SOURCE_ID],
        }
    }
    for faction, source_id in representatives.items():
        clone_id = clone_ids[source_id]
        clone_handled[source_id] = {'clone_id': clone_id}
        lines.extend([
            '',
            f'[{clone_id}]',
            f'Bounty={value(templates[source_id], "Bounty")}',
        ])
    runtime_rules, runtime_report = reprocessor_bounty_rules(
        lines,
        {
            'General': {'BountyEnablers': REPROCESSOR_SOURCE_ID},
        },
        clone_handled,
        buildable_tech_ids=representatives.values(),
    )
    runtime_enablers = comma_items(
        runtime_rules.get(REPROCESSOR_BOUNTY_SECTION, {}).get(
            REPROCESSOR_BOUNTY_KEY, ''
        )
    )
    representative_results = {
        faction: clone_ids[source_id] in runtime_report['eligible_unit_ids']
        for faction, source_id in representatives.items()
    }
    errors = []
    errors.extend(
        f'Reprocessor template lacks native {field}'
        for field, valid in native_parity.items()
        if not valid
    )
    errors.extend(
        f'{faction} representative {representatives[faction]} lacks Bounty=yes'
        for faction, valid in representative_results.items()
        if not valid
    )
    if not runtime_report['trigger_enabled']:
        errors.extend(runtime_report['issues'])
    if REPROCESSOR_SOURCE_ID not in runtime_enablers:
        errors.append('native FAREPR was removed from BountyEnablers')
    if clone_ids[REPROCESSOR_SOURCE_ID] not in runtime_enablers:
        errors.append('player Reprocessor clone was not added to BountyEnablers')
    if errors:
        raise ValueError(
            'Reprocessor bounty validation failed: ' + '; '.join(errors)
        )
    return {
        'native_parity': native_parity,
        'runtime_enablers': runtime_enablers,
        'representatives': representatives,
        'representative_results': representative_results,
        'eligible_counts': {
            faction: len(unit_ids)
            for faction, unit_ids in eligible_by_faction.items()
        },
        'excluded_unit_ids': excluded_by_faction,
    }
