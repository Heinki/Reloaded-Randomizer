"""Reloaded launcher lifecycle and Settings bridge for the Fortress controller."""

import os
import subprocess
import sys
from tkinter import ttk

from randomizer.core.paths import GAME_ROOT
from randomizer.maps.assets import claim_runtime_asset_lease


class FortressLauncherAdapter:
    def begin_direct_game_preparation(self):
        claim_runtime_asset_lease()
        self.cleanup_generated_root_maps()
        self.disable_generated_rules_for_client()
        # Generic asset cleanup releases our old lease with the staging files.
        claim_runtime_asset_lease()

    def spawn_game_process(self, command):
        options = {}
        if sys.platform != 'win32':
            environment = os.environ.copy()
            overrides = environment.get('WINEDLLOVERRIDES', '')
            if not any(part.strip().lower().startswith('ddraw=') for part in overrides.split(';')):
                environment['WINEDLLOVERRIDES'] = ';'.join(filter(None, (overrides, 'ddraw=n,b')))
            options.update(env=environment, start_new_session=True)
        process = subprocess.Popen(command, cwd=GAME_ROOT, **options)
        return process, None

    def game_speed_controls_locked(self):
        process = getattr(self, 'active_game_process', None)
        return bool(process is not None and process.poll() is None)

    def refresh_game_speed_controls(self):
        locked = self.game_speed_controls_locked()
        for name in ('game_speed_combo', 'shop_game_speed_combo'):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.configure(state='disabled' if locked else 'readonly')

    def on_game_speed_changed(self, _event=None):
        self.save_current_launcher_config()
        self.update_header_summary()

    def refresh_coop_controls(self):
        self.refresh_fortress_settings_controls()

    def refresh_challenge_support_controls(self):
        self.refresh_fortress_settings_controls()

    def open_coop_dialog(self):
        return None

    def build_fortress_settings(self, parent):
        frame = self.fortress_settings_frame = ttk.LabelFrame(
            parent, text='Final Fortress co-op', padding=12)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text='Game Mode').grid(row=0, column=0, sticky='w', padx=(0, 12))
        self.fortress_settings_mode_combo = ttk.Combobox(
            frame, textvariable=self.game_mode_var, values=self.game_mode_choices, state='readonly')
        self.fortress_settings_mode_combo.grid(row=0, column=1, sticky='ew')
        self.fortress_settings_mode_combo.bind('<<ComboboxSelected>>', self.on_game_mode_changed)
        self.fortress_settings_coop_check = ttk.Checkbutton(
            frame, text='Co-op', variable=self.final_fortress_coop_var,
            command=self.on_fortress_coop_mode_changed)
        self.fortress_settings_coop_check.grid(row=1, column=0, sticky='w', pady=8)
        ttk.Label(frame, text='Co-op players').grid(row=2, column=0, sticky='w', padx=(0, 12))
        self.fortress_settings_count_combo = ttk.Combobox(
            frame, textvariable=self._fortress_coop_count_var, values=('2', '3'),
            state='readonly', width=8)
        self.fortress_settings_count_combo.grid(row=2, column=1, sticky='w')
        self.fortress_settings_connection_button = ttk.Button(
            frame, text='Co-op Connection…', command=self.open_fortress_coop_dialog)
        self.fortress_settings_connection_button.grid(row=3, column=1, sticky='w', pady=8)
        ttk.Checkbutton(frame, text='Include challenge maps (unavailable in Final Fortress)',
                        variable=self._fortress_challenge_maps_var, state='disabled').grid(
                            row=4, column=0, columnspan=2, sticky='w')

    def layout_settings_sections(self, width):
        frame = getattr(self, 'fortress_settings_frame', None)
        if frame is None:
            return super().layout_settings_sections(width)
        if not self.final_fortress_mode_selected():
            frame.grid_remove()
            if getattr(self, '_settings_layout_signature', None) == ('fortress',):
                self._settings_layout_signature = None
            return super().layout_settings_sections(width)
        self._settings_layout_signature = ('fortress',)
        for widget in self.settings_frame.grid_slaves():
            widget.grid_remove()
        self.settings_frame.columnconfigure(0, weight=1)
        self.settings_frame.columnconfigure(1, weight=0)
        frame.grid(row=0, column=0, sticky='new')
        self.appearance_frame.grid(row=1, column=0, sticky='new', pady=8)
        self.settings_tab_label = 'Settings'
        self.workspace_tabs.tab(self.settings_tab, text='Settings')
        self.refresh_fortress_settings_controls()
        self.on_settings_content_configure()
