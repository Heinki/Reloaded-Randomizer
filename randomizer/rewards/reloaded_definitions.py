"""Runtime reward catalogue built only from reviewed C&C Reloaded facts.

This profile enables approved unit/defense access rewards, safe build-only
clones, conservative clone-local buffs, and reviewed player-facing Reloaded
powers. Internal upgrade, converter, debug, AI-only, and CABAL powers are not
part of the runtime catalogue.
"""

from randomizer.config.static import load_static_config
from randomizer.config.tuning import BUFF_EFFECTS, REWARD_PLANNING
from randomizer.content.inventory import FACTION_HOUSE_VARIANTS, read_rules_sections
from randomizer.rewards.enemy_scaling import build_enemy_reward_pool
from randomizer.rewards.power_buff_definitions import build_power_buff_rewards


_CONTENT = load_static_config('rewards/reloaded_content_catalogue.json')['content']
_BALANCE = load_static_config('rewards/reloaded_balance_catalogue.json')
_FACTIONS = load_static_config('factions.json')
_RULES, _RULES_SOURCE = read_rules_sections()
_RULE_NAMES = {str(name).upper(): name for name in _RULES}

DEFAULT_UNLOCK_BUILD_HOUSES = _FACTIONS['default_unlock_build_houses']
DEFAULT_REWARDS_PER_CHECK = int(REWARD_PLANNING['default_rewards_per_check'])
MAX_REWARDS_PER_CHECK = int(REWARD_PLANNING['maximum_rewards_per_check'])


def _approved_factions(record):
    return tuple(
        faction
        for faction, review in record['reviews'].items()
        if review['status'] == 'approved'
    )


def _source_records():
    for category, records in _CONTENT['units'].items():
        for record in records:
            yield category, record
    for record in _CONTENT['defenses']:
        yield 'defenses', record


_RUNTIME_RECORDS = tuple(
    (category, record)
    for category, record in _source_records()
    if _approved_factions(record)
    and not str(record['id']).upper().endswith('_AI')
)


def _records():
    yield from _RUNTIME_RECORDS


def _raw_label(record):
    return str(record.get('name') or record.get('ui_name') or record['id'])


_LABEL_COUNTS = {}
for _label_category, _label_record in _RUNTIME_RECORDS:
    _label_key = _raw_label(_label_record)
    _LABEL_COUNTS[_label_key] = _LABEL_COUNTS.get(_label_key, 0) + 1


def _label(record):
    label = _raw_label(record)
    factions = _approved_factions(record)
    if _LABEL_COUNTS.get(label, 0) > 1 and len(factions) == 1:
        return f'{factions[0]} {label}'
    return label


def _plural(label):
    return label if label.endswith('s') else label + 's'


def _number(values, key, default=None):
    try:
        value = next(
            value for name, value in values.items()
            if str(name).lower() == key.lower()
        )
        number = float(str(value).strip())
        return int(number) if number.is_integer() else number
    except (StopIteration, TypeError, ValueError):
        return default


_BALANCE_BY_ID = {
    str(target['id']).upper(): target
    for target in _BALANCE['buff_targets']
}
_CATEGORY_MAP = {
    'infantry': 'infantry',
    'vehicles': 'units',
    'aircraft': 'aircraft',
    'defenses': 'defenses',
}

FACTION_UNIT_ROSTERS = {
    faction: {'infantry': {}, 'units': {}, 'aircraft': {}}
    for faction in FACTION_HOUSE_VARIANTS
    if faction != 'CABAL'
}
FACTION_DEFENSE_ROSTERS = {
    faction: {} for faction in FACTION_UNIT_ROSTERS
}
BUFF_TARGETS = {}
NAVAL_UNIT_IDS = set()
NONTRAINABLE_UNIT_IDS = set()

for _category, _record in _records():
    _factions_for_record = _approved_factions(_record)
    if not _factions_for_record:
        continue
    _unit_id = str(_record['id']).upper()
    _runtime_category = _CATEGORY_MAP[_category]
    _unit_label = _label(_record)
    if _runtime_category == 'defenses':
        for _faction in _factions_for_record:
            FACTION_DEFENSE_ROSTERS[_faction][_unit_id] = _unit_label
    else:
        for _faction in _factions_for_record:
            FACTION_UNIT_ROSTERS[_faction][_runtime_category][
                _unit_id
            ] = _unit_label
    if _record.get('naval'):
        NAVAL_UNIT_IDS.add(_unit_id)
    if _record.get('trainable') is False:
        NONTRAINABLE_UNIT_IDS.add(_unit_id)

    _balance = _BALANCE_BY_ID.get(_unit_id, {})
    _stats = _balance.get('stats', {})
    _native = _RULES.get(_RULE_NAMES.get(_unit_id), {})
    _weapons = {}
    for _weapon in _balance.get('weapons', ()):
        if not _weapon.get('source_present'):
            continue
        _weapon_stats = {
            field: _weapon.get(field)
            for field in ('damage', 'rof', 'range')
            if _weapon.get(field) is not None
        }
        if _weapon_stats:
            _weapons[str(_weapon['id']).upper()] = _weapon_stats
    _target = {
        'category': _runtime_category,
        'label': _unit_label,
        'plural': _plural(_unit_label),
        'factions': list(_factions_for_record),
        'special_reward': False,
        'strength': _stats.get('strength') or _number(_native, 'Strength', 1),
        'cost': _stats.get('cost') or _number(_native, 'Cost', 1),
        'sight': _stats.get('sight') or _number(_native, 'Sight', 1),
        'guard_range': _number(
            _native, 'GuardRange', _stats.get('sight') or 1
        ),
        'trainable': bool(_stats.get('trainable', True)),
        'weapons': _weapons,
        'allowed_buff_types': [],
    }
    for _key in ('speed', 'ammo', 'passengers'):
        _value = _stats.get(_key)
        if _value is not None:
            _target[_key] = _value
    _build_limit = _record.get('build_limit')
    if _build_limit is not None:
        _target['build_limit'] = _build_limit
    _review = _balance.get('review') or {}
    _approved_types = (
        set(_review.get('approved_buff_types') or ())
        if _review.get('status') == 'approved'
        else set()
    )
    _target['allowed_buff_types'] = sorted(_approved_types)
    BUFF_TARGETS[_unit_id] = _target


ENGINEER_UNIT_IDS = frozenset(
    str(value).upper() for value in _FACTIONS['engineer_by_family'].values()
)
AMPHIBIOUS_TRANSPORT_UNIT_IDS = frozenset(
    str(values[0]).upper()
    for values in _FACTIONS['amphibious_transports'].values()
)
_INFRASTRUCTURE_IDS = {
    str(value).upper()
    for family in _FACTIONS['production_buildings'].values()
    for values in family.values()
    for value in values
}
_INFRASTRUCTURE_IDS.update(
    str(value).upper() for value in _FACTIONS['conyard_by_mcv']
)
_INFRASTRUCTURE_IDS.update(
    str(value).upper() for value in _FACTIONS['conyard_by_mcv'].values()
)
for _family_values in _FACTIONS['miners'].values():
    _INFRASTRUCTURE_IDS.update(str(value).upper() for value in _family_values)

ALWAYS_AVAILABLE_UNIT_IDS = set(
    ENGINEER_UNIT_IDS | AMPHIBIOUS_TRANSPORT_UNIT_IDS
)
ALWAYS_AVAILABLE_TECH_IDS = ALWAYS_AVAILABLE_UNIT_IDS | _INFRASTRUCTURE_IDS


def _reward_rules(record, factions):
    houses = ','.join(
        house
        for faction in factions
        for house in FACTION_HOUSE_VARIANTS[faction]
    )
    prerequisites = ','.join(record.get('prerequisite') or ())
    values = {
        'TechLevel': '1',
        'Owner': houses,
        'RequiredHouses': houses,
        'ForbiddenHouses': 'none',
    }
    if prerequisites:
        values['Prerequisite'] = prerequisites
    return {str(record['id']).upper(): values}


UNIT_UNLOCK_REWARDS = []
DEFENSE_UNLOCK_REWARDS = []
for _category, _record in _records():
    _approved = _approved_factions(_record)
    _unit_id = str(_record['id']).upper()
    if not _approved or _unit_id in ALWAYS_AVAILABLE_TECH_IDS:
        continue
    _reward = {
        'name': f'{_label(_record)} Access',
        'description': f'Allows {_label(_record)} production.',
        'kind': 'access',
        'access_category': _CATEGORY_MAP[_category],
        'rules': _reward_rules(_record, _approved),
        'factions': list(_approved),
    }
    if _category == 'defenses':
        DEFENSE_UNLOCK_REWARDS.append(_reward)
    else:
        UNIT_UNLOCK_REWARDS.append(_reward)

EXTRA_UNIT_UNLOCK_REWARDS = []
ROSTER_UNIT_UNLOCK_REWARDS = []
SPECIAL_BUILDING_UNLOCK_REWARDS = []
_POWER_RECORD_BY_ID = {
    str(record['id']).upper(): record
    for record in _BALANCE['powers']
    if record['review']['status'] == 'candidate'
}

# Only genuine player-facing controls are listed. The source review also sees
# campaign internals such as LimboUpgrade_SW*, tower converters, and paired
# implementation helpers; provider visibility alone does not make those safe
# randomizer rewards.
_POWER_DEFINITIONS = (
    ('NukeSpecial', 'Nuclear Missile', 'offensive', ('Soviets',)),
    ('LightningStormSpecial', 'Weather Storm', 'offensive', ('Allies',)),
    ('PsychicDominatorSpecial', 'Psychic Dominator', 'offensive', ('Yuri',)),
    ('TSIonCannonSpecial', 'Ion Cannon', 'offensive', ('GDI',)),
    ('TSMultiSpecial', 'Multi-Missile', 'offensive', ('Nod',)),
    ('IronCurtainSpecial', 'Iron Curtain', 'secondary', ('Soviets',)),
    ('ChronoSphereSpecial', 'Chrono Sphere', 'secondary', ('Allies',)),
    ('ForceShieldSpecial', 'Force Shield', 'secondary', (
        'Allies', 'Soviets', 'Yuri', 'GDI', 'Nod',
    )),
    ('EMPulseSpecial', 'EM Pulse', 'secondary', ('GDI', 'Nod')),
    ('ParaDropSpecial', 'Paratrooper Drop', 'aid', ('Allies',)),
    ('SpyPlaneSpecial', 'Spy Plane', 'aid', ('Soviets',)),
    ('GeneticConverterSpecial', 'Genetic Converter', 'aid', ('Yuri',)),
    ('PsychicRevealSpecial', 'Psychic Reveal', 'aid', ('Yuri',)),
    ('SonarPulseSpecial', 'Sonar Pulse', 'aid', (
        'Allies', 'Soviets', 'Yuri', 'GDI', 'Nod',
    )),
    ('TiberiumShowerSpecial', 'Chemical Bomb', 'aid', ('Nod',)),
    ('DropPodSpecial', 'Drop Pods', 'aid', ('GDI',)),
    ('HuntSeekSpecial', 'Hunter Seeker', 'aid', ('GDI', 'Nod')),
    ('SpawnCarryallFromAirSW', 'Carryall', 'aid', ('GDI',)),
)


def _power_reward(power_id, label, category, factions):
    if power_id.upper() not in _POWER_RECORD_BY_ID:
        raise ValueError(f'Reviewed Reloaded power is missing: {power_id}')
    reward = {
        'name': f'{label} Power',
        'description': (
            f'Grants an isolated {label} power in future launched missions.'
        ),
        'rules': {},
        'factions': list(factions),
        'kind': 'superweapon',
        'power_category': category,
        'superweapon': power_id,
        'special_reward': False,
    }
    if power_id == 'TiberiumShowerSpecial':
        reward['cameo_superweapon'] = 'TSSuperChemicalSpecial'
    if power_id == 'ParaDropSpecial':
        # Reloaded's normal Allied paradrop payload lives in hardcoded
        # [General] defaults. Materialize it on the private power clone so the
        # MO delivery resolver can replace E1 with its current buffed clone.
        reward['superweapon_rules'] = {
            'ParaDrop.Types': 'E1',
            'ParaDrop.Num': '7',
        }
        reward['superweapon_delivery_player_clone_ids'] = ['E1']
    if power_id == 'DropPodSpecial':
        reward['superweapon_delivery_player_clone_ids'] = ['TSE1', 'TSE2']
    if power_id == 'TiberiumShowerSpecial':
        reward['superweapon_techno_clones'] = {
            'TIBBOMB': {
                'source': 'TIBBOMB',
                'clone': 'RLRPTIBBOMB',
                'list': 'InfantryTypes',
                'reference_keys': ('ParaDrop.Types',),
                'values': {},
            },
        }
    if power_id == 'HuntSeekSpecial':
        reward['superweapon_techno_clones'] = {
            'GHUNTER': {
                'source': 'GHUNTER',
                'clone': 'RLRPGHUNTER',
                'list': 'VehicleTypes',
                'reference_keys': ('HunterSeeker.Type',),
                'values': {},
            },
        }
    if power_id == 'EMPulseSpecial':
        # Reloaded's native EM Pulse only fires through a built GAPULS/NAPULS
        # cannon, within 7-30 cells, and is blocked by several inhibitors.
        # Match Mental Omega's portable-power policy while retaining the
        # EMPulse engine path: use one invisible player-owned cannon clone,
        # its private weapon/projectile/warhead chain, and no map-tech gate.
        reward['superweapon_ignore_foreign_tech_gate'] = True
        reward['superweapon_rules'] = {
            'IsPowered': 'false',
            'SW.FireIntoShroud': 'yes',
            'SW.AutoFire': 'no',
            'SW.ManualFire': 'yes',
            'SW.ShowCameo': 'yes',
            'SW.UseAITargeting': 'no',
            'SW.AITargeting': 'None',
            'SW.RequiredHouses': '',
            'SW.ForbiddenHouses': '',
            'SW.AuxBuildings': '',
            'SW.NegBuildings': '',
            'SW.Designators': '',
            'SW.Inhibitors': '',
            'SW.AnyInhibitor': 'no',
            'SW.RangeMaximum': '-1',
            'SW.RangeMinimum': '-1',
            'EMPulse.Cannons': 'RLRPEMPCANNON',
            'EMPulse.TargetSelf': 'no',
        }
        reward['superweapon_techno_clones'] = {
            'GAPULS': {
                'source': 'GAPULS',
                'clone': 'RLRPEMPCANNON',
                'list': 'BuildingTypes',
                'reference_keys': ('EMPulse.Cannons',),
                'startup_count': 1,
                'static_startup': True,
                'values': {
                    'Name': 'Randomizer EM Pulse Provider',
                    'UIName': 'Name:NAPULS',
                    'Image': 'GAPULS',
                    'Primary': 'RLRPEMPWEAPON',
                    'SuperWeapon': None,
                    'SuperWeapon2': None,
                    'SuperWeapons': None,
                    'EMPulseCannon': 'yes',
                    'TechLevel': '-1',
                    'BuildLimit': '0',
                    'AIBuildThis': 'no',
                    'Power': '0',
                    'Powered': 'false',
                    'Capturable': 'false',
                    'Selectable': 'no',
                    'Unsellable': 'yes',
                    'LegalTarget': 'no',
                    'Insignificant': 'yes',
                    'ImmuneToEMP': 'yes',
                    'DontScore': 'yes',
                    'KeepAlive': 'no',
                    'BaseNormal': 'no',
                    'AIBaseNormal': 'no',
                    'IsBaseDefense': 'no',
                    'RadarInvisible': 'yes',
                    'IsPassable': 'yes',
                    'Sight': '0',
                },
            },
            'EMPulseWeapon': {
                'source': 'EMPulseWeapon',
                'clone': 'RLRPEMPWEAPON',
                'list': 'WeaponTypes',
                'values': {
                    'Range': '384',
                    'Projectile': 'RLRPEMPPROJECTILE',
                    'Warhead': 'RLRPEMPULS',
                },
            },
            'PulsPr': {
                'source': 'PulsPr',
                'clone': 'RLRPEMPPROJECTILE',
                'list': 'Projectiles',
                'values': {},
            },
        }
        reward['superweapon_auxiliary_clones'] = {
            'EMPuls': {
                'clone': 'RLRPEMPULS',
                'list': 'Warheads',
                'reference_keys': ('SW.Warhead',),
                'values': {},
            },
        }
    if power_id == 'SpawnCarryallFromAirSW':
        reward['superweapon_rules'] = {
            'SW.AuxBuildings': '',
            'SW.Inhibitors': '',
            'SW.AnyInhibitor': 'no',
        }
    return reward


_PLAYER_POWER_REWARDS = [
    _power_reward(*definition) for definition in _POWER_DEFINITIONS
]
SUPERWEAPON_UNLOCK_REWARDS = [
    reward for reward in _PLAYER_POWER_REWARDS
    if reward['power_category'] == 'offensive'
]
SECONDARY_SUPERWEAPON_UNLOCK_REWARDS = [
    reward for reward in _PLAYER_POWER_REWARDS
    if reward['power_category'] == 'secondary'
]
AID_POWER_UNLOCK_REWARDS = [
    reward for reward in _PLAYER_POWER_REWARDS
    if reward['power_category'] == 'aid'
]
POWER_BUFF_REWARDS = build_power_buff_rewards(_PLAYER_POWER_REWARDS)
GLOBAL_BUFF_REWARDS = [{
    'name': 'Starting Credits +1,000',
    'description': (
        'Adds 1,000 credits at the start of every future launched mission, '
        'up to a 20,000-credit bonus.'
    ),
    'rules': {},
    'factions': [],
    'kind': 'buff',
    'buff_type': 'starting_credits',
    'global_buff': True,
    'credits_per_stack': 1000,
    'maximum_credits': 20000,
}]
ENEMY_REWARD_POOL = build_enemy_reward_pool(_PLAYER_POWER_REWARDS)
BUFF_TYPES = (
    {
        'id': 'production',
        'name': 'Drill',
        'setting_label': 'Production / construction time',
        'description': '{plural} have 15% shorter build/train times in future launched missions.',
    },
    {
        'id': 'cost',
        'name': 'Logistics',
        'setting_label': 'Cost reduction',
        'description': '{plural} cost 20% less in future launched missions.',
    },
    {
        'id': 'speed',
        'name': 'Mobility',
        'setting_label': 'Movement speed',
        'description': '{plural} move faster in future launched missions.',
    },
    {
        'id': 'armor',
        'name': 'Armor Plating',
        'setting_label': 'Armor',
        'description': '{plural} take less incoming damage in future launched missions.',
    },
    {
        'id': 'health',
        'name': 'Reinforced Frames',
        'setting_label': 'Health',
        'description': '{plural} gain more health in future launched missions.',
        'requires_stat': 'strength',
    },
    {
        'id': 'sight',
        'name': 'Recon Package',
        'setting_label': 'Vision',
        'description': '{plural} gain more vision in future launched missions.',
        'requires_stat': 'sight',
    },
    {
        'id': 'damage',
        'name': 'Firepower',
        'setting_label': 'Damage',
        'description': '{plural} deal more weapon damage in future launched missions.',
        'requires_weapons': True,
        'requires_weapon_stat': 'damage',
        'requires_clone': True,
    },
    {
        'id': 'reload',
        'name': 'Weapon Tuning',
        'setting_label': 'Unit fire rate',
        'description': '{plural} fire their weapons faster in future launched missions.',
        'requires_weapons': True,
        'requires_weapon_stat': 'rof',
        'requires_weapon_min': 1,
        'requires_clone': True,
    },
    {
        'id': 'range',
        'name': 'Optics',
        'setting_label': 'Attack range',
        'description': '{plural} gain more weapon range in future launched missions.',
        'requires_weapons': True,
        'requires_weapon_stat': 'range',
        'requires_clone': True,
    },
    {
        'id': 'ammo',
        'name': 'Ammo Reserves',
        'setting_label': 'Ammo',
        'description': '{plural} gain +1 ammo capacity per stack in future launched missions.',
        'requires_stat': 'ammo',
        'requires_clone': True,
    },
    {
        'id': 'passenger_capacity',
        'name': 'Expanded Transport',
        'setting_label': 'Passenger capacity +1',
        'description': '{plural} gain +1 passenger capacity per stack in future launched missions.',
        'requires_stat': 'passengers',
        'requires_clone': True,
    },
    {
        'id': 'cloak',
        'name': 'Stealth Systems',
        'setting_label': 'Cloaking',
        'description': '{plural} gain cloaking in future launched missions.',
        'requires_clone': True,
    },
    {
        'id': 'sensors',
        'name': 'Sensor Suite',
        'setting_label': 'Sensors',
        'description': '{plural} gain sensors in future launched missions.',
        'requires_clone': True,
    },
    {
        'id': 'veteran',
        'name': 'Veteran Training',
        'setting_label': 'Veteran start',
        'description': '{plural} start as veterans for the player house in future launched missions.',
    },
)
SPECIAL_BUILDING_DEFINITIONS = ()
SPECIAL_REWARD_UNIT_IDS = frozenset()
UNIT_SIDEBAR_IMAGES = {
    # Reloaded's TS Jumpjet Infantry art points at projectile art, so its
    # actual sidebar asset cannot be inferred from Image/Cameo keys.
    'TSJUMPJET': {'source_pcx': 'JJETICON.PCX'},
}
STANDALONE_WEAPON_TEMPLATES = {}
STANDALONE_UNIT_RULE_TEMPLATES = {}
LINKED_ACCESS_VARIANTS = {}
LINKED_BUFF_VARIANTS = {}
LIMITED_HERO_BUILD_LIMITS = {}
LIMITED_HERO_UNIT_IDS = frozenset()
EXISTING_OPEN_TOPPED_IDS = frozenset()
TRANSPORT_GUNNER_IDS = frozenset()
TRANSPORT_OPEN_TOPPED_BLOCKED_IDS = frozenset()
SUICIDE_RANGE_EXCLUDED_UNIT_IDS = frozenset()
MANDATORY_EXCLUDED_BUFF_TYPE_IDS = {}
_UNIT_POLICY_CONFIG = {'ammo_display_labels': {}}


def build_buff_rewards():
    rewards = []
    for unit_id, target in BUFF_TARGETS.items():
        allowed_types = set(target.get('allowed_buff_types') or ())
        for buff_type in BUFF_TYPES:
            buff_type_id = buff_type['id']
            if buff_type_id not in allowed_types:
                continue
            if buff_type_id == 'veteran' and not target.get('trainable', True):
                continue
            if (
                buff_type_id == 'speed'
                and movement_speed_ceiling(target) is not None
                and int(target.get('speed', 0)) >= movement_speed_ceiling(target)
            ):
                continue
            required_stat = buff_type.get('requires_stat')
            if required_stat and required_stat not in target:
                continue
            if buff_type.get('requires_weapons') and not target.get('weapons'):
                continue
            required_weapon_stat = buff_type.get('requires_weapon_stat')
            if required_weapon_stat and not any(
                stats.get(required_weapon_stat, 0)
                > buff_type.get('requires_weapon_min', 0)
                for stats in target.get('weapons', {}).values()
            ):
                continue
            rewards.append({
                'name': f'{target["label"]} {buff_type["name"]} I',
                'description': buff_type['description'].format(
                    plural=target['plural']
                ),
                'rules': {},
                'factions': list(target['factions']),
                'kind': 'buff',
                'unit': unit_id,
                'buff_type': buff_type_id,
                'global_buff': False,
                'special_reward': False,
            })
    return rewards


RETIRED_REWARD_BY_NAME = {
    name: {
        'name': f'{name} (retired: requires Firestorm Generator)',
        'description': (
            'Disabled because Firestorm Defense only controls an existing '
            'Firestorm Generator network and has no standalone effect.'
        ),
        'rules': {},
        'factions': ['GDI'],
        'kind': 'retired',
        'retired_reward': True,
    }
    for name in (
        'Firestorm Defense Power',
        'Firestorm Defense Power Accelerated Recharge I',
    )
}
REWARD_ALIASES = {}


def linked_buff_variant_ids(unit_id):
    unit_id = str(unit_id or '').upper()
    return frozenset((unit_id,)) if unit_id else frozenset()


def unit_role_equivalents(unit_id):
    unit_id = str(unit_id or '').upper()
    return frozenset((unit_id,)) if unit_id else frozenset()


def unit_display_label(unit_id):
    target = BUFF_TARGETS.get(str(unit_id or '').upper(), {})
    return target.get('label', str(unit_id or 'Unknown unit'))


MOVEMENT_SPEED_SAFE_CEILINGS = {
    str(category): int(value)
    for category, value in BUFF_EFFECTS['movement_speed']['safe_ceilings'].items()
}


def movement_speed_ceiling(target):
    category = target.get('category') if isinstance(target, dict) else target
    return MOVEMENT_SPEED_SAFE_CEILINGS.get(str(category or ''))


def capped_movement_speed(target, count):
    base_speed = max(1, int(round(float(target.get('speed', 1)))))
    ceiling = movement_speed_ceiling(target)
    if ceiling is None:
        return base_speed
    factor = float(BUFF_EFFECTS['speed']['factor_per_stack'])
    return min(
        max(base_speed, ceiling),
        max(
            base_speed,
            base_speed + max(0, int(count)),
            int(round(base_speed * factor ** max(0, int(count)))),
        ),
    )


UNIT_BUFF_REWARDS = build_buff_rewards()

REWARD_POOL = (
    UNIT_UNLOCK_REWARDS
    + DEFENSE_UNLOCK_REWARDS
    + SUPERWEAPON_UNLOCK_REWARDS
    + SECONDARY_SUPERWEAPON_UNLOCK_REWARDS
    + AID_POWER_UNLOCK_REWARDS
    + GLOBAL_BUFF_REWARDS
    + UNIT_BUFF_REWARDS
    + POWER_BUFF_REWARDS
    + ENEMY_REWARD_POOL
)
REWARD_BY_NAME = {reward['name']: reward for reward in REWARD_POOL}
REWARD_BY_BUFF_KEY = {
    (reward['unit'], reward['buff_type']): reward
    for reward in UNIT_BUFF_REWARDS
}
