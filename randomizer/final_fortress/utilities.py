"""Player-only utility perks using established reward eligibility and math."""

from functools import lru_cache
from math import ceil

from randomizer.config.tuning import stacked_self_heal_amount
from randomizer.maps.buff_values import apply_unit_buff_value, resolved_safe_strength
from randomizer.maps.clone_references import _target_with_effective_unit_stats
from randomizer.rewards.catalogue import (
    BUFF_TARGETS, REWARD_POOL, linked_buff_variant_ids,
)


@lru_cache(maxsize=1)
def supported_pairs():
    return frozenset((variant, entry['buff_type']) for entry in REWARD_POOL
                     if entry.get('kind') == 'buff' and entry.get('unit') and entry.get('buff_type')
                     for variant in linked_buff_variant_ids(entry['unit'])
                     if not BUFF_TARGETS.get(variant, {}).get('linked_buff_weapon_only')
)


def utility_updates(original, row, effects, *, building=False, defense=False, linked_mobile=False):
    """Preserve live baselines and exclusions rather than broad native overrides."""
    power = effects.get('generator_power_percent', 0)
    generation = {field: str(ceil(float(row[field]) * (1 + power / 100)))
                  for field in ('Power', 'ExtraPower')
                  if building and power and float(row.get('Power', '0')) > 0
                  and float(row.get(field, '0')) > 0}
    updates = dict(generation)
    limit = effects.get('special_building_limit_stacks', 0)
    if building and limit:
        native = int(row.get('BuildLimit', '0'))
        if native > 0:
            updates['BuildLimit'] = str(native + min(limit, 3))
    if not any(effects.get(field) for field in ('healing_stacks', 'recon_stacks',
                                              'unique_limit_stacks')):
        return updates
    unit_limit = effects.get('unique_limit_stacks', 0)
    if not building and unit_limit and int(row.get('BuildLimit', '0')) > 0:
        updates['BuildLimit'] = str(int(row['BuildLimit']) + unit_limit)
    metadata = BUFF_TARGETS.get(original)
    if not metadata:
        return updates
    pairs = supported_pairs()
    target = _target_with_effective_unit_stats(metadata, row)
    mobile_or_defense = not building or defense or linked_mobile
    healing = effects.get('healing_stacks', 0)
    if mobile_or_defense and healing and any(
            (original, kind) in pairs for kind in ('self_healing', 'self_healing_rate')):
        updates.update(row)
        apply_unit_buff_value(updates, target, 'self_healing', max(2, healing))
        apply_unit_buff_value(updates, target, 'self_healing_cap', 1)
        # Rookie healing is intentional from rank one. Already stronger
        # native healing is retained; Tier perks contribute their actual HP.
        updates['SelfHealing'] = 'yes'
        updates['SelfHealing.Amount'] = str(max(int(float(row.get('SelfHealing.Amount', '0'))),
            stacked_self_heal_amount(resolved_safe_strength(target, row), healing)))
        apply_unit_buff_value(updates, target, 'self_healing_rate', 0)
    recon = effects.get('recon_stacks', 0)
    if mobile_or_defense and recon:
        if (original, 'sight') in pairs:
            apply_unit_buff_value(updates, target, 'sight', recon)
        if (original, 'sensors') in pairs:
            sensor_target = _target_with_effective_unit_stats(metadata, {**row, **updates})
            apply_unit_buff_value(updates, sensor_target, 'sensors', 1)
            updates['SensorsSight'] = str(max(int(float(row.get('SensorsSight', '0'))),
                                             int(updates['SensorsSight'])))
    limit = effects.get('unique_limit_stacks', 0)
    if not building and limit:
        native = int(row.get('BuildLimit', '0'))
        if native > 0:
            updates['BuildLimit'] = str(native + limit)
    updates.update(generation)
    if building and effects.get('special_building_limit_stacks') and int(row.get('BuildLimit', '0')) > 0:
        updates['BuildLimit'] = str(int(row['BuildLimit']) + min(3, effects['special_building_limit_stacks']))
    return {key: value for key, value in updates.items() if row.get(key) != value}
