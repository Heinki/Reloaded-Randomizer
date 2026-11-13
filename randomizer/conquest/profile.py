"""Native installation contract for this Conquest port."""

from pathlib import Path
from randomizer.core.paths import CAMEO_CACHE_DIR
from randomizer.ui.cameos import extract_mix_files_sync
from randomizer.maps.ini import all_section_value_maps_preserve


def read_ini(path):
    data = Path(path).read_bytes()
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = data.decode('latin-1')
    return {name: {key: value.split(';', 1)[0].strip() for key, value in values.items()}
            for name, values in all_section_value_maps_preserve(text.splitlines()).items()}


def installed_rules():
    """Read the installed, unmodified archive cache rather than a previous run."""
    if not extract_mix_files_sync([(RULES_FILE, CAMEO_CACHE_DIR / RULES_FILE),
                                   (ART_FILE, CAMEO_CACHE_DIR / ART_FILE),
                                   (AI_FILE, CAMEO_CACHE_DIR / AI_FILE)]):
        raise ValueError('Installed rules, art or AI data are unavailable. Repair the game installation.')
    rows = read_ini(CAMEO_CACHE_DIR / RULES_FILE)
    # Reloaded contains dormant countries. Keep the same native country
    # policy used by Fortress, leaving eight independent multiplayer seats.
    countries = [c for c in rows['Countries'].values() if c not in INACTIVE_COUNTRIES]
    rows['Countries'] = {str(i): c for i, c in enumerate(countries)}
    for category in ('InfantryTypes', 'VehicleTypes', 'AircraftTypes', 'BuildingTypes'):
        rows[category] = {k: v for k, v in rows[category].items() if v in rows}
    return rows

GAME = 'reloaded'
TITLE = 'C&C Reloaded'
RULES_FILE, ART_FILE, AI_FILE = ('rulesmd.ini', 'artmd.ini', 'aimd.ini')
INACTIVE_COUNTRIES = ('RobotCountry', 'RobotCountry2', 'UnusedCountry', 'UnusedCountry2', 'NoPilotsCountry')
INSTALLATION_FILES = ('gamemd.exe', 'Syringe.exe', 'Ares.dll', 'CnCNet-Spawner.dll', 'Phobos.dll', 'Resources/GameOptions.ini', 'INI/MPMaps.ini')
NATIVE_COUNTRIES = {'Allies': 'AlliesCountry',
 'Soviets': 'SovietCountry',
 'Yuri': 'YuriCountry',
 'GDI': 'GDICountry',
 'Nod': 'NodCountry'}
FAMILIES = {'Allies': 'Allies', 'Soviets': 'Soviets', 'Yuri': 'Yuri', 'GDI': 'GDI', 'Nod': 'Nod'}
ROSTERS = {'Allies': ('E1', 'FV', 'MTNK', 'GAPOWR', 'GAPILE', 'GAREFN', 'CMIN', 'GAPILL'),
 'Soviets': ('E2', 'HTK', 'HTNK', 'NAPOWR', 'NAHAND', 'NAREFN', 'HARV', 'NALASR'),
 'Yuri': ('INIT', 'LTNK', 'LTNK', 'YAPOWR', 'YABRCK', 'YAREFN2', 'YHARV', 'YAGGUN'),
 'GDI': ('TSE1', 'SMECH', 'PREDATOR', 'GDIPOWR', 'TSGAPILE', 'TSPROC', 'TSHARV', 'GAVULC'),
 'Nod': ('TSNE1', 'TSBGGY', 'SCORP', 'NODPOWR', 'TSNAHAND', 'TSPROC2', 'TSNHARV', 'TSLASR')}
FACTORIES = {'Allies': 'GAWEAP',
 'Soviets': 'NAWEAP',
 'Yuri': 'YAWEAP',
 'GDI': 'TSGAWEAP',
 'Nod': 'TSNAWEAP'}
AIRCRAFT_BUILDINGS = {'Allies': 'GAAIRC',
 'Soviets': 'NAHELIPAD',
 'Yuri': 'YAWEAP',
 'GDI': 'TSGAHPAD',
 'Nod': 'TSNAHPAD'}
ESCORT_ROSTERS = {'Allies': {'infantry': ('E1', 'GGI', 'JUMPJET', 'TANY'),
            'vehicles': ('MTNK', 'FV', 'SREF', 'BFRT')},
 'Soviets': {'infantry': ('E2', 'FLAKT', 'SHK', 'BORIS'),
             'vehicles': ('HTNK', 'HTK', 'V3', 'APOC')},
 'Yuri': {'infantry': ('INIT', 'BRUTE', 'YURI', 'YURIPR'),
          'vehicles': ('LTNK', 'YTNK', 'TELE', 'MIND')},
 'GDI': {'infantry': ('TSE1', 'TSE2', 'TSJUMPJET', 'TSGHOST'),
         'vehicles': ('PREDATOR', 'MMCH', 'TSSONIC', 'MM2MEC')},
 'Nod': {'infantry': ('TSNE1', 'TSE3', 'ELCAD', 'NODCOMMANDO'),
         'vehicles': ('SCORP', 'TSBIKE', 'TSSTNK', 'AVATAR')}}
