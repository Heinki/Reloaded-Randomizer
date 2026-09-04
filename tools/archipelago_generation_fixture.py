"""Write a maximum-capacity Player YAML for Archipelago generation smoke tests."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from Archipelago.catalogue_contract import build_catalogue_projection
from Archipelago.run_manifest import build_run_manifest
from Archipelago.yaml_config import parse_player_yaml, serialize_player_yaml
from randomizer.rewards.catalogue import REWARD_POOL


def build_fixture_yaml() -> str:
    projection = build_catalogue_projection()
    missions = projection["missions"]
    mission_order = [mission["code"] for mission in missions]
    repeatable_reward = next(
        reward for reward in REWARD_POOL if reward.get("kind") == "buff"
    )
    mission_checks = {
        mission["code"]: [
            {
                "id": check["id"],
                "rewards": [repeatable_reward] * int(check["maximum_slots"]),
            }
            for check in mission["checks"]
        ]
        for mission in missions
    }
    state = {
        "seed": "RLR-AP-COMPATIBILITY-SMOKE",
        "campaign_filter": "All Campaigns",
        "progression_mode": "Mission List",
        "mission_goal": len(mission_order),
        "mission_order": mission_order,
        "mission_checks": mission_checks,
        "starting_unlocked_missions": 3,
        "reward_mode": "Standard",
        "rewards_per_check": 30,
        "rewards_on_victory_only": False,
        "use_act_based_reward_multipliers": True,
        "completed_missions": [],
        "started_missions": [],
    }
    manifest = build_run_manifest(state)
    text = serialize_player_yaml(manifest, "Compatibility Smoke")
    parsed = parse_player_yaml(text)
    if parsed["run_manifest"]["manifest_checksum"] != manifest["manifest_checksum"]:
        raise RuntimeError("Player YAML round trip changed the run manifest.")
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    text = build_fixture_yaml()
    arguments.output.write_text(text, encoding="utf-8", newline="\n")
    print(f"{arguments.output}: {len(text.encode('utf-8'))} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
