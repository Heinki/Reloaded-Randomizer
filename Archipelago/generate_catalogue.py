"""Refresh the APWorld catalogue from game data or reviewed release metadata."""

import json
from pathlib import Path

from Archipelago.catalogue_contract import (
    build_snapshot,
    catalogue_sources_available,
    snapshot_checksum_is_valid,
)
from randomizer.core.version import APP_VERSION, APWORLD_VERSION


OUTPUT_PATH = (
    Path(__file__).resolve().parent
    / 'APWorld'
    / 'cnc_reloaded'
    / 'catalogue.json'
)


def main():
    existing = None
    if OUTPUT_PATH.is_file():
        existing = json.loads(OUTPUT_PATH.read_text(encoding='utf-8'))
    if catalogue_sources_available():
        snapshot = build_snapshot(existing)
    else:
        if not snapshot_checksum_is_valid(existing):
            raise ValueError(
                'Cannot prepare the APWorld catalogue without game assets: '
                'the checked-in reviewed snapshot is missing or has an '
                'invalid content checksum.'
            )
        # Release labels are excluded from the content checksum. Clean CI
        # can update them without changing reviewed content or assigned IDs.
        snapshot = dict(existing)
        snapshot.update(
            randomizer_version=APP_VERSION,
            world_version=APWORLD_VERSION,
        )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
        newline='\n',
    )
    print(
        f'{OUTPUT_PATH}: {len(snapshot["missions"])} missions, '
        f'{len(snapshot["items"])} approved items, '
        f'{len(snapshot["locations"])} reserved locations, '
        f'{snapshot["catalogue_checksum"]}'
    )


if __name__ == '__main__':
    main()
