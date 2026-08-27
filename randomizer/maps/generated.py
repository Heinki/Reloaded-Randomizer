"""Deterministic paths and source-integrity checks for generated maps."""

import hashlib
import re
from pathlib import Path

from randomizer.config.game_profile import GENERATED_HOOK_PREFIX


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generated_map_name(mission_code, scenario, source_sha256):
    """Return root-safe randomizer-owned map name without source-path reuse."""
    safe_code = re.sub(
        r'[^A-Za-z0-9_]', '', str(mission_code or '').upper()
    )[:20] or 'MISSION'
    identity = f'{mission_code}|{scenario}|{source_sha256}'.encode('utf-8')
    suffix = hashlib.sha256(identity).hexdigest()[:12].upper()
    return f'{GENERATED_HOOK_PREFIX}_{safe_code}_{suffix}.MAP'


def assert_file_hash(path, expected_sha256):
    """Fail if an authored source changed during generation."""
    actual = file_sha256(path)
    if actual != expected_sha256:
        raise ValueError(
            f'Original mission changed during generation: {path} '
            f'({expected_sha256} became {actual})'
        )
    return actual
