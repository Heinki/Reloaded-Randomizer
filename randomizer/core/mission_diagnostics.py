"""Keep bounded, local evidence before an unsuccessful mission is cleaned up."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile

from randomizer.core.paths import (
    APP_DIR, DEBUG_LOG, GAME_ROOT, LAUNCHER_LOG, OPTIONS_INI,
    SHOP_PROFILE_PATH, SHOP_RUN_PATH, SPAWN_INI, STATE_PATH,
)


REPORT_DIR = APP_DIR / 'mission_reports'
MAX_REPORTS = 5
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_REPORT_BYTES = 32 * 1024 * 1024
MAX_LOG_BYTES = 2 * 1024 * 1024


def _exception_files():
    """Include Ares' debug/snapshot-* folders, without following links."""
    directories = [GAME_ROOT, DEBUG_LOG.parent]
    if DEBUG_LOG.parent.is_dir():
        directories.extend(
            path for path in DEBUG_LOG.parent.glob('snapshot-*')
            if path.is_dir() and not path.is_symlink()
        )
    for directory in directories:
        for path in directory.iterdir() if directory.is_dir() else ():
            if path.suffix.lower() == '.dmp' or (
                path.suffix.lower() == '.txt'
                and path.name.lower().startswith('except')
            ) or (
                directory.name.startswith('snapshot-')
                and path.name.lower() in {'debug.log', 'syringe.log'}
            ):
                if path.is_file() and not path.is_symlink():
                    yield path


def _signature(path):
    stat = path.stat()
    return (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)


def mission_diagnostic_baseline():
    """Identify old exception files so they cannot be blamed on this launch."""
    return {str(path): _signature(path) for path in _exception_files()}


def preserve_mission_report(attempt, hook, returncode):
    """Archive an incomplete attempt without classifying every exit as a crash.

    The caller must invoke this before recording a Shop failure or deleting
    launch assets. Reports never alter the run or the original mission.
    """
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    code = re.sub(r'[^A-Za-z0-9_]', '', str(attempt.get('mission_code') or 'MISSION'))[:32]
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    report = Path(tempfile.mkdtemp(prefix=f'{timestamp}_{code}_', dir=REPORT_DIR))
    metadata = {
        key: value for key, value in attempt.items()
        if key != 'exception_baseline'
    }
    metadata.update({
        'format': 'reloaded-incomplete-mission-v1',
        'process_returncode': returncode,
        'outcome': 'closed_without_victory',
        'note': 'An incomplete mission is not proof of an engine crash.',
        'source_sha256': (hook or {}).get('source_sha256'),
        'exception_baseline_available': attempt.get('exception_baseline') is not None,
        'files': [],
        'skipped': [],
    })
    remaining = MAX_REPORT_BYTES - 64 * 1024

    def copy_file(source, name, *, tail=False):
        nonlocal remaining
        path = Path(source)
        try:
            if not path.is_file() or path.is_symlink():
                return
            size = path.stat().st_size
            limit = min(MAX_LOG_BYTES if tail else MAX_FILE_BYTES, remaining)
            if limit <= 0 or (size > limit and not tail):
                metadata['skipped'].append({'file': name, 'bytes': size})
                return
            # Read at most the remaining budget even if an engine log grows.
            with path.open('rb') as stream:
                if tail:
                    stream.seek(max(0, size - limit))
                data = stream.read(limit)
            (report / name).write_bytes(data)
            remaining -= len(data)
            metadata['files'].append({
                'file': name, 'bytes': len(data),
                'truncated': size > len(data),
                'sha256': hashlib.sha256(data).hexdigest(),
            })
        except OSError as exc:
            metadata['skipped'].append({'file': name, 'error': str(exc)})

    map_path = (hook or {}).get('root_map')
    if not map_path or not Path(map_path).is_file():
        map_path = (hook or {}).get('generated_map')
    if map_path:
        copy_file(map_path, 'mission.MAP')
    for path in (SPAWN_INI, OPTIONS_INI, SHOP_RUN_PATH, SHOP_PROFILE_PATH, STATE_PATH):
        copy_file(path, path.name)
    copy_file(DEBUG_LOG, 'debug.log', tail=True)
    copy_file(LAUNCHER_LOG, 'launcher.log', tail=True)
    copy_file(GAME_ROOT / 'syringe.log', 'syringe.log', tail=True)
    baseline = attempt.get('exception_baseline')
    try:
        for index, path in enumerate(sorted(_exception_files())):
            if baseline is None or baseline.get(str(path)) != _signature(path):
                copy_file(path, f'engine_{index}_{path.name}')
    except OSError as exc:
        metadata['skipped'].append({'file': 'engine exceptions', 'error': str(exc)})
    (report / 'report.json').write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False, default=str) + '\n',
        encoding='utf-8',
    )
    # Only prune directories created by this module. Leave user files alone.
    candidates = sorted(
        path for path in REPORT_DIR.iterdir()
        if path != report and path.is_dir() and not path.is_symlink()
        and re.fullmatch(r'\d{8}T\d{6}Z_[A-Za-z0-9_]+', path.name)
        and (path / 'report.json').is_file()
    )
    reports = []
    for path in candidates:
        try:
            document = json.loads((path / 'report.json').read_text(encoding='utf-8'))
            if document.get('format') == 'reloaded-incomplete-mission-v1':
                reports.append(path)
        except (OSError, ValueError, AttributeError):
            continue
    for old_report in reports[:max(0, len(reports) - MAX_REPORTS + 1)]:
        try:
            shutil.rmtree(old_report)
        except OSError:
            # A locked old report must not disrupt this mission's cleanup.
            continue
    return report
