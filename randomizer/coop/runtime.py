"""Fingerprint native Reloaded assets and launcher code before lobby agreement."""

import hashlib
import json
from pathlib import Path

from randomizer.config.game_profile import GAME_INJECTED_DLL_NAMES
from randomizer.core.paths import FROZEN, SOURCE_DIR


def installation_details(root):
    paths = [root / name for name in ('gamemd.exe', 'Syringe.exe', *GAME_INJECTED_DLL_NAMES)]
    paths.extend(sorted(root.glob('*.mix')))
    paths.append(root / 'Maps/Standard/wingsfaith.map')
    if FROZEN:
        import sys
        paths.append(Path(sys.executable))
    else:
        paths.extend(sorted((SOURCE_DIR / 'randomizer').rglob('*.py')))
    files = {}
    for path in paths:
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(chunk)
        key = path.relative_to(root).as_posix() if path.is_relative_to(root) else path.name
        files[key] = digest.hexdigest()
    fingerprint = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {'fingerprint_policy': 'reloaded-fortress-1', 'fingerprint': fingerprint,
            'files': files, 'raw_files': files}


def validate_runtime(local, remote):
    if not isinstance(remote, dict) or remote.get('fingerprint_policy') != local['fingerprint_policy']:
        raise ValueError('Reloaded compatibility policy differs. Update every launcher.')
    if local['fingerprint'] != remote.get('fingerprint'):
        changed = sorted(key for key in set(local['files']) | set(remote.get('files', {}))
                         if local['files'].get(key) != remote.get('files', {}).get(key))
        raise ValueError('Reloaded assets differ: ' + ', '.join(changed))
