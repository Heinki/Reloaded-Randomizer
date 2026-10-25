# Final Fortress in C&C Reloaded

Select **Settings → Game Mode → Final Fortress**. Choose your faction,
**Casual / Normal / Hard**, wave multiplier and game speed, then launch.
The only Fortress map is **The Wings of Faith**. Settings stays available;
select another Game Mode to return to its existing workspace and progression.

The workspace uses the Mental Omega implementation's layout and interactions:
Defense setup, Permanent perks, Challenge and Run results. Rank effects and
Challenge descriptions wrap in adjacent themed panes. Challenge supports
selection dragging, Shift/Ctrl/Alt selection, Ctrl+A, double-click/Space,
inline stack arrows and bulk controls. Help contains How to play and Wave
forecast. Results select automatically after a verified outcome.

## Survival and progression

Defend Einstein's Lab for **60 simulation minutes** against three mutually
allied, independently rolled enemy factions. The five active factions are
Allies, Soviets, Yuri, GDI and Nod; CABAL remains excluded.

The installed Lab has **1,000 HP**. Durability ranks provide **1,250 / 1,500 /
2,000 HP**. Emergency repair uses Reloaded's native **25%** red-health threshold.
The reserve uses native half-health and red-health fallback events, with a
separate once-per-run flag and objective-only shield activation.

The first scripted wave arrives at minute 5, involving one front. Two fronts
participate at minute 10, all three from minute 15. Later intervals begin after
the previous delivery completes. Separate native timers show Until Victory,
Next enemy wave and each human's purchased allied reinforcement countdown.
Ordinary native AI production continues alongside scripted waves.

Speed labels retain Reloaded's display numbering: **6 - Fastest** writes native
`GameSpeed=0`, while **0 - Slowest** writes `GameSpeed=6`. The same mapping is
used for campaign, solo Fortress and co-op, including reading native settings.

Six guarded crates exist from startup. Collection pays **10 Defensive Points**
to every human once; killing guards grants no additional camp award. Frozen
contents are 40% for 2,500 credits, 30% for ten Tier 1 units, 20% for five
Tier 2 units and 10% for a faction special. Humans receive their own payload;
AI collectors deliver the payload to the host.

Survival awards are **25 points at minute 25**, **25 at minute 45**, and **50
on victory**. Earned milestones survive defeat or quitting. Verified victory
or defeat permits five points per 50 corrected friendly native kill-score
points, capped at 500 points. Native scores can include captures. Setup
transfers and received cash escrows are deducted per friendly house.

Fortress uses its own `final_fortress_state.json` and OS lock under APP_DIR.
Its target-owned state and plan versions start at 1; MO profiles and migrations
are not imported. Purchases, selected ranks, run inputs, rewards and co-op
receipts remain separate from campaign, Grid, Shop and Archipelago saves.
Compiled launchers expose Standard progression only.

Local source runs can expose the separate **Testing (all unlocks)** profile with
`RANDOMIZER_FINAL_FORTRESS_DEBUG=1` or an ignored `final_fortress_debug.enabled`
file beside an existing `final_fortress_testing_state.json`. An explicit
`RANDOMIZER_FINAL_FORTRESS_DEBUG=0` disables the local flag. The flag and debug
save are never bundled, and compiled launchers ignore this opt-in.

## Co-op

In Settings, enable Final Fortress co-op and select **2 or 3 players**. Connect
as host or Join using the host's ZeroTier Managed IPv4 and pairing code.
Guests receive seats in arrival order; every player needs a distinct name.
The player count locks while connected and is absent from the connection dialog.

Host settings and perks are shared except Fundraising, which uses each human's
own enabled purchased rank. Helpers use the host's Fundraising rank and occupy
only unused friendly seats. Every machine prepares the frozen run, compares
its exact map digest and acknowledges readiness before launch. Rewards remain
local, with durable duplicate-run protection. Disconnect and reconnect the whole
lobby between runs; mid-game joining and reconnecting are unsupported.

The lobby uses TCP **19420**; native game endpoints use UDP **1234 / 1235 /
1236**. The installed spawner exposes Other1–Other7 and per-player ports, matching
the [upstream spawner configuration](https://github.com/CnCNet/yrpp-spawner/blob/main/src/Spawner/Spawner.Config.cpp)
and [native endpoint setup](https://github.com/CnCNet/yrpp-spawner/blob/main/src/Spawner/Spawner.cpp).
Every peer must be reachable from every other peer. The optional
`tools/configure_fortress_firewall.ps1` configures these inbound ports for the
compiled launcher/game on Windows Private networks; it is not run automatically.

## Reloaded adaptations

- **300 enemy wave units**, using five reusable 20-unit reservations per enemy;
  **90 allied reinforcement units**, using six shared 15-unit reservations.
  Starting grants, reserves, camp guards and ordinary AI production are excluded.
  These conservative caps replace MO's 480/150 because Reloaded already registers
  286 vehicle types. Tracked identities are reserved before production clones;
  generation rejects survivor-counter indices at or above the native 512 bound.
- Private countries use a compacted generated country table. The five inactive
  Robot/Unused/NoPilots entries are omitted so six active Fortress actors fit
  within Ares' 32-country limit. Original rules and country definitions are not
  edited. Friendly score identities use Reloaded's Gold, Orange and Purple
  remaps, rather than MO's color indices.
  Both map and preload emit this table in numeric order; spawner indices come
  from the actual entry order, including co-op peers. INI country keys do not
  determine native indices. Previously, lexical ordering made player index 26
  select YuriCountry2 despite a Soviet selection and misassigned the AI houses.
  The resulting crash dump reached `004F671D` after an AI house had no buildable
  war factory. Preparation now checks every active country's native war-factory
  ownership, concrete house restrictions and AI planning side before launch.
- Construction starts use the faction's native MCV/yard pair: Allied
  AMCV/GACNST, Soviet SMCV/NACNST, Yuri PCV/YACNST, GDI GDIMCV/TSGACNST and
  Nod NODMCV/TSNACNST. CABAL's broad native Owner mask cannot supply fallback
  starts: its entries are removed from Fortress's BuildConst/BaseUnit lists,
  and CABAL task forces are excluded from the private AI catalogue. Preparation
  verifies the first eligible starting type for every active actor.
- Private country parents point to their own identities. Native faction fields
  are copied explicitly and `FFCountryOrigins` records the source faction.
  The installed Phobos AI selector matches triggers against ParentCountry;
  retaining native parents prevented the country-specific Fortress recipes
  from matching. Production masks explicitly include each private actor.
- AI preloads contain active, country-specific recipes rather than the old
  disabled global recipes. Immutable scripted orders and identical task forces
  are shared. In the reported full-perk Soviet run, generated AI trigger entries
  fall from 3,227 to 1,662 and scripted order definitions from 1,129 to 28.
  Correct yards and nearby production buildings also remove invalid factory
  choices and distant construction/docking routes. Native FPS remains subject
  to gameplay review; these are measured data reductions, not measured FPS.
- Support powers have **three** cumulative ranks per faction, as selected for
  Reloaded. Superweapons retain
  two cumulative ranks; compatible power upgrades use the existing Reloaded
  power catalogue.
- Native unit and technology eligibility respects the selected concrete country,
  including its Owner/RequiredHouses/ForbiddenHouses gates and production path.
  Alternate-country labs are not added merely because they share a faction.
  Reinforcement gifts retain ordinary production: receiving a Flak Track no
  longer hides the player's buildable Flak Track copy.
- Secret Labs retain their native capture and boon-selection behavior. Their
  pools include private player and Challenge identities with corresponding
  SecretLab house gates, so a capture selects the buffed identity for its owner.
  Hidden boons keep their native TechLevel until captured, unless an explicit
  Special Unit Access perk grants them. CABAL boons remain excluded.
- Special Unit Access is an additional perk roster, not the native faction
  roster. Soviet ranks grant the TD Mammoth, RA1 Mammoth, then Scorpion.
  Both Mammoth models reference the same installed `mamuicon.pcx` / `mamuico.pcx`
  artwork and the same native CSF name. Their private names now distinguish TD
  and RA1 while preserving each model's correct native Image and cameo.
  The source all-unlocks profile enables all three bonus units intentionally.
- GDI Hunter-Seeker perks place the same invisible owned launch structure used
  by Shop/Grid. Yuri starting generators are placed after reserving arrival
  buffers, preventing its second helper's generator from blocking an apron.
- **Special building income** is removed for now: Reloaded has no reviewed
  buildable payout buildings. Captured native oil derricks keep their
  existing payout. Positive native unit/building limits receive their separate
  capacity perks without granting technology access.
- Reinforcement Challenges use Reloaded's **Paradrop** and **GDI Drop Pods**.
  Each enabled power gives every enemy three launches, twice native recharge,
  and no initially ready shot. Paradrop delivers each enemy's faction infantry;
  Drop Pods retain the native 7–9 GDI infantry payload. These deliveries are
  outside the scripted-wave caps. The catalogue contains 37 Challenges: 33
  stat/production entries, Powerhouses, two reinforcement powers and offensive
  superweapons. Bloodhounds and Moon reinforcements are not included. Mental AI
  Boost has no option, behavior or spawn field.
- Friendly and enemy private copies follow the Shop/Grid native transform
  keys, curated linked roots, initial passengers, spawned aircraft and concrete
  ownership gates. Linked forms inherit their root's tier while retaining their
  own native stats and weapons. Friendly copies keep native selection groups.
  Existing shared enemy calculations provide Challenge stat changes.
- Air waves use armed native flying vehicles or infantry. GDI uses jumpjet
  infantry. Scripted Nod Venoms use the native automatic laser without their
  hidden passenger, avoiding an untracked extra entity; private weapon bonuses
  carry over to that automatic laser. Dock-dependent aircraft are excluded.
  Later Allied, Soviet and Yuri pools retain earlier aircraft alongside their
  additional airborne types. GDI keeps jumpjets; Nod keeps Venoms and its ground
  progression rather than inventing a missing heavy-air role. Late starting and
  periodic rosters include supported air units.
- Yuri's starting refinery is the deployed Slave Miner itself, with its native
  slaves; no second mobile Slave Miner is granted alongside it.

## Map preparation and evidence

Friendly seats use waypoints **0 / 1 / 2**; enemies use **5 / 6 / 7**. Generated
starts are `(126,124)`, `(115,240)`, `(239,118)`, `(210,206)`, `(236,323)` and
`(321,248)`. Original map bytes remain untouched. The disabled authored Show Map
trigger (elapsed-time event and reveal action) is removed from generated bytes;
Fortress controls map reveal through its own perk.

Terrain preparation reads native IsoMapPack5, overlays, scenery and installed
art foundations. Layouts reserve complete 7×7 MCV areas, building exits, power
plants, 32 friendly defenses, 24 enemy defenses and six full guard formations.
Faction-specific layouts place core buildings and generators within 15 cells
on their base's plateau. Each friendly defense rank covers eight angular
sectors within 20 cells; each enemy's 24 defenses surround its yard within
16 cells. The northern start shifts four cells into the adjoining open patch
and its Lab remains beside the MCV. Runtime preparation rejects overlapping
buildings, distant grants, an open defense quadrant or core buildings on another
plateau. Arrival aprons remain inside the corresponding perimeter's open space.
Enemy apron placement also reserves a clear one-cell exit border on the base's
plateau; the original middle and eastern aprons had obstructed borders. Every
friendly arrival, reservation and Lab reserve resolves the same faction-specific
apron as the starting army. Older frozen runs with blocked enemy exits require
a new run to obtain the corrected layouts.
Only reserved 5×3 arrival cells are paved, using installed SNOWMD tile **734**.
Heights, resources and scenery are preserved. Runtime preparation checks map
bounds, terrain, MCV clearance, camp clearance and explicit Action 80 arrivals.

`python3 tools/configure_fortress_layouts.py` regenerates these production
coordinates from installed terrain and native art foundations. It writes the
configuration only after placing all five factions at all friendly and enemy
starts, without changing installed map bytes.

`tools/prepare_final_fortress.py --output generated_maps/final_fortress`
compiles a playable artifact using the local Standard profile's owned loadout,
without launching or changing progression. It emits the frozen run, map,
spawner data and native rules/AI preloads in the selected directory.
For an enabled source debug profile, add `--profile 'Testing (all unlocks)'`
to compile that profile's actual enabled loadout. The compiler never changes
either profile's progression. Scripted missile-carrier validation resolves
private spawned missile definitions as well as installed native IDs.
The October 24 Soviet crash seed was recompiled with all 29 maximum-rank perks;
inspection confirms the map and preload both assign FFPLAYER and its helpers to
Soviets, with the three frozen enemy factions assigned to their intended seats.
This establishes preparation and assignment evidence, not a native gameplay run.

The October 25 crash at native `0065D99F` occurred during the fourth wave's GDI
air delivery, whose TaskForce contained the same Jumpjet Infantry identity in
two rows (four plus one). Native recruitment only matches the first row, leaving
the final recruit without a Team pointer that reinforcement then dereferences.
Team emission now merges all repeated identities, including those in previously
frozen plans, without changing their saved balance snapshots. Unit counts
and the 300/90 population caps are preserved. Logs confirm the red GDI front's
third-wave dispatch; its absence from the first two waves follows the configured
one/two/three-front opening, rather than a missing third house.

The five prepared all-unlocks faction artifacts now pass runtime native-roster
and Secret Lab integrity checks: Allies 32, Soviets 35, Yuri 25, GDI 32 and Nod
39 native infantry/vehicle/aircraft identities, including technology-gated and
naval production. Bonus perk units and captured Secret Lab boons are separate.
The local inventory is recorded in
`generated_maps/final_fortress_rosters/ROSTERS.md`. A Standard-profile artifact
also compiles without requiring the source all-unlocks profile.

Source compilation, the existing static configuration validator, a prepared
Wings of Faith artifact, headless source-map terrain rendering and the Windows
build establish implementation evidence. They do not establish native gameplay.
No tests, automated gameplay simulations or fullscreen game launches were used.

The source launcher was visually inspected with the Fortress workspace selected.
Its outer Final Fortress/Settings tabs, Defense setup, Permanent perks, Challenge,
Run results and Help control render using MO's original Fortress view. The shell
adapter handles Reloaded's absent Copy Seed button and saves/restores complete
notebook tab options without invoking campaign layout during a partial switch.

During normal play, native review remains necessary for mixed arrivals and
transport behavior, helper attacks, delayed late waves, aircraft tracking,
all crate collectors, exact Fundraising payments, Lab repair/reserve/shield
timing, destructible expansions, maximum grants and power, two/three-player
readiness/cancellation and exactly-once results after restart. UI rendering on
Windows and each purchased loadout also remain subject to that review.
