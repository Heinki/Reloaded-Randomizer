"""Public launcher widget-construction facade."""

from .layout import _build_info_tabs, _build_right_panel, _build_window_shell
from .overlay import _build_log_and_overlay
from .settings import _build_advanced_tab, _build_gameplay_settings
from .archipelago import build_archipelago_tab
from .shop import build_shop_tab
from randomizer.config.game_profile import (
    ENABLE_ADVANCED_UI,
    ENABLE_ADVANCED_GAMEPLAY,
    ENABLE_ARCHIPELAGO,
    ENABLE_SHOP_MODE,
    GAMEPLAY_CATALOGUES_READY,
)


def create_widgets(self):
    """Construct launcher widgets by delegating each cohesive UI region."""
    main_frame = _build_window_shell(self)
    info_tabs, _, settings_frame = _build_right_panel(
        self,
        main_frame,
    )
    _build_info_tabs(self, info_tabs)
    if not GAMEPLAY_CATALOGUES_READY:
        for tab_id in tuple(info_tabs.tabs()):
            label = info_tabs.tab(tab_id, 'text')
            if label == 'Details':
                continue
            info_tabs.tab(
                tab_id,
                text=f'{label} (Review Pending)',
                state='disabled',
            )
    build_shop_tab(self, self.workspace_tabs)
    if not ENABLE_SHOP_MODE:
        self.workspace_tabs.add(
            self.shop_tab,
            text='Shop Mode (Review Pending)',
            state='disabled',
        )
    _build_advanced_tab(self, self.workspace_tabs)
    if not ENABLE_ADVANCED_UI:
        self.workspace_tabs.tab(
            self.advanced_tab,
            text='Advanced (Review Pending)',
            state='disabled',
        )
    build_archipelago_tab(self, self.workspace_tabs)
    if not ENABLE_ARCHIPELAGO:
        self.workspace_tabs.tab(
            self.archipelago_tab,
            text='Archipelago (Foundation)',
            state='disabled',
        )
    _build_gameplay_settings(self, settings_frame)
    if not GAMEPLAY_CATALOGUES_READY:
        self.seed_action_button.configure(
            text='Generate Seed (Review Pending)',
            state='disabled',
        )
    if ENABLE_SHOP_MODE:
        self.sync_shop_workspace()
    self.layout_settings_sections(self.settings_canvas.winfo_width())
    if ENABLE_ARCHIPELAGO:
        self.initialize_archipelago_control_registry()
        self.refresh_archipelago_yaml_status()
    self.refresh_setting_states()
    _build_log_and_overlay(self, main_frame)
