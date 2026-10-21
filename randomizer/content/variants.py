"""Reviewed minor unit copies consolidated for Randomizer production.

These Secret Lab identities reuse a native unit's weapons and role. Small
differences in stats, cost, art or faction gates do not warrant another unlock.
Only player rewards and production use this mapping; authored map identities
and installed rules remain unchanged.
"""


REDUNDANT_UNIT_VARIANTS = {
    'CHITZ_ST': 'CHITZ',
    'DESO_ST': 'DESO',
    'MDISK_ST': 'MDISK',
    'TERROR_ST': 'TERROR',
    'TSCYBORG_ST': 'TSCYBORG',
    'TTNK_ST': 'TTNK',
    'YURI_ST': 'YURI',
}


def canonical_player_unit_id(unit_id):
    unit_id = str(unit_id or '').strip().upper()
    return REDUNDANT_UNIT_VARIANTS.get(unit_id, unit_id)
