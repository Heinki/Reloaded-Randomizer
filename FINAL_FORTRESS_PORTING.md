# Final Fortress ports: DTA and C&C Reloaded

## Start here in this repository

This checkout's implementation target is **C&C Reloaded**, using only
**The Wings of Faith** initially. The full shared brief below covers both engines;
apply the C&C Reloaded requirements here. The adjacent
[FINAL_FORTRESS.md](FINAL_FORTRESS.md) contains the complete MO gameplay, perks,
UI and runtime reference. Its MO-only maps, coordinates, unit IDs, engine fields
and Mental AI Boost are not target requirements. This brief takes precedence
for target behavior. These files are planning documentation; no port has been
implemented by adding them.

Suggested prompt for a later implementation session:

```text
Read AGENTS.md where applicable, FINAL_FORTRESS_PORTING.md and FINAL_FORTRESS.md.
Implement Final Fortress in this C&C Reloaded repository using The Wings of Faith.
Port the current MO plan-39 behavior, including two/three-human co-op,
personal Fundraising, pickup-based camp rewards and current ranked perks.
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
Reference refreshed **2026-10-24** from the working MO checkout:
`randomizer/final_fortress/planning.py` has **PLAN_VERSION = 39**. The adjacent
[FINAL_FORTRESS.md](FINAL_FORTRESS.md) is a current MO behavior reference, with
MO-only validation history omitted. Neither document claims a completed target
implementation or verified target-engine gameplay.

The earlier plan-20 brief is superseded where it required camp-clear rewards,
human-only crate payloads, broad enemy-building immunity, five Starting army
ranks, six reinforcement ranks or the old kill-bonus ceiling. Preserve the
current behavior specified below. MO plan/schema numbers describe its history;
start target-owned versions rather than importing MO profiles or migrations.

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
`randomizer/application/final_fortress_controller.py` in each target. Use
`randomizer/application/fortress_coop_controller.py` and
`randomizer/application/fortress_coop_launch.py` as the co-op reference; adapt
existing target lobby, native spawn and runtime lease infrastructure. Use the MO
package's planning/state/persistence/reporting and UI organization as the model;
replace its engine/content dependencies through target adapters. Store ordinary
progress in `final_fortress_state.json`, with a separate lock and optional local
`final_fortress_testing_state.json`, inside that target's own APP_DIR.
There is no Mental AI Boost option in either port. Do not copy its checkbox,
`MentalAI` spawn setting, MO overlay path or required schema field. Native
game-specific AI settings are separate features, not automatic replacements.

## Gameplay to preserve

- One human, or two/three co-op humans, defends against three randomly selected
  enemy factions, including repeated factions. Enemies are allied with one
  another. There are three friendly seats total. Purchased helpers fill only
  seats left after the human roster, using the host's faction and shared perks.
  Two humans permit at most one helper; three humans permit none.
- Defend a protected objective beside the initial MCV for **60 in-game minutes**.
  Objective destruction means defeat; reaching the deadline means victory.
  Keep native elimination victory from ending survival early. Choose a suitable
  installed objective building per game; do not assume MO's Einstein Lab exists.
  Keep it unsellable, uncapturable and protected against relocation or occupation.
  Preserve objective durability, one-use emergency repair and one-use reserve
  squad perks through reviewed target mechanisms.
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
  attacks use separate teams within the same population budget. Reserve 40% /
  65% / 85% of eligible ground rosters for advanced/special units from minutes
  15 / 30 / 45. Preserve ordinary identities when space permits. Capacity-delayed
  opening batches upgrade to advanced replacements after 30 simulation minutes,
  at the same size; do not leave late games delivering queued opening troops.
- Retain small reusable living-unit reservations, rather than holding an entire
  wave until every survivor dies. MO's provisional ceilings are 480 enemy wave
  units and 150 friendly reinforcement units; review both for each engine and
  map. The current MO enemy model uses eight 20-unit groups per enemy (480
  shared). Friendly periodic reinforcements share ten 15-unit groups (150)
  across all human/helper houses, without fixed per-house quotas. Track captured,
  deployed and transformed survivors before releasing reservations. These caps
  exclude ordinary AI production, starting grants, objective reserves and camp
  guards. Freeze any reviewed target-specific cap changes explicitly.
- Friendly reinforcements arrive every five minutes when purchased, with
  independent delivery timers for the human and each helper. Spawn sites must
  remain usable after base expansion. Helpers must receive explicit useful
  attack orders for both starting armies and reinforcements. Human units stay
  under human control. Each human sees an owner-local **Next allied
  reinforcements** countdown, reset only after that house's complete delivery.
  Friendly periodic arrivals run from minute 5 through 55, strictly before victory.
- Protect only each enemy's **original starting construction yard** and fixed
  defenses, provisionally eight basic, eight anti-air and eight advanced turrets.
  Use a separate non-producible, non-undeploying starting-yard identity. Ordinary
  produced MCVs, deployed expansion yards, factories, power plants, upgrades and
  other buildings remain destructible and targetable. Keep prerequisites, docks
  and AI production connected to ordinary expansion types while recognizing the
  starting yard. Exclude only protected objects from attack targeting; helpers
  and waves must attack legal opponents without stalling on immortal structures.
- Place six camps throughout the playable map. Guard formations vary by faction
  and can include reviewed heroes/heavies. Provisional guard counts are 5/8/12
  for the first three difficulty grades, multiplied by x1–x10 and capped at
  30 per camp and 180 total. Configure additional DTA grades explicitly.
- Select camp roster factions independently of the three base AI rolls. Deal
  each active faction family before repeating: four in DTA, currently five in
  Reloaded. Do not retain MO's fixed four-family or twelve-country assumptions.
  Keep camp units under an enemy AI's ownership and alliances, stationary until
  attacked, isolated from ordinary AI recruitment, then able to retaliate.
- All six guarded camp crates exist from the start. Guard deaths neither unlock
  crates nor award points. First pickup claims that camp once and immediately
  awards **10 Defensive Points** to every human's local profile. A human receives
  the in-game payload personally; enemy or helper AI pickup delivers the same
  frozen payload to the solo player/host and counts as the host's collection.
  Use one shared claim flag across all collectors; never add a second camp-clear
  award or allow AI pickup to lose or duplicate the reward.
- Freeze each camp's random contents before launch: 40% for 2,500 credits, 30%
  for ten Tier 1 units, 20% for five Tier 2 units, 10% for one reviewed faction
  special unit. Use the host's selected faction rosters; record collector and
  contents in results. Native visual crate cash must not create duplicate money.
- Use **Defensive Points** as the Fortress progression currency, separate from
  Shop Gems or other mode wallets. MO retains internal `gems`, `gem_cost` and
  `gem_rewards` keys for compatibility; retaining those keys is acceptable, but
  public Fortress text must use Defensive Points.
- Award 25 points at **25 minutes**, another 25 at **45 minutes**, and 50 at
  **60-minute victory** (100 total survival points). Retain earned milestones
  after defeat or quit. On verified victory/defeat, award five points per 50
  corrected friendly native kill-score points, capped at **500 points at 5,000**.
  Combine all friendly humans/helpers, exclude hostile records, and subtract
  each house's setup transfers and received cash escrows before combining.
  Native score can include captures; do not label it a separate combat log.
  Unfinished quits grant no kill bonus. Freeze every reward and Challenge value,
  and show each award source in results, including defeat outcomes.

## Co-op contract

Port co-op with the mode rather than leaving the old solo-only brief as the
completion target. Use the existing target connection and native networking
adapters; campaign co-op logic alone is not Fortress run agreement.

- **Settings → Final Fortress co-op** contains a Co-op toggle and a **Co-op
  players** selector for 2 or 3, visible only in this mode and locked while
  connected. Keep player count out of the connection dialog. Disable and uncheck
  campaign **Include challenge maps** while in Fortress, restoring its saved
  choice on exit; this must not disable Fortress Challenge modifiers.
- Host connects using the Settings count and shares ZeroTier Managed IPv4 and
  pairing code. Guests Join with distinct names; assign seats in arrival order.
  Require the complete roster before launch. MO uses TCP **19420** for lobby and
  native UDP **1234/1235/1236** for players 1/2/3. Verify target spawner support
  before assigning those native ports, and adapt its firewall helper. Every peer
  must reach every other peer and use matching launcher/game assets.
- Host chooses map, faction, difficulty, multiplier and enabled perk ranks.
  All humans/helpers share host perks **except Fundraising**: each human uses
  their own enabled purchased rank; helpers use the host's rank. Advertise guest
  Fundraising before preparation and freeze the complete per-house list.
  Guest perks do not stack, and host purchases never become guest ownership.
- Freeze one run, roster and settings before preparation. Every peer generates
  its local artifact, compares the exact map digest and acknowledges readiness.
  Host starts only after all acknowledgements. Disconnect, digest mismatch or
  preparation failure cancels pending launch without completion rewards.
- Each machine watches matching native evidence and credits its own profile;
  never replace guest wallets with host state. Deduplicate shared camp points,
  milestones, kill tiers and victory/Challenge awards with durable joined-run IDs.
  Keep ownership, enabled ranks and currency local between sessions.
- No mid-game join or reconnect. Reconnect the whole lobby between runs;
  disconnecting the lobby returns to solo. Do not multiply waves automatically
  by human count; host difficulty/multiplier still control scripted pressure.

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
6. Preserve the Settings-only co-op controls and automatic guest seating above.
   Switching modes restores the other modes' Settings and workspace.
7. Keep explanations in themed **Help → How to play / Wave forecast**, with
   concise readiness or blocking errors beside launch. No Launch status popup
   and no large instruction blocks permanently filling the main workspace.
8. Compiled EXEs expose Standard progression only. Keep all-unlocks Testing
   available solely to an existing ignored local source-checkout testing save;
   never bundle that save or enable it through a public setting.

UI parity means matching layout and interaction, not MO branding or invalid
catalogue entries. Retain each launcher's palette, faction names and native
game-speed translation. Label Fortress currency Defensive Points, separate from
Shop currencies. Show only effects supported by the target game;
explain unavailable capabilities in Help rather than selling ineffective perks.

## Verified map starting points

The following are read-only findings from the installed files. They are source
waypoints, **not approved building, defense, camp or reinforcement coordinates**.
Both maps have eight starts, enough for three friendly seats and three enemies.
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

## Native delivery and placement requirements

MO fixes after the older brief are behavior requirements, not optional polish.
For Reloaded's compatible YR engine, reinforcement teams use **`Full=no`**:
`Full=yes` can pack roster members, including tanks, into transports during team
creation regardless of passenger size. `Loadable=no` does not prevent that path.
Apply the correction to waves, friendly deliveries, objective reserves and crate
reward teams. Preserve actual transport capacities and the configured unit count.

Use explicit reinforcement placement. MO uses **Action 80**, with the same
waypoint in both action and TeamType; Action 7 alone did not override placement.
Crate rewards use separate teams per frozen unit type to deliver the complete
squad. Verify equivalent native semantics in DTA rather than copying action IDs.
Placed-object experience and TeamType veterancy use different encodings; MO uses
100/200 for placed Veteran/Elite and 1/2/3 for Rookie/Veteran/Elite teams.

Provide reviewed, walkable **5x3 arrival aprons** near every active friendly and
enemy base. Invisible passable reservations prevent construction on all fifteen
cells; visible native pavement marks them without a fake pad building. Preserve
source heights, resources and scenery. Resolve compatible target tiles and pack
writers instead of copying MO tile IDs or assuming snow matches temperate assets.
Review all cells and exit paths, not just the center. MO rejects enemy aprons
farther than 16 cells from their own base or closer than 32 to any friendly
start; use these as initial clearance rules with target terrain review.

Reserve a conservative **7x7 deployment/exit area** around every active MCV.
Check every building's entire foundation against projected playable LocalSize,
terrain height and other grants. Review complete camp guard formations, aiming
for at least 32 cells from friendly starts and 40 from hostile bases, with crate
cells overlay-free and camps spread across approaches. Freeze any necessary
map-specific layout adjustment. Original skirmish maps remain untouched.

Keep target-native trigger limits explicit: MO has six distinct types per
TaskForce, 100 local flags, 511-byte action lines, 512-type survivor-counter
bounds and 31-byte text chunks including `NOSTR:`. Split rich rosters, relays and
messages before serialization; measure the actual target formats. Long co-op
names and late-rank rosters must not truncate messages or silently lose units.

## Content and capability mapping

Port current cumulative effects and prices from the refreshed reference, then
map each effect to installed target content. Do not retain the older brief's
rank counts or advertise MO units/powers under renamed factions. These are the
starting design limits; document any capability-driven deviation explicitly.

| Perk group | Current MO contract to adapt |
| --- | --- |
| Objective durability | 3 ranks: +25% / +50% / +100% of native target objective HP; starts full; prices 5 / 10 / 20 |
| Emergency objective repair | 1 rank, price 10; one full repair below native red-health threshold, restoring upgraded maximum |
| Objective reserve squad | 10 ranks: 4 / 6 / 9 / 12 / 15 / 18 / 21 / 25 / 25 / 25 units per friendly house; rank 9 Veteran, 10 highest veterancy; prices 15 / 25 / 40 / 60 / 85 / 115 / 150 / 200 / 260 / 330 |
| Supply cache | 6 ranks, +2,000 credits each through +12,000 |
| Production speed | 5 ranks, cumulative 25% shorter unit and building/defense production |
| Cheaper Construction / Cheaper Production | Separately bought, 5 ranks each, cumulative 5% per rank through 25%; friendly buildings/defenses versus units/aircraft |
| Special Building Limit | 3 ranks, +1 / +2 / +3 to eligible positive building limits; no free unlock |
| Fundraising | 4 ranks; direct 1,000 / 2,000 / 3,000 / 4,000 credit deposits every 300 simulation seconds, first at minute 5; per-human ranks in co-op |
| Starting army | 8 ranks: 3 / 6 / 9 / 12 / 15 / 15 / 15 / 15 units; later ranks replace basic units with support, heroes, heavy aircraft and specialists |
| Veteran army | 2 ranks through highest supported veterancy; two ranked infantry if Starting army disabled |
| Starting buildings | 5 ranks through plant, barracks, working refinery/harvester, radar and factory; sufficient independent native power |
| Starting defenses | 4 ranks, eight of each unlocked defense type: 8 / 16 / 24 / 32 defenses per friendly base, with full directional coverage and sufficient native power |
| Veteran defenses | 1 rank, starting and subsequently built defenses |
| Defense firepower | 6 ranks, +10% damage, fire rate and range per rank through +60% |
| Tier 1 / Tier 2 / Tier 3 units | Separate purchases, 6 ranks each; +5% health, damage and fire rate per rank through +30% |
| Faction support powers | 5 cumulative, independently cloned native powers |
| Faction superweapons | 2 ranks; secondary first, then add offensive weapon |
| Power upgrades | 6 ranks, only compatible effects at each reviewed capability's actual cap |
| Satellite intelligence / Allied helpers | Map reveal; 2 helper ranks, limited by unused friendly seats |
| Special unit access | 3 cumulative production unlocks, through reviewed native factories and actual faction access |
| Periodic reinforcements | 12 ranks: 10 / 14 / 18 / 21 / 24 / 25 / 25 / 25 / 25 / 25 / 25 / 30 units; rank 7 Veteran, 8 onward highest veterancy; later ranks enrich roles up to ten types |
| Automatic healing / Sight and stealth detection | 3 ranks each; 1% / 2% / 3% eligible native healing, +1 / +2 / +3 sight plus supported sensors |
| Unique-unit capacity | 3 ranks, +1 / +2 / +3 to eligible positive live-unit limits, without new access |
| Special building income | 4 ranks, +5 / +10 / +15 / +20 credits per existing eligible building payout; no invented income on buildings without payouts |

The objective's repair and reserve are separate once-per-run effects, shared
across the coalition. Reserve triggers below half health, with a red-health
fallback for a hit that skips half health; set used flags before effects. Give
each friendly house its complete ranked squad outside the periodic cap. Include
10 simulation seconds of **objective-only protection** with the reserve when a
reviewed engine mechanism supports it. Do not protect nearby armies or change
global health thresholds. MO's shield needs Ares' actual automatic
GenericWarhead/Self activation path; Action 42 alone did not apply Iron Curtain.
Confirm protection from actual activation rather than a request message. DTA
needs its own supported repair/shield adapter; never claim unimplemented effects.

Fundraising is a direct periodic deposit without crates or collection. In MO it
uses hidden auto-fired Ares `Money.Amount` powers with one 300-second timer per
recipient, stopped by run outcome. Reloaded must verify those installed Ares
capabilities; DTA needs its native equivalent. Disabling the perk emits no timer
or payout provider. Higher ranks change amount, not timer count or interval.
Keep income perks, discounts and building limits separate in UI and rules.

Friendly cost modifiers, buffs, access and production must remain private to
friendly houses, including when an enemy shares their faction. Maintain concrete
production gates, linked deploy/mutation forms, AI recipes, prerequisites and
harvester/refinery docks. Provide exactly one harvester for each starting
refinery. Account for simultaneous maximum building/defense power demand with
normal faction generators; combine the larger sufficient allocation rather than
silently relying on another perk, undeployed MCV power or reactor passengers.

Use each target's existing reviewed enemy buff catalogue for Challenge armor,
production and per-tier effects. MO's current catalogue has 38 modifiers:
33 reviewed stat/production entries, Powerhouses, three reinforcement-power
choices and one offensive-superweapon toggle. Vision, sensors, Defense Armor
and Defense Production are excluded from new Challenge choices; do not restore
them from an older catalogue. Target-supported entry counts may differ. Map
heavy reinforcement and offensive power Challenges to native equivalents. MO names such as Bloodhounds, Moon
reinforcements or Great Tempest are not portable feature requirements.
Unsupported powers/buffs must not appear purchasable or award pretend effects.
Keep Challenge effects on hostile ordinary armies, waves and camp guards only.
Powerhouses preserves advanced roster identities and stays within wave caps;
reviewed power-delivered armies use explicit launch budgets outside those caps.
MO uses three shots per reinforcement power, twice native recharge and no initial
ready shot. Offensive powers retain native recharge, no initial ready shot and
no friendly power upgrades. Hidden providers suppress discovery announcements,
not the real power's normal countdown or attack notifications. Default victory
bonus is five Defensive Points per enabled stat stack; MO's special bonuses are
25 for Powerhouses, 20 / 25 / 30 for reinforcement powers and 60 for offensive
superweapons. Freeze supported mappings, caps and bonuses before launch.

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
   actions, logs, launch/runtime assets, buffs, powers and co-op endpoints.
   Capability decisions belong here; UI callbacks must not contain scattered engine-specific branches.
3. Inspect the single selected map, choose the human/enemy/helper starts, review
   all placements and produce a genuine prepared map/spawn artifact before
   enabling launch. Preserve original source files and the target runtime lease.
4. Implement the protected objective, ordinary skirmish AI, timer and durable
   START/WIN/LOSS receipts. Add capped wave/friendly delivery, then camps, perks,
   Challenges and the complete results breakdown through those same adapters.
5. Persist separate Fortress state and locking under each target's own APP_DIR.
   Freeze game identity, native difficulty, seed, complete balance snapshot,
   chosen rosters/rewards, perk ranks, per-house Fundraising, frozen friendly score
   roster, setup/cash corrections and Challenge stacks. Version local plans and
   preserve old snapshots. Never import MO wallets, saves or testing profiles.
6. Reuse the fixed bounded log-reader design: checkpoint only the 64 bytes before
   the cursor, handle truncation/replacement/partial lines, promptly drain
   backlog and EOF after process exit, and require this run's START and terminal
   marker. Do not infer victory from a voice line, generic Winner row or elapsed
   launcher time. Deduplicate receipts, back up verified recovery updates, and
   exclude setup/cash transfers from kill rewards using the target's evidence.
7. Add two/three-human lobby agreement, host/guest artifact preparation and exact
   digest readiness before declaring the mode complete. Verify guest-local
   rewards and durable duplicate-run protection through native evidence.
8. Apply the exact UI checklist above in both projects, including wrapping text,
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
deliveries, usable helper armies, varied late ground/air attacks, startup crates,
once-only pickup points, human-owned payloads and AI pickups routed to the host,
enemy-only Challenge scope, per-house timers/Fundraising, two/three-human map
agreement, local progression and complete exactly-once results. Keep unverified
native behavior marked for review during the user's normal gameplay session. Do not repeatedly open or
close either game, and never launch a fullscreen application for routine checks.

Remaining content decisions are the target objective buildings, exact reviewed
placements, supported faction power/special-unit mappings and provisional
balance for DTA's extra difficulty grades. These are implementation work, not
reasons to redesign the UI or change the selected maps.

## Pending native gameplay review

Document implementation evidence separately for each target. MO compilation,
map audits and gameplay reports do not establish target-engine behavior.
During the user's normal gameplay, review complete mixed-team arrivals with no
hidden transport passengers, visible reserved aprons and usable exits, helper
attacks, late capacity-delayed rosters, air rearming/tracking, all crate collector
paths, exact Fundraising deposits and disabled recipients, objective repair/
reserve/shield timing, destructible enemy expansions, simultaneous power grants,
co-op readiness/cancellation and exactly-once local results after restart.
Keep unsupported or unverified behavior explicit until reviewed; do not launch
games or create automated gameplay checks for this documentation update.
