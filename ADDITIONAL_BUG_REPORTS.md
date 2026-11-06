# Campaign bug investigation — 6 November 2026

The six supplied generated maps were compared with the corresponding installed
mission sources under `Maps/Missions`, and with the installed Reloaded rules.
The downloaded reports were treated as gameplay evidence; neither downloaded
maps nor original campaign maps were edited. These conclusions concern map
data and source behavior. No live mission was played during this investigation.

## Findings and changes

1. **Missing E.M.Pulse information — fixed.** The Unlocks model discarded every
   power with more than one faction. EMP has both GDI and Nod, so it never
   reached rendering or search. Shared powers now appear in each applicable
   faction tab with the same reward sources and upgrade stacks. This also
   restores Force Shield, Sonar Pulse and Hunter Seeker. Search accepts
   punctuation variants such as `E.M.Pulse`, `EM Pulse`, and `EMP`. Separate
   information cards describe the native cannon-based EMP and native Ion
   Cannon; these cards are conditional technology information, not new rewards.

2. **EMP variants and cooldown buffs — intended behavior preserved.** Native
   `EMPulseSpecial` fires through `GAPULS`/`NAPULS`, with a seven-minute base
   recharge and a 7–30-cell firing window. The Randomizer version uses a private
   `GenericWarhead` strike. Cooldown and other power buffs continue to modify
   only that private version. Unlocks, descriptions and private gameplay
   captions now distinguish building-free powers from structure-based powers.

3. **Ion Cannon variants — native difference confirmed; attacks preserved.**
   `TSIonCannonSpecial`, the Randomizer source, is the classic direct strike:
   `Type=GenericWarhead`, `SW.Damage=1000`, `SW.Range=3`, recharge seven minutes.
   The native Uplink grants `TSSuperIonCannonSpecial`, which uses `MultiMissile`,
   `TSIonCannonLauncher`, `TSIonCannonPayload`, a wider effect and a 9.5-minute
   recharge. This distinction exists in installed rules, before Randomizer
   generation. The UI now explains it. The developer's design intent beyond
   those rules cannot be established from map files alone.

4. **Stealth Generator regeneration — reported maps contain a rate upgrade,
   not a healing-access upgrade.** `RLRPNODSTLH_MP` has
   `SelfHealing.Rate=0.0144` but no `SelfHealing=yes` or rank-based healing
   ability. Its native source also lacks healing access. A faster interval
   alone cannot heal this building. The Regeneration access reward already
   sets `SelfHealing=yes` for buildings. Descriptions now explicitly distinguish
   access from interval upgrades; gameplay tooltips report actual eligibility.
   No evidence supports automatically enabling healing for a rate-only reward.

5. **Advanced Power Plant progression — fixed.** The private
   `RLRPNODAPWR` building was absent from `PrerequisitePower`. Building
   prerequisite aliasing previously covered only yards and refineries.
   It now covers registered private building families, including power plants,
   generic prerequisite groups, explicit alternative paths and prerequisite
   overrides. Existing AND requirements remain intact. This also prevents the
   same defect on other cloned technology/support buildings.

6. **Nod 02 passive AI — no Randomizer trigger defect established.** The supplied
   map retains the original TeamTypes, TaskForces, attack scripts, AI trigger
   definitions/enables and production-start events. Its native AI activation
   gates include building/existence conditions and elapsed-time values of
   400/450; `TeamDelays=600,1000,2000` is also native. Objective/victory actions
   gain completion markers, not rewritten attack orders. No attack waves or
   AI production settings were changed speculatively. A map alone cannot prove
   which gates actually fired or measure the reported attack-rate difference.
   This report remains unconfirmed in live play.

7. **Nod 03 passive APC passengers — script defect fixed.** Scripts `086A8310`
   and `01000092`, both named “unload and attack”, ended with `11,14`.
   The installed editor defines mission 14 as Ambush, meaning wait until
   discovered; mission 15 is Hunt. Reviewed map-local overrides now change
   only the final order to `11,15`. Transport paths, unload instructions,
   passenger identities and trigger timing stay authored. The source missions
   already contained the mistaken order; the fix is confined to generated
   Nod 03 maps.

8. **Duplicate damaging superweapons — fixed root cause in Nod 04A.** The native
   mission identifies `NodCountry House` through `[Basic] Player`, but sets its
   `PlayerControl=no`. The enemy selector trusted that secondary flag and
   classified the actual human as hostile after scripted diplomacy analysis.
   The supplied Nod 04A map consequently contains a human-owned trigger
   granting `MORELightningStorm`, `MOREPsychicDominator` and `MORENuke`, in
   addition to legitimate player powers. Enemy discovery, active-enemy
   filtering and configured-enemy ownership exclusions now consistently honor
   the authoritative player-house set. Different-colored enemy countdowns
   visible in the screenshots are not, by themselves, duplicated player powers.

9. **Duplicated powers abort on activation — same fix as item 8.** The accidental
   `MORE*` grants explicitly have `SW.AllowPlayer=no` and `SW.ManualFire=no`.
   Their activation rejection is expected for those AI-only definitions.
   Preventing their grant to the human removes the unintended controls without
   enabling manual firing of enemy powers or changing legitimate player powers.

10. **Undeployed Tick Tank — configuration contradicts the reported design
    explanation; no gameplay change.** Installed `TICKT` has `DeployToFire=no`
    and real mobile primary/elite weapons (`dts90mm`, `dts120mmxE`). The supplied
    player clone retains that configuration and cloned weapons. Therefore the
    data does not prove that inability to fire undeployed is intended, nor does
    it explain the observed failure. No mobile weapon was removed or enabled.
    This needs an in-game observation or maintainer clarification of the
    contradictory native configuration.

11. **Redundant map reveal — not confirmed; abilities preserved.** Nod 02,
    Nod 03, Nod 04A, Nod 04B and GDI 08 have no full-map-reveal Action 16 in
    either supplied or original maps. Firestorm GDI 01 has one in both:
    action `073D6EF0`. Randomizer did not introduce that authored reveal.
    The generated Firestorm map also defines an optional Spy Satellite Uplink,
    but a registered building definition does not establish that it exists or
    that a redundant reward was activated. No supplied evidence identifies
    a useless reveal buff; valid reveal abilities remain available.

12. **Unit healing — rank and cap requirements confirmed; descriptions improved.**
    Nod Bikes have no native rookie self-healing. Native elite abilities include
    `SELF_HEAL`; the access reward advances eligibility to Veteran, then Rookie.
    Native healing caps are Rookie 50%, Veteran 75%, Elite 100%, with one HP
    restored per native tick and a 450-frame pause after damage. Rate and cap
    upgrades do not grant access. New descriptions make those distinctions
    explicit, and generated tooltips show effective eligibility, rank caps,
    healing amount and combat delay. Supplied map data does not establish that
    an eligible damaged bike below its active cap failed to heal.

13. **Firestorm GDI 01 Wolverine veterancy — withheld native eligibility fixed.**
    The supplied map lists `SMECH` in secondary human countries' `VeteranUnits`,
    but omits it from the main `GDICountry`. The cinematic house `Drop`
    inherits `GDICountry` and caused country-buff safety to reject the main
    country. Drop owns only scripted `TSORCATRAN` dropships and has zero IQ,
    credits and production nodes. A reviewed mission exception permits
    country-buff compatibility with that exact cinematic roster. Runtime and
    existing catalogue validation reject additional unit types or production.
    This restores the native Wolverine's earned country eligibility without
    promoting unearned Mammoth Mk.IIs in its mixed reinforcement teams. It does
    not grant Drop player powers, clones or helper production. Native binary
    inspection also confirms `VeteranLevel=1` preserves the created member's
    rank; the old source comment claiming it forcibly reset rank was corrected.

14. **Deployed Artillery versus Psychic Dominator — native configuration
    preserved.** Deployment changes `ART2` into BuildingType `ARTYDEP`, with
    `Armor=deployed_light_armor`. The installed Dominator damage warhead has
    zero vehicle-armor damage, and deployed artillery is not an ordinary mobile
    vehicle capture target: the native capture defaults target infantry and
    units. No Randomizer-added artillery immunity flag was
    found. There is insufficient evidence of a rules regression to justify
    changing native capture or damage behavior.

## Verification and practical limits

Source compilation, required static configuration validation, the existing
installation/catalogue audit and Archipelago audit passed. The normal Linux/Wine
build produced and installed the Windows launcher and matching APWorld; release
manifest/hash validation passed. The APWorld contains 108 missions and 3,062
approved items. The installed launcher SHA-256 is
`8488449aedd661edcaab985f0a2e195f77a263905eab308d04b54c0ed8ee8336`.
Previous artifacts were backed up under
`ReloadedRandomizerData/backups/additional-bugs-before-install-20261106-x330owje`.
Original mission files and the six supplied evidence maps remain untouched.

Engine reference: [Ares self-healing settings](https://ares-developers.github.io/Ares-docs/new/selfheal.html)
documents the independent interval, per-rank caps, healing amounts and combat
delay. Script mission numbers were checked against this installation's
`Tools/Map Editor/FALanguage.ini` and `FAData.ini`. The separate Dominator capture
and damage settings are documented in
[Ares Psychic Dominator](https://ares-developers.github.io/Ares-docs/new/superweapons/types/psychicdominator.html).

Restart the launcher and relaunch affected missions to regenerate maps with
these rules. Existing engine saves and the supplied old generated maps retain
their previous definitions. Static verification cannot establish live targeting,
timing, healing animation or mission-completion behavior; those remain gameplay
verification limits, especially for reports 6, 10 and 14.
