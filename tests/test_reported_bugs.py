"""Regressions for goal release policy and superweapon effect areas."""

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from Archipelago.client.session import ArchipelagoSession, CLIENT_GOAL, SessionConfig
from randomizer.application.archipelago_controller import ArchipelagoController
from randomizer.application.shop_archipelago_controller import ShopArchipelagoController
from randomizer.maps.power_buffs import apply_power_buffs_to_unlock_rewards
from randomizer.rewards.catalogue import REWARD_POOL
from randomizer.shop.model import RunStatus


class GridHarness(ArchipelagoController):
    def __init__(self, release_rewards=True, connected=True):
        self.state = {
            'progression_mode': 'Grid Mode',
            'unlock_all_rewards_after_final_grid_mission': release_rewards,
            'mission_order': ['OPTIONAL', 'GOAL'],
            'completed_missions': ['GOAL'],
            'grid': {'goal': 'GOAL', 'nodes': {'OPTIONAL': {}, 'GOAL': {}}},
            'mission_checks': {
                'OPTIONAL': [
                    {'id': 'objective', 'unlocked': False},
                    {'id': 'victory', 'unlocked': False},
                ],
                'GOAL': [
                    {'id': 'objective', 'unlocked': True},
                    {'id': 'victory', 'unlocked': True},
                ],
            },
        }
        self.ap_state = {'checkpoint': {}}
        self._archipelago_session = ArchipelagoSession(
            SessionConfig('localhost:38281', 'Regression')
        ) if connected else None
        self._archipelago_session_validated = connected
        self._archipelago_server_checked_locations = set()
        self.save_state = Mock()
        self.append_archipelago_history = Mock()

    def _active_archipelago_state(self):
        return self.ap_state

    def active_progression_mode(self):
        return self.state['progression_mode']

    def is_run_complete(self):
        return True

    def mission_checks(self, code):
        return self.state['mission_checks'][code]

    def _archipelago_location_ids(self, code, check_id):
        return {
            ('GOAL', 'objective'): (1,), ('GOAL', 'victory'): (2,),
            ('OPTIONAL', 'objective'): (3,), ('OPTIONAL', 'victory'): (4,),
        }.get((code, check_id), ())

    def _archipelago_local_victory_location(self, code):
        return {'GOAL': 101, 'OPTIONAL': 102}[code]


class ShopHarness(ShopArchipelagoController, GridHarness):
    def __init__(self):
        GridHarness.__init__(self)
        self.state['progression_mode'] = 'Shop Mode'
        self.shop = {
            'item_locations': list(range(1, 31)),
            'purchase_locations': [1],
            'items_per_victory': 12,
            'stage_victories': [
                {'stage': stage, 'location': stage + 1,
                 'logic_location': 100 + stage}
                for stage in range(1, 11)
            ],
        }
        self.run = SimpleNamespace(
            ap_identity='test', run_id='run', status=RunStatus.COMPLETED,
            rewarded_victories=('run:10:GOAL:victory',),
        )
        self.shop_repository = SimpleNamespace(load_run=lambda: self.run)
        self.shop_service = Mock()
        self.shop_service.pending_archipelago_purchase_ids.return_value = ()

    def archipelago_shop_slot_settings(self):
        return self.shop

    def archipelago_shop_context(self):
        return 'test', ()

    def is_run_complete(self):
        return True


class GoalReleaseTests(unittest.TestCase):
    def test_grid_goal_and_reconnect_send_only_earned_checks(self):
        for release_rewards in (False, True):
            for connected in (False, True):
                for reconcile in (False, True):
                    with self.subTest(release_rewards=release_rewards,
                                      connected=connected, reconcile=reconcile):
                        harness = GridHarness(release_rewards, connected)
                        if reconcile:
                            added = harness.reconcile_archipelago_checks()
                        else:
                            added = harness.report_archipelago_mission_completion('GOAL')
                        self.assertEqual(set(added), {1, 2, 101})
                        checkpoint = harness.ap_state['checkpoint']
                        self.assertEqual(set(checkpoint['pending_locations']), {1, 2, 101})
                        self.assertTrue(checkpoint['goal_complete'])
                        if connected:
                            commands = list(harness._archipelago_session._outbound.queue)
                            self.assertIn({'cmd': 'StatusUpdate', 'status': CLIENT_GOAL}, commands)
                            checks = [c for c in commands if c['cmd'] == 'LocationChecks']
                            self.assertEqual(checks, [{'cmd': 'LocationChecks', 'locations': [1, 2, 101]}])

    def test_optional_missions_remain_checkable_after_goal(self):
        harness = GridHarness()
        harness.report_archipelago_mission_completion('GOAL')
        for check in harness.state['mission_checks']['OPTIONAL']:
            check['unlocked'] = True
        self.assertEqual(
            set(harness.report_archipelago_mission_completion('OPTIONAL')),
            {3, 4, 102},
        )

    def test_shop_final_victory_preserves_quota_and_unbought_locations(self):
        harness = ShopHarness()
        harness.record_archipelago_shop_victory(10, SimpleNamespace(run=harness.run))
        pending = set(harness.ap_state['checkpoint']['pending_locations'])
        self.assertEqual(pending, {11, 110, *range(12, 23)})
        self.assertTrue(harness.ap_state['checkpoint']['goal_complete'])

    def test_shop_reconnect_does_not_release_unearned_locations(self):
        harness = ShopHarness()
        self.assertEqual(set(harness.reconcile_archipelago_checks()), {11, 110})
        self.assertTrue(harness.ap_state['checkpoint']['goal_complete'])


class PowerAreaTests(unittest.TestCase):
    def apply_area(self, power_id, stacks=1, sections=None):
        unlock = next(r for r in REWARD_POOL
                      if r.get('kind') == 'superweapon' and r.get('superweapon') == power_id)
        buff = next(r for r in REWARD_POOL
                    if r.get('power_buff_type') == 'area' and r.get('superweapon') == power_id)
        return apply_power_buffs_to_unlock_rewards(
            [unlock] + [buff] * stacks, sections or {}
        )[0]

    def test_effect_fields_and_native_defaults(self):
        expected = {
            'IronCurtainSpecial': '4,4', 'ChronoSphereSpecial': '4,4',
            'ForceShieldSpecial': '4.5', 'PsychicDominatorSpecial': '2.5',
            'LightningStormSpecial': '11',
        }
        sections = {'General': {'ForceShieldRadius': '4',
                                'DominatorCaptureRange': '2',
                                'LightningCellSpread': '10'}}
        for power_id, radius in expected.items():
            with self.subTest(power=power_id):
                result = self.apply_area(power_id, sections=sections)
                self.assertEqual(result['superweapon_rules'].get('SW.Range'), radius)

    def test_existing_effect_range_overrides_defaults(self):
        sections = {'IronCurtainSpecial': {'SW.Range': '6'}}
        original = deepcopy(sections)
        result = self.apply_area('IronCurtainSpecial', 2, sections)
        self.assertEqual(result['superweapon_rules']['SW.Range'], '7')
        self.assertEqual(sections, original)

    def test_lightning_rectangle_grows_by_one_cell_per_dimension(self):
        result = self.apply_area(
            'LightningStormSpecial', 2,
            {'LightningStormSpecial': {'SW.Range': '8,10', 'Range': '7'}},
        )
        self.assertEqual(result['superweapon_rules']['SW.Range'], '10,12')
        self.assertEqual(result['superweapon_rules']['Range'], '8')

    def test_stacks_cap_without_changing_unbuffed_powers(self):
        result = self.apply_area('ChronoSphereSpecial', 25)
        self.assertEqual(result['superweapon_rules']['SW.Range'], '23,23')
        result = self.apply_area('ChronoSphereSpecial', 0)
        self.assertNotIn('SW.Range', result.get('superweapon_rules', {}))

    def test_nuke_uses_private_damage_warhead(self):
        sections = {'NUKE': {'CellSpread': '10'}, 'NukeSpecial': {'Range': '7'}}
        result = self.apply_area('NukeSpecial', sections=sections)
        spec = result.get('superweapon_auxiliary_clones', {}).get('NUKE', {})
        self.assertEqual(spec.get('values', {}).get('CellSpread'), '10.5')
        self.assertEqual(spec.get('list'), 'Warheads')
        self.assertIn('SW.Warhead', spec.get('reference_keys', ()))
        self.assertEqual(result['superweapon_rules']['Range'], '7.5')
        self.assertEqual(sections['NUKE']['CellSpread'], '10')


if __name__ == '__main__':
    unittest.main()
