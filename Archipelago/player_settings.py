"""Lightweight contract for player-facing Archipelago settings."""

from copy import deepcopy


GAMEPLAY_CONFIG_KEYS = (
    'seed',
    'campaign_filter',
    'mission_goal',
    'progression_mode',
    'grid_two_start_positions',
    'unlock_all_rewards_after_final_grid_mission',
    'rewards_per_objective',
    'rewards_on_victory_only',
    'use_act_based_reward_multipliers',
    'difficulty',
    'game_speed',
    'player_color',
    'rainbowizer',
    'eva_voice',
)

PLAYER_GENERATION_KEYS = {
    'reward_mode',
    'arsenal',
    'include_no_build_missions',
    'include_no_build_production_missions',
    'include_operation_missions',
    'prioritize_no_build_missions',
    'excluded_mission_codes',
    'excluded_unit_access_ids',
    'excluded_superweapon_ids',
    'excluded_unit_buff_types',
    'excluded_power_buff_types',
    'randomize_unit_access',
    'start_with_tier_one_units',
    'start_with_tier_one_defenses',
    'starting_reward_count',
    'starting_reward_types',
    'starting_unlock_rewards',
    'include_defensive_buildings',
    'include_special_buildings',
    'include_special_rewards',
    'unlimited_hero_units',
    'share_chaos_role_buffs',
    'buff_allied_helpers',
    'failure_assistance',
    'include_buff_rewards',
    'include_superweapon_rewards',
    'include_secondary_superweapon_rewards',
    'include_aid_power_rewards',
    'include_power_buff_rewards',
    'enabled_buff_types',
    'enabled_power_buff_types',
    'reward_weights',
    'enemy_scaling',
}


def gameplay_config_snapshot(config):
    """Return player-facing gameplay controls without UI or network data."""
    if not isinstance(config, dict):
        return {}
    result = {
        key: deepcopy(config[key])
        for key in GAMEPLAY_CONFIG_KEYS
        if key in config
    }
    if isinstance(config.get('generation'), dict):
        result['generation'] = {
            key: deepcopy(value)
            for key, value in config['generation'].items()
            if key in PLAYER_GENERATION_KEYS
        }
    return result
