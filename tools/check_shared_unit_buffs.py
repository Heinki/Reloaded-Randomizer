"""Regressions for shared MCV, harvester, transporter and engineer upgrades."""

import sys
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from Archipelago.bundle_generation import _checked_in_generation_rules

unittest.enterModuleContext(patch(
    'randomizer.content.inventory.read_rules_sections',
    return_value=(_checked_in_generation_rules(), 'checked-in-apworld-rules'),
))

from randomizer.application.shop_controller import ShopController
from randomizer.maps.buff_values import _active_direct_buff_counts
from randomizer.maps.player_clones import player_unit_clone_rules
from randomizer.rewards.catalogue import (
    BUFF_TARGETS, REWARD_BY_BUFF_KEY, canonical_reward, unit_buff_counts,
)
from randomizer.rewards.reloaded_definitions import SHARED_UNIT_BUFF_GROUPS
from randomizer.rewards.arsenal import reward_matches_arsenal
from randomizer.rewards.rules import expand_equivalent_role_buffs, tech_ids_for_rewards
from randomizer.shop.active import active_shop_rewards, active_shop_tech_ids, permanent_buff_snapshot
from randomizer.shop.catalogue import shop_always_available_unit_ids, shop_catalogue
from randomizer.shop.config import SHOP_CONFIG
from randomizer.shop.model import (
    BuffPurchase, PurchaseResult, RunStatus, ShopProfile, ShopRewardType, ShopRun,
)
from randomizer.shop.persistence import ShopPersistencePaths, ShopRepository
from randomizer.shop.service import ShopProgressionService
from randomizer.shop.state import normalize_shop_profile, normalize_shop_run
from tools.check_shop_faction_upgrades import UpgradeController


class Variable:
    def __init__(self, value=''):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def reward(unit_id, kind='health'):
    return canonical_reward(REWARD_BY_BUFF_KEY[unit_id, kind])


class LoadoutController(ShopController):
    def __init__(self, run, search=''):
        self.shop_run = run
        self.shop_profile = ShopProfile()
        self.shop_config = SHOP_CONFIG
        self.shop_loadout_tree = Mock()
        self.shop_loadout_tree.selection.return_value = ()
        self.shop_loadout_tree.get_children.return_value = ()
        self.shop_loadout_search_var = Variable(search)
        self.shop_loadout_upgrade_button = Mock()
        self._shop_entry_by_reward_id = {entry.reward_id: entry for entry in shop_catalogue()}
        self._shop_buff_entries = tuple(
            entry for entry in shop_catalogue() if entry.reward_type is ShopRewardType.UNIT_BUFF
        )
        self._shop_power_buff_entries = ()
        self._clear_shop_tree_buttons = Mock()
        self._prepare_shop_unit_cameos = Mock(return_value={})
        self._shop_archipelago_cameo = Mock(return_value=None)
        self._rebuild_shop_loadout_upgrade_buttons = Mock()


class SharedUnitBuffChecks(unittest.TestCase):
    def run_state(self, **options):
        return ShopRun(
            run_id='shared-buff-check', seed='SHARED-BUFFS',
            status=RunStatus.ACTIVE, stage=1, run_length=10, run_coins=1000,
            **options,
        )

    def test_one_stack_account_and_shop_offer_per_effect(self):
        for root, (_label, members) in SHARED_UNIT_BUFF_GROUPS.items():
            for member in members:
                for kind in BUFF_TARGETS[member]['allowed_buff_types']:
                    with self.subTest(member=member, kind=kind):
                        self.assertIs(reward(member, kind), reward(root, kind))
            offers = [entry for entry in shop_catalogue()
                      if entry.target_id in members and entry.reward_type is ShopRewardType.UNIT_BUFF]
            self.assertEqual({entry.target_id for entry in offers}, {root})
            self.assertEqual(len(offers), len(BUFF_TARGETS[root]['allowed_buff_types']))
        self.assertNotEqual(reward('AMCV')['name'], reward('HARV')['name'])

    def test_old_profile_and_run_stacks_merge_without_loss(self):
        old = [
            {'reward_id': REWARD_BY_BUFF_KEY[unit, 'health']['name'], 'stacks': index + 1}
            for index, unit in enumerate((
                'AMCV', 'PCV', 'CMIN', 'TSHARV', 'SAPC', 'LCRF', 'YHVR', 'SENGINEER', 'NENGINEER',
            ))
        ]
        profile = normalize_shop_profile({'permanent_buffs': old})
        self.assertEqual({item.reward_id: item.stacks for item in profile.permanent_buffs}, {
            reward('AMCV')['name']: 3, reward('HARV')['name']: 7,
            reward('SAPC')['name']: 18,
            reward('ENGINEER')['name']: 17,
        })
        self.assertEqual(normalize_shop_profile(profile.to_dict()), profile)
        document = self.run_state().to_dict()
        for field in ('run_buffs', 'permanent_buffs_snapshot', 'starting_draft_buffs'):
            document[field] = old
        run = normalize_shop_run(document)
        for field in ('run_buffs', 'permanent_buffs_snapshot', 'starting_draft_buffs'):
            self.assertEqual(getattr(run, field), profile.permanent_buffs)
        self.assertEqual(normalize_shop_run(run.to_dict()), run)
        self.assertEqual(permanent_buff_snapshot(profile), profile.permanent_buffs)
        counts = unit_buff_counts(active_shop_rewards(run), 'SMIN')
        self.assertEqual(counts['health'], 18)  # Shared health cap, three sources.

    def test_purchase_refund_and_cap_use_shared_stacks(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = ShopRepository(ShopPersistencePaths(
                profile=root / 'profile.json', run=root / 'run.json',
                transaction=root / 'transaction.json', backup_dir=root / 'backups',
            ))
            service = ShopProgressionService(repository)
            repository.save_profile(ShopProfile(meta_coins=1000))
            first = service.purchase_permanent_buff(REWARD_BY_BUFF_KEY['PCV', 'health']['name'])
            second = service.purchase_permanent_buff(REWARD_BY_BUFF_KEY['GDIMCV', 'health']['name'])
            self.assertTrue(first.validation.allowed)
            self.assertTrue(second.validation.allowed)
            self.assertEqual(repository.load_profile().permanent_buffs,
                             (BuffPurchase(reward('AMCV')['name'], 2),))
            refund = service.refund_permanent_unit_buff(REWARD_BY_BUFF_KEY['NODMCV', 'health']['name'])
            self.assertEqual(refund.profile.meta_coins, first.profile.meta_coins)
            for member in SHARED_UNIT_BUFF_GROUPS['ENGINEER'][1]:
                bought = service.purchase_permanent_buff(REWARD_BY_BUFF_KEY[member, 'health']['name'])
                self.assertTrue(bought.validation.allowed)
            profile = repository.load_profile()
            self.assertIn(BuffPurchase(reward('ENGINEER')['name'], 5), profile.permanent_buffs)
            repository.save_run(self.run_state(permanent_buffs_snapshot=(
                BuffPurchase(reward('HARV')['name'], 17),
            )))
            bought = service.purchase_run_reward(REWARD_BY_BUFF_KEY['TSHARV', 'health']['name'])
            self.assertEqual(bought.result, PurchaseResult.OK)
            capped = service.purchase_run_reward(REWARD_BY_BUFF_KEY['SMIN', 'health']['name'])
            self.assertEqual(capped.result, PurchaseResult.MAX_STACKS)
            self.assertEqual(repository.load_run().run_buffs,
                             (BuffPurchase(reward('HARV')['name'], 1),))

    def test_expansion_once_and_only_compatible_variants(self):
        for root, (_label, members) in SHARED_UNIT_BUFF_GROUPS.items():
            expanded = expand_equivalent_role_buffs([reward(root)])
            self.assertEqual(len(expanded), len(members))
            self.assertEqual(expand_equivalent_role_buffs(expanded), expanded)
            counts = _active_direct_buff_counts(
                expanded, additional_unlocked_tech_ids=members,
                unit_specific_mode=True,
            )
            self.assertEqual(counts, {member: {'health': 1} for member in members})
            self.assertFalse(tech_ids_for_rewards(expanded))
        for kind in ('damage', 'reload', 'range', 'veteran'):
            expanded = expand_equivalent_role_buffs([reward('SMIN', kind)])
            self.assertEqual({item['unit'] for item in expanded}, {'HARV', 'SMIN'})
        allowed = expand_equivalent_role_buffs(
            [reward('PCV')], allowed_unit_ids={'AMCV', 'PCV'}, enabled=True,
        )
        self.assertEqual({item['unit'] for item in allowed}, {'AMCV', 'PCV'})
        counts = _active_direct_buff_counts(
            [reward('HARV')], additional_unlocked_tech_ids=('TSNHARV',),
            unit_specific_mode=True,
        )
        self.assertEqual(counts, {'TSNHARV': {'health': 1}})
        self.assertFalse(_active_direct_buff_counts(
            [reward('HARV', 'damage')], additional_unlocked_tech_ids=('TSNHARV',),
            unit_specific_mode=True,
        ))

    def test_permanent_selector_shows_each_group_once(self):
        controller = LoadoutController(None)
        controller.shop_profile = ShopProfile(
            permanent_unit_unlocks=('Stealth Harvester Access',), meta_coins=1000,
        )
        controller._shop_unit_entries = tuple(
            entry for entry in shop_catalogue() if entry.reward_type is ShopRewardType.UNIT_ACCESS
        )
        controller.shop_permanent_buff_tree = Mock()
        controller.shop_permanent_buff_tree.get_children.return_value = ()
        controller.shop_permanent_buff_target_var = Variable('Harvesters (shared buffs)')
        controller.shop_permanent_buff_target_combo = Mock()
        controller.shop_permanent_search_var = Variable()
        controller.refresh_permanent_buff_button = Mock()
        controller._refresh_permanent_buffs(active_run=False)
        labels = controller.shop_permanent_buff_target_combo.configure.call_args.kwargs['values']
        self.assertEqual(labels.count('MCVs (shared buffs)'), 1)
        self.assertEqual(labels.count('Harvesters (shared buffs)'), 1)
        self.assertEqual(labels.count('Transporters (shared buffs)'), 1)
        self.assertEqual(labels.count('Engineers (shared buffs)'), 1)
        self.assertNotIn('Stealth Harvester Access', labels)
        self.assertEqual(len(controller._shop_permanent_buff_rows), 12)

    def test_arsenal_matches_shared_peers_without_unlocking_them(self):
        arsenal = {'units': [{'unit_id': 'SHARV'}], 'powers': []}
        self.assertTrue(reward_matches_arsenal(reward('HARV'), arsenal))
        self.assertFalse(reward_matches_arsenal(reward('HARV', 'damage'), arsenal))
        self.assertFalse(reward_matches_arsenal(reward('AMCV'), arsenal))

    def test_generated_clones_use_each_variant_stats_and_preserve_sources(self):
        lines = '''[Basic]
Player=Player
[Houses]
0=Player
1=Enemy
[Player]
Country=AlliesCountry
PlayerControl=yes
[Enemy]
Country=SovietCountry
[Units]
0=Enemy,HARV,256,1,1,0,Guard,none,0,-1,0,-1,1,0
'''.splitlines()
        installed = _checked_in_generation_rules()
        before = deepcopy(installed)
        for mode in (False, True):
            for root, (_label, members) in SHARED_UNIT_BUFF_GROUPS.items():
                sections, sources, handled, _labels, _unsupported = player_unit_clone_rules(
                    lines, [reward(root)], installed,
                    additional_unlocked_tech_ids=members,
                    buildable_tech_ids=members, build_owner_ids=('AlliesCountry',),
                    owned_clone_templates={member: installed[member] for member in members},
                    unit_specific_mode=mode,
                )
                self.assertEqual(set(sources), set(members))
                for member in members:
                    with self.subTest(mode=mode, member=member):
                        clone = sections[handled[member]['clone_id']]
                        self.assertEqual(int(clone['Strength']),
                                         round(BUFF_TARGETS[member]['strength'] * 1.15))
                        if root == 'ENGINEER':
                            self.assertEqual(clone['Engineer'].lower(), 'yes')
                self.assertEqual(installed, before)
                self.assertEqual(lines[-1].split('=')[1].split(',')[1], 'HARV')

    def test_loadout_groups_members_buffs_and_search(self):
        run = self.run_state(
            starting_unit_ids=('E1',),
            permanent_buffs_snapshot=(BuffPurchase(reward('PCV')['name'], 2),),
            run_buffs=(BuffPurchase(reward('TSHARV')['name'], 3),),
        )
        controller = LoadoutController(run)
        controller._refresh_shop_loadout()
        calls = controller.shop_loadout_tree.insert.call_args_list
        groups = {call.kwargs['values'][1]: call for call in calls
                  if '(shared buffs)' in call.kwargs['values'][1]}
        self.assertEqual(set(groups), {
            'MCVs (shared buffs)', 'Harvesters (shared buffs)', 'Transporters (shared buffs)',
            'Engineers (shared buffs)',
        })
        for label, root, stacks in (('MCVs (shared buffs)', 'AMCV', 2),
                                    ('Harvesters (shared buffs)', 'HARV', 3)):
            call = groups[label]
            self.assertEqual(controller._shop_current_loadout_targets[call.kwargs['iid']],
                             (root, False))
            self.assertIn(f'/ {stacks} stacks', call.kwargs['values'][2])
        for search, target in (
            ('Yuri MCV', 'AMCV'), ('TSNHARV', 'HARV'), ('Slave Miner', 'HARV'),
            ('Landing Craft', 'SAPC'), ('NODHVR', 'SAPC'),
            ('Soviet Engineer', 'ENGINEER'), ('NENGINEER', 'ENGINEER'),
        ):
            filtered = LoadoutController(run, search)
            filtered._refresh_shop_loadout()
            self.assertEqual(filtered.shop_loadout_tree.insert.call_count, 1)
            self.assertEqual(list(filtered._shop_current_loadout_targets.values()), [(target, False)])

    def test_empty_core_groups_stay_visible_and_upgradeable_for_every_faction(self):
        for faction in ('Allies', 'Soviets', 'Yuri', 'GDI', 'Nod'):
            with self.subTest(faction=faction):
                run = self.run_state(reward_settings={'shop_faction_filter': faction})
                controller = LoadoutController(run)
                controller._refresh_shop_loadout()
                calls = controller.shop_loadout_tree.insert.call_args_list
                self.assertEqual([call.kwargs['values'][1] for call in calls[:4]], [
                    'MCVs (shared buffs)', 'Harvesters (shared buffs)', 'Transporters (shared buffs)',
                    'Engineers (shared buffs)',
                ])
                for call, root in zip(calls[:4], SHARED_UNIT_BUFF_GROUPS):
                    self.assertEqual(call.kwargs['values'][0], 'Always Available')
                    self.assertEqual(call.kwargs['values'][2], 'No buffs')
                    self.assertEqual(controller._shop_current_loadout_targets[call.kwargs['iid']],
                                     (root, False))
                    self.assertIn(root, active_shop_tech_ids(run))
                controller.shop_loadout_tree.yview_moveto.assert_called_once_with(0)

    def test_core_availability_does_not_depend_on_buff_offers(self):
        access = tuple(entry for entry in shop_catalogue()
                       if entry.reward_type is ShopRewardType.UNIT_ACCESS)
        with patch('randomizer.shop.catalogue.shop_catalogue', return_value=access):
            core = shop_always_available_unit_ids.__wrapped__()
        self.assertTrue({
            'AMCV', 'HARV', 'SAPC', 'PCV', 'TSNHARV', 'LCRF', 'NODHVR', 'ENGINEER', 'NENGINEER',
        } <= core)
        self.assertNotIn('SHARV', core)

    def test_current_upgrade_screen_has_buyable_rows_for_every_core_group(self):
        for native, root in (
            ('PCV', 'AMCV'), ('TSHARV', 'HARV'), ('NODHVR', 'SAPC'), ('NENGINEER', 'ENGINEER'),
        ):
            with self.subTest(native=native):
                controller = UpgradeController(self.run_state())
                controller._shop_requested_buff_target_id = native
                controller.refresh_shop_catalogue()
                self.assertEqual(controller._shop_buff_target_ids[controller.shop_buff_target_var.get()], root)
                expected = {entry.reward_id for entry in shop_catalogue()
                            if entry.target_id == root and entry.reward_type is ShopRewardType.UNIT_BUFF}
                self.assertEqual(set(controller._shop_catalogue_rows.values()), expected)
                self.assertTrue(all(controller._shop_catalogue_buyable.values()))

    def test_refresh_keeps_selected_transporter_group_visible(self):
        controller = LoadoutController(self.run_state())
        controller._shop_current_loadout_targets = {'old-row': ('NODHVR', False)}
        controller.shop_loadout_tree.selection.return_value = ('old-row',)
        controller._refresh_shop_loadout()
        selected = controller.shop_loadout_tree.selection_set.call_args.args[0]
        self.assertEqual(controller._shop_current_loadout_targets[selected], ('SAPC', False))
        controller.shop_loadout_tree.see.assert_called_once_with(selected)

    def test_transporter_run_purchases_share_stacks_and_passenger_upgrades(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = ShopRepository(ShopPersistencePaths(
                profile=root / 'profile.json', run=root / 'run.json',
                transaction=root / 'transaction.json', backup_dir=root / 'backups',
            ))
            repository.save_run(self.run_state())
            service = ShopProgressionService(repository)
            for member in SHARED_UNIT_BUFF_GROUPS['SAPC'][1]:
                bought = service.purchase_run_reward(REWARD_BY_BUFF_KEY[member, 'passenger_capacity']['name'])
                self.assertEqual(bought.result, PurchaseResult.OK)
            run = repository.load_run()
            self.assertEqual(run.run_buffs, (BuffPurchase(reward('SAPC', 'passenger_capacity')['name'], 5),))
            for member in SHARED_UNIT_BUFF_GROUPS['SAPC'][1]:
                self.assertEqual(unit_buff_counts(active_shop_rewards(run), member)['passenger_capacity'], 5)


if __name__ == '__main__':
    unittest.main()
