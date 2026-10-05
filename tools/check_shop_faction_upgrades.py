"""Regressions for upgrades to owned targets outside the Shop faction pool."""

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Archipelago.bundle_generation import _checked_in_generation_rules

# CI has no game installation. Use the reviewed rules snapshot before imports
# build the reward catalogue, and retain it for lazy clone-template reads.
unittest.enterModuleContext(patch(
    'randomizer.content.inventory.read_rules_sections',
    return_value=(_checked_in_generation_rules(), 'checked-in-apworld-rules'),
))

from randomizer.application.shop_controller import ShopController
from randomizer.shop.catalogue import shop_catalogue, shop_entry_available
from randomizer.shop.config import SHOP_CONFIG
from randomizer.shop.model import (
    PurchaseRecord, PurchaseResult, RunStatus, ShopProfile, ShopRewardType, ShopRun,
)
from randomizer.shop.persistence import ShopPersistencePaths, ShopRepository
from randomizer.shop.service import ShopProgressionService


class Variable:
    def __init__(self, value=''):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class UpgradeController(ShopController):
    def __init__(self, run):
        self.shop_run = run
        self.shop_profile = ShopProfile()
        self.shop_config = SHOP_CONFIG
        self.shop_catalogue_tree = Mock()
        self.shop_catalogue_tree.selection.return_value = ()
        self.shop_catalogue_tree.get_children.return_value = ()
        self._shop_catalogue_rows = {}
        self.shop_category_var = Variable('Unit Buffs')
        self.shop_search_var = Variable()
        self.shop_sort_var = Variable('Name')
        self.shop_show_locked_var = Variable(True)
        self.shop_buff_target_var = Variable()
        self.shop_catalogue_help_var = Variable()
        self._shop_buff_entries = tuple(
            entry for entry in shop_catalogue()
            if entry.reward_type is ShopRewardType.UNIT_BUFF
        )
        self._shop_unit_entries = ()
        self._shop_power_entries = ()
        self._shop_power_buff_entries = ()
        for name in (
            'shop_buff_target_frame', 'shop_catalogue_back_button',
            'shop_buff_target_combo', 'shop_show_locked_button',
        ):
            setattr(self, name, Mock())
        self.shop_search_label = object()
        self._clear_shop_tree_buttons = Mock()
        self._prepare_shop_unit_cameos = Mock(return_value={})
        self._rebuild_shop_catalogue_upgrade_buttons = Mock()
        self.refresh_shop_purchase_buttons = Mock()
        self.shop_launch_active = Mock(return_value=False)


class FactionUpgradeChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = shop_catalogue()
        cls.buff = next(
            entry for entry in cls.entries
            if entry.target_id == 'E2'
            and entry.reward_type is ShopRewardType.UNIT_BUFF
        )

    def run_state(self, **options):
        return replace(ShopRun(
            run_id='faction-upgrade-check', seed='FACTION-UPGRADES',
            status=RunStatus.ACTIVE, stage=1, run_length=10, run_coins=1000,
            reward_settings={'shop_faction_filter': 'GDI'},
            starting_unit_ids=('E2', 'E1'),
        ), **options)

    def test_catalogue_pool_filters_access_but_not_upgrades(self):
        for faction in ('Allies', 'Soviets', 'Yuri', 'GDI', 'Nod'):
            for mode in ('Standard', 'Chaos', 'Randomizer Arsenal'):
                for entry in self.entries:
                    is_buff = entry.reward_type in {
                        ShopRewardType.UNIT_BUFF, ShopRewardType.POWER_BUFF,
                    }
                    expected = is_buff or not entry.factions or bool(
                        {faction, 'Neutral'}.intersection(entry.factions)
                    )
                    with self.subTest(faction=faction, mode=mode, reward=entry.reward_id):
                        self.assertEqual(shop_entry_available(
                            entry, campaign_filter=faction, reward_mode=mode,
                            strict_faction=True,
                        ), expected)

    def test_conscript_screen_keeps_requested_target_and_upgrade_rows(self):
        controller = UpgradeController(self.run_state())
        controller._shop_requested_buff_target_id = 'E2'
        controller.refresh_shop_catalogue()
        self.assertEqual(controller._shop_buff_target_ids[
            controller.shop_buff_target_var.get()
        ], 'E2')
        expected = {
            entry.reward_id for entry in self.entries
            if entry.target_id == 'E2'
            and entry.reward_type is ShopRewardType.UNIT_BUFF
        }
        self.assertEqual(set(controller._shop_catalogue_rows.values()), expected)
        self.assertTrue(all(controller._shop_catalogue_buyable.values()))

    def test_purchase_and_persistence_for_each_access_source(self):
        for source in ('starter', 'permanent', 'purchased', 'archipelago'):
            with self.subTest(source=source), TemporaryDirectory() as temporary:
                root = Path(temporary)
                repository = ShopRepository(ShopPersistencePaths(
                    profile=root / 'profile.json', run=root / 'run.json',
                    transaction=root / 'transaction.json', backup_dir=root / 'backups',
                ))
                options = {'starting_unit_ids': ()}
                if source == 'starter':
                    options['starting_unit_ids'] = ('E2',)
                elif source == 'permanent':
                    options['selected_permanent_units'] = ('Conscript Access',)
                elif source == 'purchased':
                    options['run_purchases'] = (PurchaseRecord('Conscript Access'),)
                else:
                    options['ap_entitlements_snapshot'] = ('Conscript Access',)
                    options['selected_permanent_units'] = ('Conscript Access',)
                    options['ap_identity'] = 'faction-upgrade-room'
                run = self.run_state(**options)
                repository.save_run(run)
                validation = ShopProgressionService(repository).purchase_run_reward(
                    self.buff.reward_id
                )
                self.assertEqual(validation.result, PurchaseResult.OK)
                saved = repository.load_run()
                self.assertEqual(saved.run_coins, run.run_coins - validation.cost)
                self.assertEqual([(buff.reward_id, buff.stacks) for buff in saved.run_buffs],
                                 [(self.buff.reward_id, 1)])

    def test_unowned_targets_and_cross_faction_access_stay_blocked(self):
        repository = Mock()
        repository.load.return_value = (ShopProfile(), self.run_state(starting_unit_ids=()))
        service = ShopProgressionService(repository)
        self.assertEqual(service.purchase_run_reward(self.buff.reward_id).result,
                         PurchaseResult.REQUIRES_UNIT_ACCESS)
        self.assertEqual(service.purchase_run_reward('Conscript Access').result,
                         PurchaseResult.NOT_SHOP_ELIGIBLE)
        repository.save_run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
