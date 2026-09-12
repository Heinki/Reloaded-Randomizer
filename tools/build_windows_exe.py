"""Build and verify the Windows launcher with Windows Python.

The driver mirrors ``build_exe.ps1`` and also runs through Wine, allowing a
Linux checkout to produce the normal Windows release executable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile


REQUIRED_PYTHON = '3.14.6'
REQUIRED_PYINSTALLER = '6.21.0'
REQUIRED_WEBSOCKETS = '17.0'
REQUIRED_CERTIFI = '2026.07.22'
PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXECUTABLE_NAME = 'CnCReloadedRandomizer.exe'


def require_path(path: Path, label: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f'{label} is missing: {path}')
    return path


def write_version_info(path: Path, app_version: str) -> None:
    parts = [int(value) for value in app_version.split('.')]
    parts.extend([0] * (4 - len(parts)))
    version_tuple = ', '.join(str(value) for value in parts[:4])
    path.write_text(
        f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({version_tuple}),
    prodvers=({version_tuple}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [
          StringStruct(u'CompanyName', u'C&C Reloaded Randomizer contributors'),
          StringStruct(u'FileDescription', u'C&C Reloaded Randomizer Launcher'),
          StringStruct(u'FileVersion', u'{app_version}'),
          StringStruct(u'InternalName', u'CnCReloadedRandomizer'),
          StringStruct(u'OriginalFilename', u'{EXECUTABLE_NAME}'),
          StringStruct(u'ProductName', u'C&C Reloaded Randomizer Launcher'),
          StringStruct(u'ProductVersion', u'{app_version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
""",
        encoding='utf-8',
    )


def write_config_manifest(config_dir: Path, path: Path) -> None:
    files = {}
    for source in sorted(config_dir.rglob('*')):
        if not source.is_file() or 'player' in source.relative_to(config_dir).parts:
            continue
        if source.suffix.lower() != '.json' and not (
            source.suffix.lower() == '.ini'
            and source.name.startswith('Randomizer')
        ):
            continue
        relative = source.relative_to(config_dir).as_posix()
        files[relative] = hashlib.sha256(source.read_bytes()).hexdigest()
    path.write_text(
        json.dumps({'format': 1, 'files': files}, indent=2),
        encoding='utf-8',
    )


def prepare_tcl_bundle(source: Path, destination: Path) -> None:
    shutil.copytree(source, destination)
    init_path = destination / 'init.tcl'
    original_path = destination / '_rlr_original_init.tcl'
    init_path.replace(original_path)
    init_path.write_text(
        '# C&C Reloaded Randomizer bundled Tcl bootstrap\n'
        'set ::tcl_library [file dirname [info script]]\n'
        'source [file join $::tcl_library _rlr_original_init.tcl]\n',
        encoding='utf-8',
    )


def run_checked(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    print('+', subprocess.list2cmdline(command), flush=True)
    return subprocess.run(command, check=True, **kwargs)


def add_bundle_argument(command: list[str], kind: str, source: Path, target: str) -> None:
    command.extend((kind, f'{source}{os.pathsep}{target}'))


def build(output: Path) -> None:
    if os.name != 'nt':
        raise RuntimeError(
            'A Windows Python runtime is required. On Linux use build_exe_wine.sh.'
        )
    if platform.python_version() != REQUIRED_PYTHON:
        raise RuntimeError(
            f'Python {REQUIRED_PYTHON} is required; '
            f'found {platform.python_version()}.'
        )

    import certifi
    import PyInstaller
    import websockets

    if PyInstaller.__version__ != REQUIRED_PYINSTALLER:
        raise RuntimeError(
            f'PyInstaller {REQUIRED_PYINSTALLER} is required; '
            f'found {PyInstaller.__version__}.'
        )
    if websockets.__version__ != REQUIRED_WEBSOCKETS:
        raise RuntimeError(
            f'websockets {REQUIRED_WEBSOCKETS} is required; '
            f'found {websockets.__version__}.'
        )
    if certifi.__version__ != REQUIRED_CERTIFI:
        raise RuntimeError(
            f'certifi {REQUIRED_CERTIFI} is required; '
            f'found {certifi.__version__}.'
        )

    sys.path.insert(0, str(PROJECT_ROOT))
    from Archipelago.build_apworld import build as build_apworld
    from randomizer.config.static import (
        REQUIRED_STATIC_CONFIGS,
        validate_static_configs,
    )
    from randomizer.core.version import APP_VERSION

    validate_static_configs(REQUIRED_STATIC_CONFIGS)
    build_apworld(PROJECT_ROOT / 'Archipelago')

    python_root = Path(sys.base_prefix)
    icon = require_path(
        PROJECT_ROOT / 'reloaded-randomizer.ico', 'Launcher icon'
    )
    configs = require_path(PROJECT_ROOT / 'configs', 'Static config directory')
    assets = require_path(PROJECT_ROOT / 'Assets', 'Asset directory')
    apworld_source = require_path(
        PROJECT_ROOT / 'Archipelago' / 'APWorld' / 'cnc_reloaded',
        'APWorld source directory',
    )
    runtime_hook = require_path(
        PROJECT_ROOT / 'tools' / 'pyinstaller_tk_runtime.py',
        'Tcl/Tk runtime hook',
    )
    tkinter_binary = require_path(
        python_root / 'DLLs' / '_tkinter.pyd', '_tkinter runtime'
    )
    tkinter_package = require_path(
        python_root / 'Lib' / 'tkinter', 'tkinter package'
    )
    tcl_binary = require_path(python_root / 'DLLs' / 'tcl86t.dll', 'Tcl DLL')
    tk_binary = require_path(python_root / 'DLLs' / 'tk86t.dll', 'Tk DLL')
    tcl_data = require_path(python_root / 'tcl' / 'tcl8.6', 'Tcl scripts')
    tk_data = require_path(python_root / 'tcl' / 'tk8.6', 'Tk scripts')

    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix='rlr-windows-build-') as temporary:
        staging = Path(temporary)
        version_info = staging / 'version.txt'
        manifest = staging / 'bundle_manifest.json'
        tcl_bundle = staging / '_tcl_data'
        dist = staging / 'dist'
        work = staging / 'work'
        spec = staging / 'spec'
        pyinstaller_config = staging / 'pyinstaller-config'
        write_version_info(version_info, APP_VERSION)
        write_config_manifest(configs, manifest)
        prepare_tcl_bundle(tcl_data, tcl_bundle)

        command = [
            sys.executable,
            '-m',
            'PyInstaller',
            '--noconfirm',
            '--clean',
            '--onefile',
            '--runtime-tmpdir',
            '.',
            '--noupx',
            '--optimize',
            '1',
            '--windowed',
            '--version-file',
            str(version_info),
        ]
        command.extend(('--icon', str(icon)))
        add_bundle_argument(command, '--add-data', icon, '.')

        for source, target in (
            (configs / '*.json', 'configs'),
            (configs / 'README.md', 'configs'),
            (configs / 'rewards', r'configs\rewards'),
            (apworld_source, r'Archipelago\APWorld\cnc_reloaded'),
            (manifest, 'configs'),
            (assets, 'Assets'),
        ):
            add_bundle_argument(command, '--add-data', source, target)
        for source, target in (
            (tkinter_binary, '.'),
            (tcl_binary, '.'),
            (tk_binary, '.'),
        ):
            add_bundle_argument(command, '--add-binary', source, target)
        for source, target in (
            (tkinter_package, 'tkinter'),
            (tcl_bundle, '_tcl_data'),
            (tk_data, '_tk_data'),
        ):
            add_bundle_argument(command, '--add-data', source, target)
        command.extend((
            '--runtime-hook',
            str(runtime_hook),
            '--exclude-module',
            'logging.handlers',
            '--exclude-module',
            'ftplib',
            '--exclude-module',
            'smtplib',
            '--hidden-import',
            'Archipelago.client',
            '--hidden-import',
            'Archipelago.run_manifest',
            '--hidden-import',
            'Archipelago.yaml_config',
            '--name',
            'CnCReloadedRandomizer',
            '--distpath',
            str(dist),
            '--workpath',
            str(work),
            '--specpath',
            str(spec),
            str(PROJECT_ROOT / 'launcher_gui.py'),
        ))
        environment = os.environ.copy()
        environment['PYINSTALLER_CONFIG_DIR'] = str(pyinstaller_config)
        run_checked(command, cwd=PROJECT_ROOT, env=environment)

        built = require_path(dist / EXECUTABLE_NAME, 'Built launcher')
        archive = run_checked(
            [
                sys.executable,
                '-m',
                'PyInstaller.utils.cliutils.archive_viewer',
                '-l',
                str(built),
            ],
            capture_output=True,
            text=True,
        ).stdout
        normalized_archive = archive.replace('\\', '/')
        while '//' in normalized_archive:
            normalized_archive = normalized_archive.replace('//', '/')
        required_entries = (
            "'reloaded-randomizer.ico'",
            "'_tkinter.pyd'",
            "'tcl86t.dll'",
            "'tk86t.dll'",
            "'_tcl_data/init.tcl'",
            "'_tk_data/tk.tcl'",
            "'certifi/cacert.pem'",
            "'Archipelago/APWorld/cnc_reloaded/catalogue.json'",
            "'Assets/archipelago.png'",
        )
        missing = [
            entry for entry in required_entries if entry not in normalized_archive
        ]
        if missing:
            raise RuntimeError(
                'Built launcher is missing required archive entries: '
                + ', '.join(missing)
            )
        shutil.copy2(built, output)

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f'Built Windows launcher v{APP_VERSION}: {output}')
    print(f'SHA256 {digest}')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--output',
        type=Path,
        default=PROJECT_ROOT.parent / EXECUTABLE_NAME,
    )
    arguments = parser.parse_args()
    build(arguments.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
