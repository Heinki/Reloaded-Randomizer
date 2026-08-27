"""Authoritative C&C Reloaded installation and engine profile.

Game-specific names belong here instead of being scattered through launcher,
map, UI, and packaging modules. Gameplay catalogues remain separate static
configuration because they require mapper review.
"""

PRODUCT_NAME = 'C&C Reloaded Randomizer'
WINDOW_TITLE = 'C&C Reloaded Randomizer Launcher'
EXECUTABLE_NAME = 'CnCReloadedRandomizer.exe'
RUNTIME_DIRECTORY_NAME = 'ReloadedRandomizerData'
SEED_PREFIX = 'RLR'

GAME_CLIENT_NAME = 'CnCReloadedClient.exe'
GAME_LAUNCHER_NAME = 'Syringe.exe'
GAME_EXECUTABLE_NAME = 'gamemd.exe'
GAME_INJECTED_DLL_NAMES = ('Ares.dll', 'CnCNet-Spawner.dll', 'Phobos.dll')
GAME_RUNTIME_ARGUMENTS = (
    '-SPAWN',
    '-CD',
    '-SPEEDCONTROL',
    '-INCLUDE',
    '-INHERITANCE',
    '-LOG',
    '-ICON',
    'Resources/gamemd.ico',
)
SPAWN_INI_NAME = 'spawn.ini'
OPTIONS_INI_NAME = 'RA2MD.ini'
UI_INI_NAME = 'uimd.ini'
BATTLE_INI_PARTS = ('INI', 'Battle.ini')

RULES_INI_NAME = 'rulesmd.ini'
ART_INI_NAME = 'artmd.ini'
AI_INI_NAME = 'aimd.ini'
ARCHIVE_GLOB = 'expandmd*.mix'
MAP_DIRECTORY_PARTS = ('Maps', 'Missions')

CAMPAIGN_FACTIONS = ('Allies', 'Soviets', 'Yuri', 'GDI', 'Nod')
CAMPAIGN_ORDER = (
    'Red Alert 2',
    "Yuri's Revenge",
    'Tiberian Sun',
    'Firestorm',
    'Resurgence',
)
CAMPAIGN_FACTIONS_BY_NAME = {
    'Red Alert 2': ('Allies', 'Soviets'),
    "Yuri's Revenge": ('Allies', 'Soviets'),
    'Tiberian Sun': ('GDI', 'Nod'),
    'Firestorm': ('GDI', 'Nod'),
    'Resurgence': ('Yuri',),
}
CAMPAIGN_FILTER_SPECS = (
    ('Allies - Red Alert 2', 'Allies', 'Red Alert 2'),
    ('Soviets - Red Alert 2', 'Soviets', 'Red Alert 2'),
    ("Allies - Yuri's Revenge", 'Allies', "Yuri's Revenge"),
    ("Soviets - Yuri's Revenge", 'Soviets', "Yuri's Revenge"),
    ('GDI - Tiberian Sun', 'GDI', 'Tiberian Sun'),
    ('Nod - Tiberian Sun', 'Nod', 'Tiberian Sun'),
    ('GDI - Firestorm', 'GDI', 'Firestorm'),
    ('Nod - Firestorm', 'Nod', 'Firestorm'),
    ('Yuri - Resurgence', 'Yuri', 'Resurgence'),
)
CAMPAIGN_FILTER_BY_LABEL = {
    label: {'faction': faction, 'campaign': campaign}
    for label, faction, campaign in CAMPAIGN_FILTER_SPECS
}
CONTENT_FACTIONS = CAMPAIGN_FACTIONS
DEFERRED_CONTENT_FACTIONS = ('CABAL',)
FACTION_ORDER = CONTENT_FACTIONS
ACTIVE_SIDE_SECTIONS = (
    'GDI',
    'Nod',
    'ThirdSide',
    'TSGDISide',
    'TSNodSide',
)
EVA_SIDE_SECTION_BY_FACTION = {
    'Allies': 'GDI',
    'Soviets': 'Nod',
    'Yuri': 'ThirdSide',
    'GDI': 'TSGDISide',
    'Nod': 'TSNodSide',
}
EVA_TAG_FALLBACK_BY_FACTION = {
    'Yuri': 'Yuri',
}
FACTION_ALIASES = {
    'allies': 'Allies',
    'allied': 'Allies',
    'soviet': 'Soviets',
    'soviets': 'Soviets',
    'yuri': 'Yuri',
    'gdi': 'GDI',
    'nod': 'Nod',
    'cabal': 'CABAL',
    'robot': 'CABAL',
}

# Standard RA2/YR winner actions plus C&C Reloaded's reviewed Phobos winner
# action used by the Nod Firestorm campaign.
TERMINAL_WIN_ACTION_CODES = ('1', '67', '19001')
TERMINAL_END_ACTION_CODES = TERMINAL_WIN_ACTION_CODES + ('69',)

# Randomizer-owned engine identifiers. Native campaign identifiers never use
# these prefixes and remain untouched unless an explicit mission rule opts in.
GENERATED_TYPE_PREFIX = 'RLRP'
GENERATED_HOOK_PREFIX = 'RLR'

SUPPORTED_GAME_VERSION = '2.7.0'

# Runnable core uses reviewed Reloaded unit/defense access rewards and isolated
# RLRP production clones. Buffs, powers, advanced modes, Shop, and AP remain
# separately gated until their Reloaded catalogues are complete.
FOUNDATION_ONLY = False
GAMEPLAY_CATALOGUES_READY = True

# Victory hooks and 73 source-proven objective milestones are integrated.
# Manual completion remains available as recovery for runtime log failures.
OBJECTIVE_REWARDS_READY = True

# The Reloaded integrations use their own IDs and economy data. Advanced,
# power cloning, Shop, and Archipelago all use the reviewed five-faction data.
ENABLE_SHOP_MODE = True
ENABLE_ARCHIPELAGO = True
ENABLE_ADVANCED_UI = True
ENABLE_ADVANCED_GAMEPLAY = True
