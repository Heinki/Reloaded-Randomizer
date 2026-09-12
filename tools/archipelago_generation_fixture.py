"""Write a settings-only Player YAML for Archipelago generation smoke tests."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from Archipelago.yaml_config import parse_player_yaml, serialize_player_yaml
from randomizer.config.player import DEFAULT_CONFIG


CATALOGUE_PATH = (
    PROJECT_ROOT
    / 'Archipelago'
    / 'APWorld'
    / 'cnc_reloaded'
    / 'catalogue.json'
)


def build_fixture_yaml() -> str:
    catalogue = json.loads(CATALOGUE_PATH.read_text(encoding='utf-8'))
    settings = deepcopy(DEFAULT_CONFIG)
    settings.update({
        'seed': 'LOCAL-SEED-MUST-NOT-LEAK',
        'campaign_filter': 'All Campaigns',
        'progression_mode': 'Mission List',
        'mission_goal': 108,
        'rewards_per_objective': int(
            catalogue['maximum_rewards_per_check']
        ),
    })
    text = serialize_player_yaml(settings, 'Compatibility Smoke')
    parsed = parse_player_yaml(text)
    if parsed['run_manifest'] is not None:
        raise RuntimeError('Player YAML unexpectedly contains generated run data.')
    if settings['seed'] in text:
        raise RuntimeError('Player YAML leaked the local launcher seed.')
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    text = build_fixture_yaml()
    arguments.output.write_text(text, encoding='utf-8', newline='\n')
    print(f'{arguments.output}: {len(text.encode("utf-8"))} bytes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
