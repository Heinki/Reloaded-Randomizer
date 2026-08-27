"""Installed C&C Reloaded weapon relationships used by clone safety."""

from collections import defaultdict

from randomizer.content.inventory import TYPE_SECTIONS, read_rules_sections


_SECTIONS, _SOURCE = read_rules_sections()
_SECTION_NAMES = {str(name).upper(): name for name in _SECTIONS}
_WEAPON_KEYS = ('Primary', 'Secondary', 'ElitePrimary', 'EliteSecondary')


def _number(value):
    try:
        number = float(str(value).strip())
        return int(number) if number.is_integer() else number
    except (TypeError, ValueError):
        return None


def _weapon_ids(values):
    result = []
    for key in _WEAPON_KEYS:
        for value in str(values.get(key) or '').split(','):
            weapon_id = value.strip()
            if weapon_id and weapon_id.lower() not in {'none', '<none>'}:
                result.append(weapon_id.upper())
    return tuple(dict.fromkeys(result))


_users = defaultdict(set)
_direct = {}
for _registry in TYPE_SECTIONS.values():
    for _type_id in _SECTIONS.get(_registry, {}).values():
        _type_id = str(_type_id).strip().upper()
        if not _type_id:
            continue
        _values = _SECTIONS.get(_SECTION_NAMES.get(_type_id), {})
        _weapons = _weapon_ids(_values)
        if _weapons:
            _direct[_type_id] = _weapons
        for _weapon_id in _weapons:
            _users[_weapon_id].add(_type_id)

ROSTER_WEAPON_REFS = dict(_direct)
ROSTER_DAMAGE_WEAPON_REFS = dict(_direct)
WEAPON_USER_IDS = {
    weapon_id: tuple(sorted(type_ids))
    for weapon_id, type_ids in _users.items()
}
WEAPON_BASE_STATS = {}
for _weapon_id in sorted(_users):
    _values = _SECTIONS.get(_SECTION_NAMES.get(_weapon_id), {})
    WEAPON_BASE_STATS[_weapon_id] = (
        _number(_values.get('Damage')),
        _number(_values.get('ROF')),
        _number(_values.get('Range')),
    )

