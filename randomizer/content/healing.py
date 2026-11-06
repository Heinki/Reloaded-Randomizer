"""Native Ares healing facts and useful reward eligibility."""

from math import isfinite

from randomizer.config.tuning import BUFF_EFFECTS, stacked_self_heal_rate


def _number(value, default):
    try:
        text = str(value).strip()
        number = float(text.rstrip('%'))
        if text.endswith('%'):
            number /= 100
        return number if isfinite(number) else default
    except (TypeError, ValueError):
        return default


def self_healing_metadata(values, category, default_rate=None):
    values = {str(key).casefold(): value for key, value in values.items()}
    abilities = {
        rank: tuple(
            item.strip() for item in str(values.get(f'{rank}abilities', '')).split(',')
            if item.strip() and item.strip().casefold() not in {'none', '<none>'}
        )
        for rank in ('veteran', 'elite')
    }
    maximum = _number(values.get('selfhealing.max'), 1.0)
    amount = _number(values.get('selfhealing.amount'), 1)
    caps = tuple(
        maximum if 'selfhealing.max' in values else _number(
            values.get(f'selfhealing.{rank}max'), maximum
        )
        for rank in ('rookie', 'veteran', 'elite')
    )
    fallback_rate = _number(
        default_rate, float(BUFF_EFFECTS['self_heal_rate']['minutes_at_15_fps'])
    )
    if fallback_rate <= 0:
        fallback_rate = float(BUFF_EFFECTS['self_heal_rate']['minutes_at_15_fps'])
    rate = _number(values.get('selfhealing.rate'), fallback_rate)
    trainable = str(values.get('trainable', 'yes')).strip().casefold() not in {
        'no', 'false', '0',
    }
    return {
        'trainable': trainable,
        'self_healing': str(values.get('selfhealing', '')).strip().casefold() in {
            'yes', 'true', '1',
        },
        'veteran_abilities': abilities['veteran'],
        'elite_abilities': abilities['elite'],
        'self_healing_caps': caps,
        'self_healing_rate': rate if rate > 0 else fallback_rate,
        'self_healing_combat_delay': max(0, int(_number(
            values.get('selfhealing.combatdelay'), 0
        ))),
        'self_healing_amounts': tuple(
            amount if 'selfhealing.amount' in values else _number(
                values.get(f'selfhealing.{rank}amount'), amount
            ) for rank in ('rookie', 'veteran', 'elite')
        ),
        'self_healing_unlock_stacks': (
            1 if category == 'defenses' or not trainable
            or 'self_heal' in {
                ability.casefold() for ability in abilities['veteran']
            } else 2
        ),
    }


def self_healing_buff_types(target):
    if float(target.get('strength') or 0) <= 0:
        return set()
    allowed = set()
    if not target['self_healing']:
        allowed.add('self_healing')
    if min(target['self_healing_caps']) < 1:
        allowed.add('self_healing_cap')
    rate = target['self_healing_rate']
    if stacked_self_heal_rate(1, rate) < stacked_self_heal_rate(0, rate):
        allowed.add('self_healing_rate')
    return allowed


def self_healing_status_lines(values, category):
    """Describe actual engine eligibility separately from rate and caps."""
    metadata = self_healing_metadata(values, category)
    rank = 'Rookie' if metadata['self_healing'] else next((
        rank.title() for rank in ('veteran', 'elite')
        if any(ability.casefold() == 'self_heal'
               for ability in metadata[f'{rank}_abilities'])
    ), None)
    if rank is None:
        return ['Self-healing disabled; rate/cap upgrades alone do not enable it.']
    caps = ', '.join(
        f'{rank} {cap * 100:g}%'
        for rank, cap in zip(('Rookie', 'Veteran', 'Elite'), metadata['self_healing_caps'])
    )
    lines = [f'Self-healing starts at {rank} rank. Health limits: {caps}.']
    amounts = metadata['self_healing_amounts']
    if len(set(amounts)) == 1:
        lines.append(f'Restores {amounts[0]:g} HP per tick.')
    else:
        lines.append('HP per tick: ' + ', '.join(
            f'{rank} {amount:g}' for rank, amount in
            zip(('Rookie', 'Veteran', 'Elite'), amounts)
        ) + '.')
    delay = metadata['self_healing_combat_delay']
    if delay:
        lines.append(f'Damage pauses self-healing for {delay} game frames.')
    return lines
