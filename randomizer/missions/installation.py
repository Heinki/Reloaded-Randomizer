"""Read-only discovery and validation for installed Reloaded missions."""

from collections import Counter
from pathlib import Path

from randomizer.core.paths import BATTLE_INI, GAME_ROOT


def _read_ini_sections(path):
    sections = {}
    current = None
    for raw_line in Path(path).read_text(
        encoding='utf-8', errors='ignore'
    ).splitlines():
        line = raw_line.split(';', 1)[0].strip()
        if not line:
            continue
        if line.startswith('[') and line.endswith(']'):
            current = line[1:-1].strip()
            sections.setdefault(current, {})
            continue
        if current and '=' in line:
            key, value = line.split('=', 1)
            sections[current][key.strip()] = value.strip()
    return sections


def installed_mission_catalogue(battle_path=BATTLE_INI):
    """Return active Battle.ini missions in their authored catalogue order."""
    battle_path = Path(battle_path)
    if not battle_path.is_file():
        return []
    sections = _read_ini_sections(battle_path)
    mission_codes = []
    seen = set()
    for code in sections.get('Battles', {}).values():
        if code in seen or not sections.get(code, {}).get('Scenario'):
            continue
        seen.add(code)
        mission_codes.append(code)

    return [
        {
            'index': index,
            'code': code,
            'scenario': sections[code]['Scenario'],
            'title': sections[code].get('Description', code),
            'side': sections[code].get(
                'SideName', sections[code].get('Side', '')
            ),
        }
        for index, code in enumerate(mission_codes, start=1)
    ]


def resolve_installed_scenario(scenario, game_root=GAME_ROOT):
    """Resolve one catalogue path without allowing escape from game root."""
    game_root = Path(game_root).resolve()
    normalized = str(scenario or '').replace('\\', '/').lstrip('/')
    components = [
        part for part in normalized.split('/') if part not in {'', '.'}
    ]
    if not components or '..' in components:
        raise ValueError(f'Invalid mission scenario path: {scenario}')

    candidate = game_root.joinpath(*components).resolve()
    if candidate != game_root and game_root not in candidate.parents:
        raise ValueError(f'Mission scenario escapes game root: {scenario}')
    if candidate.is_file():
        return candidate

    # Battle.ini paths follow Windows' case-insensitive rules. Linux game
    # installations may preserve a different spelling for any path component.
    candidate = game_root
    try:
        for component in components:
            exact = candidate / component
            if exact.exists():
                candidate = exact
                continue
            folded = component.casefold()
            candidate = next(
                child for child in candidate.iterdir()
                if child.name.casefold() == folded
            )
    except (OSError, StopIteration):
        candidate = game_root.joinpath(*components)
    candidate = candidate.resolve()
    if candidate != game_root and game_root not in candidate.parents:
        raise ValueError(f'Mission scenario escapes game root: {scenario}')
    return candidate


def installation_catalogue_report(
    battle_path=BATTLE_INI,
    game_root=GAME_ROOT,
):
    """Return deterministic, read-only catalogue validation results."""
    missions = installed_mission_catalogue(battle_path)
    missing = []
    scenarios = []
    side_counts = Counter()
    folder_counts = Counter()
    for mission in missions:
        scenario = mission['scenario']
        path = resolve_installed_scenario(scenario, game_root)
        scenarios.append(scenario.lower().replace('\\', '/'))
        if not path.is_file():
            missing.append({'code': mission['code'], 'scenario': scenario})
        side_counts[mission['side'].strip().lower()] += 1
        parts = tuple(
            part for part in scenario.replace('\\', '/').split('/') if part
        )
        if len(parts) >= 3:
            folder_counts[parts[2]] += 1

    duplicates = sorted(
        scenario for scenario, count in Counter(scenarios).items() if count > 1
    )
    return {
        'battle_ini': str(Path(battle_path)),
        'mission_count': len(missions),
        'missing_scenarios': missing,
        'duplicate_scenarios': duplicates,
        'side_counts': dict(sorted(side_counts.items())),
        'folder_counts': dict(sorted(folder_counts.items())),
        'valid': bool(missions) and not missing and not duplicates,
    }
