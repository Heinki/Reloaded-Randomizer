"""Shared eligibility for meaningful Reloaded ammo-capacity upgrades."""

# Reloaded's Harpy uses INT32_MAX - 2 as effectively unlimited ammunition.
# Treat the entire sentinel range alike rather than offering useless upgrades
# which can also overflow the engine's signed 32-bit ammo field.
UNLIMITED_AMMO_THRESHOLD = 2_147_483_645


def has_upgradeable_ammo(ammo):
    return ammo is not None and 0 < ammo < UNLIMITED_AMMO_THRESHOLD
