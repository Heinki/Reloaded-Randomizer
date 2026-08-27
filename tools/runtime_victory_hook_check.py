"""Run one interactive real-game victory-hook verification.

The tool generates a hook-only copy of one reviewed mission, launches it, and
waits while the player completes the mission. Success requires the generated
scenario and its victory marker in ``debug.log``. Cleanup restores ``spawn.ini``
and removes only marker-owned generated maps. Authored maps are never written.
"""

import argparse
import csv
import io
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.config.game_profile import (
    GAME_INJECTED_DLL_NAMES,
    GAME_RUNTIME_ARGUMENTS,
)
from randomizer.content.inventory import read_rules_sections
from randomizer.core.paths import (
    DEBUG_LOG,
    GAME_EXE,
    GAME_LAUNCHER_EXE,
    GAME_ROOT,
    GENERATED_MAP_DIR,
    SPAWN_INI,
)
from randomizer.launch.options import spawn_ini_text
from randomizer.maps.generated import (
    assert_file_hash,
    file_sha256,
    generated_map_name,
)
from randomizer.maps.identity_safety import validate_authored_identity_contract
from randomizer.maps.rules import is_generated_hooked_map
from randomizer.missions.installation import resolve_installed_scenario
from randomizer.missions.metadata import MISSION_METADATA_BY_CODE
from randomizer.missions.runtime_hook_evidence import (
    runtime_hook_evidence_path,
)
from randomizer.validation.release import (
    generate_victory_hook_map,
    render_generated_hook_map,
)


def _parse_args():
    parser = argparse.ArgumentParser(
        description=(
            'Launch one hook-only mission. Complete it in game to verify its '
            'victory marker.'
        ),
    )
    parser.add_argument('--mission', required=True, help='Battle.ini mission code.')
    parser.add_argument(
        '--timeout',
        type=int,
        default=3600,
        help='Maximum seconds allowed for mission completion (default: 3600).',
    )
    parser.add_argument(
        '--game-speed',
        type=int,
        choices=range(0, 7),
        default=1,
        help='Spawner game-speed value from 0 through 6 (default: 1).',
    )
    return parser.parse_args()


def _image_pids(image_name):
    result = subprocess.run(
        ['tasklist', '/FI', f'IMAGENAME eq {image_name}', '/FO', 'CSV', '/NH'],
        cwd=GAME_ROOT,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='ignore',
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f'Cannot inspect running processes: {detail}')
    pids = set()
    for row in csv.reader(io.StringIO(result.stdout)):
        if len(row) < 2 or row[0].strip().lower() != image_name.lower():
            continue
        try:
            pids.add(int(row[1].strip()))
        except ValueError:
            continue
    return pids


def _terminate_pid_tree(pid):
    if pid:
        subprocess.run(
            ['taskkill', '/PID', str(pid), '/T', '/F'],
            cwd=GAME_ROOT,
            capture_output=True,
            text=True,
        )


def _remove_owned_map(path):
    path = Path(path)
    if not path.exists():
        return True
    if not is_generated_hooked_map(path):
        raise RuntimeError(f'Refusing to remove unmarked map: {path}')
    path.unlink()
    return not path.exists()


def _appended_debug_text(initial_size):
    if not DEBUG_LOG.exists():
        return ''
    offset = initial_size if DEBUG_LOG.stat().st_size >= initial_size else 0
    with DEBUG_LOG.open('r', encoding='utf-8', errors='ignore') as handle:
        handle.seek(offset)
        return handle.read()


def _metadata(mission_code):
    code = str(mission_code or '').strip().upper()
    metadata = MISSION_METADATA_BY_CODE.get(code)
    if metadata is None:
        raise ValueError(f'Unknown active mission code: {mission_code}')
    return metadata


def run_check(mission_code, timeout=3600, game_speed=1):
    """Launch one reviewed hook map and return source-bound runtime evidence."""
    if timeout < 30:
        raise ValueError('Runtime victory timeout must be at least 30 seconds.')
    for path in (GAME_LAUNCHER_EXE, GAME_EXE):
        if not path.is_file():
            raise FileNotFoundError(f'Required game executable is missing: {path}')

    baseline_pids = _image_pids(GAME_EXE.name)
    if baseline_pids:
        raise RuntimeError('gamemd.exe is already running; close it first.')

    metadata = _metadata(mission_code)
    source_path = resolve_installed_scenario(metadata['scenario'])
    source_hash = file_sha256(source_path)
    installed_sections, rules_source = read_rules_sections()
    _original, generated, contract, markers, action_ids, plan_size = (
        generate_victory_hook_map(metadata, installed_sections)
    )
    identity = validate_authored_identity_contract(contract, generated)
    generated_bytes = render_generated_hook_map(generated)
    marker = next(iter(markers))
    launch_name = generated_map_name(
        f'{metadata["code"]}_VICTORY_CHECK',
        metadata['scenario'],
        source_hash,
    )
    root_map = GAME_ROOT / launch_name
    cache_map = GENERATED_MAP_DIR / launch_name
    for path in (root_map, cache_map):
        if path.exists() and not is_generated_hooked_map(path):
            raise FileExistsError(f'Refusing to overwrite unmarked file: {path}')

    spawn_existed = SPAWN_INI.exists()
    spawn_backup = SPAWN_INI.read_bytes() if spawn_existed else None
    debug_offset = DEBUG_LOG.stat().st_size if DEBUG_LOG.exists() else 0
    process = None
    new_game_pids = set()
    report = {
        'schema_version': 1,
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'passed': False,
        'mission_code': metadata['code'],
        'campaign': metadata['campaign'],
        'faction': metadata['faction'],
        'scenario': metadata['scenario'],
        'source_path': str(source_path),
        'source_sha256': source_hash,
        'rules_source': str(rules_source),
        'generated_map': launch_name,
        'victory_action_ids': list(action_ids),
        'victory_hook_count': plan_size,
        'victory_marker': marker,
        'identity_validation': identity,
        'generated_scenario_confirmed': False,
        'victory_marker_seen': False,
        'timeout_seconds': int(timeout),
    }

    try:
        GENERATED_MAP_DIR.mkdir(parents=True, exist_ok=True)
        cache_map.write_bytes(generated_bytes)
        root_map.write_bytes(generated_bytes)
        assert_file_hash(source_path, source_hash)
        SPAWN_INI.write_text(
            spawn_ini_text(
                launch_name,
                difficulty_value=1,
                game_speed_value=int(game_speed),
            ),
            encoding='utf-8',
            newline='',
        )
        command = [
            str(GAME_LAUNCHER_EXE),
            GAME_EXE.name,
            *(f'-i={dll_name}' for dll_name in GAME_INJECTED_DLL_NAMES),
            '--args=' + ' '.join(GAME_RUNTIME_ARGUMENTS),
        ]
        print(
            f'Launching {metadata["code"]}: {metadata["title"]}. '
            'Complete the mission normally; this tool will close the game '
            'after detecting victory.',
            flush=True,
        )
        process = subprocess.Popen(command, cwd=GAME_ROOT)
        report['launcher_pid'] = process.pid
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            new_game_pids = _image_pids(GAME_EXE.name) - baseline_pids
            debug_text = _appended_debug_text(debug_offset)
            report['generated_scenario_confirmed'] = any(
                value.lower() in debug_text.lower()
                for value in (
                    f'Starting scnenario: {launch_name}',
                    f'Starting scenario: {launch_name}',
                )
            )
            report['victory_marker_seen'] = marker in debug_text
            if report['generated_scenario_confirmed'] and report['victory_marker_seen']:
                report['passed'] = True
                break
            if process.poll() is not None and not new_game_pids:
                break
            time.sleep(1)
        report['debug_tail'] = _appended_debug_text(debug_offset)[-4000:]
    finally:
        cleanup_errors = []
        if process is not None:
            try:
                _terminate_pid_tree(process.pid)
            except Exception as exc:
                cleanup_errors.append(f'launcher cleanup: {exc}')
        try:
            for pid in sorted(_image_pids(GAME_EXE.name) - baseline_pids):
                _terminate_pid_tree(pid)
        except Exception as exc:
            cleanup_errors.append(f'game cleanup: {exc}')
        try:
            if spawn_existed:
                SPAWN_INI.write_bytes(spawn_backup)
            elif SPAWN_INI.exists():
                SPAWN_INI.unlink()
        except Exception as exc:
            cleanup_errors.append(f'spawn.ini restore: {exc}')
        report['spawn_restored'] = (
            SPAWN_INI.exists() and SPAWN_INI.read_bytes() == spawn_backup
            if spawn_existed else not SPAWN_INI.exists()
        )
        removed = []
        for path in (root_map, cache_map):
            try:
                removed.append(_remove_owned_map(path))
            except Exception as exc:
                removed.append(False)
                cleanup_errors.append(f'{path.name} cleanup: {exc}')
        report['generated_maps_removed'] = all(removed)
        report['source_unchanged'] = file_sha256(source_path) == source_hash
        report['cleanup_errors'] = cleanup_errors
        report['passed'] = bool(
            report['passed']
            and report['source_unchanged']
            and report['spawn_restored']
            and report['generated_maps_removed']
            and not cleanup_errors
        )
        evidence_path = runtime_hook_evidence_path(metadata['code'])
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        report['report'] = str(evidence_path)
    return report


def main():
    args = _parse_args()
    try:
        report = run_check(args.mission, args.timeout, args.game_speed)
    except Exception as exc:
        print(f'Runtime victory-hook check failed: {exc}', file=sys.stderr)
        return 1
    print(json.dumps({
        'passed': report['passed'],
        'mission_code': report['mission_code'],
        'campaign': report['campaign'],
        'faction': report['faction'],
        'generated_scenario_confirmed': report['generated_scenario_confirmed'],
        'victory_marker_seen': report['victory_marker_seen'],
        'source_unchanged': report['source_unchanged'],
        'spawn_restored': report['spawn_restored'],
        'generated_maps_removed': report['generated_maps_removed'],
        'report': report['report'],
    }, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
