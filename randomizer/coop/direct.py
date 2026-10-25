"""Shared validation for Reloaded's authenticated private lobby."""

import os
import re
import socket


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,14}', value):
        raise ValueError('Player name must be 1–14 letters, numbers, _ or -.')
    return value


def _port(value):
    if type(value) is not int or not 1024 <= value <= 65535:
        raise ValueError('Co-op port must be between 1024 and 65535.')
    return value


def _installation(root):
    return {'machine': socket.gethostname().casefold(),
            'path': os.path.normcase(str(root.resolve())).casefold()}


def _check_separate_install(local, remote):
    if local == remote:
        raise ValueError('Each co-op player needs a separate Reloaded installation.')
