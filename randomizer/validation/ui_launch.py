"""Packaged UI-to-game integration smoke for C&C Reloaded.

The check invokes the real Tk seed and launch buttons, waits for a generated
Randomizer map to load in gamemd.exe, then restores player state and game INI
files. It is intentionally an integration check, not a unit-test framework.
"""

import argparse
import csv
import io
import json
import subprocess
import time
import traceback
from pathlib import Path

from randomizer.application.app import LauncherApp
from randomizer.config.player import CONFIG_PATH
from randomizer.core.paths import (
    DEBUG_LOG,
    GAME_EXE,
    GAME_ROOT,
    LOG_DIR,
    OPTIONS_INI,
    SPAWN_INI,
    STATE_PATH,
    UIMD_INI,
)
from randomizer.maps.generated import file_sha256
from randomizer.maps.rules import is_generated_hooked_map
from randomizer.missions.installation import resolve_installed_scenario


REPORT_PATH = LOG_DIR / 'ui_gameplay_launch_smoke.json'


def _image_pids(image_name):
    result = subprocess.run(
        ['tasklist', '/FI', f'IMAGENAME eq {image_name}', '/FO', 'CSV', '/NH'],
        cwd=GAME_ROOT,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='ignore',
    )
    if result.returncode != 0:
        return None
    pids = set()
    for row in csv.reader(io.StringIO(result.stdout)):
        if len(row) < 2 or row[0].strip().lower() != image_name.lower():
            continue
        try:
            pids.add(int(row[1].strip()))
        except ValueError:
            continue
    return pids


def _terminate_pid_tree(pid):
    if not pid:
        return
    subprocess.run(
        ['taskkill', '/PID', str(pid), '/T', '/F'],
        cwd=GAME_ROOT,
        capture_output=True,
        text=True,
    )


def _snapshot(path):
    path = Path(path)
    return {'path': path, 'existed': path.exists(), 'data': path.read_bytes() if path.exists() else b''}


def _restore(snapshot):
    path = snapshot['path']
    if snapshot['existed']:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(snapshot['data'])
    elif path.exists():
        path.unlink()


def _widget_texts(widget):
    result = []
    for child in widget.winfo_children():
        try:
            text = str(child.cget('text'))
        except Exception:
            text = ''
        if text:
            result.append((child, text))
        result.extend(_widget_texts(child))
    return result


def _tab_report(notebook):
    return [
        {
            'text': str(notebook.tab(tab_id, 'text')),
            'state': str(notebook.tab(tab_id, 'state')),
        }
        for tab_id in notebook.tabs()
    ]


def _debug_text_from(offset):
    if not DEBUG_LOG.exists():
        return ''
    size = DEBUG_LOG.stat().st_size
    start = offset if size >= offset else 0
    with DEBUG_LOG.open('r', encoding='utf-8', errors='ignore') as handle:
        handle.seek(start)
        return handle.read()


def run_ui_launch_smoke(mission_code='ALL01_RA2', seed='RLR-UI-SMOKE', timeout=120):
    if timeout < 30:
        raise ValueError('UI launch smoke timeout must be at least 30 seconds.')
    baseline_game_pids = _image_pids(GAME_EXE.name)
    if baseline_game_pids is None:
        raise RuntimeError('Cannot inspect running game processes with tasklist.')
    if baseline_game_pids:
        raise RuntimeError('gamemd.exe is already running; close it before the UI smoke test.')

    snapshots = [
        _snapshot(path)
        for path in (STATE_PATH, CONFIG_PATH, SPAWN_INI, OPTIONS_INI, UIMD_INI)
    ]
    debug_offset = DEBUG_LOG.stat().st_size if DEBUG_LOG.exists() else 0
    started = time.monotonic()
    report = {
        'passed': False,
        'mission_requested': mission_code,
        'seed_requested': seed,
        'ui': {},
        'dialogs': [],
        'cleanup_errors': [],
    }
    app = None
    source_path = None
    source_hash = None
    generated_path = None
    phase = 'initial_load'
    phase_started = started
    failure = None

    try:
        import tkinter.messagebox as messagebox

        def record_dialog(kind, title, message, **_kwargs):
            report['dialogs'].append({
                'kind': kind,
                'title': str(title),
                'message': str(message),
            })
            return True

        messagebox.showerror = lambda title, message, **kwargs: record_dialog(
            'error', title, message, **kwargs
        )
        messagebox.showwarning = lambda title, message, **kwargs: record_dialog(
            'warning', title, message, **kwargs
        )
        messagebox.showinfo = lambda title, message, **kwargs: record_dialog(
            'info', title, message, **kwargs
        )
        messagebox.askyesno = lambda *_args, **_kwargs: True

        app = LauncherApp()
        app.withdraw()

        def fail(message):
            nonlocal failure
            failure = RuntimeError(message)
            app.quit()

        def poll():
            nonlocal phase, phase_started, source_path, source_hash, generated_path, failure
            if time.monotonic() - started > timeout:
                fail(f'UI integration timed out during {phase}.')
                return
            if any(item['kind'] == 'error' for item in report['dialogs']):
                fail('UI displayed an error dialog: ' + report['dialogs'][-1]['message'])
                return

            if phase == 'initial_load':
                if not getattr(app, 'initial_load_complete', False):
                    app.after(50, poll)
                    return
                if len(app.missions) != 108:
                    fail(f'UI loaded {len(app.missions)} missions instead of 108.')
                    return
                mission = next(
                    (item for item in app.missions if item['code'].upper() == mission_code.upper()),
                    None,
                )
                if mission is None:
                    fail(f'UI mission catalogue does not contain {mission_code}.')
                    return
                campaign_filter = f'{mission["side"]} - {mission["campaign"]}'
                campaign_values = list(app.campaign_combo.cget('values'))
                app.campaign_var.set(campaign_values[0])
                workspace_tabs = _tab_report(app.workspace_tabs)
                info_tabs = _tab_report(app.info_tabs)
                # Shop intentionally replaces the ordinary mission workspace
                # only while Shop progression is selected. Exercise that
                # transition instead of expecting a permanently visible tab.
                app.progression_mode_var.set('Shop Mode')
                app.sync_shop_workspace()
                shop_workspace_tabs = _tab_report(app.workspace_tabs)
                app.progression_mode_var.set('Classic')
                app.sync_shop_workspace()
                # Exercise views that previously existed only as a disabled
                # skeleton. This also catches callback errors hidden behind
                # the Unlocks tab, such as inherited faction helpers.
                app.info_tabs.select(app.unlocks_tab)
                app.refresh_unlocks_view()
                unlock_unit_ids = sorted(app.current_unlock_unit_ids())
                unlock_card_count = sum(
                    len(content.winfo_children())
                    for content in app.unlock_icon_frames.values()
                )
                app.info_tabs.select(app.enemy_buffs_tab)
                app._enemy_buffs_view_dirty = True
                app.refresh_enemy_buffs_view()
                app.include_superweapon_rewards_var.set(True)
                app.include_secondary_superweapon_rewards_var.set(True)
                app.include_aid_power_rewards_var.set(True)
                app.include_power_buff_rewards_var.set(True)
                app.refresh_setting_states()
                app.workspace_tabs.select(app.advanced_tab)
                app.refresh_advanced_pool_views()
                advanced_units = app.advanced_unit_pool_entries()
                advanced_buffs = app.advanced_buff_unit_entries()
                advanced_powers = app.advanced_power_pool_entries()
                advanced_power_buffs = app.power_buff_entries(
                    include_excluded=True
                )
                advanced_tabs = _tab_report(app.advanced_notebook)
                app.workspace_tabs.select(app.archipelago_tab)
                app.refresh_archipelago_yaml_status()
                buttons = [
                    (widget, text)
                    for widget, text in _widget_texts(app)
                    if text == 'Launch Selected Mission'
                ]
                report['ui'] = {
                    'window_title': app.title(),
                    'mission_count': len(app.missions),
                    'seed_button_text': str(app.seed_action_button.cget('text')),
                    'seed_button_state': str(app.seed_action_button.cget('state')),
                    'launch_button_count': len(buttons),
                    'campaign_filters': campaign_values,
                    'workspace_tabs': workspace_tabs,
                    'advanced_tabs': advanced_tabs,
                    'shop_workspace_tabs': shop_workspace_tabs,
                    'information_tabs': info_tabs,
                    'unlock_unit_count': len(unlock_unit_ids),
                    'unlock_card_count': unlock_card_count,
                    'advanced_unit_count': len(advanced_units),
                    'advanced_buff_target_count': len(advanced_buffs),
                    'advanced_power_count': len(advanced_powers),
                    'advanced_power_buff_target_count': len(
                        advanced_power_buffs
                    ),
                    'reward_detail_colors': {
                        'access': app.rewards_text.tag_cget(
                            'detail_reward_access', 'foreground'
                        ),
                        'superweapon': app.rewards_text.tag_cget(
                            'detail_reward_superweapon', 'foreground'
                        ),
                    },
                    'superweapon_control_states': {
                        'offensive': str(
                            app.include_superweapon_rewards_check.cget('state')
                        ),
                        'secondary': str(
                            app.include_secondary_superweapon_rewards_check.cget('state')
                        ),
                        'aid': str(
                            app.include_aid_power_rewards_check.cget('state')
                        ),
                        'buffs': str(
                            app.include_power_buff_rewards_check.cget('state')
                        ),
                    },
                    'progression_modes': list(
                        app.progression_mode_combo.cget('values')
                    ),
                    'reward_modes': list(
                        app.reward_mode_combo.cget('values')
                    ),
                    'tier_one_units_state': str(
                        app.start_with_tier_one_units_check.cget('state')
                    ),
                    'tier_one_defenses_state': str(
                        app.start_with_tier_one_defenses_check.cget('state')
                    ),
                    'archipelago_yaml_button_state': str(
                        app.archipelago_save_yaml_button.cget('state')
                    ),
                    'buff_checkbox_state': str(app.include_buff_rewards_check.cget('state')),
                    'buff_enabled': bool(app.include_buff_rewards_var.get()),
                    'buff_type_count': len(app.buff_type_vars),
                }
                if str(app.seed_action_button.cget('state')) == 'disabled':
                    fail('Generate Seed button is disabled.')
                    return
                if not buttons:
                    fail('Launch Selected Mission button is missing.')
                    return
                if campaign_filter not in campaign_values:
                    fail(f'Campaign filter is missing: {campaign_filter}.')
                    return
                if not app.include_buff_rewards_var.get() or len(app.buff_type_vars) != 14:
                    fail('Reloaded buff controls are not active with all 14 types.')
                    return
                tab_states = {
                    entry['text']: entry['state'] for entry in workspace_tabs
                }
                shop_tab_states = {
                    entry['text']: entry['state']
                    for entry in shop_workspace_tabs
                }
                info_tab_states = {
                    entry['text']: entry['state'] for entry in info_tabs
                }
                if tab_states.get('Advanced') != 'normal':
                    fail('Advanced workspace is not enabled.')
                    return
                if tab_states.get('Archipelago') != 'normal':
                    fail('Archipelago workspace is not enabled.')
                    return
                if shop_tab_states.get('Shop Mode') != 'normal':
                    fail('Shop Mode workspace is not enabled.')
                    return
                if info_tab_states.get('Enemy Rewards') != 'normal':
                    fail('Enemy Rewards information page is not enabled.')
                    return
                if not advanced_units or not advanced_buffs or not advanced_powers:
                    fail('Advanced Reloaded reward pools did not load.')
                    return
                advanced_tab_states = {
                    entry['text']: entry['state']
                    for entry in advanced_tabs
                }
                if advanced_tab_states.get('Superpowers') != 'normal':
                    fail('Advanced Superpowers page is not enabled.')
                    return
                if advanced_tab_states.get('Superpower Buffs') != 'normal':
                    fail('Advanced Superpower Buffs page is not enabled.')
                    return
                if len(advanced_powers) != 18 or len(advanced_power_buffs) != 18:
                    fail(
                        'Reloaded power catalogue is incomplete: '
                        f'{len(advanced_powers)} powers, '
                        f'{len(advanced_power_buffs)} buff targets.'
                    )
                    return
                if any(
                    state == 'disabled'
                    for state in report['ui']['superweapon_control_states'].values()
                ):
                    fail('One or more superweapon controls are disabled.')
                    return
                dark = bool(app.dark_mode_var.get())
                expected_reward_colors = {
                    'access': '#70c7ff' if dark else '#176a9c',
                    'superweapon': '#c3afff' if dark else '#6548b8',
                }
                if report['ui']['reward_detail_colors'] != expected_reward_colors:
                    fail(
                        'Unlock detail colors do not match the launcher palette: '
                        f'{report["ui"]["reward_detail_colors"]!r}.'
                    )
                    return
                if set(report['ui']['reward_modes']) != {
                    'Standard', 'Chaos', 'Randomizer Arsenal',
                }:
                    fail('Advanced reward modes are incomplete.')
                    return
                if 'Shop Mode' not in report['ui']['progression_modes']:
                    fail('Shop progression mode is missing.')
                    return
                if any(
                    state == 'disabled'
                    for state in (
                        report['ui']['tier_one_units_state'],
                        report['ui']['tier_one_defenses_state'],
                    )
                ):
                    fail('Tier 1 starter controls are disabled.')
                    return
                if not unlock_card_count:
                    fail('Unlocks dashboard rendered no cards.')
                    return
                if str(app.archipelago_save_yaml_button.cget('state')) == 'disabled':
                    fail('Archipelago Player YAML action is disabled.')
                    return
                app.campaign_var.set(campaign_filter)
                app.progression_mode_var.set('Classic')
                app.reward_mode_var.set('Standard')
                app.rewards_on_victory_only_var.set(False)
                advanced_exclusion_id = next(
                    entry['id']
                    for entry in advanced_units
                    if entry.get('faction') == mission.get('faction')
                    and entry['id'] not in app.excluded_unit_access_ids
                )
                app.toggle_advanced_pool_entry(
                    'units', advanced_exclusion_id
                )
                report['ui']['advanced_exclusion_id'] = (
                    advanced_exclusion_id
                )
                app.seed_var.set(seed)
                app.mission_goal_var.set(3)
                app.rewards_per_check_var.set(1)
                app.seed_action_button.invoke()
                phase = 'seed_generation'
                phase_started = time.monotonic()
                app.after(50, poll)
                return

            if phase == 'seed_generation':
                if getattr(app, 'busy_depth', 0) or not app.state or app.state.get('seed') != seed:
                    app.after(50, poll)
                    return
                report['seed'] = {
                    'value': app.state.get('seed'),
                    'progression_mode': app.state.get('progression_mode'),
                    'mission_order': list(app.state.get('mission_order', ())),
                    'reward_settings': app.state.get('reward_settings', {}),
                    'elapsed_seconds': round(time.monotonic() - phase_started, 3),
                }
                objective_checks = sum(
                    1
                    for checks in app.state.get('mission_checks', {}).values()
                    for check in checks
                    if str(check.get('id', '')).startswith('objective_')
                )
                report['seed']['objective_check_count'] = objective_checks
                if objective_checks <= 0:
                    fail('Reviewed objective checks were not generated.')
                    return
                if report['ui']['advanced_exclusion_id'] not in set(
                    app.state['reward_settings'].get(
                        'excluded_unit_access_ids', ()
                    )
                ):
                    fail('Advanced unit exclusion was not frozen into the seed.')
                    return
                from Archipelago.run_manifest import build_run_manifest
                from Archipelago.yaml_config import (
                    parse_player_yaml,
                    serialize_player_yaml,
                )

                ap_manifest = build_run_manifest(app.state, app.config)
                ap_yaml = serialize_player_yaml(ap_manifest, 'Smoke Commander')
                parsed_yaml = parse_player_yaml(ap_yaml)
                if (
                    parsed_yaml['run_manifest'].get('manifest_checksum')
                    != ap_manifest.get('manifest_checksum')
                ):
                    fail('Archipelago Player YAML round-trip changed the manifest.')
                    return
                report['archipelago'] = {
                    'manifest_checksum': ap_manifest['manifest_checksum'],
                    'catalogue_checksum': ap_manifest['catalogue_checksum'],
                    'mission_count': len(ap_manifest['mission_order']),
                    'item_count': sum(ap_manifest['item_pool'].values()),
                    'yaml_bytes': len(ap_yaml.encode('utf-8')),
                    'round_trip_valid': True,
                }
                unlocked = set(app.unlocked_mission_codes())
                if mission_code not in unlocked:
                    fail(f'Requested Classic mission is not unlocked: {mission_code}.')
                    return
                index = next(
                    index for index, item in enumerate(app.missions)
                    if item['code'].upper() == mission_code.upper()
                )
                app.selected_index.set(index)
                app.redraw_mission_tree()
                launch_button = next(
                    widget for widget, text in _widget_texts(app)
                    if text == 'Launch Selected Mission'
                    and str(widget.cget('state')) != 'disabled'
                )
                source_path = resolve_installed_scenario(app.missions[index]['scenario'])
                source_hash = file_sha256(source_path)
                launch_button.invoke()
                phase = 'mission_launch'
                phase_started = time.monotonic()
                app.after(100, poll)
                return

            if phase == 'mission_launch':
                process = getattr(app, 'active_game_process', None)
                hook = getattr(app, 'active_hook', None)
                if process is None or hook is None:
                    app.after(100, poll)
                    return
                generated_path = Path(hook['root_map'])
                if not generated_path.is_file() or not is_generated_hooked_map(generated_path):
                    fail('Launcher did not create a marker-owned generated map.')
                    return
                launch_scenario = str(hook.get('launch_scenario') or generated_path.name)
                debug_text = _debug_text_from(debug_offset)
                scenario_started = any(
                    marker.lower() in debug_text.lower()
                    for marker in (
                        f'Starting scnenario: {launch_scenario}',
                        f'Starting scenario: {launch_scenario}',
                    )
                )
                observed_game_pids = _image_pids(GAME_EXE.name)
                if observed_game_pids is None:
                    app.after(250, poll)
                    return
                game_pids = observed_game_pids - baseline_game_pids
                if not scenario_started or not game_pids:
                    app.after(250, poll)
                    return
                report['launch'] = {
                    'mission': mission_code,
                    'generated_map': str(generated_path),
                    'launch_scenario': launch_scenario,
                    'game_pids': sorted(game_pids),
                    'scenario_confirmed_in_debug_log': True,
                    'source_sha256': source_hash,
                    'source_unchanged_after_start': file_sha256(source_path) == source_hash,
                    'elapsed_seconds': round(time.monotonic() - phase_started, 3),
                }
                _terminate_pid_tree(process.pid)
                phase = 'game_cleanup'
                phase_started = time.monotonic()
                app.after(250, poll)
                return

            if phase == 'game_cleanup':
                if getattr(app, 'active_game_process', None) is not None:
                    app.after(250, poll)
                    return
                if generated_path is not None and generated_path.exists():
                    app.after(250, poll)
                    return
                if source_path is not None and file_sha256(source_path) != source_hash:
                    fail('Authored mission hash changed after UI launch.')
                    return
                observed_game_pids = _image_pids(GAME_EXE.name)
                if observed_game_pids is None:
                    app.after(250, poll)
                    return
                report['cleanup'] = {
                    'generated_map_removed': generated_path is None or not generated_path.exists(),
                    'source_unchanged': source_path is None or file_sha256(source_path) == source_hash,
                    'game_processes_remaining': sorted(
                        observed_game_pids - baseline_game_pids
                    ),
                }
                report['passed'] = (
                    report['launch']['source_unchanged_after_start']
                    and report['cleanup']['generated_map_removed']
                    and report['cleanup']['source_unchanged']
                    and not report['cleanup']['game_processes_remaining']
                )
                app.quit()

        app.after(50, poll)
        app.mainloop()
        if failure is not None:
            raise failure
        if not report.get('passed'):
            raise RuntimeError('UI launch smoke ended without a passing result.')
    except Exception as exc:
        report['error'] = str(exc)
        report['traceback'] = traceback.format_exc()
    finally:
        if app is not None:
            process = getattr(app, 'active_game_process', None)
            if process is not None and process.poll() is None:
                _terminate_pid_tree(process.pid)
            try:
                app.cleanup_generated_root_maps()
                app.disable_generated_rules_for_client()
                app.destroy()
            except Exception as exc:
                report['cleanup_errors'].append(f'launcher cleanup: {exc}')
        for snapshot in snapshots:
            try:
                _restore(snapshot)
            except Exception as exc:
                report['cleanup_errors'].append(
                    f'{snapshot["path"]} restore: {exc}'
                )
        if source_path is not None and source_hash is not None:
            try:
                report['source_sha256_final'] = file_sha256(source_path)
                report['source_unchanged_final'] = (
                    report['source_sha256_final'] == source_hash
                )
            except Exception as exc:
                report['cleanup_errors'].append(f'source verification: {exc}')
        report['state_and_ini_files_restored'] = all(
            snapshot['path'].exists() == snapshot['existed']
            and (
                not snapshot['existed']
                or snapshot['path'].read_bytes() == snapshot['data']
            )
            for snapshot in snapshots
        )
        report['passed'] = bool(
            report.get('passed')
            and report.get('source_unchanged_final', True)
            and report['state_and_ini_files_restored']
            and not report['cleanup_errors']
        )
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, indent=2, default=str),
            encoding='utf-8',
        )
    return report


def run_from_command_line(arguments):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--ui-launch-smoke', action='store_true')
    parser.add_argument('--mission', default='ALL01_RA2')
    parser.add_argument('--seed', default='RLR-UI-SMOKE')
    parser.add_argument('--timeout', type=int, default=120)
    args, _unknown = parser.parse_known_args(arguments)
    report = run_ui_launch_smoke(
        mission_code=args.mission,
        seed=args.seed,
        timeout=args.timeout,
    )
    return 0 if report.get('passed') else 1
