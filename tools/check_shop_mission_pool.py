"""Regressions for Advanced mission filters and fresh Shop suggestions."""

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Archipelago.bundle_generation import _checked_in_generation_rules

unittest.enterModuleContext(patch(
    'randomizer.content.inventory.read_rules_sections',
    return_value=(_checked_in_generation_rules(), 'checked-in-apworld-rules'),
))

from randomizer.application.advanced_settings import AdvancedSettingsController
from randomizer.application.shop_archipelago_controller import ShopArchipelagoController
from randomizer.application.shop_controller import ShopController
from randomizer.missions.catalogue import OPERATION_MISSION_CODES
from randomizer.missions.metadata import MISSION_METADATA_BY_CODE
from randomizer.shop.missions import (
    generate_mission_offers, mission_pool_requires_repeats, unrestricted_shop_missions,
)
from randomizer.shop.config import SHOP_CONFIG
from randomizer.shop.model import RunStatus, ShopProfile, ShopRun
from randomizer.shop.state import normalize_shop_run


def variable(value):
    return SimpleNamespace(get=lambda: value)


class PoolController(ShopArchipelagoController, AdvancedSettingsController):
    def __init__(self):
        self.missions = [dict(mission) for mission in MISSION_METADATA_BY_CODE.values()]
        self._mission_by_code = {mission['code']: mission for mission in self.missions}
        self.shop_run = None
        self.excluded_mission_codes = {
            mission['code'] for mission in self.missions
            if mission['campaign'] == 'Resurgence'
        }
        self.campaign_var = variable('GDI - Tiberian Sun')
        self.include_no_build_missions_var = variable(True)
        self.include_no_build_production_missions_var = variable(True)
        self.include_operation_missions_var = variable(True)
        self.shop_mode_selected = lambda: True
        self.archipelago_shop_slot_settings = lambda: None


class ShopMissionPoolChecks(unittest.TestCase):
    def setUp(self):
        self.controller = PoolController()

    def test_only_resurgence_excluded_and_all_other_campaigns_available(self):
        controller = self.controller
        advanced_codes = {
            mission['code'] for mission in controller.advanced_mission_pool()
            if mission['code'] not in controller.excluded_mission_codes
        }
        shop_codes = {mission['code'] for mission in controller._shop_run_mission_pool()}
        self.assertEqual(len(controller.missions), 108)
        self.assertEqual(len(controller.excluded_mission_codes), 13)
        self.assertEqual(len(shop_codes), 95)
        self.assertEqual(shop_codes, advanced_codes)
        self.assertEqual({controller._mission_by_code[code]['campaign'] for code in shop_codes},
                         {"Yuri's Revenge", 'Red Alert 2', 'Tiberian Sun', 'Firestorm'})
        entries, _ = controller.advanced_pool_bulk_entries('missions')
        self.assertTrue(all(controller.advanced_pool_entry_is_visible(entry) for entry in entries))
        self.assertEqual({entry['id'] for entry in entries} - controller.excluded_mission_codes,
                         shop_codes)

    def test_finished_run_does_not_limit_next_run_to_old_campaign(self):
        self.controller.shop_run = ShopRun(
            run_id='old', seed='old', status=RunStatus.FAILED, stage=1,
            run_length=10, run_coins=0, campaign_filter='GDI - Tiberian Sun',
        )
        self.assertEqual(len(self.controller._shop_run_mission_pool()), 95)

    def test_shop_and_advanced_share_all_build_and_operation_filters(self):
        for no_build in (False, True):
            for production in (False, True):
                for operations in (False, True):
                    with self.subTest(no_build=no_build, production=production, operations=operations):
                        controller = self.controller
                        controller.include_no_build_missions_var = variable(no_build)
                        controller.include_no_build_production_missions_var = variable(production)
                        controller.include_operation_missions_var = variable(operations)
                        advanced = {
                            m['code'] for m in controller.advanced_mission_pool()
                            if m['code'] not in controller.excluded_mission_codes
                        }
                        shop = {m['code'] for m in controller._shop_run_mission_pool()}
                        self.assertEqual(shop, advanced)
                        if not operations:
                            self.assertFalse(shop.intersection(OPERATION_MISSION_CODES))

    def test_active_run_keeps_its_saved_pool_and_ap_keeps_signed_pool(self):
        controller = self.controller
        controller.shop_run = ShopRun(
            run_id='active', seed='active', status=RunStatus.ACTIVE, stage=1,
            run_length=10, run_coins=0, eligible_mission_codes=('YUR01', 'ALL01'),
        )
        self.assertEqual({m['code'] for m in controller._shop_run_mission_pool(controller.shop_run)},
                         {'YUR01', 'ALL01'})
        controller.shop_run = None
        controller.archipelago_shop_slot_settings = lambda: {'mission_pool': ['YUR01', 'ALL01']}
        self.assertEqual({m['code'] for m in controller._shop_run_mission_pool()}, {'YUR01', 'ALL01'})

    def test_large_custom_pool_does_not_repeat_completed_maps(self):
        pool = self.controller._shop_run_mission_pool()
        self.assertFalse(mission_pool_requires_repeats(pool, 10, 3))
        for size, expected in ((10, True), (11, True), (12, False)):
            self.assertEqual(mission_pool_requires_repeats(pool[:size], 10, 3), expected)
        completed = tuple(m['code'] for m in pool[:9])
        offers = generate_mission_offers(
            pool, run_seed='LAST-STAGE', stage=10, completed_codes=completed,
            unrestricted=True,
        )
        self.assertEqual(len(offers), 3)
        self.assertFalse(set(completed).intersection(o.mission_code for o in offers))

    def test_five_fresh_runs_avoid_recent_suggestions_without_shrinking_pool(self):
        pool = self.controller._shop_run_mission_pool()
        recent = ()
        all_offered = set()
        for seed in range(5):
            offers = generate_mission_offers(
                pool, run_seed=f'FRESH-{seed}', stage=1, unrestricted=True,
                previous_offer_codes=recent,
            )
            codes = tuple(o.mission_code for o in offers)
            self.assertEqual(len(codes), 3)
            self.assertFalse(all_offered.intersection(codes))
            all_offered.update(codes)
            recent = (*recent, *codes)[-12:]
        self.assertEqual(len(pool), 95)
        all_choices = generate_mission_offers(
            pool, run_seed='ALL-ELIGIBLE', stage=3, unrestricted=True, offer_count=95,
        )
        self.assertEqual({o.mission_code for o in all_choices}, {m['code'] for m in pool})

    def test_start_run_persists_recent_choices_and_separates_repeat_policy(self):
        pool = self.controller._shop_run_mission_pool()
        controller = ShopController()
        controller.missions = self.controller.missions
        controller.excluded_mission_codes = self.controller.excluded_mission_codes
        controller.shop_run = None
        controller.shop_config = SHOP_CONFIG
        controller.shop_profile = ShopProfile()
        controller.config = {'shop_mode_rules_acknowledged': True}
        controller.seed_var = Mock()
        controller.shop_modifier_vars = {}
        controller.shop_permanent_units_without_buffs_var = variable(False)
        controller.shop_discount_specialization_var = variable('Units')
        controller._shop_entry_by_reward_id = {}
        controller.shop_reward_settings_for_new_run = lambda: {}
        controller.shop_campaign_filter = lambda: 'All Campaigns'
        controller.starting_tier_one_unit_ids_for_seed = lambda *_args: ()
        controller.starting_tier_one_defense_ids_for_seed = lambda *_args, **_kwargs: ()
        controller.archipelago_shop_context = lambda: ('', ())
        controller._selected_loadout_reward_ids = lambda: ()
        controller._starting_buff_draft = lambda *_args: ()
        controller._shop_run_mission_pool = lambda: pool
        controller.archipelago_shop_slot_settings = lambda: None
        for name in ('shop_service', 'shop_panels', 'workspace_tabs', 'shop_tab',
                     'save_current_launcher_config', 'sync_shop_workspace',
                     'refresh_shop_mode', '_set_shop_message'):
            setattr(controller, name, Mock())
        seen = set()
        with patch('randomizer.application.shop_controller.save_config'), patch(
            'randomizer.application.shop_controller.log_event',
        ), patch(
            'randomizer.application.shop_controller.messagebox.showerror',
            side_effect=AssertionError('Starting a run must succeed'),
        ):
            for _ in range(5):
                controller.start_shop_run()
                options = controller.shop_service.start_run.call_args.kwargs
                codes = {offer.mission_code for offer in options['mission_offers']}
                self.assertFalse(codes.intersection(seen))
                self.assertFalse(options['allow_repeats'])
                self.assertTrue(options['reward_settings']['shop_unrestricted_missions'])
                self.assertEqual(set(options['eligible_mission_codes']), {m['code'] for m in pool})
                seen.update(codes)
                controller.shop_run = ShopRun(
                    run_id=options['run_id'], seed=options['seed'], status=RunStatus.FAILED,
                    stage=1, run_length=10, run_coins=0,
                    reward_settings=options['reward_settings'],
                    mission_offers=options['mission_offers'],
                )
        self.assertEqual(len(seen), 15)

    def test_recent_suggestions_fall_back_when_pool_is_too_small(self):
        pool = self.controller._shop_run_mission_pool()[:3]
        offers = generate_mission_offers(
            pool, run_seed='NARROW', stage=1, unrestricted=True,
            previous_offer_codes=[m['code'] for m in pool],
        )
        self.assertEqual(len(offers), 3)

    def test_new_policy_and_recent_history_survive_saved_run_round_trip(self):
        run = ShopRun(
            run_id='policy', seed='policy', status=RunStatus.ACTIVE, stage=1,
            run_length=10, run_coins=0,
            reward_settings={'shop_unrestricted_missions': True,
                             'shop_recent_opening_mission_codes': ['ALL01', 'ALL02']},
        )
        saved = normalize_shop_run(run.to_dict())
        self.assertFalse(saved.allow_repeats)
        self.assertTrue(unrestricted_shop_missions(saved))
        self.assertEqual(saved.reward_settings, run.reward_settings)
        self.assertTrue(unrestricted_shop_missions(replace(run, allow_repeats=True,
                                                         reward_settings={})))


if __name__ == '__main__':
    unittest.main(verbosity=2)
