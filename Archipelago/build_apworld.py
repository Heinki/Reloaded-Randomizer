"""Build the deterministic C&C Reloaded APWorld on any desktop platform."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ARCHIPELAGO_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ARCHIPELAGO_DIR.parent
MODULE_NAME = 'cnc_reloaded'
SOURCE_DIR = ARCHIPELAGO_DIR / 'APWorld' / MODULE_NAME
FIXED_TIMESTAMP = (2000, 1, 1, 0, 0, 0)


def archive_info(name: str) -> ZipInfo:
    info = ZipInfo(name, FIXED_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def build(
    output_directory: Path,
    *,
    allow_incomplete_catalogue: bool = False,
) -> Path:
    sys.path.insert(0, str(PROJECT_ROOT))
    from Archipelago.audit import archipelago_foundation_report
    from Archipelago.catalogue_contract import catalogue_sources_available
    from Archipelago.generate_catalogue import main as generate_catalogue
    from randomizer.core.version import APP_VERSION

    manifest_path = SOURCE_DIR / 'archipelago.json'
    catalogue_path = SOURCE_DIR / 'catalogue.json'
    if not manifest_path.is_file():
        raise FileNotFoundError(f'APWorld manifest not found: {manifest_path}')

    verify_live_sources = catalogue_sources_available()
    if verify_live_sources:
        generate_catalogue()
    report = archipelago_foundation_report(
        verify_live_sources=verify_live_sources,
    )
    if not report['valid']:
        raise RuntimeError('C&C Reloaded APWorld source validation failed.')
    if not report['review_complete'] and not allow_incomplete_catalogue:
        raise RuntimeError(
            'APWorld catalogue is review-gated. Use '
            '--allow-incomplete-catalogue only for structural developer builds.'
        )

    catalogue = json.loads(catalogue_path.read_text(encoding='utf-8'))
    if catalogue.get('randomizer_version') != APP_VERSION:
        raise RuntimeError(
            'APWorld launcher compatibility does not match: '
            f'launcher={APP_VERSION}, '
            f'APWorld={catalogue.get("randomizer_version")}.'
        )

    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / f'{MODULE_NAME}.apworld'

    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest.update({
        # Format 8 output only uses container features readable since format 7.
        'compatible_version': 7,
        'version': 8,
    })
    manifest_data = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(',', ':'),
    ).encode('utf-8')

    files = sorted(
        path for path in SOURCE_DIR.rglob('*')
        if path.is_file()
        and path != manifest_path
        and path.suffix != '.pyc'
        and '__pycache__' not in path.parts
    )
    with ZipFile(output_path, 'w') as archive:
        for source in files:
            relative = source.relative_to(SOURCE_DIR).as_posix()
            archive.writestr(
                archive_info(f'{MODULE_NAME}/{relative}'),
                source.read_bytes(),
            )
        archive.writestr(
            archive_info(f'{MODULE_NAME}/archipelago.json'),
            manifest_data,
        )

    print(output_path)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--output-directory',
        type=Path,
        default=ARCHIPELAGO_DIR,
    )
    parser.add_argument('--allow-incomplete-catalogue', action='store_true')
    arguments = parser.parse_args()
    build(
        arguments.output_directory,
        allow_incomplete_catalogue=arguments.allow_incomplete_catalogue,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
