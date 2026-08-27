"""Run one reversible real-game launch smoke test against C&C Reloaded.

This tool copies an unchanged authored mission into a Randomizer-owned map,
launches it through Syringe, waits for runtime evidence, then restores
``spawn.ini`` and removes only marker-verified generated files. It never
enables unfinished gameplay catalogues.
"""

import argparse
import csv
import io
import json
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from randomizer.content.inventory import read_rules_sections
from randomizer.config.game_profile import (
    GAME_INJECTED_DLL_NAMES,
    GAME_RUNTIME_ARGUMENTS,
)
from randomizer.core.paths import (
    DEBUG_LOG,
    GAME_EXE,
    GAME_LAUNCHER_EXE,
    GAME_ROOT,
    GENERATED_MAP_DIR,
    LOG_DIR,
    SPAWN_INI,
)
from randomizer.launch.options import spawn_ini_text
from randomizer.maps.generated import (
    assert_file_hash,
    file_sha256,
    generated_map_name,
)
from randomizer.maps.identity_safety import (
    capture_authored_identity_contract,
    validate_authored_identity_contract,
)
from randomizer.maps.ini import IniLines, read_text
from randomizer.maps.rules import HOOKED_MAP_MARKER, is_generated_hooked_map
from randomizer.missions.installation import (
    installed_mission_catalogue,
    resolve_installed_scenario,
)


REPORT_PATH = LOG_DIR / 'foundation_launch_smoke.json'
RUNTIME_EVIDENCE = ('Capture_Mouse()', 'MapClass::Init_Clear')


def _parse_args():
    parser = argparse.ArgumentParser(
        description='Launch one unchanged generated mission and verify source integrity.',
    )
    parser.add_argument(
        '--mission',
        help='Battle.ini mission code. Defaults to the first active mission.',
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=90,
        help='Maximum seconds to wait for runtime evidence (default: 90).',
    )
    parser.add_argument(
        '--settle-seconds',
        type=int,
        default=3,
        help='Seconds to keep the loaded game open after evidence (default: 3).',
    )
    return parser.parse_args()


def _mission_by_code(code):
    missions = installed_mission_catalogue()
    if not missions:
        raise RuntimeError('INI/Battle.ini contains no active missions.')
    if not code:
        return missions[0]
    wanted = str(code).strip().lower()
    for mission in missions:
        if mission['code'].lower() == wanted:
            return mission
    raise ValueError(f'Unknown active mission code: {code}')


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
    if not pid:
        return
    subprocess.run(
        ['taskkill', '/PID', str(pid), '/T', '/F'],
        cwd=GAME_ROOT,
        capture_output=True,
        text=True,
    )


def _remove_owned_map(path):
    path = Path(path)
    if not path.exists():
        return False
    if not is_generated_hooked_map(path):
        raise RuntimeError(f'Refusing to remove unmarked map: {path}')
    path.unlink()
    return True


def _appended_debug_text(initial_size):
    if not DEBUG_LOG.exists():
        return ''
    size = DEBUG_LOG.stat().st_size
    offset = initial_size if size >= initial_size else 0
    with DEBUG_LOG.open('r', encoding='utf-8', errors='ignore') as handle:
        handle.seek(offset)
        return handle.read()


def _write_report(report):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2),
        encoding='utf-8',
    )


def run_smoke(mission_code=None, timeout=90, settle_seconds=3):
    if timeout < 10:
        raise ValueError('Smoke timeout must be at least 10 seconds.')
    if settle_seconds < 0:
        raise ValueError('Settle time cannot be negative.')
    for path in (GAME_LAUNCHER_EXE, GAME_EXE):
        if not path.is_file():
            raise FileNotFoundError(f'Required game executable is missing: {path}')

    baseline_game_pids = _image_pids(GAME_EXE.name)
    if baseline_game_pids:
        raise RuntimeError(
            'gamemd.exe is already running; close it before the isolated smoke test.'
        )

    mission = _mission_by_code(mission_code)
    source_path = resolve_installed_scenario(mission['scenario'])
    if not source_path.is_file():
        raise FileNotFoundError(f'Mission source is missing: {source_path}')

    source_hash = file_sha256(source_path)
    source_lines = IniLines(read_text(source_path).splitlines())
    installed_sections, rules_source = read_rules_sections()
    identity_contract = capture_authored_identity_contract(
        source_lines,
        installed_sections,
    )
    identity_result = validate_authored_identity_contract(
        identity_contract,
        source_lines,
    )

    launch_name = generated_map_name(
        f'{mission["code"]}_SMOKE',
        mission['scenario'],
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
    evidence = []
    report = {
        'passed': False,
        'mission': mission,
        'rules_source': str(rules_source),
        'source_path': str(source_path),
        'source_sha256_before': source_hash,
        'generated_map': str(root_map),
        'generated_cache_map': str(cache_map),
        'identity_validation': identity_result,
        'timeout_seconds': timeout,
    }

    try:
        generated_bytes = (
            HOOKED_MAP_MARKER + '\r\n' + '\r\n'.join(source_lines) + '\r\n'
        ).encode('utf-8')
        GENERATED_MAP_DIR.mkdir(parents=True, exist_ok=True)
        cache_map.write_bytes(generated_bytes)
        root_map.write_bytes(generated_bytes)
        assert_file_hash(source_path, source_hash)
        report['source_sha256_after_generation'] = file_sha256(source_path)

        SPAWN_INI.write_text(
            spawn_ini_text(launch_name, difficulty_value=1, game_speed_value=1),
            encoding='utf-8',
            newline='',
        )
        command = [
            str(GAME_LAUNCHER_EXE),
            GAME_EXE.name,
            *(f'-i={dll_name}' for dll_name in GAME_INJECTED_DLL_NAMES),
            '--args=' + ' '.join(GAME_RUNTIME_ARGUMENTS),
        ]
        process = subprocess.Popen(command, cwd=GAME_ROOT)
        report['launcher_pid'] = process.pid
        report['command'] = command

        deadline = time.monotonic() + timeout
        debug_text = ''
        scenario_started = False
        while time.monotonic() < deadline:
            new_game_pids = _image_pids(GAME_EXE.name) - baseline_game_pids
            debug_text = _appended_debug_text(debug_offset)
            evidence = [
                marker for marker in RUNTIME_EVIDENCE if marker in debug_text
            ]
            scenario_markers = (
                f'Starting scnenario: {launch_name}',
                f'Starting scenario: {launch_name}',
            )
            scenario_started = any(
                marker.lower() in debug_text.lower()
                for marker in scenario_markers
            )
            if scenario_started:
                evidence.append(f'generated scenario {launch_name}')
            if scenario_started and new_game_pids:
                break
            if process.poll() is not None and not new_game_pids:
                break
            time.sleep(1)

        report['game_pids'] = sorted(new_game_pids)
        report['runtime_evidence'] = evidence
        report['launcher_returncode_during_check'] = process.poll()
        report['debug_log'] = str(DEBUG_LOG)
        report['debug_tail'] = debug_text[-4000:]
        if not new_game_pids:
            raise RuntimeError('gamemd.exe did not remain running during the smoke test.')
        if not scenario_started:
            raise RuntimeError(
                'Game process started, but debug.log did not confirm the generated scenario.'
            )
        if settle_seconds:
            time.sleep(settle_seconds)
        assert_file_hash(source_path, source_hash)
        report['source_sha256_after_game'] = file_sha256(source_path)
        report['passed'] = True
    finally:
        cleanup_errors = []
        if process is not None:
            try:
                _terminate_pid_tree(process.pid)
            except Exception as exc:
                cleanup_errors.append(f'launcher cleanup: {exc}')
        try:
            remaining_pids = _image_pids(GAME_EXE.name) - baseline_game_pids
            for pid in sorted(remaining_pids):
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
            SPAWN_INI.exists()
            and SPAWN_INI.read_bytes() == spawn_backup
            if spawn_existed
            else not SPAWN_INI.exists()
        )
        for label, path in (
            ('root_map_removed', root_map),
            ('cache_map_removed', cache_map),
        ):
            try:
                report[label] = _remove_owned_map(path)
            except Exception as exc:
                report[label] = False
                cleanup_errors.append(f'{path.name} cleanup: {exc}')
        report['source_sha256_final'] = file_sha256(source_path)
        report['source_unchanged'] = report['source_sha256_final'] == source_hash
        report['cleanup_errors'] = cleanup_errors
        report['passed'] = bool(
            report.get('passed')
            and report['spawn_restored']
            and report['source_unchanged']
            and not root_map.exists()
            and not cache_map.exists()
            and not cleanup_errors
        )
        _write_report(report)
    return report


def main():
    args = _parse_args()
    try:
        report = run_smoke(
            mission_code=args.mission,
            timeout=args.timeout,
            settle_seconds=args.settle_seconds,
        )
    except Exception as exc:
        print(f'Smoke test failed: {exc}', file=sys.stderr)
        if REPORT_PATH.exists():
            print(f'Report: {REPORT_PATH}', file=sys.stderr)
        return 1
    print(json.dumps({
        'passed': report['passed'],
        'mission': report['mission']['code'],
        'runtime_evidence': report['runtime_evidence'],
        'source_unchanged': report['source_unchanged'],
        'spawn_restored': report['spawn_restored'],
        'report': str(REPORT_PATH),
    }, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
