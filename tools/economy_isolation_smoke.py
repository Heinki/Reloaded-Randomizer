"""Regress unupgraded MCV access and player-only miner/refinery upgrades."""

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.content.inventory import read_rules_sections
from randomizer.core.paths import BATTLE_INI
from randomizer.maps import pipeline
from randomizer.maps.houses import map_house_records, player_controlled_houses
from randomizer.maps.identity_safety import capture_authored_identity_contract, validate_authored_identity_contract
from randomizer.maps.ini import IniLines, all_section_value_maps, read_text
from randomizer.maps.miner_buffs import upgrade_starting_player_miners, validate_refinery_miner_isolation
from randomizer.missions.access import (
    CHAOS_PRIMARY_PRODUCTION,
    CONYARD_BY_MCV,
    PRODUCTION_LOOKUP,
    always_available_mcv_rules,
)
from randomizer.missions.catalogue import parse_missions
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.rewards.catalogue import REWARD_BY_NAME
from tools.reported_mission_smoke import _MissionHarness


def values(sections, name):
    return next((v for k, v in sections.items() if k.casefold() == name.casefold()), {})


def check_mcv_production(sections, mode, context):
    for source in CONYARD_BY_MCV:
        clone = sections['RLRP' + source]
        paths = [clone['prerequisite']]
        count = int(clone.get('prerequisite.lists', '0'))
        paths.extend(clone[f'prerequisite.list{index}'] for index in range(1, count + 1))
        assert all(len(path.split(',')) == 1 for path in paths), (context, source, paths)
        assert all(PRODUCTION_LOOKUP.get(path.upper(), (None, None))[1] == 'vehicles' for path in paths), (context, source, paths)
        family = PRODUCTION_LOOKUP[CONYARD_BY_MCV[source]][0]
        factory = CHAOS_PRIMARY_PRODUCTION[family]['vehicles']
        assert factory in paths, (context, source, paths)
        if mode in {'Chaos', 'Randomizer Arsenal'}:
            assert all(production['vehicles'] in paths for production in CHAOS_PRIMARY_PRODUCTION.values()), (context, source, paths)
        assert not any(clone.get(key) for key in (
            'prerequisite.negative', 'prerequisite.stolentechs',
            'prerequisite.requiredtheaters', 'builtat', 'buildlimit',
            'factoryowners', 'factoryowners.forbidden',
        )), (context, source, clone)
    for production in CHAOS_PRIMARY_PRODUCTION.values():
        factory = sections[production['vehicles']]
        assert factory['techlevel'] == '1', (context, production, factory)
        assert factory.get('buildlimit') in {None, ''}, (context, production, factory)


def check_mcv_map_overrides():
    lines = IniLines([
        '[Basic]', 'Player=Player House', '[Houses]', '0=Player House',
        '[Player House]', 'Country=AlliesCountry', 'PlayerControl=yes',
        '[AMCV]', 'Prerequisite=GAWEAP,GADEPT,GATECH',
        'PrerequisiteOverride=GADEPT', 'Prerequisite.Lists=1',
        'Prerequisite.List1=GATECH,GADEPT', 'BuildLimit=0',
        '[GAWEAP]', 'Prerequisite=GAPILE',
    ])
    for chaos in (False, True):
        rules = always_available_mcv_rules(lines, chaos_mode=chaos)
        assert rules['AMCV']['Prerequisite'] == 'GAWEAP'
        assert rules['AMCV']['PrerequisiteOverride'] is None
        assert rules['AMCV']['BuildLimit'] is None
        assert rules['GAWEAP']['TechLevel'] == '1'
        assert 'Prerequisite' not in rules['GAWEAP'], 'Authored factory gate changed'


def check_scripted_miner_guard(installed):
    lines = IniLines([
        '[Basic]', 'Player=Player House', '[Houses]', '0=Player House',
        '[Player House]', 'Country=AlliesCountry', 'PlayerControl=yes',
        '[Units]', '0=Player House,CMIN,128,50,50,0,Harvest,None,0,-1,0,-1,1,1',
        '[Events]', 'LOSS=1,60,0,CMIN',
    ])
    original = all_section_value_maps(lines)
    handled = {'CMIN': {'clone_id': 'RLRPCMIN'}}
    assert not upgrade_starting_player_miners(lines, installed, original, handled)
    assert all_section_value_maps(lines)['Units'] == original['Units']
    contract = capture_authored_identity_contract(lines, installed)
    damaged = IniLines([line.replace(',CMIN,', ',RLRPCMIN,') if line.startswith('0=Player House,') else line for line in lines])
    try:
        validate_authored_identity_contract(contract, damaged)
    except ValueError:
        pass
    else:
        raise AssertionError('Unapproved mission identity rewrite was accepted')


def main():
    installed, _source = read_rules_sections()
    installed_lower = {name: {key.lower(): value for key, value in fields.items()} for name, fields in installed.items()}
    check_mcv_map_overrides()
    check_scripted_miner_guard(installed)
    missions = {m['code']: m for m in parse_missions(BATTLE_INI)}
    passed = []
    old_root, old_generated, old_tooltips = pipeline.GAME_ROOT, pipeline.GENERATED_MAP_DIR, pipeline.stage_randomizer_tooltips
    try:
        with tempfile.TemporaryDirectory(prefix='reloaded-economy-smoke-') as directory:
            pipeline.GAME_ROOT = Path(directory)
            pipeline.GENERATED_MAP_DIR = Path(directory) / 'generated'
            pipeline.stage_randomizer_tooltips = lambda *_args: None
            for code in ('ALL07_RA2', 'SOV01_RA2', 'YUR09', 'GDI06A_TS', 'NOD03A_TS'):
                mission = missions[code]
                native = all_section_value_maps(IniLines(read_text(resolve_installed_scenario(mission['scenario'])).splitlines()))
                records = map_house_records(IniLines(read_text(resolve_installed_scenario(mission['scenario'])).splitlines()))
                human_houses = set(player_controlled_houses(IniLines(read_text(resolve_installed_scenario(mission['scenario'])).splitlines()), records=records))
                for mode in ('Standard', 'Chaos', 'Randomizer Arsenal'):
                    for cloaked in (False, True):
                        rewards = [REWARD_BY_NAME[name] for name in ('War Miner Stealth Systems I', 'Allied MCV Stealth Systems I')] if cloaked else []
                        harness = _MissionHarness(rewards, mission['side'], mission['campaign'], seed='RLR-ECONOMY-ISOLATION', reward_mode=mode, progression_mode='Shop Mode')
                        hook = pipeline.prepare_hooked_map(harness, mission, extra_rules=harness.mission_required_launch_rules(mission))
                        result = all_section_value_maps(IniLines(read_text(Path(hook['generated_map'])).splitlines()))
                        check_mcv_production(result, mode, (code, mode, cloaked))
                        for source, yard in CONYARD_BY_MCV.items():
                            clone = result['RLRP' + source]
                            assert clone['techlevel'] == '1', (code, mode, source, clone['techlevel'])
                            assert clone.get('prerequisite'), (code, source, 'missing factory gate')
                            deployed = result[clone['deploysinto']]
                            assert deployed['undeploysinto'] == 'RLRP' + source
                            assert deployed['techlevel'] == '11', (code, mode, cloaked, source, deployed['techlevel'])
                            assert clone['requiredhouses'] == deployed['requiredhouses']
                        for source in ('GAREFN', 'NAREFN', 'TSPROC', 'TSPROC2'):
                            native_values = dict(values(installed_lower, source)); native_values.update(values(native, source))
                            if source in result:
                                assert result[source].get('freeunit', native_values.get('freeunit')) == native_values.get('freeunit')
                            clone = result.get('RLRP' + source)
                            if clone:
                                expected = 'RLRP' + native_values['freeunit'].upper()
                                assert clone['freeunit'] == expected
                                assert 'RLRP' + source in result[expected]['dock'].split(',')
                                assert 'RLRPOriginalGate' in result[source]['prerequisite.negative'].split(',')
                        for key, value in native.get('Units', {}).items():
                            tokens = value.split(',')
                            if tokens[0] not in human_houses:
                                assert result['Units'][key] == value, (code, 'enemy placement changed')
                        if code == 'ALL07_RA2':
                            for key in ('7', '8'):
                                before = native['Units'][key].split(','); after = result['Units'][key].split(',')
                                assert before[1] == 'CMIN' and after[1] == 'RLRPCMIN'
                                assert before[:1] + before[2:] == after[:1] + after[2:]
                            assert (result['RLRPCMIN'].get('cloakable', 'no') == 'yes') == cloaked
                            if cloaked:
                                assert result['RLRPHARV']['cloakable'] == 'yes'
                            for source in ('CMIN', 'HARV'):
                                native_values = dict(values(installed_lower, source)); native_values.update(values(native, source))
                                assert result.get(source, {}).get('cloakable', native_values.get('cloakable')) == native_values.get('cloakable')
                            # Factory AND refinery requirements survive both native and private paths.
                            miner = result['RLRPCMIN']
                            paths = [value.split(',') for key, value in miner.items() if key.startswith('prerequisite.list') and key != 'prerequisite.lists']
                            assert ['GAWEAP', 'RLRPGAREFN'] in paths
                            assert all(len(path) == 2 for path in paths)
                        assert not validate_refinery_miner_isolation(IniLines(read_text(Path(hook['generated_map'])).splitlines()), installed, native, {
                            source: {'clone_id': 'RLRP' + source} for source in ('CMIN', 'HARV', 'TSHARV', 'TSNHARV')
                        })
                        passed.append(f'{code}/{mode}/cloak={cloaked}')
    finally:
        pipeline.GAME_ROOT, pipeline.GENERATED_MAP_DIR, pipeline.stage_randomizer_tooltips = old_root, old_generated, old_tooltips
    print(json.dumps({'valid': True, 'passed': len(passed), 'cases': passed}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
