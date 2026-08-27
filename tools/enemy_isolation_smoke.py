"""Prove hostile houses cannot receive player rewards or legacy AI buffs."""

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.core.paths import BATTLE_INI
from randomizer.maps.generated import file_sha256
from randomizer.maps.ini import IniLines, all_section_value_maps, read_text
from randomizer.maps.pipeline import prepare_hooked_map
from randomizer.maps.rules import is_generated_hooked_map
from randomizer.missions.catalogue import parse_missions
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.rewards.catalogue import REWARD_BY_NAME
from tools.core_gameplay_smoke import _Harness


MISSION_CODES = ('SOV01_RA2', 'SOV01')
PLAYER_REWARDS = (
    'Tesla Tank Mobility I',
    'Flak Track Mobility I',
    'Allied Pill Box Weapon Tuning I',
    'Attack Dog Access',
)
HOSTILE_FIELDS = {
    'strength', 'armor', 'speed', 'sight', 'ammo', 'passengers', 'cost',
    'buildtimemultiplier', 'cloakable', 'sensors', 'selfhealing',
    'firepowermultiplier', 'armormultiplier',
}


class _NoEnemyHarness(_Harness):
    def active_reward_settings(self):
        settings = super().active_reward_settings()
        settings['buff_allied_helpers'] = True
        settings['enemy_scaling'] = {
            'maximum_total_buffs': 0,
            'allowed_buff_ids': ['*'],
            'caps': {},
        }
        return settings

    def active_enemy_scaling_entries(self):
        return []


class _ExplicitEnemyHarness(_NoEnemyHarness):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enemy_applications = []

    def active_enemy_scaling_entries(self):
        return [{
            'reward': REWARD_BY_NAME['AI T1 Unit Cloaking'],
            'source': 'isolation smoke',
            'earned_from': 'explicit opt-in',
        }]

    def record_enemy_reward_applications(self, _code, applications):
        self.enemy_applications = list(applications or ())


def _remove_generated(path):
    path = Path(path)
    if not path.exists():
        return
    if not is_generated_hooked_map(path):
        raise RuntimeError(f'Refusing to remove unmarked map: {path}')
    path.unlink()


def _values(sections, section):
    return next((
        values for name, values in sections.items()
        if str(name).casefold() == str(section).casefold()
    ), {})


def _hostile_field_changes(source_sections, generated_sections, type_id):
    source = _values(source_sections, type_id)
    generated = _values(generated_sections, type_id)
    changed = []
    keys = {
        str(key).casefold(): key
        for key in set(source) | set(generated)
    }
    for lowered, key in keys.items():
        if lowered not in HOSTILE_FIELDS:
            continue
        source_value = next((
            value for name, value in source.items()
            if str(name).casefold() == lowered
        ), None)
        generated_value = next((
            value for name, value in generated.items()
            if str(name).casefold() == lowered
        ), None)
        if source_value != generated_value:
            changed.append(f'{key}: {source_value!r}->{generated_value!r}')
    return changed


def main():
    rewards = [REWARD_BY_NAME[name] for name in PLAYER_REWARDS]
    missions = {item['code']: item for item in parse_missions(BATTLE_INI)}
    failures = []
    for code in MISSION_CODES:
        mission = missions[code]
        source_path = resolve_installed_scenario(mission['scenario'])
        source_hash = file_sha256(source_path)
        source_sections = all_section_value_maps(
            IniLines(read_text(source_path).splitlines())
        )
        harness = _NoEnemyHarness(
            rewards,
            mission['side'],
            mission['campaign'],
            seed='RLR-ENEMY-ISOLATION-SMOKE',
        )
        hook = None
        try:
            hook = prepare_hooked_map(harness, mission)
            generated_path = Path(hook['root_map'])
            generated_sections = all_section_value_maps(
                IniLines(read_text(generated_path).splitlines())
            )
            hostile_type = 'E1'
            changes = _hostile_field_changes(
                source_sections, generated_sections, hostile_type
            )
            if changes:
                raise RuntimeError(
                    f'hostile {hostile_type} changed: {"; ".join(changes)}'
                )
            forbidden_logs = (
                'Applied AI stat bonuses',
                'Applied native T1/T2/T3 AI unit buffs',
                'Prepared AI-only cloned powers',
            )
            leaked_logs = [
                entry['message'] for entry in harness.logs
                if any(text in entry['message'] for text in forbidden_logs)
            ]
            if leaked_logs:
                raise RuntimeError('; '.join(leaked_logs))
            if not any(
                'Validated hostile-house isolation' in entry['message']
                for entry in harness.logs
            ):
                raise RuntimeError('clone house-isolation audit did not run')
            if file_sha256(source_path) != source_hash:
                raise RuntimeError('authored source changed')
            print(f'PASS {code}: hostile E1 native; clones isolated', flush=True)
        except Exception as exc:
            failures.append({'mission': code, 'error': str(exc)})
            print(f'FAIL {code}: {exc}', flush=True)
        finally:
            if hook:
                _remove_generated(hook['root_map'])
                _remove_generated(hook['generated_map'])

    explicit_hook = None
    try:
        mission = missions['SOV01']
        explicit = _ExplicitEnemyHarness(
            rewards,
            mission['side'],
            mission['campaign'],
            seed='RLR-EXPLICIT-ENEMY-REWARD-SMOKE',
        )
        explicit_hook = prepare_hooked_map(explicit, mission)
        if not any(
            item.get('effect_id') == 'tier1_cloak'
            and str(item.get('target') or '').upper() == 'E1'
            for item in explicit.enemy_applications
        ):
            raise RuntimeError(
                'explicit enemy cloak produced no E1 dashboard receipt'
            )
        print(
            'PASS SOV01: explicit enemy cloak applied and receipted for UI',
            flush=True,
        )
    except Exception as exc:
        failures.append({'mission': 'SOV01-explicit-enemy', 'error': str(exc)})
        print(f'FAIL SOV01 explicit enemy reward: {exc}', flush=True)
    finally:
        if explicit_hook:
            _remove_generated(explicit_hook['root_map'])
            _remove_generated(explicit_hook['generated_map'])

    report = {
        'valid': not failures,
        'mission_count': len(MISSION_CODES),
        'explicit_enemy_reward_ui_receipt': not any(
            item['mission'] == 'SOV01-explicit-enemy'
            for item in failures
        ),
        'failures': failures,
    }
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report['valid'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
