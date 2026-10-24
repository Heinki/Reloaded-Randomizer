# Final Fortress ports: DTA and C&C Reloaded

## Start here in this repository

This checkout's implementation target is **C&C Reloaded**, using only
**The Wings of Faith** initially. The full shared brief below covers both engines;
apply the C&C Reloaded requirements here. The adjacent
[FINAL_FORTRESS.md](FINAL_FORTRESS.md) contains the complete MO gameplay, perks,
UI and runtime reference. Its MO-only map, unit IDs and Mental AI Boost are not
target requirements. These files are planning documentation; no port has been
implemented by adding them.

Suggested prompt for a later implementation session:

```text
Read AGENTS.md where applicable, FINAL_FORTRESS_PORTING.md and FINAL_FORTRESS.md.
Implement Final Fortress in this C&C Reloaded repository using The Wings of Faith.
Keep the Mental Omega UI layout and interactions, retain Settings and switching
back to other modes, and isolate Fortress from Shop/Grid and campaign saves.
Adapt native factions, units, buffs, powers, difficulty and engine behavior
according to the porting brief. Do not add Mental AI Boost or expose the local
all-unlocks Testing profile in compiled EXEs. Follow this repository's validation
policy; do not launch fullscreen applications or repeatedly open/close the game.
```

This is an implementation brief, not an implemented feature. Add the existing
Mental Omega Final Fortress experience to both launchers, retaining the same UI
and gameplay flow while adapting factions, engine behavior and difficulty.
The reference is the current MO implementation, including plan-20 mixed air
waves and the subsequent restriction of Testing profiles to local source use.
See [FINAL_FORTRESS.md](FINAL_FORTRESS.md) for the complete mode contract.

## Scope and selected maps

| Target | Source checkout relative to its game root | Only initial Fortress map | Installed source |
| --- | --- | --- | --- |
| DTA | `RandomizerLauncher/` | King of the Hills Extreme | `Maps/Default/king_of_the_hills_extreme.map` |
| C&C Reloaded | `Reloaded-Randomizer/` | The Wings of Faith | `Maps/Standard/wingsfaith.map` |

Implement a standalone `randomizer/final_fortress/` package and a dedicated
application controller in each project. Keep Shop, Grid, campaign and Archipelago
state and gameplay independent. Reuse each project's existing infrastructure;
do not introduce imports that require the MO checkout to be installed.
Create `configs/final_fortress.json` and
`randomizer/application/final_fortress_controller.py` in each target. Use the MO
package's planning/state/persistence/reporting and UI organization as the model;
replace its engine/content dependencies through target adapters. Store ordinary
progress in `final_fortress_state.json`, with a separate lock and optional local
`final_fortress_testing_state.json`, inside that target's own APP_DIR.
There is no Mental AI Boost option in either port. Do not copy its checkbox,
`MentalAI` spawn setting, MO overlay path or required schema field. Native
game-specific AI settings are separate features, not automatic replacements.

## Gameplay to preserve

- One human chooses a playable faction against three randomly selected enemy
  factions. Enemies are allied with one another. Optional purchased helpers are
  allied to the human, using the human faction and applicable enabled perks.
- Defend a protected objective beside the initial MCV for **60 in-game minutes**.
  Objective destruction means defeat; reaching the deadline means victory.
  Keep native elimination victory from ending survival early. Choose a suitable
  installed objective building per game; do not assume MO's Einstein Lab exists.
- Show **Until Victory** and a separate **Next enemy wave** countdown. First wave
  is at minute 5; one front participates at 5, two at 10, all three from 15.
  Further five-minute intervals follow completed deliveries. Capacity delays do
  not cause catch-up bursts. Stop all delivery chains at the run outcome.
- Difficulty and the independent **x1–x10 wave multiplier** affect scripted
  reinforcements in addition to normal skirmish AI production. Each later wave
  grows by its difficulty's starting base amount, subject to the shared caps.
- Use changing infantry, vehicles, anti-air and artillery compositions over
  time, including infantry-led variants. Add faction air attacks from minute
  15 and heavier choices from 30, provisionally replacing 15% then 25% of each
  wave. Preserve infantry and selected Challenge heavy units. Air and ground
  attacks use separate teams within the same population budget.
- Retain small reusable living-unit reservations, rather than holding an entire
  wave until every survivor dies. MO's provisional ceilings are 480 enemy wave
  units and 150 friendly reinforcement units; review both for each engine and
  map. These do not include ordinary AI production or camp guards.
- Friendly reinforcements arrive every five minutes when purchased, with
  independent delivery timers for the human and each helper. Spawn sites must
  remain usable after base expansion. Helpers must receive explicit useful
  attack orders for both starting armies and reinforcements.
- Enemies have indestructible base construction and substantial fixed anti-rush
  defenses. Player/helper AI must not repeatedly attack immortal targets.
  Keep ordinary hostile combat units and camp guards destructible.
- Place six camps throughout the playable map. Guard formations vary by faction
  and can include reviewed heroes/heavies. Provisional guard counts are 5/8/12
  for the first three difficulty grades, multiplied by x1–x10 and capped at
  30 per camp and 180 total. Configure additional DTA grades explicitly.
- Select camp roster factions independently of the three base AI rolls. Deal
  each active faction family before repeating: four in DTA, currently five in
  Reloaded. Do not retain MO's fixed four-family or twelve-country assumptions.
  Keep camp units under an enemy AI's ownership and alliances, stationary until
  attacked, isolated from ordinary AI recruitment, then able to retaliate.
- Clearing a camp awards Gems immediately. Its separately collected reward
  randomly grants money, a Tier 1/Tier 2 squad or a faction special unit. Only
  human collection activates the payload. If native visual crates are still
  collectible by AI, AI pickup must not consume the human reward claim.
- Award survival Gems at **25 minutes**, **45 minutes**, and **60-minute victory**.
  The MO baseline is 25 + 25 + 50 Gems, plus camp rewards, verified combat kill
  tiers and enabled Challenge victory bonuses. Freeze configurable values before
  launch and show every award source in Run results, including defeat outcomes.

## UI parity is required

Use MO's `randomizer/final_fortress/ui.py` and
`randomizer/application/final_fortress_controller.py` as the interaction reference.
Adapt their imports and theme integration rather than designing another screen.

1. Rename the applicable progression selector to **Game Mode** and add **Final
   Fortress** there. Its workspace replaces the normal mission/grid/shop area
   only while selected. Keep **Settings** accessible and allow switching back.
   Advanced and Archipelago can be hidden in this workspace and restored on exit.
   Do not expose Fortress as a permanently visible top-level tab in other modes.
2. Keep the same compact header, Defense setup, game-speed selection and launch
   action. Setup contains map, player faction, AI difficulty and wave multiplier.
   Offer only the selected target map. Remove Mental AI Boost without leaving
   an empty or disabled row. Map these values to separate Fortress preferences.
3. Keep **Permanent perks**, **Challenge**, and **Run results** in the same order.
   Result selection and reward breakdown should happen automatically when a
   verified result arrives. Do not require Refresh progression or manual victory.
4. Perks retain the themed list and adjacent wrapping **Rank effects** pane.
   Show Perk, Next rank cost, and Rank/status. Describe every rank's cumulative
   faction-specific effect; do not repeat prices in the description. Keep Buy
   and enable/disable controls, a vertical list scrollbar, and no horizontal or
   duplicate scrollbar. Text panes must match the current light/dark palette.
5. Challenge remains enemy-only. Double-click or Space toggles selected rows.
   Decrease/increase arrows stay **inside each row beside Stacks**. Retain drag,
   Shift/Ctrl/Alt selection, Ctrl+A/Select all, bulk enable/disable and Max stacks.
   Max stacks applies to the selected group without silently enabling it.
   Descriptions wrap in the adjacent Effect at selected stacks pane. Do not
   restore an Apply stacks button or an Enable selected modifier checkbox.
6. Keep explanations in themed **Help → How to play / Wave forecast**, with
   concise readiness or blocking errors beside launch. No Launch status popup
   and no large instruction blocks permanently filling the main workspace.
7. Compiled EXEs expose Standard progression only. Keep all-unlocks Testing
   available solely to an existing ignored local source-checkout testing save;
   never bundle that save or enable it through a public setting.

UI parity means matching layout and interaction, not MO branding or invalid
catalogue entries. Retain each launcher's palette, faction names, currencies'
display conventions and native game-speed translation. Keep Fortress Gems
separate from Shop currencies. Show only effects supported by the target game;
explain unavailable capabilities in Help rather than selling ineffective perks.

## Verified map starting points

The following are read-only findings from the installed files. They are source
waypoints, **not approved building, defense, camp or reinforcement coordinates**.
Both maps have eight starts, enough for the human, three enemies and two helpers.
Choose opposing human/enemy regions and nearby helper sites after inspecting
terrain, access routes and space for full bases.

| Target | Size | LocalSize | Source properties |
| --- | --- | --- | --- |
| DTA | `0,0,136,140` | `4,6,128,128` | TEMPERATE; MaxPlayer 8; IgnoreGlobalAITriggers=no; MultiplayerOnly=no |
| Reloaded | `0,0,200,200` | `2,4,196,192` | SNOW; MaxPlayer 8; IgnoreGlobalAITriggers=no; MultiplayerOnly=1 |

| Waypoint | DTA packed cell | Reloaded packed cell |
| --- | --- | --- |
| 0 | 107077 | 122122 |
| 1 | 73117 | 241115 |
| 2 | 167091 | 118240 |
| 3 | 137132 | 185149 |
| 4 | 101165 | 150186 |
| 5 | 214120 | 210210 |
| 6 | 175174 | 323235 |
| 7 | 127215 | 244323 |

The installed map format packs these as `y * 1000 + x`; use section-aware parsing
and the target's existing helpers, not the first `Size=` occurrence in a file.

DTA's `INI/MPMaps.ini` registers King of the Hills Extreme as a skirmish map even
though its source Basic flag says `MultiplayerOnly=no`. MO's current strict
`inspect_map` check would reject it. Validate its registered skirmish identity,
starts and AI settings, then set appropriate properties in the **generated copy**
if required. Do not rewrite the installed map or treat it as a campaign mission.
Its registry also forces bridge destruction and naval options off; review and
preserve those map restrictions in the Fortress launch.

The Wings of Faith contains authored Houses and a trigger/event/action. Review
those before adding countries and survival logic; do not blindly discard them.
Use the standard map mode, not Nuke War or Meat Grinder overlays.

For each map, configure the objective foundation, base/building/power positions,
outer defense batteries, six camp centers and guard cells, enemy fortifications,
protected arrival areas and hidden utility providers. Check full foundations,
height, trees, resources, cliffs, water, paths and playable projected bounds.
Never carry Miners in the Sun's coordinates, snow/temperate assets or reserved
cells into either port. Spread defenses outside the build core while retaining
safe power supply. Do not block MCV deployment or base expansion.

## Target differences and implementation entry points

| Concern | Reloaded | DTA |
| --- | --- | --- |
| Engine/launch | `Syringe.exe`, `gamemd.exe`, Ares + Phobos + CnCNet Spawner | `LaunchVinifera.dat`, `game.exe`, Tiberian Sun/Vinifera |
| Game identity | `randomizer/config/game_profile.py` | `randomizer/core/paths.py`, `randomizer/dta/` |
| Native rule/art/AI names | `rulesmd.ini`, `artmd.ini`, `aimd.ini` | Installed DTA INI layout; inspect `randomizer/dta/rules.py` and existing runtime writers |
| Faction evidence | `config/game_profile.py`, `content/inventory.py`, `content/faction_paths.py`, `configs/factions.json` | `dta/rules.py`, `dta/access.py`, `dta/clones.py`, `configs/factions.json` |
| Buff and power adapters | `maps/enemy_scaling.py`, `maps/power_buffs.py`, `maps/powers.py`, existing reward catalogues | `dta/enemies.py`, `dta/clones.py`, `dta/powers.py`, `rewards/dta_power_buffs.py` |
| Spawn/log evidence | Existing launch controller and `maps/hooks.py` / `maps/progress_hooks.py`; `debug/debug.log` | `coop/spawn.py`, existing launch controller and hook code; newest appropriate log under `Debug/` |

### Reloaded

The active game profile currently contains **Allies, Soviets, Yuri, GDI and Nod**.
CABAL is gated by `ENABLE_CABAL=False`; respect that gate throughout faction
selection, camps, waves, powers and prices. Resolve concrete country identities
from the target catalogue. Broad Owner masks alone are insufficient faction
evidence in Reloaded; reuse its reviewed production-path resolution.

Much of the MO engine structure is reusable, but verify trigger/action formats,
country indices, private registration, art dependencies and installed extension
capabilities. Replace MO filenames, DLL assumptions, special unit IDs, provider
buildings and terminal marker conventions with the target's existing equivalents.
Keep native result-hook semantics: a trigger event being logged is not always
proof that all attached objects satisfied it and its actions executed.

Reloaded's current launcher choices are **Casual, Normal, Hard**. Preserve these
labels instead of adding Mental. The provisional wave baselines can remain
3/6/9, with native AI difficulty translated by the existing target conventions.

### DTA

Treat this as an engine-adapter port, not a direct copy of MO INI fields. DTA uses
Vinifera House/ActsLike production semantics rather than MO's country setup.
Its existing clone code documents the relevant production masks. Its multiplayer
spawn adapter explicitly avoids YR-only fields. Reuse those conventions for
human/AI houses, spawn positions, alliances, colors and handicaps.

The four production families are **GDI, Nod, Allies and Soviet**. Use the target's
canonical IDs and existing rosters, not renamed MO families. DTA's conservative
enemy adapter can skip an effect when a friendly force shares that family;
Fortress must not silently claim the effect works in that case. Provide reviewed
private-type/house isolation or omit the unsupported modifier with an explanation.
Do not globally buff a type used by both human and enemy.

The launcher already lists **Easy, Normal, Hard, Brutal, Extreme, Ultimate and
Impossible**. Preserve that order in the same difficulty control. These seven
labels are not seven native engine handicap values: `dta/difficulty.py` resolves
authored campaign selectors and is not a drop-in skirmish difficulty mapping.
Define explicit Fortress profiles containing display label, native skirmish AI
setting, any supported private enemy modifiers, wave baseline/growth and rewards.
Higher grades must have actual configured behavior rather than relabelled Hard.
Inspect DTA's installed client/spawner settings before assigning native values;
never write the UI indices 0–6 directly into a three-level engine field.

Keep the native handicap, additional difficulty modifiers, optional Challenges,
and wave multiplier distinct. Freeze all resolved values in the run. Make the
configuration validator and wave planner accept the target's full difficulty
table instead of copying MO's fixed three-element `DIFFICULTY_IDS`. Review
growth/caps for every grade at x10; a high baseline must not exceed native
population limits or make a selected combination impossible to launch silently.

DTA's lobby checkbox named `chkExtremeAI` currently displays **Advanced AI** and
loads `INI/Game Options/Advanced AI.ini`. Its name is not a difficulty mapping
and it is not Mental AI Boost. Review any overlay needed for ordinary DTA AI;
do not import MO's toggle or substitute another public boost control in this port.

Verify timer text, a second countdown display, team orders, veterancy encoding,
type-absence events, immunity/target exclusion and live-unit tracking against
Vinifera. Do not copy MO action IDs or its hidden GenericWarhead clock provider
as if they were supported. Implement equivalent native behavior or a clearly
documented compatible alternative; never show a countdown that does not control
the real delivery schedule. Use DTA's rotating-log discovery for result watching.

## Content and capability mapping

Port perk behavior and UI rank presentation, then map each effect to installed
target content. Keep the current MO rank limits as the starting design:

- Supply cache 6; production speed 5, affecting units and buildings.
- Starting army 5, adding three units per rank through fifteen, with increasing
  quality and reviewed faction special units; Veteran army 2 through maximum
  supported veterancy. Verify placed-unit experience separately from team rank.
- Starting buildings 5, including a working refinery/harvester; starting defenses
  4, with four of each unlocked defense plus enough faction power plants.
- Veteran defenses; defense firepower 6; separate Tier 1/2/3 unit buffs 6 each.
- Faction support powers 5, secondary then offensive superweapons 2, and power
  upgrades 6. Map actual effect dependencies, duration/radius/payload upgrades
  and provider ownership using the target's working adapters.
- Satellite intelligence; up to two allied helpers sharing applicable perks.
- Special-unit production access and recurring reinforcements, including the
  final Veteran/maximum-veterancy ranks. Do not sell inaccessible faction units.
- Automatic healing, sight/stealth detection, unique-unit capacity, and income
  from eligible special buildings. Distinguish periodic cash from ore/tiberium
  processing bonuses and show the actual supported effect in rank descriptions.

Use each target's existing reviewed enemy buff catalogue for Challenge armor,
production and per-tier effects. Map heavy reinforcement and offensive power
Challenges to native equivalents. MO names such as Bloodhounds, Moon
reinforcements or Great Tempest are not portable feature requirements.
Unsupported powers/buffs must not appear purchasable or award pretend effects.

For air waves, choose armed types that can arrive, attack repeatedly and remain
tracked under the target engine. MO's flying vehicles do not prove that DTA's
fixed-wing aircraft can use the same spawn/reload method. Review docking,
rearming, crashes, transformations, spawned aircraft, passengers and deployable
forms. Either track all resulting entities inside the cap or exclude the type.
Retain per-game tier definitions rather than inferring MO tiers from another
game's raw TechLevel values.

## Implementation order and completion criteria

1. Add the isolated package/controller/config and restore identical mode-switch
   behavior first. Register the static config in target schema, validation and
   packaging paths. Keep shared Settings and other modes functional.
2. Build target adapters for catalogue/rules, factions, difficulty, native map
   actions, logs, launch/runtime assets, buffs and powers. Capability decisions
   belong here; UI callbacks must not contain scattered engine-specific branches.
3. Inspect the single selected map, choose the human/enemy/helper starts, review
   all placements and produce a genuine prepared map/spawn artifact before
   enabling launch. Preserve original source files and the target runtime lease.
4. Implement the protected objective, ordinary skirmish AI, timer and durable
   START/WIN/LOSS receipts. Add capped wave/friendly delivery, then camps, perks,
   Challenges and the complete results breakdown through those same adapters.
5. Persist separate Fortress state and locking under each target's own APP_DIR.
   Freeze game identity, native difficulty, seed, complete balance snapshot,
   chosen rosters/rewards, perk ranks and Challenge stacks. Version local plans
   and preserve old snapshots. Never import MO Gems, saves or testing profiles.
6. Reuse the fixed bounded log-reader design: checkpoint only the 64 bytes before
   the cursor, handle truncation/replacement/partial lines, promptly drain
   backlog and EOF after process exit, and require this run's START and terminal
   marker. Do not infer victory from a voice line, generic Winner row or elapsed
   launcher time. Deduplicate receipts, back up verified recovery updates, and
   exclude setup/cash transfers from kill rewards using the target's evidence.
7. Apply the exact UI checklist above in both projects, including wrapping text,
   scrollbars, inline stack controls and bulk selection. Keep compiled builds
   on Standard only. Do not recreate the removed MO handoff history as public
   player documentation; retain one current mode guide and pending tasks.

Follow each target's `AGENTS.md`. Use source compilation, inspection of actual
prepared artifacts and existing production configuration/catalogue validation
where permitted. Do not introduce or run unit tests, test harnesses, automated
gameplay simulations or new test suites. Check only the chosen Fortress map in
each game; unrelated map sweeps are outside this work.

Acceptance requires correct UI switching and persistence, all selected factions
and difficulty grades, no off-map/overlapping placements, continuing capped
deliveries, usable helper armies, varied ground/air attacks, camp-clear Gems
independent of pickup, player-only payloads, enemy-only Challenge scope, readable
timers and complete exactly-once results. Keep unverified native behavior marked
for review during the user's normal gameplay session. Do not repeatedly open or
close either game, and never launch a fullscreen application for routine checks.

Remaining content decisions are the target objective buildings, exact reviewed
placements, supported faction power/special-unit mappings and provisional
balance for DTA's extra difficulty grades. These are implementation work, not
reasons to redesign the UI or change the selected maps.
