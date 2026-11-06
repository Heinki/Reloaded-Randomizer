"""Stage private provenance, power-output and self-healing descriptions."""

from functools import lru_cache

from randomizer.content.healing import self_healing_status_lines
from randomizer.core.csf import read_csf, write_csf
from randomizer.core.mix import MixArchive, MixFormatError
from randomizer.core.paths import GAME_ROOT
from randomizer.maps.assets import (
    RUNTIME_ASSET_DIR, _activate_runtime_assets, _runtime_manifest,
)
from randomizer.maps.ini import all_section_value_maps, merge_ini_section_values


MARKER = 'Granted by Randomizer'

# Some localized installations omit the Lunar Infantry description. Use this
# only when the installed text is absent; translated descriptions take priority.
DESCRIPTION_FALLBACKS = {
    'LUNR': 'Flying infantry. Attacks air targets and detects cloaked units.',
}


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


def stage_randomizer_tooltips(
    lines, clone_handled, *, installed_sections=None, power_bonus_report=None,
):
    """Extend native descriptions without replacing shared installed CSF keys."""
    installed, occupied = installed_string_tables()
    filename = next((
        f'stringtable{index:02d}.csf' for index in reversed(range(100))
        if f'stringtable{index:02d}.csf' not in occupied
    ), None)
    if filename is None:
        raise ValueError('No unused Ares string-table slot for Randomizer tooltips')
    sections = all_section_value_maps(lines)
    labels, rules = {}, {}
    installed_sections = {
        str(name).casefold(): {
            str(key).casefold(): value for key, value in values.items()
        }
        for name, values in (installed_sections or {}).items()
    }
    power_outputs = (power_bonus_report or {}).get('display_outputs', {})
    targets = {
        str(details.get('clone_id')): (source_id, True)
        for source_id, details in clone_handled.items()
        if details.get('clone_id')
    }
    for building in power_outputs:
        targets.setdefault(building, (building, False))
    for clone_id, (source_id, granted) in sorted(targets.items()):
        values = dict(installed_sections.get(str(source_id).casefold(), {}))
        values.update(installed_sections.get(clone_id.casefold(), {}))
        values.update(sections.get(clone_id, {}))
        power = power_outputs.get(clone_id)
        description = str(values.get('uidescription') or '')
        if description.upper().startswith('NOSTR:'):
            text = description[6:]
        elif description.casefold() in installed:
            text = installed[description.casefold()]
        elif description and source_id.upper() not in DESCRIPTION_FALLBACKS and not power:
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
        if not text.strip():
            text = DESCRIPTION_FALLBACKS.get(source_id.upper(), '')
        if source_id.upper() == 'NODSTLH_MP':
            healing = str(values.get('selfhealing', '')).casefold() in {'yes', 'true', '1'}
            text += '\n' + (
                'Self-healing repairs this structure only; it does not heal nearby units.'
                if healing else
                'Self-repair requires the Regeneration access upgrade; Rapid Regeneration only changes its interval.'
            )
        if any(key.startswith('selfhealing') for key in values):
            text += '\n' + '\n'.join(self_healing_status_lines(values, ''))
        if power:
            text += (
                f'\nYour power output with Randomizer upgrades: +{power["output"]}.'
                f'\nTooltip header shows base power (+{power["base"]}).'
            )
        if granted and MARKER not in text:
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
    if not path:
        return []
    # Asset activation deliberately skips missing/invalid optional inputs.
    # This table is mandatory once a map contains private RLRD/RLRN labels;
    # do not silently launch with MISSING labels if staging was cleaned.
    deployed = _activate_runtime_assets([path])
    if len(deployed) != 1 or not deployed[0].is_file():
        raise ValueError('Randomizer tooltip string table was not deployed')
    return deployed
