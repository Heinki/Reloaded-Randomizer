"""Build reviewable five-faction production facts from installed Reloaded rules."""

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.config.game_profile import (
    DEFERRED_CONTENT_FACTIONS,
    GENERATED_TYPE_PREFIX,
    SUPPORTED_GAME_VERSION,
)
from randomizer.content.inventory import (
    FACTION_HOUSES,
    read_rules_sections,
    rules_fingerprint,
)


OUTPUT_PATH = PROJECT_ROOT / 'configs' / 'production_topology.json'
FACTIONS_PATH = PROJECT_ROOT / 'configs' / 'factions.json'
FACTORY_KINDS = {
    'base': 'BuildingType',
    'infantry': 'InfantryType',
    'vehicles': 'UnitType',
    'air': 'AircraftType',
    'naval': 'UnitType',
}
REGISTRIES = {
    'BuildingTypes': 'BuildingType',
    'InfantryTypes': 'InfantryType',
    'VehicleTypes': 'UnitType',
    'AircraftTypes': 'AircraftType',
}

# TechLevel 11 and campaign-only factories are evidence, not automatically
# active production. They stay pending until their missions are reviewed.
ALTERNATE_FACTORIES = {
    'allies': ['GAAIRC2', 'GAAIRC3', 'GAAIRC4', 'GAWEAP2', 'GAWEAP3', 'GAYARD2'],
    'soviets': ['NAHAND2', 'NAWEAP2', 'NAWEAP3', 'NAHELIPAD2', 'NAHELIPAD3', 'NAYARD2', 'NAFIST'],
    'yuri': ['YAWEAP2', 'YAWEAP3', 'YAYARD2'],
    'gdi': [
        'TSGAWEAP2', 'TSGAWEAP3', 'TSGAHPAD2', 'TSGAHPAD3', 'TSGAHPAD4',
        'TSGAHPAD5', 'TSGAHPAD6', 'TSGAHPAD7', 'TSGAHPAD8', 'TSGAHPAD9',
        'TSGAHPAD10', 'TSGAHPAD11', 'TSGAHPAD12', 'TSGAYARD2', 'DGWEAP',
    ],
    'nod': [
        'TSNAMECHFACT', 'TSNAWEAP2', 'TSNAWEAP3', 'TSNAHPAD2', 'TSNAHPAD3',
        'TSNAHPAD4', 'TSNAHPAD5', 'TSNAHPAD6', 'TSNAHPAD7', 'TSNAHPAD8',
        'TSNAHPAD9', 'TSNAHPAD10', 'TSNAYARD2', 'DNWEAP',
    ],
}
COMPONENT_CHAINS = {
    'allies': [],
    'soviets': [],
    'yuri': [],
    'gdi': [{
        'base': 'GACTWR_TS',
        'upgrades': ['GAVULC_TS', 'GAROCK_TS', 'GACSAM_TS'],
    }],
    # Installed 2.7.0 rules expose no Nod PowersUpBuilding component chain.
    'nod': [],
}


def _split(value):
    return [
        item.strip()
        for item in str(value or '').split(',')
        if item.strip() and item.strip().lower() not in {'none', '<none>'}
    ]


def _integer(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _registered_types(sections):
    result = {}
    for registry, kind in REGISTRIES.items():
        for type_id in sections.get(registry, {}).values():
            if type_id:
                result[str(type_id).upper()] = kind
    return result


def _fact(type_id, sections, registered):
    values = sections.get(type_id, {})
    return {
        'id': type_id,
        'registered_as': registered.get(type_id.upper(), ''),
        'name': values.get('Name', type_id),
        'factory': values.get('Factory', ''),
        'construction_yard': values.get('ConstructionYard', '').lower() == 'yes',
        'tech_level': _integer(values.get('TechLevel')),
        'prerequisite': _split(values.get('Prerequisite')),
        'built_at': _split(values.get('BuiltAt')),
        'deploys_into': values.get('DeploysInto', ''),
        'undeploys_into': values.get('UndeploysInto', ''),
        'engineer': values.get('Engineer', '').lower() == 'yes',
        'resource_gatherer': (
            values.get('Harvester', '').lower() == 'yes'
            or values.get('ResourceGatherer', '').lower() == 'yes'
        ),
        'naval': values.get('Naval', '').lower() == 'yes',
        'movement_zone': values.get('MovementZone', ''),
        'passengers': _integer(values.get('Passengers')) or 0,
        'powers_up_building': values.get('PowersUpBuilding', ''),
        'upgrades': _integer(values.get('Upgrades')) or 0,
    }


def _factory_category(fact):
    for category, factory_kind in FACTORY_KINDS.items():
        if fact['factory'].lower() != factory_kind.lower():
            continue
        if category == 'naval' and not fact['naval']:
            continue
        if category == 'vehicles' and fact['naval']:
            continue
        return category
    return ''


def _source_name(source):
    archive = str(source).split('::', 1)[0]
    suffix = f'::{str(source).split("::", 1)[1]}' if '::' in str(source) else ''
    return Path(archive).name + suffix


def _load_factions():
    return json.loads(FACTIONS_PATH.read_text(encoding='utf-8'))['sections']


def build_document():
    sections, source = read_rules_sections()
    factions = _load_factions()
    registered = _registered_types(sections)
    families = {}
    source_failures = []

    pair_by_yard = {yard: mcv for mcv, yard in factions['conyard_by_mcv'].items()}
    for family in factions['active_families']:
        production = {}
        for category, type_ids in factions['production_buildings'][family].items():
            records = [_fact(type_id, sections, registered) for type_id in type_ids]
            production[category] = records
            for fact in records:
                expected = FACTORY_KINDS[category]
                valid = (
                    fact['registered_as'] == 'BuildingType'
                    and fact['factory'].lower() == expected.lower()
                    and (category != 'naval' or fact['naval'])
                )
                if not valid:
                    source_failures.append(
                        f'{family}:{category}:{fact["id"]}: factory mismatch'
                    )

        yard_id = next(iter(factions['production_buildings'][family]['base']))
        mcv_id = pair_by_yard[yard_id]
        mcv = _fact(mcv_id, sections, registered)
        yard = _fact(yard_id, sections, registered)
        reciprocal = (
            mcv['registered_as'] == 'UnitType'
            and yard['registered_as'] == 'BuildingType'
            and mcv['deploys_into'].upper() == yard_id
            and yard['undeploys_into'].upper() == mcv_id
            and yard['construction_yard']
        )
        if not reciprocal:
            source_failures.append(f'{family}:{mcv_id}/{yard_id}: non-reciprocal base pair')

        engineer_id = factions['engineer_by_family'][family]
        engineer = _fact(engineer_id, sections, registered)
        if engineer['registered_as'] != 'InfantryType' or not engineer['engineer']:
            source_failures.append(f'{family}:{engineer_id}: invalid engineer')

        harvester_id, factory_id, refinery_id = factions['miners'][family]
        harvester = _fact(harvester_id, sections, registered)
        if harvester['registered_as'] != 'UnitType' or not harvester['resource_gatherer']:
            source_failures.append(f'{family}:{harvester_id}: invalid resource gatherer')

        transport_id, shipyard_id = factions['amphibious_transports'][family]
        transport = _fact(transport_id, sections, registered)
        if not (
            transport['registered_as'] == 'UnitType'
            and transport['passengers'] > 0
            and 'amphibious' in transport['movement_zone'].lower()
        ):
            source_failures.append(f'{family}:{transport_id}: invalid amphibious transport')

        alternates = []
        for type_id in ALTERNATE_FACTORIES[family]:
            fact = _fact(type_id, sections, registered)
            fact['category'] = _factory_category(fact)
            alternates.append(fact)
            if not fact['category']:
                source_failures.append(f'{family}:{type_id}: invalid alternate factory')

        component_chains = []
        for chain in COMPONENT_CHAINS[family]:
            base = _fact(chain['base'], sections, registered)
            upgrades = [_fact(type_id, sections, registered) for type_id in chain['upgrades']]
            component_chains.append({'base': base, 'upgrades': upgrades})
            for upgrade in upgrades:
                if upgrade['powers_up_building'].upper() != base['id'].upper():
                    source_failures.append(
                        f'{family}:{upgrade["id"]}: component target mismatch'
                    )

        families[family] = {
            'display_name': family.title() if family != 'gdi' else 'GDI',
            'canonical_country': FACTION_HOUSES[family.title() if family != 'gdi' else 'GDI'],
            'mcv_conyard_pair': {'mcv': mcv, 'construction_yard': yard, 'reciprocal': reciprocal},
            'production': production,
            'alternate_production_candidates': alternates,
            'engineer': engineer,
            'resource_gatherer': {
                'unit': harvester,
                'factory_id': factory_id,
                'refinery_id': refinery_id,
            },
            'amphibious_transport': {'unit': transport, 'shipyard_id': shipyard_id},
            'component_tower_chains': component_chains,
            'review': {'status': 'pending_review', 'notes': ''},
        }

    return {
        'schema_version': 1,
        'description': 'Installed C&C Reloaded five-faction production topology and clone-safety policy.',
        'sections': {
            'catalogue_version': 1,
            'game_version': SUPPORTED_GAME_VERSION,
            'rules_source': _source_name(source),
            'rules_fingerprint_sha256': rules_fingerprint(sections),
            'active_families': list(factions['active_families']),
            'deferred_factions': list(DEFERRED_CONTENT_FACTIONS),
            'families': families,
            'safe_clone_policy': {
                'generated_type_prefix': GENERATED_TYPE_PREFIX,
                'factory_production_uses_clones': True,
                'authored_placements_remain_native': True,
                'authored_taskforces_remain_native': True,
                'native_starting_direct_buff_checks': [
                    'opponent_does_not_start_same_type',
                    'type_not_globally_shared_with_opponent',
                    'weapons_not_shared_with_opponent',
                ],
                'lock_access_before_stat_buffs': True,
            },
            'source_validation': {
                'valid': not source_failures,
                'failures': source_failures,
            },
            'review_complete': False,
        },
    }


def preserve_reviews(document):
    if not OUTPUT_PATH.is_file():
        return document
    try:
        existing = json.loads(OUTPUT_PATH.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return document
    old_sections = existing.get('sections', {})
    new_sections = document['sections']
    if old_sections.get('rules_fingerprint_sha256') != new_sections['rules_fingerprint_sha256']:
        return document
    for family, values in new_sections['families'].items():
        old_review = old_sections.get('families', {}).get(family, {}).get('review', {})
        if old_review.get('status') in {'approved', 'excluded'}:
            values['review'] = {
                'status': old_review['status'],
                'notes': str(old_review.get('notes') or ''),
            }
    new_sections['review_complete'] = all(
        values['review']['status'] in {'approved', 'excluded'}
        for values in new_sections['families'].values()
    )
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    document = preserve_reviews(build_document())
    if not args.write:
        print(json.dumps(document['sections']['source_validation'], indent=2))
        return 0 if document['sections']['source_validation']['valid'] else 1
    OUTPUT_PATH.write_text(json.dumps(document, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {OUTPUT_PATH.name}: {len(document["sections"]["families"])} active families')
    return 0 if document['sections']['source_validation']['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
