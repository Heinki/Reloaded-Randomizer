<p align="center">
  <img src="../Assets/cncr-logo_puzzle.png" alt="C&amp;C Reloaded" width="375">
</p>

<p align="center">
  <img src="../Assets/ra2-logo_puzzle.png" alt="Command &amp; Conquer: Red Alert 2" height="70">
  <img src="../Assets/ra2yrlogo_puzzle.png" alt="Command &amp; Conquer: Yuri's Revenge" height="70">
  <img src="../Assets/tslogo_puzzle.png" alt="Command &amp; Conquer: Tiberian Sun" height="70">
  <img src="../Assets/tsFire_puzzle.png" alt="Command &amp; Conquer: Tiberian Sun – Firestorm" height="70">
</p>

<p align="center">
  <sub>Campaigns from Red Alert 2, Yuri's Revenge, Tiberian Sun, and Firestorm.</sub>
</p>

# Playing C&C Reloaded with Archipelago

This guide explains how to install the C&C Reloaded Randomizer and APWorld,
create a Player YAML, connect to a room, play checks, and continue an existing
multiworld game.

## What you need

- C&C Reloaded 2.7.0 in a separate, unmodified game installation
- C&C Reloaded Randomizer Launcher 1.0
- Archipelago 0.6.7 or newer
- `cnc_reloaded.apworld` from the same Randomizer release as the launcher

Launcher, APWorld, and Player YAML catalogues must be compatible. Mental Omega
rooms, YAML files, saves, items, and locations are incompatible. CABAL is not
part of this world.

## Install the Randomizer

1. Put `CnCReloadedRandomizer.exe` in the C&C Reloaded game folder.
2. Confirm that it is beside `CnCReloadedClient.exe`, `Syringe.exe`, and
   `gamemd.exe`.
3. Start `CnCReloadedRandomizer.exe`.

Use a dedicated C&C Reloaded installation. Do not install the Randomizer over
a game folder containing unrelated map or rule modifications.

## Install the APWorld

1. Close all Archipelago programs.
2. Copy `cnc_reloaded.apworld` into Archipelago's `custom_worlds` folder.
3. Restart the Archipelago Launcher.

Every person who generates or hosts the room needs this APWorld installed.
Other players need it only when their local Archipelago setup processes custom
world data for room generation or hosting.

## Create your Player YAML

The Randomizer exports the YAML used by Archipelago from the settings currently
visible in the launcher.

1. Open the Randomizer.
2. Choose campaigns, progression, rewards, difficulty, and advanced settings.
3. Open the **Archipelago** tab.
4. Enter the unique slot name you will use in the room.
5. Select **Save Player YAML** and choose a destination.
6. Give the YAML to the room host, or place it in Archipelago's `Players`
   folder when generating the room yourself.

Reuse the same YAML to generate additional rooms with the same settings.
Archipelago assigns a fresh Randomizer seed during each room generation.
Re-export only after changing launcher settings. Do not hand-edit generated
template data or replace YAML after a room has already been generated.

## Generate and host the room

Generate the multiworld normally with Archipelago after every player's YAML is
in the `Players` folder. Reusing a Player YAML does not reuse its Randomizer
seed. Upload or host generated output using the normal Archipelago workflow.

The Reloaded world reserves locations for mission objectives, victories, and
Shop Mode purchases. One private local-victory event per mission connects real
launcher progression with Archipelago logic.

## Connect the launcher

1. Open the room page and find its game-server port.
2. Open the Randomizer's **Archipelago** tab.
3. For an Archipelago-hosted room, enter `archipelago.gg` as the server.
4. Enter the separate game-server port shown on the room page.
5. Enter the exact slot name used in the Player YAML.
6. Enter the room password when required.
7. Select **Connect**.

Do not paste the browser room URL into the server field. Hosted rooms use the
bare `archipelago.gg` hostname and a separate port. TLS certificate and
hostname verification remain enabled.

After validation, the connection status turns green. The launcher loads the
room's missions, progression, completed checks, received items, and signed
settings. Room-controlled gameplay settings become read-only while connected.

## Play and report checks

Launch missions through the Randomizer. Supported objectives and mission
victories are reported automatically. Items received by your slot enter the
normal unlock system and apply to future generated missions.

The activity feed shows server, chat, and item messages. Its chat field accepts
normal messages and Archipelago commands such as `!hint` and `!release`.

In Grid Mode, visible nodes and mission availability come from the connected
room. In Shop Mode, use the **Shop Run** workspace. Victories report stage and
mission locations; **AP Purchases** spend displayed Gems to report
generated purchase locations. Each purchase row uses the Archipelago emblem
and shows the scouted item plus its recipient player/world. Received AP items
use the same emblem in Shop loadouts and Unlocks views. Pending purchases retry
after reconnecting without charging twice.

## Disconnect and continue later

Disconnecting returns the launcher to its latest standalone state. Reconnect
to the same room and slot to restore Archipelago state. The server remains
authoritative for reported checks, received items, mission completion, and
multiworld progression. Synchronization does not grant rewards twice.

## Troubleshooting

### The launcher cannot connect

- Use `archipelago.gg`, not the browser room URL.
- Copy the room's game-server port exactly.
- Match the slot name, including spaces and capitalization.
- Enter the password if the room requires one.
- Confirm that the room is running and has not expired.

TLS uses the same maintained `certifi` CA bundle as the official Archipelago
client. For `CERTIFICATE_VERIFY_FAILED`, check the system clock, then check
whether antivirus or a network proxy intercepts TLS. Do not disable certificate
verification.

### Version or manifest mismatch

- Use launcher and `cnc_reloaded.apworld` from the same release.
- Generate the room with the APWorld installed.
- Use the Player YAML that generated the room.
- Export a new YAML and generate a new room when settings change.

### Wrong missions, checks, or unlocks appear

- Confirm that connection status is green.
- Confirm that you connected to the intended room and slot.
- Disconnect to inspect standalone state; reconnect to restore room state.

### A completed check has not appeared

- Keep the launcher running while playing.
- Confirm that it remains connected after returning from the game.
- Reconnect to request synchronization.
- Review `ReloadedRandomizerData\logs\launcher.log` and the activity feed for a
  compatibility error or server refusal.

## Maintainer commands

Regenerate, audit, and build the APWorld from the repository root:

```powershell
python -m Archipelago.generate_catalogue
python -m Archipelago.audit
.\Archipelago\build_apworld.ps1
```

The platform-neutral build command is:

```bash
python3 Archipelago/build_apworld.py
```

Output is `Archipelago\cnc_reloaded.apworld`. The launcher build publishes the
matching world beside `CnCReloadedRandomizer.exe`.

## Shop Mode and YAML compatibility fixes

Replace the installed APWorld in Archipelago's `custom_worlds` folder with the
APWorld from this checkout, then restart Archipelago before generating. An
older installed APWorld keeps its old version checks even after the launcher
is updated.

Launcher release labels no longer reject an otherwise compatible run. Schema,
mission/reward catalogue, and manifest integrity checks still reject incompatible
or damaged input. The APWorld validates exported template data, derives a fresh
deterministic Randomizer seed from each Archipelago generation, then signs
room-specific data sent to the launcher. Legacy fixed-manifest YAMLs are
reseeded too. Player YAML uses JSON-compatible YAML mappings to preserve setting
types exactly. Re-export through **Save Player YAML** when changing settings or
replacing an incompatible catalogue.

For an AP Shop run, select **Shop Mode**, save the Player YAML, generate and host
the room, then connect the launcher. **Start Shop Mode** remains available after
connection validation and after a failed or completed run. Generation settings
remain locked while connected. AP purchases are scouted; stage victories are
sent as checks, and stage-marker receipts are acknowledged without becoming
ordinary Shop rewards. Only a completed run belonging to the current AP slot
can report its goal.

Run `tools/check_archipelago_integration.py --archipelago-root /path/to/Archipelago`
with Archipelago 0.6.7's Python environment to verify YAML, generation, item fill,
beatability, handshake, and Shop controls. Add `--apworld /path/to/game.apworld`
to test the packaged world.
