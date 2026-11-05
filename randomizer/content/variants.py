"""Reviewed minor unit copies consolidated for Randomizer production.

These technology and Secret Lab identities reuse a native unit's weapons and role. Small
differences in stats, cost, art or faction gates do not warrant another unlock.
Only player rewards and production use this mapping; authored map identities
and installed rules remain unchanged.
"""


REDUNDANT_UNIT_VARIANTS = {
    'ORCA2': 'ORCA',
    'CHITZ_ST': 'CHITZ',
    'DESO_ST': 'DESO',
    'MDISK_ST': 'MDISK',
    'TERROR_ST': 'TERROR',
    'TSCYBORG_ST': 'TSCYBORG',
    'TTNK_ST': 'TTNK',
    'YURI_ST': 'YURI',
}

# The Secret Lab's broad barracks access must not turn the Nod Cyborg into
# an ordinary cross-faction unit in Standard mode. Legacy access and buffs
# still migrate to the native identity.
CONSOLIDATED_UNIT_FACTIONS = {'TSCYBORG': ('Nod',)}


def canonical_player_unit_id(unit_id):
    unit_id = str(unit_id or '').strip().upper()
    return REDUNDANT_UNIT_VARIANTS.get(unit_id, unit_id)
