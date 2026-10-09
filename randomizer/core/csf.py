"""Read and write Westwood string tables without changing installed labels."""

import struct


def read_csf(data):
    if len(data) < 24 or data[:4] != b' FSC':
        raise ValueError('Invalid CSF header')
    count = struct.unpack_from('<I', data, 8)[0]
    offset = 24
    labels = {}

    def take(size):
        nonlocal offset
        if size < 0 or size > len(data) - offset:
            raise ValueError('Truncated CSF record')
        result = data[offset:offset + size]
        offset += size
        return result

    def integer():
        return struct.unpack('<I', take(4))[0]

    for _ in range(count):
        if take(4) != b' LBL':
            raise ValueError('Invalid CSF label')
        strings, size = integer(), integer()
        label = take(size).decode('ascii').casefold()
        for index in range(strings):
            tag = take(4)
            if tag not in {b' RTS', b'WRTS'}:
                raise ValueError('Invalid CSF string')
            value = bytes(byte ^ 255 for byte in take(integer() * 2))
            if index == 0:
                labels[label] = value.decode('utf-16-le')
            if tag == b'WRTS':
                take(integer())
    return labels


def write_csf(labels):
    data = bytearray(b' FSC' + struct.pack('<5I', 3, len(labels), len(labels), 0, 0xFFFFFFFF))
    for label, value in sorted(labels.items()):
        name = label.encode('ascii')
        encoded = value.encode('utf-16-le')
        data.extend(b' LBL' + struct.pack('<2I', 1, len(name)) + name)
        data.extend(b' RTS' + struct.pack('<I', len(encoded) // 2))
        data.extend(byte ^ 255 for byte in encoded)
    return bytes(data)
