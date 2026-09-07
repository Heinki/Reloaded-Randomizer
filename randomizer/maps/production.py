"""Player production essentials and native/clone sidebar isolation."""

from ._shared import (
    comma_items,
    section_value_map_preserve,
    unique_in_order,
)
from .buff_values import _register_map_type


PLAYER_ORIGINAL_PRODUCTION_GATE_ID = 'RLRPOriginalGate'


def _value_case_insensitive(values, key, default=None):
    lowered = str(key).lower()
    return next(
        (
            value
            for name, value in (values or {}).items()
            if str(name).lower() == lowered
        ),
        default,
    )


def foreign_capturable_factory_forbidden_houses(
    native_sections,
    installed_sections,
    records,
    source_ids,
    production_lookup,
    target_factions_by_source,
):
    """Find foreign factory builders that could leak locked native units.

    Player-owned scripted units cannot always carry the hidden negative
    prerequisite: it can stop their authored TeamType from forming.  Their
    fallback ``FactoryOwners.Forbidden`` gate must therefore also cover
    capturable foreign factories present on this map.  Only foreign production
    families are added, preserving normal AI production for the unit's own
    faction.
    """
    sections_by_upper = {
        str(section).upper(): values
        for section, values in (native_sections or {}).items()
    }
    installed_by_upper = {
        str(section).upper(): values
        for section, values in (installed_sections or {}).items()
    }
    foreign_builders = []
    for placement in sections_by_upper.get('STRUCTURES', {}).values():
        tokens = [token.strip() for token in str(placement).split(',')]
        if len(tokens) < 2:
            continue
        owner_house, factory_id = tokens[0], tokens[1].upper()
        production = production_lookup.get(factory_id)
        if not production:
            continue
        factory_values = dict(installed_by_upper.get(factory_id, {}))
        factory_values.update(sections_by_upper.get(factory_id, {}))
        if str(_value_case_insensitive(
            factory_values, 'Capturable', 'true'
        )).strip().lower() == 'no':
            continue
        owner_record = (records or {}).get(owner_house, {})
        owner_country = str(
            owner_record.get('country')
            or owner_house.removesuffix(' House')
        ).strip()
        if owner_country:
            foreign_builders.append((str(production[0]).lower(), owner_country))

    result = {}
    for source_id in source_ids or ():
        source_id = str(source_id).upper()
        target_factions = {
            str(faction).lower()
            for faction in target_factions_by_source.get(source_id, ())
        }
        forbidden = unique_in_order(
            country
            for family, country in foreign_builders
            if family not in target_factions
        )
        if forbidden:
            result[source_id] = forbidden
    return result


def original_player_production_gate_rules(
    lines,
    installed_sections,
    native_source_ids,
    existing_rule_sections=None,
    native_sections=None,
    negative_gate_exclusions=(),
    native_taskforce_ids=(),
    factory_owner_only_ids=(),
    preserve_forbidden_house_ids=(),
    player_runtime_ids=(),
    player_forbidden_houses=(),
    player_factory_forbidden_houses=(),
    foreign_factory_forbidden_houses_by_source=None,
):
    """Block native production for houses owning the hidden player gate.

    Native ownership, AI production, placements, TeamTypes, and exact campaign
    references remain unchanged. Ares evaluates ``Prerequisite.Negative`` for
    normal, alternate-prerequisite, captured-factory, and reverse-engineered
    production. Restore the authored native TechLevel and BuildLimit here:
    campaign Autocreate teams obey both fields, so leaving randomizer locks on
    the shared original silently disables AI paradrops and air attacks. The
    exact-House hidden negative prerequisite keeps the human on isolated
    clones without changing AI production eligibility. Build-only story
    sources instead use ``FactoryOwners.Forbidden`` because their native
    identity must remain creatable by authored player TeamTypes. Native types
    used only by non-player TaskForces keep both fields authored: either
    generated gate can prevent campaign AI teams from forming. If the same
    native identity is already player-owned, its authored house filter wins
    and only player-original factories are excluded.
    """
    native_source_ids = {
        str(source_id).upper()
        for source_id in (native_source_ids or ())
        if str(source_id).strip()
    }
    if not native_source_ids:
        return {}
    negative_gate_exclusions = {
        str(source_id).upper()
        for source_id in (negative_gate_exclusions or ())
        if str(source_id).strip()
    }
    native_taskforce_ids = {
        str(source_id).upper()
        for source_id in (native_taskforce_ids or ())
        if str(source_id).strip()
    }
    factory_owner_only_ids = {
        str(source_id).upper()
        for source_id in (factory_owner_only_ids or ())
        if str(source_id).strip()
    }
    preserve_forbidden_house_ids = {
        str(source_id).upper()
        for source_id in (preserve_forbidden_house_ids or ())
        if str(source_id).strip()
    }
    player_runtime_ids = {
        str(source_id).upper()
        for source_id in (player_runtime_ids or ())
        if str(source_id).strip()
    }
    factory_owner_only_ids.difference_update(native_taskforce_ids)
    # A native identity already owned by the player cannot carry a matching
    # ForbiddenHouses value: the engine leaves that object visible but unable
    # to receive commands. Keep its runtime ownership valid and isolate only
    # production from factories originally owned by the player.
    factory_owner_only_ids.update(player_runtime_ids)
    negative_gate_exclusions.update(factory_owner_only_ids)
    negative_gate_exclusions.update(native_taskforce_ids)
    player_forbidden_houses = unique_in_order(
        str(house).strip()
        for house in (player_forbidden_houses or ())
        if str(house).strip()
    )
    player_factory_forbidden_houses = unique_in_order(
        list(player_forbidden_houses)
        + [
            str(house).strip()
            for house in (player_factory_forbidden_houses or ())
            if str(house).strip()
        ]
    )
    foreign_factory_forbidden_houses_by_source = {
        str(source_id).upper(): unique_in_order(
            str(house).strip()
            for house in houses
            if str(house).strip()
        )
        for source_id, houses in (
            foreign_factory_forbidden_houses_by_source or {}
        ).items()
    }

    installed_by_lower = {
        str(section).lower(): values
        for section, values in (installed_sections or {}).items()
    }
    native_by_lower = {
        str(section).lower(): values
        for section, values in (native_sections or {}).items()
    }
    # Mental Omega used DUMMYDUMMY as hidden gate template. Reloaded does not
    # register it; its installed invisible light post provides the same safe
    # noninteractive BuildingType base without importing MO rules.
    dummy_values = (
        installed_by_lower.get('dummydummy')
        or installed_by_lower.get('ingalite')
    )
    if not dummy_values:
        from randomizer.content.inventory import read_rules_sections

        installed_rules, _source = read_rules_sections()
        dummy_values = next(
            (
                values for section, values in installed_rules.items()
                if str(section).lower() == 'ingalite'
            ),
            None,
        )
    if not dummy_values:
        raise ValueError(
            'Installed INGALITE rules unavailable for player production gate.'
        )

    rules = {}
    _register_map_type(
        rules,
        lines,
        installed_sections,
        'BuildingTypes',
        PLAYER_ORIGINAL_PRODUCTION_GATE_ID,
    )
    gate_values = dict(dummy_values)
    gate_values.update({
        'Name': 'Randomizer Original Production Gate',
        'UIName': 'NOSTR:Randomizer Original Production Gate',
        'Image': str(dummy_values.get('Image') or 'GALITE'),
        'InvisibleInGame': 'yes',
        'SuperWeapon': None,
        'SuperWeapon2': None,
        'TechLevel': '-1',
        'BuildLimit': '0',
        'AIBuildThis': 'no',
        'Power': '0',
        'Powered': 'false',
        'Immune': 'yes',
        'Capturable': 'false',
        'NeedsEngineer': 'no',
        'Selectable': 'no',
        'Unsellable': 'yes',
        'LegalTarget': 'no',
        'Insignificant': 'yes',
        'ImmuneToEMP': 'yes',
        'DontScore': 'yes',
        'KeepAlive': 'no',
        'BaseNormal': 'no',
        'AIBaseNormal': 'no',
        'IsBaseDefense': 'no',
        'RadarInvisible': 'yes',
        'IsPassable': 'yes',
        'Firestorm.Wall': 'no',
        'Sight': '0',
    })
    rules[PLAYER_ORIGINAL_PRODUCTION_GATE_ID] = gate_values

    existing_rule_sections = existing_rule_sections or {}
    for source_id in sorted(native_source_ids):
        negatives = []
        for values in (
            installed_by_lower.get(source_id.lower(), {}),
            section_value_map_preserve(lines, source_id),
            existing_rule_sections.get(source_id, {}),
        ):
            negatives.extend(comma_items(
                _value_case_insensitive(values, 'Prerequisite.Negative', '')
            ))
        source_rules = rules.setdefault(source_id, {})
        negatives = [
            prerequisite
            for prerequisite in unique_in_order(negatives)
            if prerequisite.upper() != PLAYER_ORIGINAL_PRODUCTION_GATE_ID.upper()
        ]
        source_rules['Prerequisite.Negative'] = (
            ','.join(negatives)
            if source_id in negative_gate_exclusions
            else ','.join(negatives + [PLAYER_ORIGINAL_PRODUCTION_GATE_ID])
        ) or None
        # DropPod payload identities cannot carry the hidden negative gate:
        # Ares can reject their TeamType before creating the transport. Use
        # Ares' production-specific initial-factory-owner filter instead.
        # This blocks factories originally built by the player countries,
        # keeps enemy/script DropPods valid, and still permits captured enemy
        # technology whose factory was initially built by another country.
        if source_id in negative_gate_exclusions:
            if (
                source_id in native_taskforce_ids
                and source_id not in player_runtime_ids
            ):
                factory_forbidden = comma_items(_value_case_insensitive(
                    native_by_lower.get(source_id.lower(), {}),
                    'FactoryOwners.Forbidden',
                    _value_case_insensitive(
                        installed_by_lower.get(source_id.lower(), {}),
                        'FactoryOwners.Forbidden',
                        '',
                    ),
                ))
            else:
                factory_forbidden = []
                for values in (
                    installed_by_lower.get(source_id.lower(), {}),
                    section_value_map_preserve(lines, source_id),
                    existing_rule_sections.get(source_id, {}),
                ):
                    factory_forbidden.extend(comma_items(
                        _value_case_insensitive(
                            values, 'FactoryOwners.Forbidden', ''
                        )
                    ))
            source_rules['FactoryOwners.Forbidden'] = (
                ','.join(unique_in_order(factory_forbidden)) or None
                if (
                    source_id in native_taskforce_ids
                    and source_id not in player_runtime_ids
                )
                else ','.join(unique_in_order(
                    factory_forbidden
                    + list(player_factory_forbidden_houses)
                    + list(foreign_factory_forbidden_houses_by_source.get(
                        source_id, ()
                    ))
                )) or None
            )
        installed_values = installed_by_lower.get(source_id.lower(), {})
        native_values = native_by_lower.get(source_id.lower(), {})
        # Clone discovery finishes after the earlier native-overlay pass.  Add
        # the player-country exclusion here, where every actual registered
        # clone source is known.  This hides originals exposed by captured
        # factories instead of leaving native and generated cameos side by side.
        effective_forbidden = _value_case_insensitive(
            native_values,
            'ForbiddenHouses',
            _value_case_insensitive(installed_values, 'ForbiddenHouses', ''),
        )
        if (
            source_id in factory_owner_only_ids
            or source_id in preserve_forbidden_house_ids
        ):
            # Build-only clones deliberately leave authored placements,
            # TaskForces, Events, and Actions on the native identity. A player
            # ForbiddenHouses value can therefore reject the story team before
            # it forms (Bleed Red Boris, Fatal Impact's heroes, and Moonlight's
            # Soviet Engineers). Keep the authored runtime house filters
            # byte-for-byte effective. Most build-only sources use the factory
            # owner gate above; Engineers can safely use only the hidden
            # negative prerequisite because it does not block Team creation.
            source_rules['ForbiddenHouses'] = (
                str(effective_forbidden).strip() or None
            )
        else:
            source_rules['ForbiddenHouses'] = ','.join(unique_in_order(
                comma_items(effective_forbidden) + list(player_forbidden_houses)
            )) or 'none'
        source_rules['TechLevel'] = _value_case_insensitive(
            native_values,
            'TechLevel',
            _value_case_insensitive(installed_values, 'TechLevel'),
        )
        source_rules['BuildLimit'] = _value_case_insensitive(
            native_values,
            'BuildLimit',
            _value_case_insensitive(installed_values, 'BuildLimit'),
        )
    return rules


def validate_native_taskforce_production_filters(
    lines,
    installed_sections,
    native_sections,
    native_taskforce_ids,
    player_runtime_ids=(),
    player_forbidden_houses=(),
    player_factory_forbidden_houses=(),
    foreign_factory_forbidden_houses_by_source=None,
):
    """Reject player-isolation gates on authored non-player team payloads."""
    installed_by_lower = {
        str(section).lower(): values
        for section, values in (installed_sections or {}).items()
    }
    native_by_lower = {
        str(section).lower(): values
        for section, values in (native_sections or {}).items()
    }
    player_runtime_ids = {
        str(value).upper()
        for value in (player_runtime_ids or ())
        if str(value).strip()
    }
    allowed_player_factory_owners = {
        str(value).strip().casefold()
        for value in (
            list(player_forbidden_houses or ())
            + list(player_factory_forbidden_houses or ())
        )
        if str(value).strip()
    }
    foreign_factory_forbidden_houses_by_source = {
        str(source_id).upper(): {
            str(value).strip().casefold()
            for value in values
            if str(value).strip()
        }
        for source_id, values in (
            foreign_factory_forbidden_houses_by_source or {}
        ).items()
    }

    def effective_value(source_id, values, key):
        return _value_case_insensitive(
            values,
            key,
            _value_case_insensitive(
                installed_by_lower.get(source_id.lower(), {}), key, ''
            ),
        )

    failures = []
    for source_id in sorted({
        str(value).upper()
        for value in (native_taskforce_ids or ())
        if str(value).strip()
    }):
        authored = native_by_lower.get(source_id.lower(), {})
        generated = section_value_map_preserve(lines, source_id)
        generated_negative = comma_items(effective_value(
            source_id, generated, 'Prerequisite.Negative'
        ))
        if any(
            value.upper() == PLAYER_ORIGINAL_PRODUCTION_GATE_ID.upper()
            for value in generated_negative
        ):
            failures.append(f'{source_id}: hidden prerequisite gate')

        authored_factory = {
            value.casefold()
            for value in comma_items(effective_value(
                source_id, authored, 'FactoryOwners.Forbidden'
            ))
            if value.casefold() not in {'none', '<none>'}
        }
        generated_factory = {
            value.casefold()
            for value in comma_items(effective_value(
                source_id, generated, 'FactoryOwners.Forbidden'
            ))
            if value.casefold() not in {'none', '<none>'}
        }
        if source_id in player_runtime_ids:
            added_factory_owners = generated_factory - authored_factory
            if (
                not authored_factory.issubset(generated_factory)
                or not added_factory_owners.issubset(
                    allowed_player_factory_owners
                    | foreign_factory_forbidden_houses_by_source.get(
                        source_id, set()
                    )
                )
            ):
                failures.append(f'{source_id}: factory-owner filter changed')
        elif generated_factory != authored_factory:
            failures.append(f'{source_id}: factory-owner filter changed')

    if failures:
        raise ValueError(
            'Generated player-production isolation can disable authored '
            'non-player TaskForces: ' + '; '.join(failures)
        )
    return len(set(native_taskforce_ids or ()))
