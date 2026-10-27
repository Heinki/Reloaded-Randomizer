"""Deterministic, serializable run inputs, independent of campaign RNG streams."""

from copy import deepcopy
import hashlib
import json
import random

from randomizer.final_fortress.catalogue import SIDE_COUNTRIES

from . import MODE_ID
from .config import (
    DIFFICULTY_IDS, configuration_gaps, text, validate_config, validate_wave_multiplier,
)
from .waves import build_wave_schedule


PLAN_VERSION = 1


def configuration_digest(config):
    encoded = json.dumps(config, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def build_run_plan(config, *, difficulty, seed, player_country, selected_perks=(),
                   wave_multiplier=1, plan_version=PLAN_VERSION, selected_challenges=(),
                   challenge_stacks=None, perk_ranks=None, coop_players=(), fundraising_ranks=None, player_color=None):
    """Freeze approved inputs before the engine adapter creates map bytes.

    Times are simulation seconds. Victory owns the duration boundary, so the
    periodic wave schedule stops strictly before it. This function consumes
    no global or campaign random state.
    """
    if type(plan_version) is not int or plan_version != PLAN_VERSION:
        raise ValueError('Unsupported Reloaded Fortress plan version.')
    validate_config(config)
    validate_wave_multiplier(wave_multiplier)
    if coop_players:
        from randomizer.coop.direct import _name
        if (not isinstance(coop_players, (list, tuple)) or not 2 <= len(coop_players) <= 3):
            raise ValueError('Fortress co-op requires two or three human players and a new run.')
        for name in coop_players:
            _name(name)
        if len({name.casefold() for name in coop_players}) != len(coop_players):
            raise ValueError('Every Fortress player needs a different name.')
    sized_waves = 'wave_pressure' in config
    text(seed, 'Final Fortress seed')
    if difficulty not in DIFFICULTY_IDS:
        raise ValueError('Unknown Final Fortress difficulty.')
    if player_country not in SIDE_COUNTRIES:
        raise ValueError('Choose a playable C&C Reloaded country.')
    gaps = configuration_gaps(config, difficulty, wave_multiplier)
    if gaps:
        raise ValueError(' '.join(gaps))
    if not config['map'].get('enemy_defenses'):
        raise ValueError('Configure safe enemy base fortification layouts before starting a new Fortress run.')
    if not config['map'].get('enemy_wave_positions'):
        raise ValueError('Configure safe enemy reinforcement aprons before starting a new Fortress run.')
    catalogue = {perk['id']: perk for perk in config['perks']}
    selected = tuple(sorted(selected_perks))
    if len(set(selected)) != len(selected) or any(key not in catalogue for key in selected):
        raise ValueError('Selected perks must be unique configured IDs.')
    from .perks import resolve_effects
    effects = resolve_effects(config, selected, perk_ranks or {}, player_country,
                              include_power=True, include_power_upgrades=True,
                              include_arsenal=True, include_utilities=True,
                              include_lab_support=True, include_lab_shield=True,
                              include_lab_health=True,
                              include_lab_veterancy=True,
                              include_generator_power=True,
                              include_economy=True,
                              share_starting_power=True)
    settings = config['settings']
    enemy_rng = random.Random(f'{seed}:final_fortress:enemy_countries')
    enemies = [enemy_rng.choice(SIDE_COUNTRIES) for _ in range(3)]
    wave_schedule = build_wave_schedule(
        config, difficulty=difficulty, seed=seed, enemies=enemies,
        wave_multiplier=wave_multiplier, legacy=False,
        sized_waves=sized_waves,
    )
    rewards = {'victory': settings['completion_gems']}
    rewards.update({f'milestone:{entry["id"]}': entry['gems']
                    for entry in config['milestones']})
    rewards.update({f'camp:{entry["id"]}': entry['gems']
                    for entry in config['map']['camps']})
    if player_color is not None and (type(player_color) is not int or not 0 <= player_color < 64):
        raise ValueError('Invalid Final Fortress player color.')
    plan = {
        'mode_id': MODE_ID,
        'config_digest': configuration_digest(config),
        'seed': seed,
        'difficulty': difficulty,
        'player_country': player_country,
        'enemy_countries': enemies,
        'map': deepcopy(config['map']),
        'survival_seconds': settings['survival_seconds'],
        'wave_schedule': wave_schedule,
        'engine_difficulty': config['difficulties'][difficulty]['engine_difficulty'],
        'max_wave_units': settings['max_wave_units'],
        'milestones': deepcopy(config['milestones']),
        'selected_perks': list(selected),
        'effects': effects,
        'gem_rewards': rewards,
    }
    plan['perk_ranks'] = {key: (perk_ranks or {}).get(key, 1) for key in selected}
    # Helpers use the player's faction and share every enabled perk.
    allies = (min(2, len(coop_players) - 1 + effects['allied_helpers'])
              if coop_players else effects['allied_helpers'])
    plan['allied_countries'] = [player_country] * allies
    available = config['map'].get('allied_waypoints', [])
    if len(available) < allies:
        raise ValueError('This map has no configured allied helper start positions.')
    plan['allied_waypoints'] = available[:allies]
    if player_color is not None:
        plan['player_color'] = player_color
    if coop_players:
        plan['coop_players'] = list(coop_players)
    from .economy import validate_fundraising_ranks
    count = len(coop_players) or 1
    personal = ([effects['fundraising_stacks']] * count
                if fundraising_ranks is None else fundraising_ranks)
    validate_fundraising_ranks(personal, count)
    if personal[0] != effects['fundraising_stacks']:
        raise ValueError('Host Fundraising rank differs from the selected loadout.')
    plan['fundraising_ranks'] = list(personal)
    from .reinforcements import build_schedule
    plan['reinforcement_schedule'] = build_schedule(plan)
    plan.update(plan_version=PLAN_VERSION, game_id='cnc_reloaded', wave_multiplier=wave_multiplier)
    from .camps import resolve_camps
    resolve_camps(plan, config)
    plan.update(wave_pressure=deepcopy(config.get('wave_pressure')),
                wave_interval_seconds=settings['wave_interval_seconds'])
    # Native Action 14 counts transferred objects in the receiving house's
    # Kills statistic. Those setup transfers are not combat performance.
    plan['initial_transfer_kills'] = (1 + sum(unit['count'] for unit in effects['starting_units'])
                                      + len(effects['starting_defenses'])
                                      + len(effects.get('starting_buildings', []))
                                      + len(effects.get('defense_types', [])))
    # Refineries are accompanied by their native free harvester.
    plan['initial_transfer_kills'] += (len(effects['support_powers']))
    plan['initial_transfer_kills'] += sum(unit['count'] for unit in effects['starting_harvesters'])
    plan['initial_transfer_kills'] += len(effects['starting_power_buildings'])
    if wave_schedule:
        # The hidden wave-clock provider is transferred to the human once.
        plan['initial_transfer_kills'] += 1
    if effects.get('reinforcements'):
        plan['initial_transfer_kills'] += 1
    plan['performance'] = deepcopy(config.get('performance'))
    if plan['performance']:
        performance = plan['performance']
        rewards.update({f'kills:{tier * performance["units_per_tier"]}':
                        performance['gems_per_tier']
                        for tier in range(1, performance['max_tiers'] + 1)})
    challenges = {entry['id']: entry for entry in config.get('challenges', [])}
    chosen = sorted(selected_challenges)
    if len(chosen) != len(set(chosen)) or any(key not in challenges for key in chosen):
        raise ValueError('Selected challenges must be unique configured IDs.')
    plan['challenges'] = [deepcopy(challenges[key]) for key in chosen]
    from .challenges import maximum
    for entry in plan['challenges']:
        if 'enemy_effect_id' in entry:
            stacks = (challenge_stacks or {}).get(entry['id'], 1)
            if type(stacks) is not int or not 1 <= stacks <= maximum(entry):
                raise ValueError('Challenge stacks exceed the Grid buff limit.')
            entry['stacks'] = stacks
            entry['victory_gems'] = stacks * entry['victory_gems_per_stack']
    options = config.get('crate_rewards', [])
    for camp in plan['map']['camps']:
        if not options:
            continue
        rng = random.Random(f'{seed}:final_fortress:crate:{camp["id"]}')
        reward = rng.choices(options, weights=[entry['weight'] for entry in options], k=1)[0]
        camp['crate_reward'] = {
            'id': reward['id'], 'display_name': reward['display_name'],
            'credits': reward['credits'],
            'units': deepcopy(reward['units_by_country'].get(player_country, [])),
        }
    rewards['victory'] += sum(entry['victory_gems'] for entry in plan['challenges'])
    from .enemy_powers import add_powerhouses
    if config.get('wave_priorities'):
        plan['wave_priorities'] = deepcopy(config['wave_priorities'])
    add_powerhouses(plan)
    from .waves import add_air_support
    add_air_support(plan, config)
    if config.get('wave_priorities'):
        from .wave_priority import apply_priorities
        apply_priorities(plan, config['wave_priorities'])
    if coop_players:
        for slot in range(len(coop_players)):
            for camp in plan['map']['camps']:
                rewards[f'camp_pick:{slot}:{camp["id"]}'] = 0
        # Guests have the same grants, but neither the objective nor wave clock.
        powers = effects.get('support_powers', [])
        host_proxy = int(bool(effects.get('reveal_map')) and not powers)
        plan['initial_transfer_kills'] += host_proxy
        guest_transfers = (plan['initial_transfer_kills'] - 1 - int(bool(wave_schedule))
                           + int(not powers) - host_proxy)
        plan['coop_initial_transfer_kills'] = [plan['initial_transfer_kills'],
                                              *[guest_transfers] * (len(coop_players) - 1)]
    from .player_perks import coalition
    # Native score records identify computer houses by remap scheme, not
    # their repeated "Computer" name. These are the fixed friendly colors
    # used by both solo and co-op spawners (0, 4 and 6).
    # Reloaded UIMD: Gold, Orange and Purple, native scheme indices 3/13/17.
    humans = len(coop_players) or 1
    grants = (sum(unit['count'] for unit in effects['starting_units'])
              + sum(unit['count'] for unit in effects['starting_defenses'])
              + len(effects.get('starting_buildings', []))
              + len(effects.get('defense_types', []))
              + sum(unit['count'] for unit in effects.get('starting_harvesters', []))
              + len(effects.get('starting_power_buildings', [])))
    powers = effects.get('support_powers', [])
    helper_transfers = grants + (len(powers) or int(bool(coop_players or effects['starting_credits'])))
    plan['coalition_scores'] = [
        {'actor': actor, 'scheme': (3, 13, 17)[index],
         'name': (coop_players[index] if coop_players else 'Commander') if index < humans else None,
         'initial_transfers': (plan['coop_initial_transfer_kills'][index] if coop_players
                               else plan['initial_transfer_kills']) if index < humans else helper_transfers,
         'camp_slot': index if coop_players and index < humans else None}
        for index, (actor, _, _) in enumerate(coalition(plan))]
    return plan
