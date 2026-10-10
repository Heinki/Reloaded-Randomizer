"""Stage native campaign sidebar backgrounds before the engine opens them.

The reported 0072FC92 crash dereferences a null large-background SHP in
the engine's sidebar initialization at 1280x1024. Loose, leased copies avoid
depending on the lifetime of nested side MIX files during campaign loading.
"""

import tempfile
from pathlib import Path

from randomizer.core.mix import MixArchive, extract_mix_members
from randomizer.core.paths import GAME_ROOT
from randomizer.maps.assets import (
    CustomAssetError, RUNTIME_ASSET_DIR, _activate_runtime_assets,
)
from randomizer.maps.houses import map_house_records, player_house_from_map
from randomizer.maps.ini import IniLines, all_section_value_maps, read_text
from randomizer.ui.cameos import installed_rules_registry


def deploy_campaign_sidebar_backgrounds(map_path):
    """Deploy the selected side's installed SHPs through the asset lease."""
    lines = IniLines(read_text(Path(map_path)).splitlines())
    sections = all_section_value_maps(lines)
    records = map_house_records(lines, sections=sections)
    house = player_house_from_map(lines, records=records)
    country = records.get(house, {}).get('country', '')
    _powers, installed = installed_rules_registry()

    def effective(section):
        values = {k.lower(): v for k, v in installed.get(section, {}).items()}
        values.update(sections.get(section, {}))
        return values

    side = effective(country).get('side', '')
    values = effective(side)
    index = int(values.get('sidebar.mixfileindex', {'GDI': 1, 'Nod': 2}.get(side, 3)))
    yuri_names = str(values.get('sidebar.yurifilenames', side == 'ThirdSide')).lower() in {
        'yes', 'true', '1',
    }
    suffix = 'y' if yuri_names else ''
    names = [f'bkgd{size}{suffix}.shp' for size in ('lg', 'md', 'sm')]
    names.append(f'uibkgd{suffix}.pal')
    # Stock sides are supplied by the base game. Reloaded's custom side MIX
    # files are in expandmd archives and can be extracted without decryption.
    if index <= 2:
        return []
    data_by_name = {}
    archives = sorted(GAME_ROOT.glob('*.mix'), key=lambda p: p.name.lower(), reverse=True)
    with tempfile.TemporaryDirectory(prefix='reloaded-sidebar-') as directory:
        for mix_name in (f'sidec{index:02d}md.mix', f'sidec{index:02d}.mix', f'sidenc{index:02d}.mix'):
            loose = GAME_ROOT / mix_name
            source = loose if loose.is_file() else Path(directory) / mix_name
            if not loose.is_file():
                extract_mix_members(archives, [(mix_name, source)])
            if not source.is_file():
                continue
            with MixArchive(source) as archive:
                for name in names:
                    if name not in data_by_name:
                        data = archive.read(name)
                        if data:
                            data_by_name[name] = data
    missing = [name for name in names if name not in data_by_name and not (GAME_ROOT / name).is_file()]
    if missing:
        raise CustomAssetError('Installed campaign sidebar backgrounds are missing: ' + ', '.join(missing))
    RUNTIME_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    staged = []
    for name, data in data_by_name.items():
        if (GAME_ROOT / name).is_file():
            continue
        target = RUNTIME_ASSET_DIR / name
        target.write_bytes(data)
        staged.append(target)
    return _activate_runtime_assets(staged) if staged else []
