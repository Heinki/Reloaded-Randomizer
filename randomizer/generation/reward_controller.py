"""Generation methods shared with launcher; no GUI dependency."""

from randomizer.config.game_profile import CAMPAIGN_FACTIONS
from randomizer.rewards.catalogue import ALWAYS_AVAILABLE_TECH_IDS, BUFF_TARGETS, DEFAULT_REWARDS_PER_CHECK, MAX_REWARDS_PER_CHECK, REWARD_POOL, canonical_reward, canonical_rewards, check_rewards, clamp_int, linked_buff_variant_ids
from randomizer.rewards.arsenal import ARSENAL_MODE, arsenal_power_ids, arsenal_reward_pool, arsenal_unit_ids
from randomizer.ui.config import DEFAULT_PROGRESSION_MODE
from randomizer.missions.catalogue import FALLBACK_OBJECTIVE_COUNT, campaign_filter_factions, mission_reward_class, mission_reward_multiplier
from randomizer.rewards.planning import MAX_REWARDS_ACHIEVED_REWARD, is_max_rewards_achieved_reward, plan_seed_rewards
from randomizer.rewards.starting import filter_starting_reward_pool, normalize_starting_reward_count, normalize_starting_reward_types
from randomizer.rewards.weights import normalize_reward_weights, reward_selection_weight
from randomizer.rewards.rules import tech_ids_for_rewards




class RewardGeneration:
    def mission_lookup(self):
        return self._mission_by_code

    def objective_templates_for_code(self, code):
        mission = self.mission_lookup().get(code, {})
        objectives = list(mission.get('objectives') or ())
        reviewed_count = mission.get('objective_count')
        objective_count = (
            max(0, int(reviewed_count))
            if isinstance(reviewed_count, int)
            else len(objectives) or FALLBACK_OBJECTIVE_COUNT
        )
        templates = [
            (
                f'objective_{idx}',
                f'Objective {idx}',
                (
                    objectives[idx - 1]
                    if idx <= len(objectives)
                    else f'Complete reviewed objective milestone {idx}.'
                ),
            )
            for idx in range(1, objective_count + 1)
        ]
        templates.append(('victory', 'Mission Victory', 'Win the mission.'))
        return templates

    def active_launch_reward_factions(self):
        """Return factions whose saved rewards may affect this launch.

        Existing state files retain their original serialized reward data.
        Canonicalizing and filtering again at launch prevents an old catalog
        mistake from leaking foreign technology into a single-faction seed.
        """
        if self.active_reward_mode() in {'Chaos', ARSENAL_MODE}:
            return None
        generation_context = self.__dict__.get('_seed_generation_context') or {}
        selected = generation_context.get('campaign_filter')
        if selected is None:
            selected = (self.state or {}).get('campaign_filter', '')
        if not selected and hasattr(self, 'campaign_var'):
            selected = self.campaign_var.get()
        factions = set(campaign_filter_factions(selected))
        return factions | {'Neutral'} if factions else None

    def mission_arsenal(self, code):
        code = str(code or '').upper()
        override = self.__dict__.get('_arsenal_override')
        if isinstance(override, dict):
            return override.get(code, {})
        return (self.state or {}).get('mission_arsenals', {}).get(code, {})

    def reward_pool_for_code(self, code):
        reward_mode = self.active_reward_mode()
        if reward_mode == ARSENAL_MODE:
            return arsenal_reward_pool(
                self.configured_reward_pool(),
                self.mission_arsenal(code),
            )
        if reward_mode == 'Chaos':
            return self.configured_reward_pool()
        factions = self.reward_factions_for_code(code)
        pool = [
            reward
            for reward in REWARD_POOL
            if (
                not reward.get('factions')
                or factions.intersection(reward.get('factions', []))
                or 'Neutral' in reward.get('factions', [])
            )
        ]
        return self.filter_reward_pool(pool)

    def configured_reward_pool(self):
        settings = self.active_reward_settings()
        reward_mode = self.active_reward_mode()
        starting_access_ids = frozenset(
            self.active_starting_tier_one_access_ids()
        )
        cached = self.__dict__.get('_configured_reward_pool_cache')
        if (
            cached is not None
            and cached[0] is settings
            and cached[1] == reward_mode
            and cached[2] == starting_access_ids
        ):
            return cached[3]
        pool = self.filter_reward_pool(REWARD_POOL)
        self._configured_reward_pool_cache = (
            settings,
            reward_mode,
            starting_access_ids,
            pool,
        )
        return pool

    def configured_manual_starting_rewards(self):
        """Resolve exact selected rewards, omitting duplicate TechnoType access."""
        selected = set(self.active_starting_unlock_names())
        seen_tech_ids = (
            set(self.active_starting_tier_one_access_ids())
            | set(ALWAYS_AVAILABLE_TECH_IDS)
        )
        rewards = []
        for source in REWARD_POOL:
            reward = canonical_reward(source)
            if reward.get('name') not in selected:
                continue
            if (
                reward.get('kind') in {'buff', 'message', 'retired'}
                or not self.reward_is_permanent_starting_unlock(reward)
            ):
                continue
            allowed_factions = self.active_launch_reward_factions()
            if (
                allowed_factions is not None
                and reward.get('factions')
                and allowed_factions.isdisjoint(reward.get('factions', ()))
            ):
                continue
            tech_ids = tech_ids_for_rewards([reward])
            if reward.get('kind') != 'buff' and tech_ids & seen_tech_ids:
                continue
            rewards.append(dict(reward))
            if reward.get('kind') != 'buff':
                seen_tech_ids.update(tech_ids)
        return rewards

    def generate_starting_reward_plan(self, seed, initial_rewards=()):
        """Roll pre-run rewards on an RNG stream isolated from mission slots."""
        settings = self.active_reward_settings()
        count = normalize_starting_reward_count(
            settings.get('starting_reward_count', 0)
        )
        if count <= 0:
            return []
        allowed_types = normalize_starting_reward_types(
            settings.get('starting_reward_types')
        )
        code = '__starting_rewards__'

        def allowed_pool(pool):
            return filter_starting_reward_pool(pool, allowed_types)

        plan = plan_seed_rewards(
            [code],
            seed,
            {code: count},
            progression_mode='Starting Rewards',
            grid=None,
            reward_factions_for_code=self.reward_factions_for_code,
            reward_pool_for_code=lambda _code: allowed_pool(
                self.reward_pool_for_code(code)
            ),
            configured_reward_pool=lambda: allowed_pool(
                self.configured_reward_pool()
            ),
            starting_unlocked_tech_ids=(
                self.active_starting_tier_one_access_ids()
            ),
            initial_rewards=initial_rewards,
            require_access_for_unit_buffs=self.randomize_unit_access_enabled(),
            share_role_buffs=self.share_chaos_role_buffs_enabled(),
            reward_weights=settings.get('reward_weights'),
            rng_namespace='starting-rewards',
            avoid_unlocked_access=True,
            blocked_reward_names=self.active_starting_unlock_names(),
        )
        rewards = plan[code]
        real_rewards = [
            reward for reward in rewards
            if not is_max_rewards_achieved_reward(reward)
        ]
        if len(real_rewards) != len(rewards):
            real_rewards.append(dict(MAX_REWARDS_ACHIEVED_REWARD))
        return real_rewards

    def reward_is_defensive_building(self, reward):
        if reward.get('access_category') == 'defense':
            return True
        unit_id = reward.get('unit')
        return bool(unit_id and BUFF_TARGETS.get(unit_id, {}).get('category') == 'defenses')

    def reward_is_special_building(self, reward):
        if reward.get('access_category') == 'special_building':
            return True
        unit_id = str(reward.get('unit') or '').upper()
        return bool(
            unit_id
            and BUFF_TARGETS.get(unit_id, {}).get('category') == 'special_buildings'
        )

    def reward_is_special_reward(self, reward):
        if reward.get('special_reward') or reward.get('access_category') == 'special':
            return True
        unit_id = str(reward.get('unit') or '').upper()
        if not unit_id:
            tech_ids = tech_ids_for_rewards([reward])
            unit_id = next(iter(tech_ids), '')
        return bool(
            unit_id and BUFF_TARGETS.get(unit_id, {}).get('special_reward')
        )

    def filter_reward_pool(self, pool):
        reward_settings = self.active_reward_settings()
        excluded_access_ids = {
            str(unit_id).upper()
            for unit_id in reward_settings.get('excluded_unit_access_ids', [])
        }
        excluded_superweapon_ids = {
            str(power_id).upper()
            for power_id in reward_settings.get('excluded_superweapon_ids', [])
        }
        starting_access_ids = self.active_starting_tier_one_access_ids()
        randomize_access = bool(reward_settings.get('randomize_unit_access', True))
        include_buffs = bool(reward_settings.get('include_buff_rewards', True))
        include_superweapons = bool(reward_settings.get('include_superweapon_rewards', False))
        include_secondary_superweapons = bool(
            reward_settings.get('include_secondary_superweapon_rewards', False)
        )
        include_aid_powers = bool(reward_settings.get('include_aid_power_rewards', False))
        include_power_buffs = bool(
            reward_settings.get('include_power_buff_rewards', False)
        )
        include_defensive_buildings = bool(reward_settings.get('include_defensive_buildings', True))
        include_special_buildings = bool(reward_settings.get('include_special_buildings', True))
        include_special_rewards = bool(reward_settings.get('include_special_rewards', True))
        enabled_buff_types = set(reward_settings.get('enabled_buff_types') or [])
        enabled_power_buff_types = set(
            reward_settings.get('enabled_power_buff_types') or []
        )
        excluded_unit_buff_types = {
            str(unit_id).upper(): {str(buff_type) for buff_type in buff_types}
            for unit_id, buff_types in reward_settings.get(
                'excluded_unit_buff_types', {}
            ).items()
            if isinstance(buff_types, (list, tuple, set))
        }
        excluded_power_buff_types = {
            str(power_id).upper(): {str(buff_type) for buff_type in buff_types}
            for power_id, buff_types in reward_settings.get(
                'excluded_power_buff_types', {}
            ).items()
            if isinstance(buff_types, (list, tuple, set))
        }
        chaos_mode = self.active_reward_mode() == 'Chaos'
        reward_weights = normalize_reward_weights(
            reward_settings.get('reward_weights')
        )

        def power_category_enabled(reward):
            category = reward.get('power_category', 'offensive')
            return (
                (category == 'offensive' and include_superweapons)
                or (
                    category == 'secondary'
                    and include_secondary_superweapons
                )
                or (category == 'aid' and include_aid_powers)
            )

        def buff_unit_is_allowed(reward):
            unit_id = str(reward.get('unit') or '').upper()
            if not unit_id or unit_id in ALWAYS_AVAILABLE_TECH_IDS:
                return True
            return not linked_buff_variant_ids(unit_id).intersection(
                excluded_access_ids
            )

        configured_pool = []
        for reward in pool:
            if reward.get('enemy_reward'):
                # Enemy bonuses use an independent additional-reward plan.
                # They never consume or reserve a normal player-reward slot.
                continue
            else:
                configured_pool.append(reward)

        return [
            reward
            for reward in configured_pool
            if (
                reward_selection_weight(reward, reward_weights) > 0
                and
                (
                    (
                        reward.get('kind') == 'buff'
                        and reward.get('power_buff_type')
                        and include_power_buffs
                        and (include_special_rewards or not self.reward_is_special_reward(reward))
                        and power_category_enabled(reward)
                        and reward.get('power_buff_type')
                        in enabled_power_buff_types
                        and str(reward.get('superweapon') or '').upper()
                        not in excluded_superweapon_ids
                        and reward.get('power_buff_type')
                        not in excluded_power_buff_types.get(
                            str(reward.get('superweapon') or '').upper(), set()
                        )
                    )
                    or (
                        reward.get('kind') == 'buff'
                        and not reward.get('power_buff_type')
                        and include_buffs
                        and (include_special_rewards or not self.reward_is_special_reward(reward))
                        and (include_defensive_buildings or not self.reward_is_defensive_building(reward))
                        and (include_special_buildings or not self.reward_is_special_building(reward))
                        and (
                            reward.get('buff_type') == 'starting_credits'
                            or reward.get('buff_type') in enabled_buff_types
                        )
                        and reward.get('buff_type') not in excluded_unit_buff_types.get(
                            str(reward.get('unit') or '').upper(), set()
                        )
                        and buff_unit_is_allowed(reward)
                        and not (
                            reward_settings.get('unlimited_hero_units')
                            and reward.get('buff_type') == 'build_limit'
                            and not self.reward_is_special_building(reward)
                        )
                        and not (
                            chaos_mode
                            and reward.get('buff_type') == 'production'
                            and not reward.get('global_buff')
                        )
                    )
                    or (
                        reward.get('kind') == 'superweapon'
                        and (include_special_rewards or not self.reward_is_special_reward(reward))
                        and power_category_enabled(reward)
                        and str(reward.get('superweapon') or '').upper()
                        not in excluded_superweapon_ids
                    )
                    or (
                        reward.get('kind') not in {'buff', 'superweapon'}
                        and randomize_access
                        and (include_special_rewards or not self.reward_is_special_reward(reward))
                        and (include_defensive_buildings or not self.reward_is_defensive_building(reward))
                        and (include_special_buildings or not self.reward_is_special_building(reward))
                        and not tech_ids_for_rewards([reward]).intersection(starting_access_ids)
                        and not tech_ids_for_rewards([reward]).intersection(excluded_access_ids)
                    )
                )
            )
        ]

    def reward_factions_for_code(self, _code):
        if self.active_reward_mode() == ARSENAL_MODE:
            return set(
                self.active_reward_settings().get('arsenal', {}).get(
                    'factions', ()
                )
            )
        generation_context = self.__dict__.get('_seed_generation_context') or {}
        selected = generation_context.get('campaign_filter')
        if selected is None:
            selected = self.campaign_var.get() if hasattr(self, 'campaign_var') else ''
        return (
            set(campaign_filter_factions(selected))
            or set(CAMPAIGN_FACTIONS)
        )

    def state_objective_summary(self, mission_codes):
        return {
            code: [hint for _, _, hint in self.objective_templates_for_code(code)]
            for code in mission_codes
        }

    def build_mission_checks(
        self,
        mission_codes,
        seed,
        earned_rewards=None,
        completed_missions=None,
        preserved_checks=None,
        rewards_per_check=DEFAULT_REWARDS_PER_CHECK,
        rewards_on_victory_only=False,
        progression_mode=None,
        grid=None,
        starting_rewards=None,
        progress=None,
    ):
        templates_by_code = {code: self.objective_templates_for_code(code) for code in mission_codes}
        reward_check_ids_by_code = {
            code: (
                {'victory'}
                if rewards_on_victory_only
                else {check_id for check_id, _name, _hint in templates}
            )
            for code, templates in templates_by_code.items()
        }
        earned_rewards = list(earned_rewards or [])
        starting_rewards = list(starting_rewards or [])
        completed_missions = list(completed_missions or [])
        rewards_per_check = clamp_int(rewards_per_check, 1, MAX_REWARDS_PER_CHECK, DEFAULT_REWARDS_PER_CHECK)
        completed = set(completed_missions)
        completed_rewards = {
            code: reward
            for code, reward in zip(completed_missions, earned_rewards)
        }
        preserved_checks = preserved_checks or {}
        checks = {}
        preserved_reward_check_ids = {}
        for code in mission_codes:
            old_checks = {
                check.get('id'): check
                for check in preserved_checks.get(code, [])
                if check.get('id')
            }
            preserved_reward_check_ids[code] = {
                check_id
                for check_id, _name, _hint in templates_by_code[code]
                if check_id in reward_check_ids_by_code[code]
                if (
                    check_id in old_checks
                    and (
                        old_checks[check_id].get('unlocked')
                        or old_checks[check_id].get('released')
                    )
                    and check_rewards(old_checks[check_id])
                ) or (
                    check_id == (
                        'victory' if rewards_on_victory_only else 'objective_1'
                    )
                    and code in completed_rewards
                )
            }
        multipliers_by_code = {}
        for code in mission_codes:
            old_multiplier = next((
                check.get('reward_multiplier')
                for check in preserved_checks.get(code, [])
                if isinstance(check.get('reward_multiplier'), int)
                and not isinstance(check.get('reward_multiplier'), bool)
                and check.get('reward_multiplier') >= 1
            ), None)
            multipliers_by_code[code] = (
                old_multiplier
                if old_multiplier is not None
                else mission_reward_multiplier(code)
            )
        base_slots_by_code = {
            code: (
                len(
                    reward_check_ids_by_code[code]
                    - preserved_reward_check_ids[code]
                )
            ) * rewards_per_check
            for code in mission_codes
        }
        base_rewards_by_code = self.generate_seed_reward_plan(
            mission_codes,
            seed,
            base_slots_by_code,
            progression_mode=progression_mode,
            grid=grid,
            initial_rewards=starting_rewards + earned_rewards,
            avoid_unlocked_access=bool(starting_rewards),
            reserved_rewards=(),
        )
        if progress is not None:
            progress('Planning mission multiplier rewards.', 0, 1)
        bonus_slots_by_code = {
            code: (
                len(reward_check_ids_by_code[code])
                * rewards_per_check
                * (multipliers_by_code[code] - 1)
                if 'victory' not in preserved_reward_check_ids[code]
                else 0
            )
            for code in mission_codes
        }
        bonus_rewards_by_code = self.generate_mission_bonus_reward_plan(
            mission_codes,
            seed,
            bonus_slots_by_code,
            base_rewards_by_code,
            progression_mode=progression_mode,
            grid=grid,
            initial_rewards=starting_rewards + earned_rewards,
            reserved_rewards=(),
            progress=progress,
        )

        for code in mission_codes:
            mission_checks = []
            base_rewards = base_rewards_by_code.get(code, [])
            bonus_rewards = bonus_rewards_by_code.get(code, [])
            base_reward_index = 0
            old_checks = {
                check.get('id'): check
                for check in preserved_checks.get(code, [])
                if check.get('id')
            }
            templates = templates_by_code[code]
            for check_id, name, hint in templates:
                old_check = old_checks.get(check_id)
                if (
                    check_id in reward_check_ids_by_code[code]
                    and
                    old_check
                    and (old_check.get('unlocked') or old_check.get('released'))
                    and check_rewards(old_check)
                ):
                    rewards_for_check = check_rewards(old_check)
                    unlocked = bool(old_check.get('unlocked'))
                    released = bool(old_check.get('released')) and not unlocked
                elif (
                    check_id == (
                        'victory' if rewards_on_victory_only else 'objective_1'
                    )
                    and code in completed_rewards
                ):
                    rewards_for_check = canonical_rewards(completed_rewards[code])
                    unlocked = code in completed
                    released = False
                elif check_id not in reward_check_ids_by_code[code]:
                    rewards_for_check = []
                    unlocked = False
                    released = False
                else:
                    rewards_for_check = base_rewards[
                        base_reward_index:base_reward_index + rewards_per_check
                    ]
                    if check_id == 'victory':
                        rewards_for_check += bonus_rewards
                    real_rewards = [
                        reward for reward in rewards_for_check
                        if not is_max_rewards_achieved_reward(reward)
                    ]
                    if len(real_rewards) != len(rewards_for_check):
                        rewards_for_check = real_rewards + [
                            dict(MAX_REWARDS_ACHIEVED_REWARD)
                        ]
                    unlocked = False
                    released = False
                if (
                    check_id in reward_check_ids_by_code[code]
                    and check_id not in preserved_reward_check_ids[code]
                ):
                    base_reward_index += rewards_per_check
                primary_reward = (
                    rewards_for_check[0] if rewards_for_check else None
                )
                mission_checks.append({
                    'id': check_id,
                    'name': name,
                    'hint': hint,
                    'reward': primary_reward,
                    'rewards': rewards_for_check,
                    'base_reward_count': (
                        rewards_per_check
                        if check_id in reward_check_ids_by_code[code]
                        else 0
                    ),
                    'multiplier_bonus_count': (
                        bonus_slots_by_code[code]
                        if check_id == 'victory' else 0
                    ),
                    'reward_multiplier': multipliers_by_code[code],
                    'reward_class': mission_reward_class(code),
                    'unlocked': unlocked or code in completed,
                    'released': released and code not in completed,
                })
            checks[code] = mission_checks

        return checks

    def generate_mission_bonus_reward_plan(
        self,
        mission_codes,
        seed,
        slots_by_code,
        base_rewards_by_code,
        *,
        progression_mode=None,
        grid=None,
        initial_rewards=(),
        reserved_rewards=(),
        progress=None,
    ):
        """Plan valid completion bonuses without changing base assignments."""
        bonus_plan = {code: [] for code in mission_codes}
        all_base_rewards = {
            code: list(base_rewards_by_code.get(code, ()))
            for code in mission_codes
        }
        available_base_rewards = []
        prior_bonus_rewards = []
        bonus_codes = [
            code for code in mission_codes
            if max(0, int(slots_by_code.get(code, 0))) > 0
        ]
        bonus_total = len(bonus_codes)
        bonus_index = 0
        for code_index, code in enumerate(mission_codes):
            slot_count = max(0, int(slots_by_code.get(code, 0)))
            available_base_rewards.extend(all_base_rewards[code])
            if slot_count <= 0:
                continue
            bonus_index += 1
            if progress is not None:
                progress(
                    f'Planning mission bonuses: {bonus_index}/{bonus_total}.',
                    bonus_index,
                    bonus_total,
                )
            reserved = [
                reward
                for other_code in mission_codes[code_index + 1:]
                for reward in all_base_rewards[other_code]
            ] + list(reserved_rewards)
            plan = self.generate_seed_reward_plan(
                [code],
                seed,
                {code: slot_count},
                progression_mode=progression_mode,
                grid=None,
                initial_rewards=(
                    list(initial_rewards)
                    + available_base_rewards
                    + prior_bonus_rewards
                ),
                avoid_unlocked_access=True,
                rng_namespace=f'mission-reward-multiplier:{code}',
                reserved_rewards=reserved,
            )
            bonus_plan[code] = plan.get(code, [])
            prior_bonus_rewards.extend(bonus_plan[code])
        return bonus_plan

    def generate_seed_reward_plan(
        self,
        mission_codes,
        seed,
        slots_by_code,
        progression_mode=None,
        grid=None,
        initial_rewards=(),
        avoid_unlocked_access=False,
        rng_namespace='seed-rewards',
        reserved_rewards=(),
    ):
        if progression_mode is None:
            progression_mode = (
                self.state.get('progression_mode')
                if getattr(self, 'state', None)
                else self.progression_mode_var.get()
                if hasattr(self, 'progression_mode_var')
                else DEFAULT_PROGRESSION_MODE
            )
        if grid is None and getattr(self, 'state', None):
            grid = self.state.get('grid')
        arsenal_units = set()
        arsenal_powers = set()
        if self.active_reward_mode() == ARSENAL_MODE:
            for code in mission_codes:
                arsenal = self.mission_arsenal(code)
                arsenal_units.update(arsenal_unit_ids(arsenal))
                arsenal_powers.update(arsenal_power_ids(arsenal))
        return plan_seed_rewards(
            mission_codes,
            seed,
            slots_by_code,
            progression_mode=progression_mode,
            grid=grid,
            reward_factions_for_code=self.reward_factions_for_code,
            reward_pool_for_code=self.reward_pool_for_code,
            configured_reward_pool=self.configured_reward_pool,
            reward_pool_cache_key_for_code=(
                (lambda code: ('arsenal', str(code).upper()))
                if self.active_reward_mode() == ARSENAL_MODE
                else None
            ),
            allow_cross_pool_fallback=(
                self.active_reward_mode() != ARSENAL_MODE
            ),
            starting_unlocked_tech_ids=(
                arsenal_units or self.active_starting_tier_one_access_ids()
            ),
            starting_unlocked_power_ids=arsenal_powers,
            initial_rewards=initial_rewards,
            require_access_for_unit_buffs=self.randomize_unit_access_enabled(),
            share_role_buffs=self.share_chaos_role_buffs_enabled(),
            reward_weights=self.active_reward_settings().get(
                'reward_weights'
            ),
            avoid_unlocked_access=avoid_unlocked_access,
            blocked_reward_names=self.active_starting_unlock_names(),
            rng_namespace=rng_namespace,
            reserved_rewards=reserved_rewards,
        )

