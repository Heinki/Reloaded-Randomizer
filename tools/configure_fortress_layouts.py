"""Compile compact, faction-specific Fortress layouts from installed terrain.

Writes production configuration only after all layouts have been placed. Native
terrain, resources and scenery remain unchanged. Every defense rank surrounds
the same base; no search can silently spill grants into distant map regions.
"""

import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from randomizer.core.paths import GAME_ROOT
from randomizer.core.storage import atomic_write_json
from randomizer.final_fortress.catalogue import SIDE_COUNTRIES, SIDE_FAMILIES
from randomizer.final_fortress.config import validate_config
from randomizer.final_fortress.native import installed_rules_registry
from randomizer.final_fortress.perks import ranks, resolve_effects
from randomizer.final_fortress.placement import deployment_cells, foundation, installed_art
from randomizer.final_fortress.terrain import Terrain
from randomizer.maps.ini import all_section_value_maps_preserve


def point(cell):
    return dict(zip(('x', 'y'), cell))


def expanded(cells, margin):
    return {(x + dx, y + dy) for x, y in cells
            for dx in range(-margin, margin + 1) for dy in range(-margin, margin + 1)}


class Layout:
    def __init__(self, terrain, rules, art, center, *, reserved=()):
        self.terrain, self.rules, self.art = terrain, rules, art
        self.center = center
        self.occupied = set(reserved) | deployment_cells(*center)
        x, y = center
        self.candidates = [(x + dx, y + dy) for dx in range(-23, 24)
                           for dy in range(-23, 24) if dx * dx + dy * dy <= 23 * 23]

    def shape(self, kind):
        row = self.rules[kind]
        return foundation({**row, 'Image': row.get('Image', kind)}, self.art)

    def place(self, shape, *, radius, angle=None, target=None, margin=1, minimum=0,
              clearance=0):
        ox = sum(x for x, _ in shape) / len(shape)
        oy = sum(y for _, y in shape) / len(shape)
        cx, cy = self.center

        def score(p):
            x, y = p[0] + ox - cx, p[1] + oy - cy
            distance = math.hypot(x, y)
            if angle is not None:
                error = abs(math.atan2(math.sin(math.atan2(y, x) - angle),
                                      math.cos(math.atan2(y, x) - angle)))
                return error * 60 + abs(distance - target) * 3, distance, p
            return distance, p

        for p in sorted(self.candidates, key=score):
            x, y = p[0] + ox - cx, p[1] + oy - cy
            distance = math.hypot(x, y)
            if not minimum <= distance <= radius:
                continue
            if angle is not None:
                error = abs(math.atan2(math.sin(math.atan2(y, x) - angle),
                                      math.cos(math.atan2(y, x) - angle)))
                if error > math.pi / 8:
                    continue
            cells = {(p[0] + dx, p[1] + dy) for dx, dy in shape}
            if cells & self.occupied or not self.terrain.clear(cells):
                continue
            if clearance and (not self.terrain.clear(expanded(cells, clearance))
                              or self.terrain.heights[p] != self.terrain.heights[self.center]):
                continue
            self.occupied.update(expanded(cells, margin))
            return point(p)
        raise ValueError(f'No compact placement beside {self.center}; radius={radius}, angle={angle}')

    def ring(self, kinds, *, first_radius, maximum):
        positions = [None] * len(kinds)
        for i in sorted(range(len(kinds)), key=lambda i: -len(self.shape(kinds[i]))):
            positions[i] = self.place(self.shape(kinds[i]), radius=maximum, minimum=first_radius - 6,
                angle=(i % 8) * math.pi / 4 + (i // 8) * math.pi / 32,
                target=first_radius + (i // 8) * 1.5, margin=1)
        return positions


def main():
    path = Path(__file__).resolve().parents[1] / 'configs/final_fortress.json'
    document = json.loads(path.read_text())
    config = document['sections']
    definition = config['map']
    definition['compact_layouts'] = True
    _, rules = installed_rules_registry()
    art = installed_art()
    source = all_section_value_maps_preserve((GAME_ROOT / definition['source']).read_text(
        encoding='latin-1').splitlines())
    terrain = Terrain(source, rules, art)
    # The authored northern start has cliffs in its north-west quadrant. A
    # four-cell shift puts the deployment square in the adjacent open patch,
    # giving all eight perimeter sectors buildable ground without landscaping.
    definition['start_positions']['0'] = {'x': 126, 'y': 124}
    northern = Layout(terrain, rules, art, (126, 124))
    lab = definition['protected_building']
    lab['position'] = northern.place(northern.shape(lab['type']), radius=10, minimum=5)
    definition['wave_clock_position'] = {'x': 121, 'y': 124}
    selected = [perk['id'] for perk in config['perks']]
    purchased = {perk['id']: len(ranks(perk)) for perk in config['perks']}
    for waypoint, layout in definition['perk_layouts'].items():
        layout.setdefault('faction_layouts', {})
        center = definition['start_positions'][waypoint]
        center = center['x'], center['y']
        for country, family in zip(SIDE_COUNTRIES, SIDE_FAMILIES):
            effects = resolve_effects(config, selected, purchased, country,
                include_power=True, include_power_upgrades=True, include_arsenal=True,
                include_utilities=True, include_lab_support=True, include_lab_shield=True,
                include_lab_health=True, include_lab_veterancy=True,
                include_generator_power=True, include_economy=True, share_starting_power=True)
            reserved = set()
            if int(waypoint) == definition['player_waypoint']:
                lab = definition['protected_building']
                row = rules[lab['type']]
                reserved = expanded({(lab['position']['x'] + dx, lab['position']['y'] + dy)
                    for dx, dy in foundation({**row, 'Image': row.get('Image', lab['type'])}, art)}, 1)
            compiler = Layout(terrain, rules, art, center, reserved=reserved)
            defenses = compiler.ring(effects['defense_types'], first_radius=14, maximum=20)
            # Place the largest production footprints before small generators.
            buildings = [None] * 5
            order = sorted(range(5), key=lambda i: -len(compiler.shape(effects['starting_buildings'][i])))
            for i in order:
                if int(rules[effects['starting_buildings'][i]].get('Power', '0')) > 0:
                    continue
                buildings[i] = compiler.place(compiler.shape(effects['starting_buildings'][i]), radius=13)
            army = compiler.place({(x, y) for x in range(5) for y in range(3)}, radius=13, margin=2)
            # Reserve the complete arrival buffer before any generator,
            # including the starting generator in building slot zero.
            for i in order:
                if buildings[i] is None:
                    buildings[i] = compiler.place(compiler.shape(effects['starting_buildings'][i]), radius=15, margin=0)
            powers = [compiler.place(compiler.shape(kind), radius=15, margin=0)
                      for kind in effects['starting_power_buildings']]
            layout['faction_layouts'][family] = {
                'generator': buildings[0], 'buildings': buildings,
                'power': powers, 'defenses': defenses, 'units': army,
            }
            print(f'Friendly {waypoint} {family}: compact core and {len(defenses)} ring defenses')
        # Keep the legacy fallback coherent for older readers of the document.
        fallback = layout['faction_layouts']['allies']
        for field in ('buildings', 'power', 'defenses', 'units'):
            layout[field] = fallback[field]
    defense = definition['enemy_defenses']
    defense['layouts_by_country'] = {}
    for waypoint in definition['enemy_waypoints']:
        center = definition['start_positions'][str(waypoint)]
        compiler = Layout(terrain, rules, art, (center['x'], center['y']))
        definition['enemy_wave_positions'][str(waypoint)] = compiler.place(
            {(x, y) for x in range(5) for y in range(3)}, radius=13, margin=2, clearance=1)
    for country in SIDE_COUNTRIES:
        defense['layouts_by_country'][country] = {}
        for waypoint in definition['enemy_waypoints']:
            center = definition['start_positions'][str(waypoint)]
            arrival = definition['enemy_wave_positions'][str(waypoint)]
            reserved = {(arrival['x'] + dx, arrival['y'] + dy)
                        for dx in range(-2, 7) for dy in range(-2, 5)}
            compiler = Layout(terrain, rules, art, (center['x'], center['y']), reserved=reserved)
            kinds = defense['types_by_country'][country] * 8
            positions = compiler.ring(kinds, first_radius=10, maximum=16)
            defense['layouts_by_country'][country][str(waypoint)] = positions
            print(f'Enemy {waypoint} {country}: 24 ring defenses')
    defense['layouts'] = defense['layouts_by_country']['AlliesCountry']
    validate_config(config)
    atomic_write_json(path, document)
    print('Updated production Fortress layouts; original map unchanged.')


if __name__ == '__main__':
    main()
