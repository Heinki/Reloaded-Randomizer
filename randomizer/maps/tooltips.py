"""Append Randomizer provenance to private Phobos tooltip descriptions."""

from functools import lru_cache

from randomizer.core.csf import read_csf, write_csf
from randomizer.core.mix import MixArchive, MixFormatError
from randomizer.core.paths import GAME_ROOT
from randomizer.maps.assets import (
    RUNTIME_ASSET_DIR, _activate_runtime_assets, _runtime_manifest,
)
from randomizer.maps.ini import all_section_value_maps, merge_ini_section_values


MARKER = 'Granted by Randomizer'


@lru_cache(maxsize=1)
def installed_string_tables():
    """Follow Ares table order, preferring loose files over MIX members."""
    tables = {}
    names = ['ra2md.csf', *(f'stringtable{index:02d}.csf' for index in range(100))]
    pending = []
    managed = _runtime_manifest()
    for name in names:
        path = GAME_ROOT / name
        if name in managed:
            continue
        if path.is_file():
            tables[name] = read_csf(path.read_bytes())
        else:
            pending.append(name)
    for archive_path in sorted(GAME_ROOT.glob('*.mix'), reverse=True):
        if not pending:
            break
        try:
            with MixArchive(archive_path) as archive:
                for name in tuple(pending):
                    data = archive.read(name)
                    if data is not None:
                        tables[name] = read_csf(data)
                        pending.remove(name)
        except (OSError, MixFormatError):
            continue
    labels = {}
    for name in names:
        labels.update(tables.get(name, {}))
    return labels, frozenset(tables)


def stage_randomizer_tooltips(lines, clone_handled):
    """Keep native text and append a marker without overriding native CSF keys."""
    installed, occupied = installed_string_tables()
    filename = next((
        f'stringtable{index:02d}.csf' for index in reversed(range(100))
        if f'stringtable{index:02d}.csf' not in occupied
    ), None)
    if filename is None:
        raise ValueError('No unused Ares string-table slot for Randomizer tooltips')
    sections = all_section_value_maps(lines)
    labels, rules = {}, {}
    for source_id, details in sorted(clone_handled.items()):
        clone_id = str(details.get('clone_id') or '')
        if not clone_id:
            continue
        values = sections.get(clone_id, {})
        description = str(values.get('uidescription') or '')
        if description.upper().startswith('NOSTR:'):
            text = description[6:]
        elif description.casefold() in installed:
            text = installed[description.casefold()]
        elif description:
            # An unresolved native label must stay intact. Put provenance in
            # the name instead, using a private CSF label with no NOSTR limit.
            name = str(values.get('uiname') or '')
            text = name[6:] if name.upper().startswith('NOSTR:') else (
                installed.get(name.casefold(), str(source_id))
            )
            label = f'RLRN:{clone_id}'
            labels[label] = f'{text} [Randomizer]'
            rules[clone_id] = {'UIName': label}
            continue
        else:
            text = ''
        if MARKER not in text:
            text = '\n'.join(part for part in (text.rstrip(), MARKER) if part)
        label = f'RLRD:{clone_id}'
        labels[label] = text
        rules[clone_id] = {'UIDescription': label}
    if not labels:
        return None
    merge_ini_section_values(lines, rules)
    RUNTIME_ASSET_DIR.mkdir(parents=True, exist_ok=True)
    target = RUNTIME_ASSET_DIR / filename
    target.write_bytes(write_csf(labels))
    return target


def deploy_randomizer_tooltips(path):
    """Use the existing lease, ownership manifest, and cleanup lifecycle."""
    return _activate_runtime_assets([path]) if path else []
