"""Write a maximum-capacity Player YAML for Archipelago generation smoke tests."""

from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from Archipelago.yaml_config import parse_player_yaml, serialize_player_yaml


CATALOGUE_PATH = (
    PROJECT_ROOT
    / "Archipelago"
    / "APWorld"
    / "cnc_reloaded"
    / "catalogue.json"
)


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sign_manifest(manifest):
    signed = deepcopy(manifest)
    signed.pop("manifest_checksum", None)
    signed["manifest_checksum"] = sha256(
        _canonical_json(signed).encode("utf-8")
    ).hexdigest()
    return signed


def build_fixture_yaml() -> str:
    catalogue = json.loads(CATALOGUE_PATH.read_text(encoding="utf-8"))
    missions = catalogue["missions"]
    mission_order = [mission["code"] for mission in missions]
    repeatable_reward = next(
        item["name"] for item in catalogue["items"] if item["repeatable"]
    )
    locations = {
        mission["code"]: [
            (check["id"], int(check["maximum_slots"]))
            for check in mission["checks"]
        ]
        for mission in missions
    }
    location_count = sum(
        count for checks in locations.values() for _check_id, count in checks
    )
    seed = "RLR-AP-COMPATIBILITY-SMOKE"
    launcher_settings = {
        "campaign_filter": "All Campaigns",
        "progression_mode": "Mission List",
        "mission_goal": len(mission_order),
        "rewards_per_objective": 30,
    }
    manifest = _sign_manifest({
        "schema_version": 1,
        "randomizer_version": catalogue["randomizer_version"],
        "randomizer_seed": seed,
        "catalogue_checksum": catalogue["catalogue_checksum"],
        "campaign_filter": "All Campaigns",
        "progression_mode": "Mission List",
        "mission_goal": len(mission_order),
        "mission_order": mission_order,
        "progression": {
            "type": "victory_count",
            "starting_missions": mission_order[:3],
            "mission_requirements": {
                code: max(0, index - 2)
                for index, code in enumerate(mission_order)
            },
        },
        "grid": None,
        "goal": {"type": "all_missions"},
        "shop": None,
        "locations": {
            code: dict(checks) for code, checks in locations.items()
        },
        "item_pool": {repeatable_reward: location_count},
        "starting_items": {},
        "local_placements": [],
        "frozen_settings": {"launcher": {**launcher_settings, "seed": seed}},
        "state_snapshot": {
            "seed": seed,
            "campaign_filter": "All Campaigns",
            "progression_mode": "Mission List",
            "mission_order": mission_order,
            "mission_checks": {
                code: [{"id": check_id} for check_id, _count in checks]
                for code, checks in locations.items()
            },
        },
    })
    text = serialize_player_yaml(manifest, "Compatibility Smoke")
    parsed = parse_player_yaml(text)
    parsed_manifest = parsed["run_manifest"]
    if _sign_manifest(parsed_manifest) != parsed_manifest:
        raise RuntimeError("Player YAML round trip invalidated the run manifest.")
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
