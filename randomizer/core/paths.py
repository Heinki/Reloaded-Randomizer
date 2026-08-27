"""Shared filesystem paths for the C&C Reloaded randomizer launcher."""

import sys
from pathlib import Path

from randomizer.config.game_profile import (
    BATTLE_INI_PARTS,
    GAME_CLIENT_NAME,
    GAME_EXECUTABLE_NAME,
    GAME_LAUNCHER_NAME,
    MAP_DIRECTORY_PARTS,
    OPTIONS_INI_NAME,
    RULES_INI_NAME,
    RUNTIME_DIRECTORY_NAME,
    SPAWN_INI_NAME,
    UI_INI_NAME,
)


FROZEN = bool(getattr(sys, 'frozen', False))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = PROJECT_ROOT
WINDOW_ICON_PATH = SOURCE_DIR / 'reloaded-randomizer.ico'

# A one-file build is placed directly in the C&C Reloaded folder. PyInstaller
# expands bundled modules to a temporary directory, so __file__ cannot locate
# the game or persistent state in frozen builds.
if FROZEN:
    GAME_ROOT = Path(sys.executable).resolve().parent
    APP_DIR = GAME_ROOT / RUNTIME_DIRECTORY_NAME
else:
    APP_DIR = SOURCE_DIR
    GAME_ROOT = SOURCE_DIR.parent

GAME_CLIENT_EXE = GAME_ROOT / GAME_CLIENT_NAME
GAME_LAUNCHER_EXE = GAME_ROOT / GAME_LAUNCHER_NAME
GAME_EXE = GAME_ROOT / GAME_EXECUTABLE_NAME
SPAWN_INI = GAME_ROOT / SPAWN_INI_NAME
OPTIONS_INI = GAME_ROOT / OPTIONS_INI_NAME
UIMD_INI = GAME_ROOT / UI_INI_NAME
DEBUG_LOG = GAME_ROOT / 'debug' / 'debug.log'
RULES_INI = GAME_ROOT / RULES_INI_NAME
DISABLED_RULES_INI = GAME_ROOT / f'{RULES_INI_NAME}.randomizer-disabled'
BATTLE_INI = GAME_ROOT.joinpath(*BATTLE_INI_PARTS)
MISSION_MAP_DIR = GAME_ROOT.joinpath(*MAP_DIRECTORY_PARTS)

STATE_PATH = APP_DIR / 'randomizer_state.json'
SHOP_PROFILE_PATH = APP_DIR / 'shop_profile.json'
SHOP_RUN_PATH = APP_DIR / 'shop_run.json'
SHOP_TRANSACTION_PATH = APP_DIR / 'shop_transaction.json'
BACKUP_DIR = APP_DIR / 'backups'
EXTRACTED_MAP_DIR = APP_DIR / 'extracted_maps'
GENERATED_MAP_DIR = APP_DIR / 'generated_maps'
CAMEO_CACHE_DIR = APP_DIR / 'cameo_cache'
CONFIG_DIR = APP_DIR / 'configs' / 'player'
LEGACY_CONFIG_DIR = APP_DIR / 'config'
LOG_DIR = APP_DIR / 'logs'
LAUNCHER_LOG = LOG_DIR / 'launcher.log'
