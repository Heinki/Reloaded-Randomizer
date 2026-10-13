"""Regress cloak retention across miner, MCV, and stealth-generator forms."""

import json
import sys
from itertools import product
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.content.inventory import read_rules_sections
from randomizer.core.paths import BATTLE_INI, GAME_ROOT, GENERATED_MAP_DIR
from randomizer.maps.buff_validation import _unit_fields_are_effective
from randomizer.maps.buff_values import apply_unit_buff_value
from randomizer.maps.generated import file_sha256, generated_map_name
from randomizer.maps.ini import IniLines, all_section_value_maps, read_text
from randomizer.maps.pipeline import prepare_hooked_map
from randomizer.missions.catalogue import parse_missions
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.rewards.catalogue import REWARD_POOL
from tools.reported_mission_smoke import _MissionHarness
from tools.core_gameplay_smoke import _remove_owned


def _sections(path):
    return all_section_value_maps(IniLines(read_text(path).splitlines()))


def main():
    installed, _source = read_rules_sections()
    installed = {
        name: {key.lower(): value for key, value in values.items()}
        for name, values in installed.items()
    }
    mission = next(m for m in parse_missions(BATTLE_INI)
                   if m['code'] == 'NOD03A_TS')
    source = resolve_installed_scenario(mission['scenario'])
    source_hash = file_sha256(source)
    original = _sections(source)
    fixture = PROJECT_ROOT / 'bugreports' / 'RLR_NOD03A_TS_6C764AEBA952.map'
    if fixture.exists():
        reported = _sections(fixture)
        assert reported['RLRPSMIN']['cloakable'] == 'yes'
        assert reported['RLRPSMIN']['deploysinto'] == 'YAREFN'
        assert 'RLRPYAREFN' not in reported
        # The reported MCV is native and has no map-local mutation. A CTD's
        # actual instruction cannot be identified from this map alone.
        assert reported.get('NODMCV', {}) == original.get('NODMCV', {})
        assert reported.get('TSNACNST', {}) == original.get('TSNACNST', {})

    values = {'cloakable.allowed': 'no'}
    apply_unit_buff_value(values, {}, 'cloak', 1)
    assert 'cloakable.allowed' not in values
    assert _unit_fields_are_effective('cloak', values, {})
    values['Cloakable.Allowed'] = 'no'
    assert not _unit_fields_are_effective('cloak', values, {})

    # Preserve existing generated mission copies: map names are source-based,
    # so a smoke launch can share its filename with the user's current run.
    name = generated_map_name(mission['code'], mission['scenario'], source_hash)
    paths = [GAME_ROOT / name, GENERATED_MAP_DIR / name]
    backups = {path: path.read_bytes() if path.exists() else None for path in paths}
    cases = []
    try:
        for mode in ('Standard', 'Chaos', 'Randomizer Arsenal'):
            for progression, cloaked in product(
                ('Mission List', 'Grid Mode', 'Shop Mode'), (False, True),
            ):
                rewards = [r for r in REWARD_POOL if r.get('kind') == 'access']
                if cloaked:
                    rewards += [r for r in REWARD_POOL
                                if r.get('kind') == 'buff'
                                and r.get('buff_type') in {'cloak', 'health'}
                                and r.get('unit') in {'SMIN', 'NODSTLH_MP', 'NODMCV', 'SGEN'}]
                harness = _MissionHarness(
                    rewards, mission['side'], mission['campaign'],
                    seed='RLR-CLOAK-DEPLOY-SMOKE', reward_mode=mode,
                    progression_mode=progression,
                )
                hook = prepare_hooked_map(
                    harness, mission,
                    extra_rules=harness.mission_required_launch_rules(mission),
                )
                sections = _sections(Path(hook['generated_map']))
                registered = {
                    registry: set(installed[registry].values())
                    | set(sections.get(registry, {}).values())
                    for registry in ('VehicleTypes', 'BuildingTypes', 'InfantryTypes')
                }
                for mobile, deployed in (
                    ('SMIN', 'YAREFN'), ('NODMCV', 'TSNACNST'),
                    ('SGEN', 'MSTL'),
                ):
                    mobile_id, deployed_id = 'RLRP' + mobile, 'RLRP' + deployed
                    if mobile_id not in registered['VehicleTypes'] and not cloaked:
                        assert mobile == 'NODMCV'
                        assert sections.get(mobile, {}) == original.get(mobile, {})
                        continue
                    assert mobile_id in registered['VehicleTypes']
                    assert deployed_id in registered['BuildingTypes']
                    assert sections[mobile_id]['deploysinto'] == deployed_id
                    assert sections[deployed_id]['undeploysinto'] == mobile_id
                    assert sections[deployed_id]['owner'] == sections[mobile_id]['owner']
                    if cloaked:
                        for identifier in (mobile_id, deployed_id):
                            assert sections[identifier]['cloakable'] == 'yes'
                            assert sections[identifier]['cloakable.allowed'] == 'yes'
                deployed_generator = sections['RLRPMSTL']
                assert deployed_generator['ismobilestealth'] == 'yes'
                assert deployed_generator['cloakgenerator'] == 'yes'
                assert deployed_generator['cloakradiusincells'] == installed['MSTL']['cloakradiusincells']
                if not cloaked:
                    assert deployed_generator['cloakable.allowed'] == 'no'
                    assert deployed_generator.get('cloakable', 'no') == 'no'
                for native_id in ('SGEN', 'MSTL'):
                    for key in ('cloakable', 'cloakable.allowed', 'deploysinto', 'undeploysinto'):
                        assert sections.get(native_id, {}).get(key) == original.get(native_id, {}).get(key)
                if cloaked:
                    generator = sections['RLRPNODSTLH_MP']
                    assert generator['cloakable.allowed'] == 'yes'
                    assert generator['cloakgenerator'] == 'yes'
                    assert generator['cloakradiusincells'] == installed['NODSTLH_MP']['cloakradiusincells']
                    slave_id = sections['RLRPSMIN']['enslaves']
                    assert slave_id != 'SLAV'
                    assert sections['RLRPYAREFN']['enslaves'] == slave_id
                    assert slave_id in registered['InfantryTypes']
                    slave = sections[slave_id]
                    assert slave['cloakable'] == slave['cloakable.allowed'] == 'yes'
                    assert slave['techlevel'] == '-1'
                    for key in ('strength', 'speed', 'primary', 'harvestrate', 'storage', 'slaved'):
                        assert slave[key] == installed['SLAV'][key]
                else:
                    assert sections['RLRPSMIN']['enslaves'] == 'SLAV'
                    assert sections['RLRPYAREFN']['enslaves'] == 'SLAV'
                assert sections.get('SLAV', {}) == original.get('SLAV', {})
                for key, value in original.get('TaskForces', {}).items():
                    assert sections['TaskForces'][key] == value
                assert file_sha256(source) == source_hash
                cases.append(f'{mode}/{progression}/cloak={cloaked}')
    finally:
        for path, data in backups.items():
            if data is not None:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            elif path.exists():
                _remove_owned(path)
    print(json.dumps({'valid': True, 'cases': cases}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
