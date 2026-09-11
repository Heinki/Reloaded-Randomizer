<p align="center">
  <img src="Assets/cncr-logo_puzzle.png" alt="C&amp;C Reloaded" width="375">
</p>

<p align="center">
  <img src="Assets/ra2-logo_puzzle.png" alt="Command &amp; Conquer: Red Alert 2" height="70">
  <img src="Assets/ra2yrlogo_puzzle.png" alt="Command &amp; Conquer: Yuri's Revenge" height="70">
  <img src="Assets/tslogo_puzzle.png" alt="Command &amp; Conquer: Tiberian Sun" height="70">
  <img src="Assets/tsFire_puzzle.png" alt="Command &amp; Conquer: Tiberian Sun – Firestorm" height="70">
</p>

<p align="center">
  <sub>Campaigns from Red Alert 2, Yuri's Revenge, Tiberian Sun, and Firestorm.</sub>
</p>

# C&C Reloaded Randomizer Launcher

[![Security checks](https://github.com/Heinki/Reloaded-Randomizer/actions/workflows/security.yml/badge.svg)](https://github.com/Heinki/Reloaded-Randomizer/actions/workflows/security.yml)

A Windows campaign randomizer for C&C Reloaded 2.7.0 with standalone and
Archipelago 0.6.7 play. It creates deterministic mission and reward plans,
launches generated copies of campaign maps, tracks objectives and victories,
and applies earned unit access, buffs, powers, and enemy rewards.

The active factions are Allies, Soviets, Yuri, GDI, and Nod. CABAL is not yet
supported.

## Disclaimer

This is an unofficial fan project. Its maintainer is not part of the C&C
Reloaded development team and did not contribute to C&C Reloaded. Credit for
the mod and its game content belongs to the C&C Reloaded developers and the
original Command & Conquer developers and publishers.

## Quick start

1. Make a separate, clean C&C Reloaded 2.7.0 installation. Do not use a copy
   containing map packs, rule edits, or other gameplay modifications.
2. Start that installation normally once and confirm that an original campaign
   mission launches.
3. Put `CnCReloadedRandomizer.exe` in the game folder beside
   `CnCReloadedClient.exe`, `Syringe.exe`, and `gamemd.exe`.
4. Run `CnCReloadedRandomizer.exe`.
5. Choose settings and select **Generate New Seed**.
6. Select an available mission and launch it through the Randomizer.
7. Complete objectives and win missions to earn rewards and progression.

For multiworld play, also download the matching `cnc_reloaded.apworld` and
follow the [C&C Reloaded Archipelago guide](Archipelago/README.md). Never mix a
launcher, APWorld, or Player YAML from different releases.

## Supported campaigns and modes

The launcher reads 108 missions from the installed `INI/Battle.ini`:

- Allies and Soviets in Red Alert 2
- Allies and Soviets in Yuri's Revenge
- GDI and Nod in Tiberian Sun
- GDI and Nod in Firestorm
- Yuri in Resurgence

Progression supports Classic, Mission List, Grid Mode, and Shop Mode. Reward
modes include Standard, Chaos, and Randomizer Arsenal. Advanced controls cover
unit access, buffs, powers, starting unlocks, enemy rewards, and mission
assistance.

Shop Mode uses all 108 reviewed Reloaded missions and its complete approved
catalogue: 166 unit access rewards, 1,885 unit buffs, 18 powers, and 44 power
buffs. Temporary mission cards can add one of 12 Reloaded player boons or 7
Reloaded AI challenges; active power boons are not offered twice.

Permanent Shop progression spends Gems on unit access, unit buffs, all 18
reviewed superweapons and support powers, plus their 44 power buffs. Purchased
permanent powers activate automatically in future Shop runs; unit buffs follow
selected starting-loadout access.

The first two Shop missions offer Standard choices, including a fixed-unit or
hero mission when available. From mission 3 onward, every remaining eligible
mission has equal selection probability, regardless of class or run length.
All three choices can be finales. Completed missions cannot repeat, and the
configured mission pool still applies.

Each Shop mission card shows a deterministic per-offer game difficulty. Early
stages favor Casual, middle stages favor Normal, and late stages can select
Hard. Mission Difficulty Assist lowers only its chosen offer by one step while
preserving the reward. Expanding the launcher log exposes a developer-only
offer picker for recovery and test completion through normal Shop transitions.

The Reloaded APWorld contains 2,161 items, 108 missions, and reserved locations
for objectives, victories, and Shop Mode. Each Shop seed has 120 shuffled item
locations. Mission victories release up to 12 unchecked locations across failed
and restarted runs. Completing the run releases every remaining location before
reporting the goal.

## Installation safety

Only original C&C Reloaded campaign maps are supported. Custom maps and other
gameplay modifications can redefine houses, units, weapons, triggers, and
mission scripts in ways the Randomizer has not audited.

The launcher never overwrites files under `Maps/Missions` or modifies the
game's MIX archives. It creates marker-owned `RLR_*.MAP` copies in the game
folder and verifies original map hashes before and after play. Persistent
settings, saves, logs, and caches are stored in `ReloadedRandomizerData`.

Map-authored units, TaskForces, triggers, events, and actions keep their native
identities. Player production uses isolated Randomizer clones where necessary
to avoid changing enemy or scripted units that share the original type.

## AI-assisted development

This project was developed with assistance from OpenAI's ChatGPT and Codex.
AI tools have supported source analysis, implementation, refactoring,
debugging, and documentation. Generated work is reviewed and validated against
project requirements; final design and release decisions remain the
maintainer's responsibility.

## Documentation

Each maintained document has one purpose:

| Document                                                                       | Audience               | Content                                                                              |
| ------------------------------------------------------------------------------ | ---------------------- | ------------------------------------------------------------------------------------ |
| [Archipelago/README.md](Archipelago/README.md)                                 | Players and room hosts | APWorld installation, Player YAML export, room connection, play, and troubleshooting |
| [configs/README.md](configs/README.md)                                         | Maintainers            | Static mission, faction, reward, unit, Shop, and UI configuration                    |
| [configs/player/README.md](configs/player/README.md)                           | Developers             | Source-mode player configuration location and privacy rules                          |
| [Archipelago APWorld setup](Archipelago/APWorld/cnc_reloaded/docs/setup_en.md) | Archipelago clients    | Short package metadata and compatibility guide embedded in the APWorld               |

## Developer workflow

Run from source with Python 3.14.6 from the fixed `Reloaded-Randomizer`
directory:

```powershell
python -m pip install -r requirements-build.txt
python launcher_gui.py
```

On Linux, create a virtual environment, install the runtime dependency, and
launch the same entry point. The launcher starts C&C Reloaded through Wine, so
both `wine` and `winepath` must be available on `PATH`.

```bash
cd Reloaded-Randomizer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-runtime.txt
python launcher_gui.py
```

Validate changes from the `Reloaded-Randomizer` directory:

```powershell
python -m compileall -q randomizer Archipelago launcher_gui.py
python -c "from randomizer.config.static import REQUIRED_STATIC_CONFIGS, validate_static_configs; validate_static_configs(REQUIRED_STATIC_CONFIGS)"
python -m randomizer.audit
python -m Archipelago.audit
python tools\all_mission_generation_smoke.py
```

Build the launcher and matching APWorld on Windows:

```powershell
.\build_exe.ps1
```

The build script automatically selects an installed Python 3.14.6 even when
`python` on `PATH` points to an older version. Use `-PythonExecutable` with a
full path to override discovery.

On Linux, Wine and the pinned Windows Python 3.14.6 runtime at
`C:\Python3146` can build both normal release artifacts:

```bash
cd Reloaded-Randomizer
./build_all_linux.sh
```

Set `WINE_PYTHON` if Windows Python is installed elsewhere. The individual
commands are `./build_exe_wine.sh` and
`python3 Archipelago/build_apworld.py`. They still produce the Windows
`CnCReloadedRandomizer.exe`; there is no separate Linux executable format.
The combined build also refreshes the tracked APWorld and publishes a copy in
the game folder beside the EXE.

The build publishes `CnCReloadedRandomizer.exe` and
`cnc_reloaded.apworld` beside the repository in the game folder. PyInstaller
extracts the one-file runtime into the Windows temporary directory; a build or
runtime extraction directory is not part of the project.

## Source layout

| Path                      | Responsibility                                                            |
| ------------------------- | ------------------------------------------------------------------------- |
| `launcher_gui.py`         | Source and packaged entry point                                           |
| `randomizer/application/` | Application state, seed, progression, launch, and Archipelago controllers |
| `randomizer/config/`      | Static and player configuration loading and validation                    |
| `randomizer/core/`        | Paths, storage, diagnostics, and version primitives                       |
| `randomizer/maps/`        | Generated-map pipeline, ownership, clones, buffs, hooks, and settings     |
| `randomizer/missions/`    | Mission catalogue, policy, safety, and review evidence                    |
| `randomizer/progression/` | Mission List and Grid progression                                         |
| `randomizer/rewards/`     | Reward definitions, planning, and display                                 |
| `randomizer/shop/`        | Standalone and Archipelago Shop Mode                                      |
| `randomizer/ui/`          | Tk user interface                                                         |
| `Archipelago/`            | APWorld, embedded client, manifest, and YAML integration                  |
| `configs/`                | Reloaded-owned static JSON policy and ignored local player data           |
| `tools/`                  | Maintainer audits, data generation, and Windows packaging driver          |
| `build_exe_wine.sh`       | Windows PyInstaller build through Wine on Linux                           |
| `build_all_linux.sh`      | Combined Linux-side launcher and APWorld release build                    |

## Troubleshooting

Run this check first:

```powershell
.\CnCReloadedRandomizer.exe --self-check
```

The packaged report is written to
`ReloadedRandomizerData\self_check.json`. Launcher diagnostics are stored in
`ReloadedRandomizerData\logs\launcher.log`; objective and victory marker
activity comes from `debug\debug.log`.

When reporting a problem, include those diagnostics, the mission code, seed,
reward and progression modes, and whether the issue also occurs in a fresh,
unmodified C&C Reloaded installation. Review `randomizer_state.json` before
sharing it because it contains seed and progress data.
