"""Read native snow terrain and reject unsafe generated-object placements."""

import base64
import struct
from .ground import _decode_lzo, CELL
from .placement import PlayableBounds, foundation


def _lcw(data):
    output = bytearray()
    cursor = 0
    relative = data[:1] == b'\0'
    if relative:
        cursor = 1
    while cursor < len(data):
        command = data[cursor]
        cursor += 1
        if not command & 0x80:
            count = (command >> 4) + 3
            offset = ((command & 15) << 8) | data[cursor]
            cursor += 1
            position = len(output) - offset
        elif not command & 0x40:
            count = command & 63
            if not count:
                break
            output.extend(data[cursor:cursor + count])
            cursor += count
            continue
        elif command == 0xFE:
            count = struct.unpack_from('<H', data, cursor)[0]
            output.extend(bytes([data[cursor + 2]]) * count)
            cursor += 3
            continue
        else:
            count = (command & 63) + 3
            if command == 0xFF:
                count = struct.unpack_from('<H', data, cursor)[0]
                cursor += 2
            offset = struct.unpack_from('<H', data, cursor)[0]
            cursor += 2
            position = len(output) - offset if relative else offset
        for index in range(count):
            output.append(output[position + index])
    return output



def unpack(section, *, lzo=False):
    packed = base64.b64decode(''.join(section.values()), validate=True)
    output = bytearray()
    cursor = 0
    while cursor < len(packed):
        size, length = struct.unpack_from('<HH', packed, cursor)
        cursor += 4
        if not size or size > len(packed) - cursor or not 0 < length <= 8192:
            raise ValueError('Invalid packed Fortress terrain header.')
        data = packed[cursor:cursor + size]
        cursor += size
        block = _decode_lzo(data, length) if lzo else _lcw(data)
        if len(block) != length:
            raise ValueError('Invalid packed Fortress terrain length.')
        output.extend(block)
    return output


class Terrain:
    def __init__(self, sections, rules=None, art=None):
        self.bounds = PlayableBounds(sections['Map'])
        raw = unpack(sections['IsoMapPack5'], lzo=True)
        self.cells = {(x, y): (tile, height) for x, y, tile, sub, height, extra in CELL.iter_unpack(raw)}
        self.heights = {cell: value[1] for cell, value in self.cells.items()}
        self.overlays = unpack(sections['OverlayPack'])
        self.objects = {(int(cell) % 1000, int(cell) // 1000) for cell in sections.get('Terrain', {})}
        for value in sections.get('Structures', {}).values():
            fields = value.split(',')
            kind = fields[1]
            x, y = map(int, fields[3:5])
            row = dict((rules or {}).get(kind, {}))
            row.setdefault('Image', kind)
            self.objects.update((x + dx, y + dy) for dx, dy in foundation(row, art or {}))

    def clear(self, cells):
        if not self.bounds.contains(cells, heights=self.heights):
            return False
        heights = set()
        for x, y in cells:
            tile, height = self.cells.get((x, y), (-1, -1))
            # SNOWMD flat LATs only. Slopes, cliffs, ice and water are excluded.
            if tile not in {0, 65535, *range(734, 765), *range(131, 148), *range(696, 730), *range(293, 314)}:
                return False
            if (x, y) in self.objects or self.overlays[y * 512 + x] != 255:
                return False
            heights.add(height)
        return len(heights) == 1
